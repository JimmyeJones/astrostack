"""Reprocess-everything: restack all targets serially, non-destructively.

Covers the pure helpers, the batch job body (reuse of each target's last
settings, per-target failure isolation, cancel-between-targets), the
duplicate-batch guard, and end-to-end wiring through the API — including that
old runs are preserved (additive).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job, JobManager


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root) -> Settings:
    return Settings(data_root=str(root), auto_ingest=False, auto_qc=False,
                    auto_solve=False, auto_stack=False)


# --------------------------------------------------------------------------- #
# Pure helper: which run's options to reuse
# --------------------------------------------------------------------------- #

def test_stack_options_from_run_json_genuine():
    opts = pipeline._stack_options_from_run_json(
        json.dumps({"sigma_clip": True, "sigma_kappa": 2.5, "junk": 1}))
    assert opts == {"sigma_clip": True, "sigma_kappa": 2.5}  # unknown key dropped


@pytest.mark.parametrize("bad", [
    None, "", "{}", "not json", "[1,2,3]",
    json.dumps({"editor_recipe": {"ops": []}}),   # editor-export run
    json.dumps({"channel_combine": []}),           # combine run
    json.dumps({"junk_only": 1}),                  # no real StackOptions keys
])
def test_stack_options_from_run_json_rejects(bad):
    assert pipeline._stack_options_from_run_json(bad) is None


def test_reprocess_output_basename_is_version_tagged_and_unique():
    # Fresh, version-tagged name when nothing collides.
    assert pipeline._reprocess_output_basename(set(), "0.81.3") == "master_v0.81.3"
    # Never collides with the existing "master" (the bug this guards against).
    assert pipeline._reprocess_output_basename({"master"}, "0.81.3") == "master_v0.81.3"
    # Suffixes when the version-tagged name is already taken (double reprocess).
    assert pipeline._reprocess_output_basename(
        {"master", "master_v0.81.3"}, "0.81.3") == "master_v0.81.3_2"
    assert pipeline._reprocess_output_basename(
        {"master_v0.81.3", "master_v0.81.3_2"}, "0.81.3") == "master_v0.81.3_3"


def test_reprocess_all_preserves_the_existing_master_output(solved_client, solved_library):
    """Regression: reprocess-all must not archive/overwrite a target's existing
    ``master`` output. Before the fix the reused options carried
    ``output_name="master"``, so the restack renamed the original master.fits to a
    timestamped orphan and wrote the new pixels in its place — the old run's row
    then silently served the new image. Now each reprocess run gets a fresh,
    version-tagged basename, so the original file is untouched and both runs are
    reachable in History."""
    import hashlib

    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
    finally:
        lib.close()
    victim = targets[0]

    # Produce a *real* first stack so master.fits exists on disk with known content.
    r = solved_client.post(f"/api/targets/{victim}/stack", json={})
    assert r.status_code == 200
    _wait_job(solved_client, r.json()["job_id"])

    runs_before = solved_client.get(f"/api/targets/{victim}/stack-runs").json()
    assert len(runs_before) == 1
    assert runs_before[0]["output_basename"] == "master"
    # Resolve the master output path from the recorded run rather than assuming the
    # on-disk layout.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(victim)
        try:
            master = Path(next(iter(proj.iter_stack_runs())).fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    assert master.exists()
    before_digest = hashlib.sha256(master.read_bytes()).hexdigest()

    # Reprocess everything (no stale filter → the victim is restacked).
    r = solved_client.post("/api/reprocess-all")
    assert r.status_code == 200
    body = _wait_job(solved_client, r.json()["job_id"])
    assert body["state"] == "done"

    # The original master.fits is byte-for-byte unchanged (not archived/overwritten).
    assert master.exists()
    assert hashlib.sha256(master.read_bytes()).hexdigest() == before_digest

    # The reprocessed run is a NEW run with a distinct, version-tagged basename, and
    # both runs' outputs exist and are reachable.
    runs_after = solved_client.get(f"/api/targets/{victim}/stack-runs").json()
    assert len(runs_after) == 2
    basenames = {run["output_basename"] for run in runs_after}
    assert "master" in basenames               # the original run is still there
    new_names = basenames - {"master"}
    assert len(new_names) == 1
    assert next(iter(new_names)).startswith("master_v")  # fresh version-tagged name
    for run in runs_after:
        assert run["has_fits"], f"{run['output_basename']} lost its FITS output"


# --------------------------------------------------------------------------- #
# Batch body
# --------------------------------------------------------------------------- #

def _patch_run_stack(monkeypatch, *, capture: list | None = None):
    """Fake run_stack that records the opts it was called with."""
    def fake(proj, opts, *, progress=None, cancel=None, memory_budget_gb=None, app_version=None):  # noqa: ANN001
        if capture is not None:
            capture.append(opts)
        # emit a little progress so the phase/detail interplay is exercised
        if progress:
            progress("combine", 1, 1)
        return SimpleNamespace(output_dir="/tmp/x", run_id=1, n_frames_used=3,
                               canvas_shape=(1, 1, 3), cancelled=False,
                               errors=[], excluded_frames=[])
    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake)


def test_reprocess_all_restacks_every_target_reusing_last_options(solved_library, monkeypatch):
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    lib = Library.open_or_create(solved_library / "library")
    try:
        # Seed each target with a genuine prior stack run carrying a distinctive
        # kappa, so we can assert the reprocess reused it.
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"method": "sigma", "sigma_kappa": 4.25}),
                ))
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        # Call the body directly (submit would run it on a worker thread).
        summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)
    finally:
        lib.close()

    assert summary["total"] == 2
    assert summary["stacked"] == 2
    assert summary["failed"] == []
    assert summary["cancelled"] is False
    # Every target restacked with the reused kappa.
    assert len(captured) == 2
    assert all(abs(o.sigma_kappa - 4.25) < 1e-6 for o in captured)


def _seed_prior_runs_without_calibration(lib) -> None:
    """Give each target a genuine prior stack run whose options carry no
    calibration, so a reprocess reuses them and auto-bind has room to act."""
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                coverage_min=1, coverage_max=3,
                options_json=json.dumps({"method": "sigma", "sigma_kappa": 4.25}),
            ))
        finally:
            proj.close()


def _register_matching_dark(root):
    import numpy as np

    from seestack.calibrate.masters import MasterMeta
    from tests.webapp.conftest import FRAME_H, FRAME_W
    from webapp import calibration
    # The synth subs are 10 s / gain 80 (tests/synth.py) at FRAME_W×FRAME_H, so
    # this dark matches on exposure/gain *and* dimensions (auto-bind rejects a
    # wrong-size master so it can't hard-fail run_stack's validate()).
    return calibration.register_master(
        root, name="Dark 10s",
        array=np.full((FRAME_H, FRAME_W), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, FRAME_W, FRAME_H, "median",
                        exposure_s=10.0, gain=80.0))


def test_reprocess_all_auto_binds_calibration_when_enabled(solved_library, monkeypatch):
    """With auto_bind_calibration on, an unattended restack that had no
    calibration chosen picks up the library's matching master dark."""
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    root = solved_library / "library"
    dark = _register_matching_dark(root)
    lib = Library.open_or_create(root)
    try:
        _seed_prior_runs_without_calibration(lib)
        settings = Settings(data_root=str(solved_library), auto_ingest=False,
                            auto_qc=False, auto_solve=False, auto_stack=False,
                            auto_bind_calibration=True)
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all, settings, job)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert len(captured) == 2
    dark_name = dark["filename"]
    # Every restack bound the matching master dark as a server-side path.
    assert all(o.dark_path and Path(o.dark_path).name == dark_name for o in captured)


