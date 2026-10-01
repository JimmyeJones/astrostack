""""You've shot more of this since the picture was made" — library-wide.

The per-target version of this nudge has shipped since v0.90.0, but it only
speaks to someone already looking at the picture that has fallen behind. With
auto-stack off and a target per object across many nights (AGENTS.md §1), the
question after a night's capture is *which* target to open — and until
``GET /api/new-subs-waiting`` nothing anywhere answered it.

These pin the definition ("new" = accepted **and** solved, and missing from the
newest *genuine* stack — shot after it, or set aside while it was made and since
put back), the honesty cases that keep it from nagging, and that the library-wide
answer is exactly the union of the Target page's own two numbers.
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

# A restoration stamp later than every run these tests write. A real row holds
# `restoration_stamp()`'s output — `datetime.now(timezone.utc).isoformat()` — so a
# literal of that shape is what the column actually carries.
RESTORED_AFTER_EVERYTHING = "2026-06-01T00:00:00+00:00"

# A run stamped between the synthetic frames' own capture time and `SHOT_AFTER_MID`,
# so one sub of a three-sub target can be shot after the picture and another shot
# before it — the disjoint fixture the union guard needs.
MID = "2024-10-01T00:00:00+00:00"
SHOT_AFTER_MID = "2024-11-01T00:00:00+00:00"


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


def test_count_light_missing_from_stack_sees_a_sub_that_came_back_after_it(
        solved_library):
    """The half `count_accepted_solved_after` cannot see.

    The app sets subs aside by itself and puts them back by itself, and a sub
    restored *after* a picture was stacked is not in that picture — however long
    before it the sub was shot. That is usually the very night the picture is made
    of, so the capture-time test is silent on it by construction.
    """
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            frames = list(proj.iter_frames())
            assert len(frames) == 3
            # A picture stacked after every sub was shot: nothing is "new".
            assert proj.count_accepted_solved_after(AFTER) == 0
            assert proj.count_light_missing_from_stack(AFTER) == 0

            # One of them was set aside while that picture was made, and came
            # back afterwards. The capture-time question still answers zero; the
            # picture is still missing a sub.
            proj.update_frame(frames[0].id,
                              restored_utc=RESTORED_AFTER_EVERYTHING)
            assert proj.count_accepted_solved_after(AFTER) == 0
            assert proj.count_light_missing_from_stack(AFTER) == 1

            # A sub that is both shot after the picture *and* restored after it is
            # one missing sub, not two — the reason this is one COUNT with an OR
            # rather than two counts added together.
            assert proj.count_light_missing_from_stack(BEFORE) == 3

            # The same bar as the other half: a re-stack has to be able to use it.
            proj.update_frame(frames[0].id, accept=0)
            assert proj.count_light_missing_from_stack(AFTER) == 0
            proj.update_frame(frames[0].id, accept=1, wcs_json=None)
            assert proj.count_light_missing_from_stack(AFTER) == 0

            # And a restoration that happened *before* the picture was stacked is
            # light the picture has: the run combined it.
            proj.update_frame(frames[0].id, wcs_json=frames[0].wcs_json,
                              restored_utc=BEFORE)
            assert proj.count_light_missing_from_stack(AFTER) == 0
        finally:
            proj.close()
    finally:
        lib.close()



def test_a_sub_set_aside_after_the_picture_was_made_is_not_missing_from_it(
        solved_library):
    """The over-count the restoration stamp alone cannot avoid.

    ``apply_grade_report`` can set aside a frame an *earlier* stack used — a
    re-grade on a bigger population moves the percentile cut — and
    ``apply_grade_reaccepts`` then puts it back, stamping a restoration later
    than that stack. Read on the restoration alone the sub looks missing from a
    picture whose pixels contain it, so the Dashboard note says a target is
    behind when it is not and "Bring my pictures up to date" spends hours of NAS
    CPU producing the identical picture.

    ``frames.rejected_utc`` settles it: the sub was still accepted when the run
    started, so the run has it.
    """
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            frames = list(proj.iter_frames())
            assert proj.count_light_missing_from_stack(AFTER) == 0

            # Set aside *after* the picture at AFTER, then put back later still.
            proj.update_frame(frames[0].id, accept=0,
                              reject_reason="auto:grade:fwhm_px")
            aside = proj.get_frame(frames[0].id).rejected_utc
            assert aside is not None and aside > AFTER
            proj.update_frame(frames[0].id, accept=1, reject_reason=None,
                              restored_utc=RESTORED_AFTER_EVERYTHING)

            # Fails before: the restoration postdates the run, so the naive rule
            # counted it as light the picture lacks. It does not lack it.
            assert proj.count_light_missing_from_stack(AFTER) == 0

            # …and the genuine case is untouched: a sub set aside *before* that
            # picture and put back after it really is missing from it.
            proj.update_frame(frames[1].id, rejected_utc=BEFORE,
                              restored_utc=RESTORED_AFTER_EVERYTHING)
            assert proj.count_light_missing_from_stack(AFTER) == 1

            # A legacy row carries no set-aside stamp at all, and keeps exactly
            # the answer it had before the column existed.
            proj.update_frame(frames[2].id, rejected_utc=None,
                              restored_utc=RESTORED_AFTER_EVERYTHING)
            assert proj.count_light_missing_from_stack(AFTER) == 2
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



def test_a_target_whose_only_shortfall_is_a_restored_sub_is_still_named(
        client, solved_library):
    """The case the library-wide note was blind to, and the reason it matters.

    ``reconcile_bad_solve_frames`` (v0.489.0) exists to hand back subs a stack
    dropped for a wrong-scale plate solve — up to 178 of them on the owner's
    library — and every one of those was shot long before the picture it is
    missing from. On the capture-time rule alone the note said nothing about those
    targets, so the one library-wide offer that could restack them in a batch
    could not reach them either: the only route was target by target.
    """
    _add_run(solved_library, "M_42", AFTER)          # stacked after every sub
    assert _waiting(client)["count"] == 0            # …so: silence, correctly

    _update_frames(solved_library, "M_42",
                   restored_utc=RESTORED_AFTER_EVERYTHING)
    data = _waiting(client)
    assert data["count"] == 1
    assert data["total_new_subs"] == 3
    assert data["items"][0]["safe"] == "M_42"
    assert data["items"][0]["n_new_subs"] == 3
    assert data["items"][0]["stacked_utc"] == AFTER


def test_the_library_note_is_the_union_of_the_target_page_s_own_two_numbers(
        client, solved_library):
    """The drift guard for a definition that is deliberately *wider* than one of
    its siblings.

    The Target page keeps the two reasons apart on purpose — *"N new subs since
    your last stack"* counts by capture time, and the ``restored-subs`` card
    counts the subs that came back — because beside one picture the reason is
    worth saying. The library-wide roll-up only has to answer *which* pictures are
    behind, so it is their union. Re-derived here from the very payloads that page
    reads, on a fixture where the two sets are **disjoint**, so the union is their
    sum and the three surfaces cannot drift into naming different numbers.
    """
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            a, b, _c = list(proj.iter_frames())
            # a: shot after the picture was made. b: shot before it, set aside
            # while it was made, and put back afterwards. c: in the picture.
            proj.update_frame(a.id, timestamp_utc=SHOT_AFTER_MID)
            proj.update_frame(b.id, restored_utc=RESTORED_AFTER_EVERYTHING)
        finally:
            proj.close()
    finally:
        lib.close()
    _add_run(solved_library, "M_42", MID)

    runs = client.get("/api/targets/M_42/stack-runs").json()
    newest_genuine = next(r for r in runs if r["reusable"])
    frames = client.get("/api/targets/M_42/frames").json()
    rows = frames["frames"] if isinstance(frames, dict) else frames
    page_new = sum(
        1 for f in rows
        if f.get("accept") and f.get("solved") and f.get("timestamp_utc")
        and f["timestamp_utc"] > newest_genuine["timestamp_utc"]
    )
    back = client.get("/api/targets/M_42/restored-subs").json()
    page_restored = back["n_restored"]
    # The fixture, stated so a change to it is visible: one sub of each kind, and
    # no sub of both — so the union is the sum and this is an equality.
    assert (page_new, page_restored) == (1, 1)

    data = _waiting(client)
    assert data["items"][0]["n_new_subs"] == page_new + page_restored
    assert data["items"][0]["stacked_utc"] == newest_genuine["timestamp_utc"]


# ------------------------- the one install where "solved" is not the bar ---

# What a run records when the stacker was told to place the subs no plate solve
# could locate, by matching their star patterns to the reference
# (`StackOptions.star_match_unsolved`, off by default and hand-set advanced).
STAR_MATCH_OPTS = json.dumps({"sigma_clip": True, "star_match_unsolved": True})

# Two run stamps that both *predate* `FRAME_UTC`, so every sub is light captured
# after either of them and the only thing separating the two cases is the run's
# own options. (`MID` would not do: it postdates the synthetic frames, so a
# target measured against it has nothing waiting whatever the bar is — a test
# built on it would pass without the gate being read at all.)
EARLIER = "2024-08-01T00:00:00+00:00"


def test_count_light_missing_can_be_asked_without_the_solved_half_of_the_bar(
        solved_library):
    """The engine half, in isolation: ``include_unsolved`` widens the count and
    nothing else about it moves."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            frames = list(proj.iter_frames())
            assert len(frames) == 3
            for f in frames:
                proj.update_frame(f.id, wcs_json=None)

            # Today's bar: no solve, no place on the canvas, nothing waiting.
            assert proj.count_light_missing_from_stack(BEFORE) == 0
            # Asked the other way, the same three subs are light the picture lacks.
            assert proj.count_light_missing_from_stack(
                BEFORE, include_unsolved=True) == 3

            # Every other clause still holds: rejected is still rejected, and an
            # undated sub still cannot be placed on either side of the stack.
            proj.update_frame(frames[0].id, accept=0)
            assert proj.count_light_missing_from_stack(
                BEFORE, include_unsolved=True) == 2
            proj.update_frame(frames[1].id, timestamp_utc=None)
            assert proj.count_light_missing_from_stack(
                BEFORE, include_unsolved=True) == 1
            # And a picture stacked after everything is still not behind.
            assert proj.count_light_missing_from_stack(
                AFTER, include_unsolved=True) == 0
        finally:
            proj.close()
    finally:
        lib.close()


