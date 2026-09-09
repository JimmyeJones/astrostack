""""You've shot more of this since the picture was made" — library-wide.

The per-target version of this nudge has shipped since v0.90.0, but it only
speaks to someone already looking at the picture that has fallen behind. With
auto-stack off and a target per object across many nights (AGENTS.md §1), the
question after a night's capture is *which* target to open — and until
``GET /api/new-subs-waiting`` nothing anywhere answered it.

These pin the definition ("new" = accepted **and** solved **and** dated, after
the newest *genuine* stack), the honesty cases that keep it from nagging, and
that it never claims a target the Target page's own nudge would call quiet.
"""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow

# A run's options as a real stack writes them. `{}` is deliberately *not* used:
# a run that recorded no settings at all is not a genuine stack to either of the
# app's two "is this a real run?" predicates, so it would silently skip.
REAL_OPTS = json.dumps({"sigma_clip": True, "kappa": 3.0})
EDITOR_OPTS = json.dumps({"editor_recipe": {"ops": []}})

# The synthetic frames' own DATE-OBS (tests/synth.py), normalised on ingest.
FRAME_UTC = "2024-09-12T03:14:55.123000+00:00"
BEFORE = "2024-09-01T00:00:00+00:00"
AFTER = "2025-01-01T00:00:00+00:00"


def _add_run(data_root, safe, ts, *, options_json=REAL_OPTS, basename="master",
             n_frames_used=5) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename=basename,
                fits_path=None, tiff_path=None, preview_path=None,
                n_frames_used=n_frames_used, canvas_h=10, canvas_w=10,
                coverage_min=1, coverage_max=1, options_json=options_json,
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _update_frames(data_root, safe, **fields):
    """Apply ``fields`` to every frame of one target."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, **fields)
        finally:
            proj.close()
    finally:
        lib.close()


def _waiting(client):
    r = client.get("/api/new-subs-waiting")
    assert r.status_code == 200
    return r.json()


# ------------------------------------------------- the count, in isolation ---

def test_count_accepted_solved_after_counts_only_usable_dated_new_subs(solved_library):
    """The rule is `run_stack`'s: a sub only counts as *waiting* if a re-stack
    would actually combine it."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            frames = list(proj.iter_frames())
            assert len(frames) == 3
            assert proj.count_accepted_solved_after(BEFORE) == 3
            # Nothing was shot after the stack: silence, not a nag.
            assert proj.count_accepted_solved_after(AFTER) == 0
            # An empty stamp is "we don't know when", never "everything".
            assert proj.count_accepted_solved_after("") == 0

            # Rejected: the stacker would skip it, so it is not light waiting.
            proj.update_frame(frames[0].id, accept=0)
            assert proj.count_accepted_solved_after(BEFORE) == 2
            # Unsolved: same — no WCS, no place on the canvas.
            proj.update_frame(frames[1].id, wcs_json=None)
            assert proj.count_accepted_solved_after(BEFORE) == 1
            # Undated: it cannot be placed on either side of the stack.
            proj.update_frame(frames[2].id, timestamp_utc=None)
            assert proj.count_accepted_solved_after(BEFORE) == 0
        finally:
            proj.close()
    finally:
        lib.close()


# ------------------------------------------------------------ the endpoint ---

def test_a_library_with_no_stacks_says_nothing(client, solved_library):
    """Never stacked is a different sentence, and other surfaces already say it."""
    assert _waiting(client) == {"count": 0, "total_new_subs": 0, "items": []}


def test_subs_shot_after_the_stack_are_reported_with_the_picture_they_are_missing_from(
        client, solved_library):
    _add_run(solved_library, "M_42", BEFORE, n_frames_used=2)
    data = _waiting(client)
    assert data["count"] == 1
    assert data["total_new_subs"] == 3
    (item,) = data["items"]
    assert item["safe"] == "M_42"
    assert item["n_new_subs"] == 3
    # What the re-stack would grow *from*, not only by.
    assert item["n_frames_used"] == 2
    assert item["stacked_utc"] == BEFORE