def test_reprocess_all_auto_binds_scaled_dark_with_bias(solved_library, monkeypatch):
    """With auto_bind_calibration on and only an exposure-mismatched (but same-gain)
    master dark plus a matching master bias, the unattended restack recovers the
    dark by exposure-scaling it to the subs — binding dark_path + bias_path +
    scale_dark_to_light rather than falling back to the (weaker) bias-only path."""
    import numpy as np

    from seestack.calibrate.masters import MasterMeta
    from tests.webapp.conftest import FRAME_H, FRAME_W
    from webapp import calibration

    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    root = solved_library / "library"
    # Subs are 10 s / gain 80; the only dark is a same-gain 30 s (exposure mismatch),
    # and a matching master bias is present → scale the dark to 10 s.
    dark = calibration.register_master(
        root, name="Dark 30s",
        array=np.full((FRAME_H, FRAME_W), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, FRAME_W, FRAME_H, "median",
                        exposure_s=30.0, gain=80.0))
    bias = calibration.register_master(
        root, name="Bias",
        array=np.full((FRAME_H, FRAME_W), 0.5, dtype=np.float32),
        meta=MasterMeta("bias", 5, FRAME_W, FRAME_H, "median",
                        exposure_s=0.0, gain=80.0))
    lib = Library.open_or_create(root)
    try:
        _seed_prior_runs_without_calibration(lib)
        settings = Settings(data_root=str(solved_library), auto_ingest=False,
                            auto_qc=False, auto_solve=False, auto_stack=False,
                            auto_bind_calibration=True)
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all, settings, job)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert len(captured) == 2
    for o in captured:
        assert o.dark_path and Path(o.dark_path).name == dark["filename"]
        assert o.bias_path and Path(o.bias_path).name == bias["filename"]
        assert o.scale_dark_to_light is True