def test_a_shortfall_of_only_unsolved_subs_is_invisible_unless_the_run_star_matched(
        client, solved_library):
    """Both directions of the gate, on the endpoint, on one fixture.

    A target whose every sub is un-located is *not* a picture behind its data on
    an ordinary install — ``run_stack`` would skip those subs, so naming the
    target would be a nag. With ``star_match_unsolved`` on it is exactly that,
    because the stacker places un-located subs by matching their stars to the
    reference, and that is the whole point of the option: on a faint or star-poor
    field ASTAP fails on most subs and the picture is the handful that solved.

    Fails before: the solved half of the bar was unconditional, so the
    library-wide note answered "nothing waiting" on both runs.
    """
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, wcs_json=None)
        finally:
            proj.close()
    finally:
        lib.close()

    _add_run(solved_library, "M_42", EARLIER)
    assert _waiting(client)["count"] == 0

    # The same subs, the same shortfall — re-stacked with star-matching on.
    _add_run(solved_library, "M_42", BEFORE, options_json=STAR_MATCH_OPTS,
             basename="master2")
    data = _waiting(client)
    assert data["count"] == 1
    assert data["total_new_subs"] == 3
    assert data["items"][0]["safe"] == "M_42"
    assert data["items"][0]["n_new_subs"] == 3
    assert data["items"][0]["stacked_utc"] == BEFORE


