"""How many *nights* a stack is made of — the recording half.

The capture window (``capture_start_utc`` / ``capture_end_utc``, schema 18)
answers *when* a picture was shot but not *how much*: a window of 15→18 Nov is
equally consistent with two nights and with four, and "600 subs over 4 nights"
is the sentence a person actually says about their picture. So a run also
records the hours its subs arrived in, and the read side buckets those into
observing nights for the observer's own longitude.

These cover the recording half: what the stacker measures off the frames, its
round trip through the project DB, and the migration onto an install that has
never had the column.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from seestack.io.project import Project, StackRunRow
from seestack.stack.stacker import _capture_hours


@dataclass
class _Frame:
    timestamp_utc: str | None = None
    exposure_s: float = 10.0


def test_hours_are_distinct_sorted_and_on_the_hour():
    """Many subs an hour collapse to one entry — that is what keeps a 500-sub
    row small — and the entries come back as instants the read side can parse."""
    frames = [
        _Frame("2024-11-15T22:01:00Z"),
        _Frame("2024-11-15T22:44:30Z"),
        _Frame("2024-11-15T23:02:00Z"),
        _Frame("2024-11-16T03:12:00Z"),
    ]
    assert _capture_hours(frames) == [
        "2024-11-15T22:00:00Z",
        "2024-11-15T23:00:00Z",
        "2024-11-16T03:00:00Z",
    ]


def test_a_five_hundred_sub_night_records_one_entry_per_hour():
    """The whole reason this stores hours rather than stamps: the row stays a
    handful of entries however many subs went in."""
    start = datetime(2024, 11, 15, 20, 0, 0, tzinfo=timezone.utc)
    frames = [  # 500 x 30 s back to back ≈ 4 h 10 m, so five clock hours
        _Frame((start + timedelta(seconds=30 * i)).isoformat().replace(
            "+00:00", "Z"))
        for i in range(500)
    ]
    assert _capture_hours(frames) == [
        f"2024-11-15T{h:02d}:00:00Z" for h in (20, 21, 22, 23)
    ] + ["2024-11-16T00:00:00Z"]


def test_hours_are_normalised_to_utc_whatever_the_spelling():
    """The app writes UTC in three shapes; all three must land in one bucket,
    or a single night would count as three."""
    frames = [
        _Frame("2024-11-15T22:10:00Z"),
        _Frame("2024-11-15T22:20:00+00:00"),
        _Frame("2024-11-15T22:30:00"),        # naive → treated as UTC
        _Frame("2024-11-15T23:30:00+01:00"),  # 22:30 UTC — same hour
    ]
    assert _capture_hours(frames) == ["2024-11-15T22:00:00Z"]


def test_undated_and_unparseable_frames_are_skipped():
    frames = [_Frame(None), _Frame(""), _Frame("not-a-date"),
              _Frame("2024-11-15T22:01:00Z")]
    assert _capture_hours(frames) == ["2024-11-15T22:00:00Z"]


def test_nothing_dated_records_nothing():
    """No usable capture time → no count. A caller says nothing rather than
    claiming a picture came from zero nights."""
    assert _capture_hours([_Frame(None), _Frame("nonsense")]) == []
    assert _capture_hours([]) == []


def _row(**kw) -> StackRunRow:
    base = dict(
        id=None, timestamp_utc="2026-08-30T12:00:00Z", output_basename="master",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=3,
        canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
        options_json=json.dumps({}),
    )
    base.update(kw)
    return StackRunRow(**base)


def test_hours_round_trip_through_the_project_db(tmp_path):
    proj = Project.create(tmp_path / "t", name="T")
    try:
        hours = ["2024-11-15T22:00:00Z", "2024-11-18T21:00:00Z"]
        proj.add_stack_run(_row(capture_hours_json=json.dumps(hours)))
        run = next(iter(proj.iter_stack_runs()))
        assert json.loads(run.capture_hours_json) == hours
    finally:
        proj.close()


def test_a_run_recorded_without_hours_reads_as_none(tmp_path):
    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row())
        assert next(iter(proj.iter_stack_runs())).capture_hours_json is None
    finally:
        proj.close()


def test_an_older_project_migrates_and_keeps_its_runs(tmp_path):
    """Upgrade safety (§9): a project written before the column existed must
    open, keep every row, and simply answer None."""
    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(output_basename="old"))
    finally:
        proj.close()

    # Roll the DB back to the schema-18 shape a live install would be on.
    conn = sqlite3.connect(tmp_path / "t" / "project.sqlite")
    try:
        conn.execute("ALTER TABLE stack_runs DROP COLUMN capture_hours_json")
        conn.execute("PRAGMA user_version = 18")
        conn.commit()
    finally:
        conn.close()

    proj = Project.open(tmp_path / "t")
    try:
        runs = list(proj.iter_stack_runs())
        assert [r.output_basename for r in runs] == ["old"]
        assert runs[0].capture_hours_json is None
        # …and the migrated DB records hours on the next stack.
        proj.add_stack_run(_row(
            output_basename="new",
            capture_hours_json=json.dumps(["2024-11-15T22:00:00Z"]),
        ))
        fresh = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert json.loads(fresh["new"].capture_hours_json) == [
            "2024-11-15T22:00:00Z"]
        assert fresh["old"].capture_hours_json is None
    finally:
        proj.close()