def test_reprocess_all_no_calibration_bind_when_disabled(solved_library, monkeypatch):
    """Default (off) — the autonomous restack stays uncalibrated even when a
    matching master exists, so the behaviour on a live install is unchanged."""
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    root = solved_library / "library"
    _register_matching_dark(root)
    lib = Library.open_or_create(root)
    try:
        _seed_prior_runs_without_calibration(lib)
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert len(captured) == 2
    assert all(not o.dark_path for o in captured)  # auto-bind is opt-in


def test_interactive_stack_never_auto_binds_calibration(solved_library, monkeypatch):
    """The interactive Stack form honours exactly what the user picked: even with
    auto_bind_calibration on, a form-submitted stack with no masters chosen stays
    uncalibrated (only the unattended chains auto-bind)."""
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    root = solved_library / "library"
    _register_matching_dark(root)
    settings = Settings(data_root=str(solved_library), auto_ingest=False,
                        auto_qc=False, auto_solve=False, auto_stack=False,
                        auto_bind_calibration=True)
    job = Job(kind="stack")
    # submit_stack is the form path; it passes explicit options and never the flag.
    _run_body(pipeline.submit_stack, settings, job, safe="M_42", options={})

    assert len(captured) == 1
    assert not captured[0].dark_path  # form submissions are never auto-calibrated


def test_reprocess_all_isolates_a_failing_target(solved_library, monkeypatch):
    seen: list[str] = []

    def fake(proj, opts, *, progress=None, cancel=None, memory_budget_gb=None, app_version=None):  # noqa: ANN001
        seen.append(getattr(proj, "safe_name", "?"))
        if len(seen) == 1:
            raise ValueError("boom on first target")
        return SimpleNamespace(output_dir="/tmp/x", run_id=1, n_frames_used=3,
                               canvas_shape=(1, 1, 3), cancelled=False,
                               errors=[], excluded_frames=[])
    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake)

    job = Job(kind="reprocess_all")
    summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)

    assert summary["total"] == 2
    assert summary["stacked"] == 1           # the second target still stacked
    assert len(summary["failed"]) == 1       # the first was isolated, not fatal
    assert "boom" in summary["failed"][0]["error"]
    assert summary["cancelled"] is False


def test_reprocess_all_stale_only_skips_current_version_targets(solved_library, monkeypatch):
    """With stale_only, a target already stacked on the current app version is
    skipped; one whose latest genuine stack is on an older version is reprocessed."""
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        assert len(targets) == 2
        # One target up to date (current version), one stale (old version).
        vers = {targets[0]: pipeline.APP_VERSION, targets[1]: "0.0.1"}
        for safe in targets:
            proj = lib.open_target(safe)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"method": "sigma", "sigma_kappa": 4.25}),
                    engine_version=vers[safe],
                ))
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library),
                            job, stale_only=True)
    finally:
        lib.close()

    assert summary["total"] == 2
    assert summary["stacked"] == 1      # only the stale target
    assert summary["skipped"] == 1      # the up-to-date one was skipped
    assert summary["failed"] == []
    assert len(captured) == 1           # run_stack called once, for the stale target