def test_a_target_stacked_after_its_newest_sub_is_quiet(client, solved_library):
    _add_run(solved_library, "M_42", AFTER)
    assert _waiting(client)["count"] == 0


def test_an_editor_export_does_not_reset_the_clock(client, solved_library):
    """An export re-renders an existing picture; it never folds in a sub. If it
    counted as "the last stack", saving an edit would silently retire the nudge."""
    _add_run(solved_library, "M_42", BEFORE)
    _add_run(solved_library, "M_42", AFTER, options_json=EDITOR_OPTS,
             basename="master_edit")
    data = _waiting(client)
    assert data["count"] == 1
    assert data["items"][0]["n_new_subs"] == 3
    # It reports the *genuine* run, not the newer export.
    assert data["items"][0]["stacked_utc"] == BEFORE


def test_rejected_and_unsolved_new_subs_never_nag(client, solved_library):
    _add_run(solved_library, "M_42", BEFORE)
    _update_frames(solved_library, "M_42", accept=0)
    assert _waiting(client)["count"] == 0


def test_targets_are_ranked_by_how_much_a_restack_would_buy(client, solved_library):
    """Most waiting first — the target where pressing Stack pays off most."""
    _add_run(solved_library, "M_42", BEFORE)
    _add_run(solved_library, "NGC_7000", BEFORE)
    # Leave M_42 with one waiting sub and NGC_7000 with all three.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            for f in list(proj.iter_frames())[:2]:
                proj.update_frame(f.id, accept=0)
        finally:
            proj.close()
    finally:
        lib.close()
    data = _waiting(client)
    assert data["count"] == 2
    assert data["total_new_subs"] == 4
    assert [i["safe"] for i in data["items"]] == ["NGC_7000", "M_42"]
    assert [i["n_new_subs"] for i in data["items"]] == [3, 1]


def test_the_dashboard_and_the_target_page_cannot_disagree(client, solved_library):
    """One definition, two surfaces.

    The Target page counts accepted+solved frames captured after the newest run
    whose ``reusable`` flag is set (``countNewSubsSinceStack``). This re-derives
    that number from the very payloads that page reads — the frame list and the
    run listing — and asserts the library-wide answer matches it exactly.
    """
    _add_run(solved_library, "M_42", BEFORE)
    _add_run(solved_library, "M_42", AFTER, options_json=EDITOR_OPTS,
             basename="master_edit")

    runs = client.get("/api/targets/M_42/stack-runs").json()
    newest_genuine = next(r for r in runs if r["reusable"])
    frames = client.get("/api/targets/M_42/frames").json()
    rows = frames["frames"] if isinstance(frames, dict) else frames
    page_count = sum(
        1 for f in rows
        if f.get("accept") and f.get("solved") and f.get("timestamp_utc")
        and f["timestamp_utc"] > newest_genuine["timestamp_utc"]
    )
    assert page_count == 3  # the fixture, stated so a change to it is visible

    data = _waiting(client)
    assert data["items"][0]["n_new_subs"] == page_count
    assert data["items"][0]["stacked_utc"] == newest_genuine["timestamp_utc"]


def test_one_unreadable_project_does_not_cost_the_whole_answer(
        client, solved_library, monkeypatch):
    """The same degradation the other cross-target reads have: a corrupt target
    is skipped, not 500'd, and the healthy one is still reported."""
    from seestack.io.project import Project

    _add_run(solved_library, "M_42", BEFORE)
    _add_run(solved_library, "NGC_7000", BEFORE)
    real_open = Project.open

    def _boom(path, *a, **kw):
        if "NGC_7000" in str(path):
            raise OSError("database is locked")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(Project, "open", staticmethod(_boom))
    data = _waiting(client)
    assert [i["safe"] for i in data["items"]] == ["M_42"]
