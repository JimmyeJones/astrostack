""""While you were asleep" — the walk-away half of the Dashboard's "Last night"
card: the pictures the app made overnight, and the targets its scan held back.

The aggregation lives in :mod:`webapp.overnight` and is pure, so most of this
file drives it directly; the last few cases go through ``GET /api/last-night``
to pin the wire shape and the "nothing to report" behaviour.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from seestack.io.project import FrameRow, StackRunRow
from webapp.jobs import Job
from webapp.overnight import needs_a_look, new_pictures_since, newest_scan_summary

NIGHT = dt.datetime(2026, 7, 8, 21, 0, 0, tzinfo=dt.UTC)
# The options a genuine integration records; an editor export / channel combine
# stores a different shape, which is what `is_genuine` is reading.
GENUINE = json.dumps({"sigma_clip": True, "sigma_kappa": 3.0})


@dataclass
class _Run:
    """The handful of ``RecentStack`` fields the digest reads."""

    safe: str
    target_name: str
    run_id: int
    timestamp_utc: str
    n_frames_used: int
    is_genuine: bool = True


def _stamp(hours: float) -> str:
    return (NIGHT + dt.timedelta(hours=hours)).isoformat()


# --------------------------------------------------------------------------
# new_pictures_since
# --------------------------------------------------------------------------

def test_only_runs_after_the_window_start_count():
    runs = [
        _Run("M_42", "M 42", 1, _stamp(-30), 60),   # yesterday afternoon
        _Run("M_42", "M 42", 2, _stamp(6), 120),    # overnight
    ]
    made = new_pictures_since(runs, _stamp(0))
    assert [(p.safe, p.run_id) for p in made] == [("M_42", 2)]
    # …and it knows what the picture it replaced was made of, so the card can
    # say "deeper than before" rather than only "new".
    assert made[0].previous_frames == 60
    assert made[0].n_frames == 120
    assert made[0].name == "M 42"


def test_a_targets_first_ever_picture_has_nothing_to_compare_against():
    made = new_pictures_since([_Run("M_42", "M 42", 1, _stamp(6), 120)], _stamp(0))
    assert made[0].previous_frames is None


def test_two_scans_on_one_night_are_one_new_picture_not_two():
    """A scan that fired, then a second scan after more subs landed, produced one
    picture as far as the owner is concerned — the latest."""
    runs = [
        _Run("M_42", "M 42", 1, _stamp(3), 60),
        _Run("M_42", "M 42", 2, _stamp(7), 120),
    ]
    made = new_pictures_since(runs, _stamp(0))
    assert [(p.run_id, p.n_frames) for p in made] == [(2, 120)]
    # The earlier overnight run is *not* used as "before": the comparison is
    # against the picture that stood when the owner went to bed.
    assert made[0].previous_frames is None


def test_editor_exports_and_combines_are_not_new_pictures():
    runs = [
        _Run("M_42", "M 42", 2, _stamp(6), 120),
        _Run("M_42", "M 42", 3, _stamp(7), 120, is_genuine=False),
    ]
    made = new_pictures_since(runs, _stamp(0))
    assert [p.run_id for p in made] == [2]


def test_newest_target_leads_and_every_target_gets_a_line():
    runs = [
        _Run("M_42", "M 42", 1, _stamp(4), 120),
        _Run("NGC_7000", "NGC 7000", 2, _stamp(6), 54),
    ]
    made = new_pictures_since(runs, _stamp(0))
    assert [p.safe for p in made] == ["NGC_7000", "M_42"]


def test_stamps_are_compared_as_times_not_strings():
    """The app writes UTC in two shapes — ``…Z`` from the job manager, a full
    offset from the stacker — and ``"2026-07-08T21:00:00Z" < "2026-07-08T21:00:00+00:00"``
    lexicographically, which would drop a picture made minutes after the window
    opened."""
    runs = [_Run("M_42", "M 42", 1, "2026-07-08T23:30:00Z", 120)]
    made = new_pictures_since(runs, "2026-07-08T21:00:00+00:00")
    assert [p.run_id for p in made] == [1]


def test_no_window_and_unparseable_stamps_are_simply_quiet():
    assert new_pictures_since([_Run("M_42", "M 42", 1, _stamp(6), 120)], None) == []
    assert new_pictures_since([_Run("M_42", "M 42", 1, "not a date", 120)],
                              _stamp(0)) == []


# --------------------------------------------------------------------------
# needs_a_look / newest_scan_summary
# --------------------------------------------------------------------------

def test_holds_are_reported_with_the_scans_own_numbers():
    held = needs_a_look({
        "auto_stack_held_unreadable": [
            {"target": "M_42", "offered": 787, "readable": 271, "unreadable": 516},
        ],
        "auto_stack_held_thin": [{"target": "NGC_7000", "frames": 3, "min": 8}],
    }, {"M_42": "M 42", "NGC_7000": "NGC 7000"}.get)
    assert [(h.safe, h.kind, h.n_frames, h.n_other) for h in held] == [
        ("M_42", "missing_files", 271, 516),
        ("NGC_7000", "too_thin", 3, 8),
    ]
    assert held[0].name == "M 42"


def test_missing_files_leads_and_a_doubly_held_target_is_reported_once():
    held = needs_a_look({
        "auto_stack_held_thin": [{"target": "M_42", "frames": 3, "min": 8}],
        "auto_stack_held_unreadable": [
            {"target": "M_42", "offered": 10, "readable": 4, "unreadable": 6}],
    })
    assert [(h.safe, h.kind) for h in held] == [("M_42", "missing_files")]


def test_a_clean_scan_and_a_junk_summary_both_say_nothing():
    assert needs_a_look({"auto_stacked": ["M_42"]}) == []
    assert needs_a_look(None) == []
    assert needs_a_look({"auto_stack_held_thin": "surprise"}) == []
    assert needs_a_look({"auto_stack_held_thin": [{"no": "target"}, 7]}) == []


def test_newest_scan_wins_and_a_resolved_hold_stops_being_news():
    @dataclass
    class _Job:
        kind: str
        state: str
        result: dict | None

    jobs = [  # newest first, as the job manager lists them
        _Job("pipeline", "done", {"auto_stacked": ["M_42"]}),
        _Job("pipeline", "done", {"auto_stack_held_thin": [
            {"target": "M_42", "frames": 3, "min": 8}]}),
    ]
    assert needs_a_look(newest_scan_summary(jobs)) == []
    # Drop the scan that resolved it and the hold is news again.
    assert [h.kind for h in needs_a_look(newest_scan_summary(jobs[1:]))] == \
        ["too_thin"]
    # A still-running scan has no verdict yet; another job kind is not a scan.
    assert newest_scan_summary(
        [_Job("pipeline", "running", None)] + jobs[1:]) == jobs[1].result
    assert newest_scan_summary([_Job("stack", "done", {"x": 1})]) is None
    assert newest_scan_summary([]) is None


# --------------------------------------------------------------------------
# GET /api/last-night — the wire shape
# --------------------------------------------------------------------------

def _add_night(lib, safe, start, *, n):
    proj = lib.open_target(safe)
    try:
        for i in range(n):
            proj.add_frame(FrameRow(
                source_path=f"/x/{safe}-{start:%Y%m%d%H%M}-{i}.fit",
                timestamp_utc=(start + dt.timedelta(seconds=30 * i)).isoformat(),
                exposure_s=10.0, accept=True,
            ))
    finally:
        proj.close()


def _add_run(lib, safe, when, *, n_frames, options_json=GENUINE):
    proj = lib.open_target(safe)
    try:
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc=when, output_basename=f"{safe}-{n_frames}",
            fits_path=None, tiff_path=None, preview_path=None,
            n_frames_used=n_frames, canvas_h=100, canvas_w=100,
            coverage_min=n_frames, coverage_max=n_frames,
            options_json=options_json,
        ))
    finally:
        proj.close()


def _finished_scan(client, result: dict, *, when="2026-07-09T05:00:00Z") -> None:
    jm = client.app.state.job_manager
    job = Job(kind="pipeline")
    job.state = "done"
    job.created_utc = job.finished_utc = when
    job.result = result
    jm._jobs[job.id] = job
    jm._persist(job)


def test_last_night_carries_the_overnight_digest(client, built_library):
    from seestack.io.library import Library

    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, "M_42", NIGHT, n=6)
        _add_run(lib, "M_42", _stamp(-30), n_frames=60)   # the old picture
        _add_run(lib, "M_42", _stamp(7), n_frames=120)    # made overnight
        _add_run(lib, "M_42", _stamp(8), n_frames=120,    # an editor export
                 options_json=json.dumps({"editor_recipe": {"ops": []}}))
    finally:
        lib.close()
    _finished_scan(client, {"auto_stack_held_thin": [
        {"target": "NGC_7000", "frames": 3, "min": 8}]})

    body = client.get("/api/last-night").json()
    assert body["since_utc"] == body["start_utc"]
    assert [(p["safe"], p["n_frames"], p["previous_frames"])
            for p in body["new_pictures"]] == [("M_42", 120, 60)]
    # The held target is named from the registry, not from the job summary,
    # which records only safe names.
    assert [(h["safe"], h["kind"], h["n_frames"], h["n_other"])
            for h in body["needs_look"]] == [("NGC_7000", "too_thin", 3, 8)]
    assert body["needs_look"][0]["name"] == "NGC_7000"


def test_a_night_the_app_did_nothing_with_reports_nothing(client, built_library):
    """Auto-stack off (the owner's live setting) — the card keeps its capture
    paragraph and simply carries two empty lists, so nothing new is drawn."""
    from seestack.io.library import Library

    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, "M_42", NIGHT, n=6)
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert body["new_pictures"] == []
    assert body["needs_look"] == []


def test_an_empty_library_is_still_a_null_card(client):
    assert client.get("/api/last-night").json() is None
