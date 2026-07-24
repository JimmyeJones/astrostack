"""Calibration-availability auto-restack: re-stack an already-stacked but
*uncalibrated* target once a confident master becomes bindable, so the darks a
beginner adds *after* their first stack actually get applied without a manual
reprocess (closes the loop the frame-count auto-stack trigger can't).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp import calibration
from webapp.config import Settings
from webapp.jobs import Job

from .conftest import FRAME_H, FRAME_W


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root, *, auto_bind: bool = True) -> Settings:
    return Settings(
        data_root=str(root), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True, auto_bind_calibration=auto_bind,
    )


def _patch_run_stack(monkeypatch):
    """Record which targets were (re)stacked; never actually stack."""
    from webapp import pipeline  # imported here so monkeypatch targets the engine

    calls: list[str] = []

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        calls.append(getattr(proj, "name", "?"))
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=3, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
            n_offered=3, n_align_failed=0,
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    _ = pipeline  # keep the import referenced
    return calls


def _register_matching_dark(root) -> None:
    """A master dark whose dimensions match the fixture's frames, so
    ``auto_bind_master_paths`` confidently binds it (unknown acquisition params
    on either side don't gate — only a *mismatch* would)."""
    from seestack.calibrate.masters import MasterMeta

    arr = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
    calibration.register_master(
        _settings(root).resolved_library_root,
        name="MatchingDark", array=arr,
        meta=MasterMeta("dark", 5, FRAME_W, FRAME_H, "median",
                        exposure_s=10.0, gain=80.0, sensor_temp_c=-10.0),
    )


def _seed_prior_run(lib, *, calstat: str | None) -> int:
    """Give every solvable target one prior stack run covering all its solved
    frames, with the given ``calstat`` provenance. Returns targets seeded."""
    seeded = 0
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            n = sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)
            if n == 0:
                continue
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=n,
                canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=n,
                options_json="{}", calstat=calstat,
            ))
            seeded += 1
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)
    return seeded


def _run(root, settings=None):
    from webapp import pipeline

    lib = Library.open_or_create(root / "library")
    try:
        return pipeline._pipeline_body(
            settings or _settings(root), _FakeJM(), Job(kind="pipeline"), root=None)
    finally:
        lib.close()


def test_uncalibrated_target_restacks_once_a_master_appears(solved_library, monkeypatch):
    """The core loop-closer: a stacked-but-uncalibrated target with NO new subs is
    re-stacked exactly once a confident master becomes available — and not again."""
    from webapp import pipeline

    calls = _patch_run_stack(monkeypatch)
    _register_matching_dark(solved_library)
    lib = Library.open_or_create(solved_library / "library")
    try:
        seeded = _seed_prior_run(lib, calstat=None)  # prior run, uncalibrated
        assert seeded >= 1
    finally:
        lib.close()

    # First scan: no new frames, but the master is now bindable → re-stack fires.
    summary = _run(solved_library)
    assert summary["auto_stacked"], "an uncalibrated target should re-stack once a master appears"
    assert len(calls) == seeded

    # The once-per-master-set marker is now stamped on each re-stacked target.
    lib = Library.open_or_create(solved_library / "library")
    try:
        for safe in summary["auto_stacked"]:
            proj = lib.open_target(safe)
            try:
                assert proj.get_meta(pipeline.AUTO_STACK_CALIB_META_KEY)
            finally:
                proj.close()
    finally:
        lib.close()

    # Second scan, same data + same master: the marker holds → NO churny re-stack.
    before = len(calls)
    summary2 = _run(solved_library)
    assert len(calls) == before, "the same master set must not re-trigger a restack"
    assert summary2["auto_stacked"] == []
    assert summary2["auto_stack_skipped"]


def test_no_restack_without_a_confident_master(solved_library, monkeypatch):
    """No master registered → nothing to apply → the recheck must not fire."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        assert _seed_prior_run(lib, calstat=None) >= 1
    finally:
        lib.close()
    summary = _run(solved_library)
    assert calls == []
    assert summary["auto_stacked"] == []


def test_no_restack_when_auto_bind_is_off(solved_library, monkeypatch):
    """Even with a bindable master, the retrigger stays off unless
    ``auto_bind_calibration`` is on — otherwise the restack couldn't apply it."""
    calls = _patch_run_stack(monkeypatch)
    _register_matching_dark(solved_library)
    lib = Library.open_or_create(solved_library / "library")
    try:
        assert _seed_prior_run(lib, calstat=None) >= 1
    finally:
        lib.close()
    summary = _run(solved_library, settings=_settings(solved_library, auto_bind=False))
    assert calls == []
    assert summary["auto_stacked"] == []


def test_no_restack_when_prior_run_was_already_calibrated(solved_library, monkeypatch):
    """A target that was already stacked *with* calibration is not our loop to
    close — a newly-available master must not churn it."""
    calls = _patch_run_stack(monkeypatch)
    _register_matching_dark(solved_library)
    lib = Library.open_or_create(solved_library / "library")
    try:
        assert _seed_prior_run(lib, calstat="dark+flat") >= 1
    finally:
        lib.close()
    summary = _run(solved_library)
    assert calls == []
    assert summary["auto_stacked"] == []


def test_recheck_helper_returns_frame_count_and_fingerprint(solved_library, monkeypatch):
    """The recheck helper itself: returns (count, fingerprint) for an eligible
    target and None once its marker records that master set."""
    from webapp import pipeline

    _register_matching_dark(solved_library)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _seed_prior_run(lib, calstat=None)
        settings = _settings(solved_library)
        checked = 0
        for entry in lib.list_targets():
            safe = entry.safe_name
            proj = lib.open_target(safe)
            try:
                n = pipeline._solved_accepted_count(proj)
            finally:
                proj.close()
            if n == 0:
                continue
            checked += 1
            got = pipeline._auto_stack_calibration_recheck(settings, lib, safe)
            assert got is not None
            count, fp = got
            assert count == n
            assert fp  # non-empty fingerprint naming the bound master
            # Once the marker records this master set, the recheck goes quiet.
            pipeline._mark_auto_stack_calib_retrigger(lib, safe, fp)
            assert pipeline._auto_stack_calibration_recheck(settings, lib, safe) is None
        assert checked >= 1
    finally:
        lib.close()
