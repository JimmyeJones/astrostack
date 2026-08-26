"""Degraded-result heal: re-stack a target whose *newest* picture came out far
thinner than an earlier one, once every sub is readable again.

The readability hold (v0.270.1) stops the walk-away path *publishing* a thin
picture from now on; it does nothing for an install already sitting on one,
because the frame-count trigger correctly refuses to re-stack unchanged data.
This is the other half — the owner's own 787 → 271 sequence healing back to a
full-frame stack in one scan, and then staying quiet.
"""

from __future__ import annotations

from types import SimpleNamespace

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp.config import Settings
from webapp.jobs import Job


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root) -> Settings:
    return Settings(
        data_root=str(root), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True, auto_bind_calibration=False,
    )


def _patch_run_stack(monkeypatch, *, n_frames_used: int = 3):
    """Record which targets were (re)stacked; never actually stack."""
    calls: list[str] = []

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        calls.append(getattr(proj, "name", "?"))
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=n_frames_used,
            canvas_shape=(1, 1, 3), cancelled=False, errors=[], excluded_frames=[],
            n_offered=n_frames_used, n_align_failed=0,
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    return calls


def _add_run(proj, *, n_frames_used: int, when: str,
             options_json: str = "{}", notes: str | None = None) -> None:
    proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc=when, output_basename=f"master_{when}",
        fits_path=None, tiff_path=None, preview_path=None,
        n_frames_used=n_frames_used, canvas_h=10, canvas_w=10,
        coverage_min=1, coverage_max=n_frames_used,
        options_json=options_json, notes=notes,
    ))


def _seed_degraded(lib, *, best: int = 3, newest: int = 1) -> list[str]:
    """Give every solvable target a good run followed by a much thinner one —
    the state an install hit by a storage hiccup is left in."""
    seeded: list[str] = []
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            n = sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)
            if n == 0:
                continue
            _add_run(proj, n_frames_used=best, when="2026-05-01T00:00:00Z")
            _add_run(proj, n_frames_used=newest, when="2026-05-02T00:00:00Z")
            seeded.append(entry.safe_name)
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)
    return seeded


def _run(root, settings=None):
    from webapp import pipeline

    return pipeline._pipeline_body(
        settings or _settings(root), _FakeJM(), Job(kind="pipeline"), root=None)


def test_degraded_target_is_restacked_once_and_only_once(solved_library, monkeypatch):
    """The core heal: a target whose newest run collapsed to a fraction of its
    best is re-stacked from the full set — and the next scan stays quiet."""
    from webapp import pipeline

    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        seeded = _seed_degraded(lib)
        assert seeded, "fixture must have solvable targets"
    finally:
        lib.close()

    summary = _run(solved_library)
    assert sorted(summary["auto_stacked"]) == sorted(seeded)
    assert len(calls) == len(seeded)
    healed = summary["auto_stack_healed"]
    assert sorted(h["target"] for h in healed) == sorted(seeded)
    assert all(h["previous"] == 1 and h["best"] == 3 for h in healed)

    # The once-per-collapse marker is stamped, so a second scan does nothing.
    lib = Library.open_or_create(solved_library / "library")
    try:
        for safe in seeded:
            proj = lib.open_target(safe)
            try:
                assert proj.get_meta(pipeline.AUTO_STACK_DEGRADED_META_KEY) == "3:1"
            finally:
                proj.close()
    finally:
        lib.close()

    before = len(calls)
    summary2 = _run(solved_library)
    assert len(calls) == before, "the same collapse must not re-trigger a heal"
    assert summary2["auto_stacked"] == []
    assert "auto_stack_healed" not in summary2
    assert summary2["auto_stack_skipped"]


def test_healthy_target_is_never_healed(solved_library, monkeypatch):
    """A target whose newest run is its best (the normal case) is left alone —
    the heal must be invisible on a healthy install."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                n = sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)
                if n == 0:
                    continue
                _add_run(proj, n_frames_used=n, when="2026-05-01T00:00:00Z")
                _add_run(proj, n_frames_used=n, when="2026-05-02T00:00:00Z")
            finally:
                proj.close()
    finally:
        lib.close()
    summary = _run(solved_library)
    assert calls == []
    assert summary["auto_stacked"] == []
    assert "auto_stack_healed" not in summary


def test_ordinary_alignment_attrition_is_not_a_collapse(solved_library, monkeypatch):
    """A newest run that dropped a *few* subs at alignment is normal, not a
    degraded picture — it must not trigger a re-stack."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        # 9 of 10 = 90%, comfortably above the 80% collapse bar.
        _seed_degraded(lib, best=10, newest=9)
    finally:
        lib.close()
    summary = _run(solved_library)
    assert calls == []
    assert summary["auto_stacked"] == []