def test_reprocess_all_default_reprocesses_current_version_targets(solved_library, monkeypatch):
    """Without stale_only (the default), a target already on the current version is
    still reprocessed — the version filter is strictly opt-in."""
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"method": "sigma", "sigma_kappa": 4.25}),
                    engine_version=pipeline.APP_VERSION,
                ))
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert summary["skipped"] == 0
    assert len(captured) == 2


def _seed_run(proj, *, version, basename="master", options=None):
    proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc="2026-05-01T00:00:00Z",
        output_basename=basename, fits_path=None, tiff_path=None,
        preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
        coverage_min=1, coverage_max=3,
        options_json=json.dumps(options or {"method": "sigma", "sigma_kappa": 4.25}),
        engine_version=version,
    ))


def test_reprocess_status_counts_outdated_up_to_date_and_never_stacked(solved_library):
    """A target on an older version is outdated; one on the current version is up to
    date; a never-stacked target is neither (no existing image to refresh)."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        assert len(targets) == 2
        # First target: stale (old version). Second: leave un-stacked entirely.
        proj = lib.open_target(targets[0])
        try:
            _seed_run(proj, version="0.0.1")
        finally:
            proj.close()
        status = pipeline.reprocess_status(lib)
    finally:
        lib.close()

    assert status["current_version"] == pipeline.APP_VERSION
    assert status["total_targets"] == 2
    assert status["outdated"] == 1       # the old-version target
    assert status["up_to_date"] == 0     # none on the current version
    # The never-stacked target is counted in neither bucket.
    assert status["outdated"] + status["up_to_date"] == 1


def test_reprocess_status_predates_version_tracking_is_outdated(solved_library):
    """A genuine stack with no recorded engine_version (predates tracking) was made
    by some older build, so it counts as outdated."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                _seed_run(proj, version=None)  # legacy run, no version
            finally:
                proj.close()
        status = pipeline.reprocess_status(lib)
    finally:
        lib.close()

    assert status["outdated"] == 2
    assert status["up_to_date"] == 0


def test_reprocess_status_current_version_is_up_to_date(solved_library):
    """A target whose newest genuine stack is on the current version is up to date,
    not outdated — even if an *older* run also exists (newest wins)."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                _seed_run(proj, version="0.0.1", basename="old")
                _seed_run(proj, version=pipeline.APP_VERSION, basename="new")
            finally:
                proj.close()
        status = pipeline.reprocess_status(lib)
    finally:
        lib.close()

    assert status["outdated"] == 0
    assert status["up_to_date"] == 2


def test_reprocess_status_ignores_editor_and_combine_runs(solved_library):
    """A target whose only runs are editor-export / combine (non-genuine) has no
    real stack, so it's neither outdated nor up to date."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                _seed_run(proj, version="0.0.1", basename="edit",
                          options={"editor_recipe": {"ops": []}})
            finally:
                proj.close()
        status = pipeline.reprocess_status(lib)
    finally:
        lib.close()

    assert status["outdated"] == 0
    assert status["up_to_date"] == 0
    assert status["total_targets"] == 2


# --------------------------------------------------------------------------- #
# Library-wide auto-edit sky-cast aggregation
# --------------------------------------------------------------------------- #

def _seed_run_with_cast(proj, cast):
    """Add a stack run and stamp it with an auto-edit sky-cast meta (or none when
    ``cast`` is ``None``). Returns the new run id."""
    from webapp.routers.editor import AUTO_EDIT_SKYCAST_PREFIX

    run_id = proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc="2026-05-01T00:00:00Z",
        output_basename="master", fits_path=None, tiff_path=None,
        preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
        coverage_min=1, coverage_max=3,
        options_json=json.dumps({"method": "sigma", "sigma_kappa": 4.25}),
        engine_version=pipeline.APP_VERSION,
    ))
    if cast is not None:
        proj.set_meta(f"{AUTO_EDIT_SKYCAST_PREFIX}{run_id}", json.dumps(cast))
    return run_id


