"""When a picture's subs were *shot*, as opposed to when the stack ran.

A stack run's ``timestamp_utc`` is the moment it was *processed*. Everything the
app said about "when was this taken" used to read that stamp — the shareable
caption asserted "shot on <the day you pressed stack>" — which is right only if
you stack the night you shoot, and years out for a Seestar owner arriving with a
back catalogue. These cover the recording half: the window the stacker measures
off the frames, its round trip through the project DB, and the migration onto an
install that has never had the columns.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

import pytest

from seestack.io.project import Project, StackRunRow
from seestack.stack.stacker import _capture_window


@dataclass
class _Frame:
    timestamp_utc: str | None = None
    exposure_s: float = 10.0


def test_capture_window_spans_first_and_last_sub():
    frames = [
        _Frame("2024-11-16T03:12:00Z"),
        _Frame("2024-11-15T22:01:00Z"),
        _Frame("2024-11-18T21:40:00Z"),
    ]
    assert _capture_window(frames) == (
        "2024-11-15T22:01:00Z", "2024-11-18T21:40:00Z")


def test_capture_window_orders_by_instant_not_spelling():
    """The app writes UTC in more than one shape, so a lexicographic min/max
    would pick whichever *spelling* sorts first. Here the earliest instant is
    the one whose string sorts last."""
    frames = [
        _Frame("2024-11-15T23:00:00+00:00"),   # earliest instant
        _Frame("2024-11-16T01:00:00Z"),
    ]
    first, last = _capture_window(frames)
    assert first == "2024-11-15T23:00:00+00:00"
    assert last == "2024-11-16T01:00:00Z"
    # …and the naive spelling of the same instant is treated as UTC, not skipped.
    assert _capture_window([_Frame("2024-11-15T23:00:00")])[0] == "2024-11-15T23:00:00"


def test_capture_window_returns_stamps_verbatim():
    """The row stores what was recorded, not a normalised re-rendering of it."""
    frames = [_Frame("2024-11-15T22:01:00.500Z")]
    assert _capture_window(frames) == (
        "2024-11-15T22:01:00.500Z", "2024-11-15T22:01:00.500Z")


def test_capture_window_skips_undated_and_unparseable_frames():
    frames = [
        _Frame(None),
        _Frame(""),
        _Frame("not-a-date"),
        _Frame("2024-11-15T22:01:00Z"),
    ]
    assert _capture_window(frames) == (
        "2024-11-15T22:01:00Z", "2024-11-15T22:01:00Z")


def test_capture_window_is_none_when_nothing_is_dated():
    """No usable capture time → no claim. Every caller drops the clause rather
    than falling back to the stack's own stamp, which is the whole bug."""
    assert _capture_window([_Frame(None), _Frame("nonsense")]) == (None, None)
    assert _capture_window([]) == (None, None)


def _row(**kw) -> StackRunRow:
    base = dict(
        id=None, timestamp_utc="2026-08-30T12:00:00Z", output_basename="master",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=3,
        canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
        options_json=json.dumps({}),
    )
    base.update(kw)
    return StackRunRow(**base)


def test_capture_window_round_trips_through_the_project_db(tmp_path):
    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(
            capture_start_utc="2024-11-15T22:01:00Z",
            capture_end_utc="2024-11-18T21:40:00Z",
        ))
        run = next(iter(proj.iter_stack_runs()))
        assert run.capture_start_utc == "2024-11-15T22:01:00Z"
        assert run.capture_end_utc == "2024-11-18T21:40:00Z"
        # …and it is a *different* fact from when the stack ran.
        assert run.timestamp_utc == "2026-08-30T12:00:00Z"
    finally:
        proj.close()


def test_a_run_recorded_without_a_window_reads_as_none(tmp_path):
    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row())
        run = next(iter(proj.iter_stack_runs()))
        assert run.capture_start_utc is None
        assert run.capture_end_utc is None
    finally:
        proj.close()


def test_an_older_project_migrates_and_keeps_its_runs(tmp_path):
    """Upgrade safety (§9): a project written before the columns existed must
    open, keep every row, and simply answer None."""
    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(output_basename="old"))
    finally:
        proj.close()

    # Roll the DB back to the pre-capture-window shape: drop the two columns and
    # stamp the older schema version, exactly as a live install would look.
    db = tmp_path / "t" / "project.sqlite"
    conn = sqlite3.connect(db)
    try:
        for col in ("capture_start_utc", "capture_end_utc"):
            conn.execute(f"ALTER TABLE stack_runs DROP COLUMN {col}")
        conn.execute("PRAGMA user_version = 17")
        conn.commit()
    finally:
        conn.close()

    proj = Project.open(tmp_path / "t")
    try:
        runs = list(proj.iter_stack_runs())
        assert [r.output_basename for r in runs] == ["old"]
        assert runs[0].capture_start_utc is None
        assert runs[0].capture_end_utc is None
        # …and the migrated DB can record a window on the next stack.
        proj.add_stack_run(_row(
            output_basename="new", timestamp_utc="2026-08-31T12:00:00Z",
            capture_start_utc="2024-11-15T22:01:00Z",
            capture_end_utc="2024-11-15T23:59:00Z",
        ))
        fresh = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert fresh["new"].capture_start_utc == "2024-11-15T22:01:00Z"
        assert fresh["old"].capture_start_utc is None
    finally:
        proj.close()


@pytest.mark.parametrize("bad", ["", None])
def test_blank_window_is_stored_as_absent(tmp_path, bad):
    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(capture_start_utc=bad, capture_end_utc=bad))
        run = next(iter(proj.iter_stack_runs()))
        assert not run.capture_start_utc
        assert not run.capture_end_utc
    finally:
        proj.close()