def test_the_star_match_bar_is_read_off_the_newest_genuine_run_only(
        client, solved_library):
    """An *older* run's setting says nothing about what a re-stack would do now.

    A reprocess reuses the newest genuine run's options
    (``webapp.pipeline._last_stack_options_for_target``), so that run is the one
    whose option decides — otherwise a single historical star-matched run would
    keep a target permanently named on an install that has since turned it off.
    """
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, wcs_json=None)
        finally:
            proj.close()
    finally:
        lib.close()

    _add_run(solved_library, "M_42", EARLIER, options_json=STAR_MATCH_OPTS)
    _add_run(solved_library, "M_42", BEFORE, basename="master2")  # no star-matching
    # Both runs predate every sub, so "nothing waiting" here is the *bar* saying
    # no, not the clock: with the older run's option honoured it would be 3.
    assert _waiting(client)["count"] == 0


def test_an_editor_export_over_a_star_matched_stack_does_not_reset_the_bar(
        client, solved_library):
    """The "which run?" rule and the "which bar?" rule must read the *same* run.

    An export is a re-render of a stack, not a stack, so it neither resets the
    clock nor supplies settings — both questions have to walk past it to the same
    genuine run, or the note would compare against one picture's timestamp using
    another picture's rules.
    """
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, wcs_json=None)
        finally:
            proj.close()
    finally:
        lib.close()

    _add_run(solved_library, "M_42", EARLIER, options_json=STAR_MATCH_OPTS)
    _add_run(solved_library, "M_42", BEFORE, options_json=EDITOR_OPTS,
             basename="export")
    data = _waiting(client)
    assert data["count"] == 1
    assert data["items"][0]["n_new_subs"] == 3
    assert data["items"][0]["stacked_utc"] == EARLIER    # not the export