def _cast(cast, deviation, *, r=0.2, g=0.2, b=0.2):
    return {"r": r, "g": g, "b": b,
            "neutral": cast == "neutral", "cast": cast, "deviation": deviation}


def test_auto_cast_summary_aggregates_neutral_and_cast_runs(solved_library):
    """Aggregates every auto-edited run's stamped sky-cast into a neutral/cast
    split, per-tint counts, and the median deviation — ignoring runs with no
    stamp and unmeasurable ('unknown') ones."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(targets[0])
        try:
            _seed_run_with_cast(proj, _cast("neutral", 0.004))
            _seed_run_with_cast(proj, _cast("neutral", 0.006))
            _seed_run_with_cast(proj, _cast("green", 0.02))
            _seed_run_with_cast(proj, _cast("magenta", 0.03))
            _seed_run_with_cast(proj, _cast("unknown", 0.0))  # not measurable
            _seed_run_with_cast(proj, None)                    # manual/older run
        finally:
            proj.close()
        proj = lib.open_target(targets[1])
        try:
            _seed_run_with_cast(proj, _cast("green", 0.015))
        finally:
            proj.close()
        summary = pipeline.auto_cast_summary(lib)
    finally:
        lib.close()

    # 5 measurable runs (2 neutral + 3 cast); unknown + unstamped excluded.
    assert summary["measured"] == 5
    assert summary["neutral"] == 2
    assert summary["cast"] == 3
    assert summary["by_cast"] == {"green": 2, "magenta": 1}
    # Deviations of the measurable runs: 0.004, 0.006, 0.02, 0.03, 0.015 → median 0.015.
    assert summary["median_deviation"] == 0.015


def test_auto_cast_summary_empty_until_runs_accrue(solved_library):
    """With no auto-edited runs stamped, the read-out is all zeros / no median —
    off-nothing on a fresh or pre-feature install."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        summary = pipeline.auto_cast_summary(lib)
    finally:
        lib.close()
    assert summary == {"measured": 0, "neutral": 0, "cast": 0,
                       "by_cast": {}, "median_deviation": None}


def test_auto_cast_summary_ignores_malformed_meta(solved_library):
    """A corrupt/non-JSON or non-dict cast meta is skipped, never crashing the
    aggregation (defensive against a partially-written meta)."""
    from webapp.routers.editor import AUTO_EDIT_SKYCAST_PREFIX

    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(targets[0])
        try:
            good = _seed_run_with_cast(proj, _cast("neutral", 0.003))
            bad1 = _seed_run_with_cast(proj, None)
            proj.set_meta(f"{AUTO_EDIT_SKYCAST_PREFIX}{bad1}", "not json")
            bad2 = _seed_run_with_cast(proj, None)
            proj.set_meta(f"{AUTO_EDIT_SKYCAST_PREFIX}{bad2}", json.dumps([1, 2, 3]))
            assert good  # the good run is present
        finally:
            proj.close()
        summary = pipeline.auto_cast_summary(lib)
    finally:
        lib.close()
    assert summary["measured"] == 1
    assert summary["neutral"] == 1


def test_auto_cast_summary_endpoint(solved_client, solved_library):
    """GET /api/auto-cast-summary reports the library-wide neutral/cast split."""
    # Empty until any auto-edited run is stamped.
    r = solved_client.get("/api/auto-cast-summary")
    assert r.status_code == 200
    assert r.json() == {"measured": 0, "neutral": 0, "cast": 0,
                        "by_cast": {}, "median_deviation": None}

    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        proj = lib.open_target(targets[0])
        try:
            _seed_run_with_cast(proj, _cast("neutral", 0.005))
            _seed_run_with_cast(proj, _cast("green", 0.02))
        finally:
            proj.close()
    finally:
        lib.close()

    body = solved_client.get("/api/auto-cast-summary").json()
    assert body["measured"] == 2
    assert body["neutral"] == 1
    assert body["cast"] == 1
    assert body["by_cast"] == {"green": 1}


