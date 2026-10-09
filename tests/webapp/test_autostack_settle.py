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
    """Make every target's subs look ``seconds`` old, on the rows *and* the file —
    the rows are what the hold reads, the file is what a re-scan would re-stamp.

    Both stored times, because the hold reads the **later** of them
    (``Project.newest_accepted_sub_time``): ``ingested_at`` says when the sub
    landed in the library and ``source_mtime`` when its file was written, and a
    helper that aged only one would leave the fixture looking freshly-arrived
    however old it claimed to be."""
    when = time.time() - seconds
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            proj._conn.execute(  # noqa: SLF001 — reaching for the stored fact
                "UPDATE frames SET source_mtime = ?, ingested_at = ?",
                (when, when))
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
                    "UPDATE frames SET source_mtime = NULL, ingested_at = NULL, "
                    "timestamp_utc = NULL")
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
                "UPDATE frames SET source_mtime = NULL, ingested_at = NULL, "
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


# --- the arrival clock: observer issue #1090 ---------------------------------
#
# The hold above had never held anything on the owner's install, and could not:
# it asked for the newest sub's time and was answered with the newest sub's
# *capture* time. ``frames.source_mtime`` is the source file's own ``st_mtime``,
# so every copy that preserves timestamps — measured on 118 of 118 of his drop
# folders — records when the sub was shot, hours to months before the folder was
# dropped in, and the 20-minute window was already spent before the first sub of
# a folder reached the database. ``frames.ingested_at`` is the arrival itself.


def test_a_sub_captured_weeks_ago_but_ingested_now_holds_the_target(
        solved_library, monkeypatch):
    """The owner's shape, end to end: a folder of subs shot weeks ago, copied in
    with its timestamps preserved, ingested seconds ago.

    Fails before: every target stacked, because the only time the hold could ask
    for said the subs were three weeks old — so the guard that exists for exactly
    "subs are still arriving" stood aside for the one case it was written for."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _age_every_sub(lib, seconds=21 * 24 * 3600)   # captured three weeks ago
        _landed_just_now(lib)                         # …and copied in this minute

        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)

        assert calls == []
        assert summary["auto_stacked"] == []
        held = summary.get("auto_stack_held_settling")
        assert held, "a folder that landed seconds ago must be held"
        assert all(h["quiet_min"] == 0 and h["settle_min"] == 20 for h in held), held
    finally:
        lib.close()


def _landed_just_now(lib: Library) -> None:
    """Stamp every sub's *arrival* as now, leaving its capture time alone."""
    now = time.time()
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            proj._conn.execute(  # noqa: SLF001
                "UPDATE frames SET ingested_at = ?", (now,))
            proj._conn.commit()  # noqa: SLF001
        finally:
            proj.close()


def test_the_answer_is_the_later_of_arrival_and_capture(solved_library):
    """Not one column in preference to the other: either being recent means the
    target is still moving, so the max is what the hold must see. That also makes
    the change one-sided — it can only ever report a *more* recent time than the
    pair did before ``ingested_at`` existed, so the hold became more cautious and
    never less."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = next(iter(lib.list_targets())).safe_name
        proj = lib.open_target(safe)
        try:
            old, recent = time.time() - 30 * 24 * 3600, time.time() - 90
            # Shot a month ago, landed 90 s ago → the arrival wins.
            proj._conn.execute(  # noqa: SLF001
                "UPDATE frames SET source_mtime = ?, ingested_at = ?",
                (old, recent))
            proj._conn.commit()  # noqa: SLF001
            assert abs(proj.newest_accepted_sub_time() - recent) < 1
            # Landed a month ago, re-copied (so re-stamped) 90 s ago → capture
            # wins, which is today's behaviour unchanged.
            proj._conn.execute(  # noqa: SLF001
                "UPDATE frames SET source_mtime = ?, ingested_at = ?",
                (recent, old))
            proj._conn.commit()  # noqa: SLF001
            assert abs(proj.newest_accepted_sub_time() - recent) < 1
        finally:
            proj.close()
    finally:
        lib.close()


def test_a_project_predating_the_arrival_column_answers_exactly_as_before(
        tmp_path):
    """§9: the column is added by ``_reconcile_table_columns`` on first open, so
    an in-place upgrade self-heals — and because every existing row is left NULL,
    such a library's answer is the old one (``source_mtime``) byte for byte.

    The ``ALTER`` that drops it back out is this test's way of being an *old*
    project; it is never something the app does."""
    from seestack.io.project import Project

    proj = Project.create(tmp_path / "t", name="t")
    try:
        proj.add_frame(_frame(tmp_path / "a.fit", mtime=1_700_000_000.0))
        proj.add_frame(_frame(tmp_path / "b.fit", mtime=1_700_000_500.0))
    finally:
        proj.close()
    # Rewind to before the column existed. SQLite can drop a plain column.
    import sqlite3

    conn = sqlite3.connect(tmp_path / "t" / "project.sqlite")
    try:
        conn.execute("ALTER TABLE frames DROP COLUMN ingested_at")
        conn.commit()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(frames)")}
        assert "ingested_at" not in cols
    finally:
        conn.close()

    proj = Project.open(tmp_path / "t")
    try:
        cols = {r[1] for r in
                proj._conn.execute("PRAGMA table_info(frames)")}  # noqa: SLF001
        assert "ingested_at" in cols, "the reconcile must restore it on open"
        rows = list(proj.iter_frames())
        assert [r.ingested_at for r in rows] == [None, None]
        assert proj.newest_accepted_sub_time() == 1_700_000_500.0
    finally:
        proj.close()


def _frame(path, *, mtime: float):
    from seestack.io.project import FrameRow

    return FrameRow(source_path=str(path), source_mtime=mtime,
                    wcs_json="CTYPE1", accept=True)