# ------------------------------------- the picture on the wall is measured ---
#
# 2026-09-30 audit, C-F1. The run measured used to be the *newest genuine* one,
# whatever the target was showing. After a Combine that is the one-night stack
# carried in — its own recent timestamp, a subset of the subs — so the one target
# a Combine exists to deepen answered "nothing missing", and the same reading was
# wrong for any pinned older cover. The picture on the wall is the one measured
# now, and where a run recorded which subs it was offered, "missing" is
# membership rather than a clock (``tests/test_stack_run_frames.py``).

def _give_a_picture(data_root, safe, ts, *, options_json=REAL_OPTS,
                    basename="master") -> int:
    """A run with its files on disk, so a merge carries it and the wall shows it."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            out = proj.project_dir / "output"
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{basename}.fits").write_bytes(safe.encode())
            (out / f"{basename}_preview.png").write_bytes(b"png:" + safe.encode())
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename=basename,
                fits_path=str(out / f"{basename}.fits"), tiff_path=None,
                preview_path=str(out / f"{basename}_preview.png"),
                n_frames_used=3, canvas_h=10, canvas_w=10,
                coverage_min=1, coverage_max=1, options_json=options_json,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _combine(data_root, into, source):
    lib = Library.open_or_create(data_root / "library")
    try:
        return lib.merge_targets_result(into, [source])
    finally:
        lib.close()


def test_a_combined_target_is_named_with_the_other_nights_subs(client, solved_library):
    """The audit's case. Both nights were stacked after every sub was shot, so
    by the clock neither picture is missing anything; the Combine pins the deep
    target's own picture, which has never seen the second night's subs."""
    _give_a_picture(solved_library, "M_42", AFTER)
    _give_a_picture(solved_library, "NGC_7000", MID)
    assert _waiting(client)["count"] == 0

    result = _combine(solved_library, "M_42", "NGC_7000")
    assert result.pictures_kept == 1 and result.picture_pinned is True

    data = _waiting(client)
    assert data["count"] == 1
    (item,) = data["items"]
    assert item["safe"] == "M_42"
    assert item["n_new_subs"] == 3           # the second night, all of it
    assert item["stacked_utc"] == AFTER      # the picture on the wall, not the carried run
    # …and the Settings count the batch quotes agrees, so the note and the
    # "Bring my pictures up to date" dialog cannot name different targets.
    status = client.get("/api/reprocess-status").json()
    assert status["new_light"] == 1
    assert status["new_light_subs"] == 3


def test_a_combined_target_showing_the_carried_picture_is_missing_its_own_night(
        client, solved_library):
    """The other way round: the deep folder had never been stacked, so the
    carried one-night picture is what the wall shows — and it is missing every
    sub the target already held."""
    _give_a_picture(solved_library, "NGC_7000", AFTER)
    _combine(solved_library, "M_42", "NGC_7000")

    data = _waiting(client)
    assert data["count"] == 1
    (item,) = data["items"]
    assert item["safe"] == "M_42"
    assert item["n_new_subs"] == 3
    assert item["stacked_utc"] == AFTER


def test_a_pinned_older_cover_is_the_picture_measured(client, solved_library):
    """A cover the owner pinned outranks the newest run on every wall surface,
    so it is the picture that can fall behind — and the newest run being up to
    date is no answer about it."""
    older = _give_a_picture(solved_library, "M_42", BEFORE)
    _give_a_picture(solved_library, "M_42", AFTER, basename="master_2")
    assert _waiting(client)["count"] == 0     # newest picture has everything

    lib = Library.open_or_create(solved_library / "library")
    try:
        lib.set_target_cover("M_42", older)
    finally:
        lib.close()
    data = _waiting(client)
    assert data["count"] == 1
    assert data["items"][0]["n_new_subs"] == 3
    assert data["items"][0]["stacked_utc"] == BEFORE


def test_an_export_on_the_wall_is_measured_as_the_stack_it_was_rendered_from(
        client, solved_library):
    """An export re-renders an existing picture; the picture it *is* is the run
    it derives from, and that is what falls behind."""
    origin = _give_a_picture(solved_library, "M_42", BEFORE)
    _give_a_picture(solved_library, "M_42", AFTER, basename="master_edit",
                    options_json=json.dumps({"editor_recipe": {"ops": []},
                                             "derived_from": origin}))
    data = _waiting(client)
    assert data["count"] == 1
    assert data["items"][0]["run_id"] == origin
    assert data["items"][0]["stacked_utc"] == BEFORE


def test_an_export_that_does_not_say_what_it_derives_from_resolves_to_the_nearest_stack(
        client, solved_library):
    """An export recorded before ``derived_from`` existed is a re-render of the
    newest stack older than it — never a reset of the clock."""
    _give_a_picture(solved_library, "M_42", BEFORE)
    _give_a_picture(solved_library, "M_42", AFTER, basename="master_edit",
                    options_json=EDITOR_OPTS)
    data = _waiting(client)
    assert data["count"] == 1
    assert data["items"][0]["stacked_utc"] == BEFORE


def test_a_picture_the_batch_kept_on_the_wall_is_not_nagged_about(client, solved_library):
    """A cover the bulk restack pinned to keep a hand-finished picture is not
    the owner's choice of picture — the deeper run it kept in History is what is
    measured, or every batch would re-name the target, restack it, keep it, and
    never stop. A pin he made himself (no record) is still the picture measured."""
    from seestack.coverpin import PIN_REASON_KEPT_FINISHED, mark_app_pin

    kept = _give_a_picture(solved_library, "M_42", BEFORE)
    _give_a_picture(solved_library, "M_42", AFTER, basename="master_2")
    lib = Library.open_or_create(solved_library / "library")
    try:
        lib.set_target_cover("M_42", kept)
        proj = lib.open_target("M_42")
        try:
            mark_app_pin(proj, kept, PIN_REASON_KEPT_FINISHED)
        finally:
            proj.close()
    finally:
        lib.close()
    assert _waiting(client)["count"] == 0         # the deeper picture has it all

    # The owner re-pins the same run by hand: the record no longer matches
    # (a fresh pin is his), and the kept picture is measured again.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            proj.delete_meta("cover_pinned_by_app")
        finally:
            proj.close()
    finally:
        lib.close()
    assert _waiting(client)["count"] == 1


# ------------- …and the Target page's own line, through the same function ---

# Until v0.492.x the line beside the picture — *"N new subs since your last
# stack"* — was computed in the browser, from the frame list and the run listing,
# as "accepted + solved frames captured after the newest ``reusable`` run". That
# is two readings away from the rule above: the clock instead of membership, and
# the newest genuine run instead of the picture on the wall. A Combine diverges on
# both at once, so the Dashboard named the target while the target's own page said
# nothing. `GET /api/targets/{safe}/new-light` is the same function's answer for
# one target; `_page_note` below is what the page now reads, and `_old_browser_
# reading` re-derives the TypeScript it replaced, so the gap is in the test rather
# than in a changelog.

def _page_note(client, safe="M_42"):
    r = client.get(f"/api/targets/{safe}/new-light")
    assert r.status_code == 200
    return r.json()


def _old_browser_reading(client, safe="M_42") -> int:
    """``countNewSubsSinceStack``, re-derived from the payloads it read."""
    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    newest_genuine = next((r for r in runs if r["reusable"]), None)
    if newest_genuine is None:
        return 0
    frames = client.get(f"/api/targets/{safe}/frames").json()
    rows = frames["frames"] if isinstance(frames, dict) else frames
    return sum(
        1 for f in rows
        if f.get("accept") and f.get("solved") and f.get("timestamp_utc")
        and f["timestamp_utc"] > newest_genuine["timestamp_utc"]
    )


def test_the_target_page_s_own_line_names_a_combined_targets_missing_night(
        client, solved_library):
    """The bug, and the fix, in one test.

    Both nights were stacked after every sub was shot and the Combine pins the
    deep target's own picture, so the browser's capture-time reading against the
    newest genuine run sees **nothing** — while the Dashboard names the target
    with all three of the carried night's subs.
    """
    _give_a_picture(solved_library, "M_42", AFTER)
    _give_a_picture(solved_library, "NGC_7000", MID)
    _combine(solved_library, "M_42", "NGC_7000")

    assert _old_browser_reading(client) == 0      # what the page used to say

    note = _page_note(client)
    assert note is not None
    assert note["n_new_subs"] == 3
    assert note["timestamp_utc"] == AFTER         # the picture on the wall


def test_the_target_page_and_the_library_roll_up_cannot_disagree(
        client, solved_library):
    """One function, so the two surfaces answer with the same number, the same
    run and the same date — on the fixture where the old reading diverged."""
    _give_a_picture(solved_library, "M_42", AFTER)
    _give_a_picture(solved_library, "NGC_7000", MID)
    _combine(solved_library, "M_42", "NGC_7000")

    (item,) = _waiting(client)["items"]
    note = _page_note(client)
    assert (note["n_new_subs"], note["run_id"], note["timestamp_utc"]) == (
        item["n_new_subs"], item["run_id"], item["stacked_utc"])
    assert note["n_frames_used"] == item["n_frames_used"]


def test_the_target_page_measures_the_pinned_older_cover_it_is_showing(
        client, solved_library):
    """A cover the owner pinned is the picture that can fall behind, and the
    newest run being up to date is no answer about it."""
    older = _give_a_picture(solved_library, "M_42", BEFORE)
    _give_a_picture(solved_library, "M_42", AFTER, basename="master_2")
    assert _page_note(client) is None             # newest picture has everything

    lib = Library.open_or_create(solved_library / "library")
    try:
        lib.set_target_cover("M_42", older)
    finally:
        lib.close()
    note = _page_note(client)
    assert note is not None
    assert (note["run_id"], note["n_new_subs"]) == (older, 3)


def test_the_target_page_says_nothing_when_the_picture_has_every_sub(
        client, solved_library):
    """The common case: one stack, nothing shot since, nothing put back."""
    _add_run(solved_library, "M_42", AFTER)
    assert _page_note(client) is None


def test_the_target_page_says_nothing_about_a_target_never_stacked(
        client, solved_library):
    """*"You have never stacked this"* is another surface's sentence — this one
    is about a picture that has fallen behind, and there is no picture."""
    assert _page_note(client) is None


def test_a_restored_sub_the_clock_cannot_see_is_in_the_page_s_number(
        client, solved_library):
    """The widening v0.492.3 gave the library-wide note now reaches the line
    beside the picture too. The *reason* stays the restored card's to say — the
    page gives it the slot when a restoration is the whole shortfall — but the
    number the page holds is the honest one either way."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            frame = next(iter(proj.iter_frames()))
            proj.update_frame(frame.id, restored_utc=RESTORED_AFTER_EVERYTHING)
        finally:
            proj.close()
    finally:
        lib.close()
    _add_run(solved_library, "M_42", AFTER)

    assert _old_browser_reading(client) == 0      # a restored sub was shot before
    note = _page_note(client)
    assert note is not None and note["n_new_subs"] == 1
    back = client.get("/api/targets/M_42/restored-subs").json()
    assert back["n_restored"] == 1                # and the card still says why