def test_reprocess_all_deep_rescan_reruns_qc_solve_grade_before_each_stack(
        solved_library, monkeypatch):
    """With deep_rescan, each target is re-QC'd/re-solved/re-graded *before* it's
    restacked; the default (off) skips the refresh entirely."""
    _patch_run_stack(monkeypatch)
    rescanned: list[str] = []

    def fake_qc_solve(proj, **kw):  # noqa: ANN001
        rescanned.append(getattr(proj, "safe_name", "?"))
        # The refresh must re-derive *all* frames, not just new ones.
        assert kw.get("only_new_qc") is False
        assert kw.get("run_qc") is True and kw.get("run_solve") is True
        return {"qc_done": 0, "qc_total": 0, "solve_done": 0, "solve_total": 0}
    # Patch where pipeline looks it up (imported into the module namespace).
    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve", fake_qc_solve)

    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                _seed_run(proj, version="0.0.1")
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all,
                            _settings(solved_library), job, deep_rescan=True)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert summary["rescanned"] == 2
    assert len(rescanned) == 2          # QC/solve ran once per target


def test_reprocess_all_default_does_not_rescan(solved_library, monkeypatch):
    """Without deep_rescan (the default), the QC/solve refresh never runs."""
    _patch_run_stack(monkeypatch)
    calls: list = []
    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve",
                        lambda proj, **kw: calls.append(1))  # noqa: ANN001

    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                _seed_run(proj, version="0.0.1")
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all,
                            _settings(solved_library), job)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert summary["rescanned"] == 0
    assert calls == []                  # refresh never invoked


def test_reprocess_all_deep_rescan_isolates_a_failing_refresh(solved_library, monkeypatch):
    """A refresh that blows up is best-effort: the target is still restacked."""
    _patch_run_stack(monkeypatch)

    def boom(proj, **kw):  # noqa: ANN001
        raise RuntimeError("QC exploded")
    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve", boom)

    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                _seed_run(proj, version="0.0.1")
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all,
                            _settings(solved_library), job, deep_rescan=True)
    finally:
        lib.close()

    # The failing refresh didn't sink the restack — both targets still stacked.
    assert summary["stacked"] == 2
    assert summary["rescanned"] == 2
    assert summary["failed"] == []


def test_reprocess_all_deep_rescan_skips_rescan_for_stale_only_skipped(
        solved_library, monkeypatch):
    """deep_rescan + stale_only: a target already current on this version is
    skipped, so its (expensive) refresh is skipped too."""
    _patch_run_stack(monkeypatch)
    rescanned: list[str] = []
    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve",
                        lambda proj, **kw: rescanned.append(getattr(proj, "safe_name", "?")))  # noqa: ANN001

    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        vers = {targets[0]: pipeline.APP_VERSION, targets[1]: "0.0.1"}
        for safe in targets:
            proj = lib.open_target(safe)
            try:
                _seed_run(proj, version=vers[safe])
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all,
                            _settings(solved_library), job,
                            stale_only=True, deep_rescan=True)
    finally:
        lib.close()

    assert summary["stacked"] == 1      # only the stale target
    assert summary["skipped"] == 1
    assert summary["rescanned"] == 1    # only the reprocessed target was rescanned
    assert len(rescanned) == 1


def test_reprocess_all_auto_edit_chains_on_each_restacked_run(solved_library, monkeypatch):
    """With auto_edit, the one-click Auto recipe is chained onto every restacked run
    (via _auto_edit_process_run), so a reprocess yields finished pictures. The
    default (off) never auto-edits."""
    _patch_run_stack(monkeypatch)
    edited: list[tuple[str, int]] = []
    monkeypatch.setattr("webapp.pipeline._auto_edit_process_run",
                        lambda lib, safe, run_id: (edited.append((safe, run_id)), 3)[1])  # noqa: ANN001

    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                _seed_run(proj, version="0.0.1")
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all,
                            _settings(solved_library), job, auto_edit=True)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert summary["auto_edited"] == 2      # one per restacked run
    assert len(edited) == 2


