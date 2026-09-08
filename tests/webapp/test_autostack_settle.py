"""Hold a target the sky is still filling: the walk-away settle window.

``_auto_stack_frame_count`` fires whenever more solved subs exist than the last
stack covered, and nothing between it and the stack asked whether subs were still
*arriving*. So on a night spent shooting one target, each poll delivered a batch,
the scan solved it, and the app re-stacked the **whole** target — every night's
subs — only for the next poll to make it do so again. The single-worker job
manager serialises those, so the box spent the night re-stacking and the newest
picture kept being replaced by a picture of a night that was not over.

The hold is the same discipline as the thin and readability holds: no attempt
marker, so the target stacks on the first scan after the subs stop. Delayed,
never stranded, never skipped.
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

from seestack.io.library import Library
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root, *, settle_min: int = 20) -> Settings:
    return Settings(
        data_root=str(root), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True, auto_stack_settle_min=settle_min,
    )


def _patch_run_stack(monkeypatch):
    calls: list[str] = []

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        calls.append(getattr(proj, "name", "?"))
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=3, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    return calls


def _age_every_sub(lib: Library, seconds: float) -> None:
    """Make every target's subs look ``seconds`` old, on the row *and* the file —
    the row is what the hold reads, the file is what a re-scan would re-stamp."""
    when = time.time() - seconds
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            proj._conn.execute(  # noqa: SLF001 — reaching for the stored fact
                "UPDATE frames SET source_mtime = ?", (when,))
            proj._conn.commit()  # noqa: SLF001
            for row in proj.iter_frames():
                if row.source_path and os.path.exists(row.source_path):
                    os.utime(row.source_path, (when, when))
        finally:
            proj.close()


def test_a_target_still_receiving_subs_is_held_until_the_night_settles(
        solved_library, monkeypatch):
    """Fails before: the fixture's subs are seconds old and every target stacked
    anyway, which is exactly the all-night re-stack the owner would have met the
    moment he turned auto-stack on."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _age_every_sub(lib, seconds=120)          # a sub arrived two minutes ago
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)

        assert calls == []
        assert summary["auto_stacked"] == []
        held = summary.get("auto_stack_held_settling")
        assert held, "expected the still-shooting targets to be held"
        assert all(h["settle_min"] == 20 and h["quiet_min"] == 2 for h in held), held

        # Held, not stamped: nothing about this target has been decided, so the
        # next scan re-checks it — the same discipline as the other two holds.
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
            finally:
                proj.close()

        # …and once the subs stop, the very next scan stacks it, once, on the
        # whole night.
        _age_every_sub(lib, seconds=30 * 60)
        summary2 = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert calls, "a settled target must stack"
        assert summary2["auto_stacked"]
        assert not summary2.get("auto_stack_held_settling")
    finally:
        lib.close()


def test_a_zero_window_is_todays_behaviour(solved_library, monkeypatch):
    """The setting's escape hatch, and the upgrade story for anyone who wants the
    old cadence: 0 must not hold anything, however fresh the subs are."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _age_every_sub(lib, seconds=5)
        summary = pipeline._pipeline_body(
            _settings(solved_library, settle_min=0), _FakeJM(),
            Job(kind="pipeline"), root=None)
        assert calls
        assert summary["auto_stacked"]
        assert not summary.get("auto_stack_held_settling")
    finally:
        lib.close()


def test_a_library_with_no_sub_times_is_never_held(solved_library, monkeypatch):
    """A library old enough to predate the fingerprint columns, whose frames also
    carry no ``DATE-OBS``, cannot answer "when did this land?" — and must not be
    held on a fact it can't supply. Silence means stack, never wait."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                proj._conn.execute(  # noqa: SLF001
                    "UPDATE frames SET source_mtime = NULL, timestamp_utc = NULL")
                proj._conn.commit()  # noqa: SLF001
                assert proj.newest_accepted_sub_time() is None
            finally:
                proj.close()
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert calls
        assert summary["auto_stacked"]
    finally:
        lib.close()


def test_a_frames_capture_time_stands_in_when_the_file_time_is_missing(
        solved_library):
    """The fallback, in the direction that can only make a target stack *sooner*:
    a sub shot long ago and copied in today reads as old, so it is never held."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        entry = next(iter(lib.list_targets()))
        proj = lib.open_target(entry.safe_name)
        try:
            proj._conn.execute(  # noqa: SLF001
                "UPDATE frames SET source_mtime = NULL, "
                "timestamp_utc = '2024-11-15T21:00:00+00:00'")
            proj._conn.commit()  # noqa: SLF001
            newest = proj.newest_accepted_sub_time()
        finally:
            proj.close()
        assert newest is not None
        assert time.time() - newest > 365 * 24 * 3600
    finally:
        lib.close()


# --- the hold itself, in isolation -------------------------------------------


def test_the_hold_reports_how_long_the_target_has_been_quiet(solved_library):
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(iter(lib.list_targets())).safe_name
        _age_every_sub(lib, seconds=7 * 60)
        hold = pipeline._auto_stack_settle_hold(lib, safe, 20)
        assert hold is not None
        assert hold["target"] == safe
        assert hold["quiet_min"] == 7
        assert hold["settle_min"] == 20
        # Past the window, the answer is "stack now".
        assert pipeline._auto_stack_settle_hold(lib, safe, 5) is None
    finally:
        lib.close()


def test_a_sub_timestamped_in_the_future_holds_for_one_window_not_forever(
        solved_library):
    """A source filesystem whose clock runs ahead — the same skew the watcher's
    own age gate can meet. It reads as "0 minutes quiet" and costs the window
    *plus the skew*, then passes: the window is measured from the file's own
    stamp, so it can never strand a target the way an absolute gate would."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(iter(lib.list_targets())).safe_name
        _age_every_sub(lib, seconds=-600)          # ten minutes in the future
        hold = pipeline._auto_stack_settle_hold(lib, safe, 20)
        assert hold is not None
        assert hold["quiet_min"] == 0
        # Still held at +20 min of real time: the stamp itself was 10 min ahead.
        assert pipeline._auto_stack_settle_hold(
            lib, safe, 20, now=time.time() + 20 * 60) is not None
        # …and free at +31, i.e. the window plus the skew, and no longer.
        assert pipeline._auto_stack_settle_hold(
            lib, safe, 20, now=time.time() + 31 * 60) is None
    finally:
        lib.close()


def test_the_named_default_is_the_settings_default(solved_library):
    """The constant carries the justification for the number (longer than any
    poll, shorter than a meridian flip); the setting must not drift from it."""
    assert (Settings(data_root=str(solved_library)).auto_stack_settle_min
            == pipeline.AUTO_STACK_SETTLE_DEFAULT_MIN)