def test_a_user_who_rejected_half_the_frames_is_not_second_guessed(
        solved_library, monkeypatch):
    """A legitimately thinner newest run — the user rejected subs and re-stacked
    — must be left alone: the data itself is thinner, so there is nothing better
    to make and re-stacking would just undo their choice."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        # best=9 is more than the target actually *has* solved+accepted (3), which
        # is exactly the shape of "they rejected most of it after the good run".
        _seed_degraded(lib, best=9, newest=1)
    finally:
        lib.close()
    summary = _run(solved_library)
    assert calls == []
    assert summary["auto_stacked"] == []


def test_an_editor_export_run_does_not_look_like_a_collapse(solved_library, monkeypatch):
    """An editor export records a tiny ``n_frames_used`` in the same table. It is
    not an integration, so it must not be read as the target's newest stack."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                n = sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)
                if n == 0:
                    continue
                _add_run(proj, n_frames_used=n, when="2026-05-01T00:00:00Z")
                _add_run(proj, n_frames_used=1, when="2026-05-02T00:00:00Z",
                         options_json='{"editor_recipe": {"ops": []}}', notes="edited")
                _add_run(proj, n_frames_used=1, when="2026-05-03T00:00:00Z",
                         options_json='{"channel_combine": {"mode": "lrgb"}}',
                         notes="channel combine")
            finally:
                proj.close()
    finally:
        lib.close()
    summary = _run(solved_library)
    assert calls == []
    assert summary["auto_stacked"] == []


def test_a_still_unreadable_target_is_not_healed(solved_library, monkeypatch):
    """While the outage is *ongoing*, the retry cannot do better than the run it
    would replace — so it must not burn a stack on every scan."""
    from webapp import pipeline

    calls = _patch_run_stack(monkeypatch)
    monkeypatch.setattr(pipeline, "_solved_accepted_unreadable", lambda proj: 2)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _seed_degraded(lib)
    finally:
        lib.close()
    summary = _run(solved_library)
    assert calls == []
    assert summary["auto_stacked"] == []


def test_a_target_with_one_genuine_run_is_not_healed(solved_library, monkeypatch):
    """A target that has stacked exactly once has no predecessor to have degraded
    from — even when a thin *editor export* is sitting on top of it as the newest
    row in the same table."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                n = sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)
                if n == 0:
                    continue
                _add_run(proj, n_frames_used=n, when="2026-05-01T00:00:00Z")
                _add_run(proj, n_frames_used=1, when="2026-05-02T00:00:00Z",
                         options_json='{"editor_recipe": {"ops": []}}', notes="edited")
            finally:
                proj.close()
    finally:
        lib.close()
    summary = _run(solved_library)
    assert calls == []
    assert summary["auto_stacked"] == []
    assert summary["auto_stack_skipped"]


def test_heal_helper_returns_count_and_fingerprint(solved_library):
    """The helper itself, exercised directly: (count, "best:newest") for an
    eligible target, and ``None`` once the marker records that collapse."""
    from webapp import pipeline

    lib = Library.open_or_create(solved_library / "library")
    try:
        seeded = _seed_degraded(lib)
        checked = 0
        for safe in seeded:
            got = pipeline._auto_stack_degraded_recheck(lib, safe)
            assert got is not None
            count, fp = got
            assert count == 3 and fp == "3:1"
            pipeline._mark_auto_stack_degraded_heal(lib, safe, fp)
            assert pipeline._auto_stack_degraded_recheck(lib, safe) is None
            # Clearing it (the survivable-failure path) re-opens the heal.
            pipeline._clear_auto_stack_degraded_heal(lib, safe)
            assert pipeline._auto_stack_degraded_recheck(lib, safe) is not None
            checked += 1
        assert checked >= 1
    finally:
        lib.close()


def test_a_survivable_stack_failure_clears_the_marker(solved_library, monkeypatch):
    """The marker is written *before* the heal only to break a process-crash
    loop, so a survivable failure must not strand the target on its thin
    picture forever."""
    from webapp import pipeline

    def boom(proj, opts, **kw):  # noqa: ANN001
        raise RuntimeError("flapping mount")

    monkeypatch.setattr("seestack.stack.stacker.run_stack", boom)
    lib = Library.open_or_create(solved_library / "library")
    try:
        seeded = _seed_degraded(lib)
    finally:
        lib.close()

    summary = _run(solved_library)
    assert summary["auto_stacked"] == []
    assert summary["stack_errors"]

    lib = Library.open_or_create(solved_library / "library")
    try:
        for safe in seeded:
            proj = lib.open_target(safe)
            try:
                assert proj.get_meta(pipeline.AUTO_STACK_DEGRADED_META_KEY) is None
            finally:
                proj.close()
    finally:
        lib.close()