def test_reprocess_all_default_does_not_auto_edit(solved_library, monkeypatch):
    """Without auto_edit (the default), the auto-edit chain never runs."""
    _patch_run_stack(monkeypatch)
    calls: list = []
    monkeypatch.setattr("webapp.pipeline._auto_edit_process_run",
                        lambda lib, safe, run_id: calls.append(1))  # noqa: ANN001

    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                _seed_run(proj, version="0.0.1")
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all,
                            _settings(solved_library), job)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert summary["auto_edited"] == 0
    assert calls == []                      # helper never invoked


def test_reprocess_all_cancels_between_targets(solved_library, monkeypatch):
    calls: list = []

    def fake(proj, opts, *, progress=None, cancel=None, memory_budget_gb=None, app_version=None):  # noqa: ANN001
        calls.append(1)
        return SimpleNamespace(output_dir="/tmp/x", run_id=1, n_frames_used=3,
                               canvas_shape=(1, 1, 3), cancelled=False,
                               errors=[], excluded_frames=[])
    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake)

    job = Job(kind="reprocess_all")
    job._cancel.set()  # cancel before the first target is picked up
    summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)

    assert summary["cancelled"] is True
    assert calls == []                       # never started a stack
    assert summary["stacked"] == 0


def _run_body(submit_fn, settings, job, **submit_kwargs):
    """Invoke a submit_* function's body synchronously by capturing the job fn
    it hands to a recording JobManager."""
    captured: dict = {}

    class _RecordingJM(_FakeJM):
        def submit(self, kind, fn, *, target=None):  # noqa: ANN001
            captured["fn"] = fn
            return job
    submit_fn(settings, _RecordingJM(), **submit_kwargs)
    return captured["fn"](job)


# --------------------------------------------------------------------------- #
# Duplicate-batch guard (JobManager.active_of_kind)
# --------------------------------------------------------------------------- #

def test_active_of_kind(tmp_path: Path):
    jm = JobManager(tmp_path / "jobs.sqlite")
    assert jm.active_of_kind("reprocess_all") is None
    running = Job(kind="reprocess_all", state="running")
    jm._jobs[running.id] = running
    assert jm.active_of_kind("reprocess_all") is running
    assert jm.active_of_kind("stack") is None
    # A terminal job of the same kind doesn't count as active.
    running.state = "done"
    assert jm.active_of_kind("reprocess_all") is None


# --------------------------------------------------------------------------- #
# End-to-end through the API (real stacker), additive / non-destructive
# --------------------------------------------------------------------------- #

@pytest.fixture
def solved_client(solved_library, monkeypatch):
    monkeypatch.setenv("ASTROSTACK_DATA", str(solved_library))
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    from fastapi.testclient import TestClient

    from webapp.main import create_app

    app = create_app()
    with TestClient(app) as c:
        c.put("/api/settings", json={"watcher_enabled": False})
        yield c


def _wait_job(client, job_id, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_reprocess_all_endpoint_is_additive(solved_client, solved_library):
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        # Seed one genuine prior run per target so we can prove it's preserved.
        for safe in targets:
            proj = lib.open_target(safe)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="seed", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"sigma_clip": True, "sigma_kappa": 3.0}),
                ))
            finally:
                proj.close()
    finally:
        lib.close()

    before = {s: len(solved_client.get(f"/api/targets/{s}/stack-runs").json())
              for s in targets}

    r = solved_client.post("/api/reprocess-all")
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert r.json()["already_running"] is False

    body = _wait_job(solved_client, job_id)
    assert body["state"] == "done"
    assert body["result"]["total"] == len(targets)
    assert body["result"]["stacked"] == len(targets)
    assert body["result"]["failed"] == []

    # Each target gained exactly one new run; the seeded run is still there.
    for s in targets:
        runs = solved_client.get(f"/api/targets/{s}/stack-runs").json()
        assert len(runs) == before[s] + 1
        assert any(r.get("output_basename") == "seed" for r in runs)


def test_reprocess_all_endpoint_auto_edit_saves_a_recipe_on_each_new_run(
        solved_client, solved_library):
    """POST {auto_edit: true} chains the one-click Auto recipe onto each restacked
    run: the new run opens with a non-empty saved editor recipe (a finished
    picture), while the plain reprocess default leaves a flat linear master."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
    finally:
        lib.close()

    r = solved_client.post("/api/reprocess-all", json={"auto_edit": True})
    assert r.status_code == 200
    body = _wait_job(solved_client, r.json()["job_id"])
    assert body["state"] == "done"
    assert body["result"]["stacked"] == len(targets)
    assert body["result"]["auto_edited"] == len(targets)

    # Each target's newest run carries a non-empty Auto recipe (the tone stretch is
    # always present), i.e. it opens as a finished picture rather than linear.
    for s in targets:
        runs = solved_client.get(f"/api/targets/{s}/stack-runs").json()
        rid = runs[0]["id"]  # newest first — the reprocessed run
        recipe = solved_client.get(
            f"/api/targets/{s}/stack-runs/{rid}/editor/recipe").json()
        ops = [o for o in recipe["ops"] if o.get("enabled", True)]
        assert any(o["id"] == "tone.stretch" for o in ops)


def test_reprocess_all_endpoint_default_leaves_a_linear_master(solved_client, solved_library):
    """Without auto_edit (the default), a reprocessed run opens with an empty
    recipe — the finished-picture seed is strictly opt-in."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
    finally:
        lib.close()

    r = solved_client.post("/api/reprocess-all")
    assert r.status_code == 200
    body = _wait_job(solved_client, r.json()["job_id"])
    assert body["state"] == "done"
    assert body["result"]["auto_edited"] == 0

    for s in targets:
        runs = solved_client.get(f"/api/targets/{s}/stack-runs").json()
        rid = runs[0]["id"]
        recipe = solved_client.get(
            f"/api/targets/{s}/stack-runs/{rid}/editor/recipe").json()
        ops = [o for o in recipe["ops"] if o.get("enabled", True)]
        assert ops == []


def test_reprocess_all_endpoint_stale_only_skips_current_version(solved_client, solved_library):
    """POST {stale_only: true} skips targets whose latest genuine stack was already
    made with the current app version — no new run is added for them."""
    from webapp import __version__ as app_version

    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        for safe in targets:
            proj = lib.open_target(safe)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="uptodate", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"sigma_clip": True, "sigma_kappa": 3.0}),
                    engine_version=app_version,
                ))
            finally:
                proj.close()
    finally:
        lib.close()

    before = {s: len(solved_client.get(f"/api/targets/{s}/stack-runs").json())
              for s in targets}

    r = solved_client.post("/api/reprocess-all", json={"stale_only": True})
    assert r.status_code == 200
    body = _wait_job(solved_client, r.json()["job_id"])
    assert body["state"] == "done"
    assert body["result"]["total"] == len(targets)
    assert body["result"]["stacked"] == 0
    assert body["result"]["skipped"] == len(targets)

    # No target gained a new run — all were up to date and skipped.
    for s in targets:
        runs = solved_client.get(f"/api/targets/{s}/stack-runs").json()
        assert len(runs) == before[s]


def test_reprocess_status_endpoint(solved_client, solved_library):
    """GET /api/reprocess-status reports how many targets' images are outdated."""
    from webapp import __version__ as app_version

    # No genuine stacks yet → nothing outdated, nothing up to date.
    r = solved_client.get("/api/reprocess-status")
    assert r.status_code == 200
    body = r.json()
    assert body["current_version"] == app_version
    assert body["total_targets"] == 2
    assert body["outdated"] == 0
    assert body["up_to_date"] == 0

    # Seed one stale target and one current-version target.
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        for safe, ver in zip(targets, ("0.0.1", app_version), strict=True):
            proj = lib.open_target(safe)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"sigma_clip": True, "sigma_kappa": 3.0}),
                    engine_version=ver,
                ))
            finally:
                proj.close()
    finally:
        lib.close()

    body = solved_client.get("/api/reprocess-status").json()
    assert body["outdated"] == 1
    assert body["up_to_date"] == 1
    assert body["total_targets"] == 2
