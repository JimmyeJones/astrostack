"""`GET /api/targets/{safe}/restored-subs` — "some of your subs came back after
this picture was made".

The engine half is unit-tested in ``tests/test_restorednudge.py``; these pin the
endpoint's own contract on a real library: genuine runs only, only subs that are
accepted *and* solved now, and — most importantly — **silence** in every state
that isn't a genuine restoration. This nudge sits on the Target page the owner
opens every session, so a false positive is a permanent one.
"""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow

RAN = "2026-08-30T14:32:05+00:00"
BEFORE = "2026-08-30T09:00:00+00:00"
AFTER = "2026-08-31T22:10:00+00:00"


def _register_run(data_root, safe: str, *, ts: str, n_frames: int = 40,
                  options: dict | None = None) -> int:
    """Add a stack run. ``options=None`` writes a genuine ``StackOptions``
    payload; pass a bare dict for a non-genuine (editor-export/combine) run."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts,
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=n_frames,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=n_frames,
                options_json=json.dumps(
                    options if options is not None else {"output_name": "m42"}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _mark_restored(data_root, safe: str, *, when: str, n: int = 1,
                   solved: bool = True, accept: bool = True) -> None:
    """Stamp ``n`` of the target's frames as having been put back at ``when``."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for f in list(proj.iter_frames())[:n]:
                proj.update_frame(
                    f.id, restored_utc=when, accept=accept,
                    wcs_json="{}" if solved else None,
                )
        finally:
            proj.close()
    finally:
        lib.close()


def test_subs_that_came_back_after_the_stack_are_offered_a_restack(
    client, built_library,
):
    """The case the note exists for. Fails before: there was no endpoint, and
    nothing anywhere recorded that the subs had been put back."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(built_library, safe, ts=RAN)
    _mark_restored(built_library, safe, when=AFTER, n=2)

    body = client.get(f"/api/targets/{safe}/restored-subs").json()
    assert body is not None
    assert body["run_id"] == run_id
    assert body["n_restored"] == 2
    assert body["n_frames_used"] == 40      # what the picture on screen combined
    assert body["timestamp_utc"] == RAN


def test_a_target_with_no_restorations_says_nothing(client, built_library):
    """Every healthy install, and the default this must never drift off."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN)
    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


def test_a_restoration_the_picture_already_includes_says_nothing(
    client, built_library,
):
    """Reconsidered, *then* stacked — the picture is correct, so sending the
    owner off to re-make it would be a lie that never goes away."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN)
    _mark_restored(built_library, safe, when=BEFORE, n=2)
    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


def test_a_restored_sub_that_is_still_unsolved_is_not_promised(
    client, built_library,
):
    """It would not go into the re-stack, so counting it would over-promise.
    It self-heals the moment the solve lands."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN)
    _mark_restored(built_library, safe, when=AFTER, n=2, solved=False)
    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


def test_a_restored_sub_the_user_has_since_rejected_is_not_promised(
    client, built_library,
):
    """Their decision wins: a sub they set aside by hand isn't coming back into
    the picture, so it is not a reason to re-stack."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN)
    _mark_restored(built_library, safe, when=AFTER, n=2, accept=False)
    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


def test_an_editor_export_is_not_the_picture_this_is_about(client, built_library):
    """An export is made *from* a stack, not from subs, so it can neither gain
    nor miss one — the newest *genuine* run is the picture in question."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(built_library, safe, ts=RAN)
    _register_run(built_library, safe, ts="2026-09-02T09:00:00+00:00",
                  options={"edit_export": True})
    _mark_restored(built_library, safe, when=AFTER, n=1)

    body = client.get(f"/api/targets/{safe}/restored-subs").json()
    assert body is not None
    assert body["run_id"] == run_id      # not the export


def test_a_target_with_no_stack_says_nothing(client, built_library):
    """There is no picture to be thinner than the data yet."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _mark_restored(built_library, safe, when=AFTER, n=2)
    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


def test_the_restack_lands_and_the_note_goes_away(client, built_library):
    """Self-hiding is what stops it being a nag: a newer genuine run postdates
    the restoration, so there is nothing left to say."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN)
    _mark_restored(built_library, safe, when=AFTER, n=2)
    assert client.get(f"/api/targets/{safe}/restored-subs").json() is not None

    _register_run(built_library, safe, ts="2026-09-03T01:00:00+00:00")
    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


# --------------------------------- the star-matching install's own bar ---

# A run whose options say the stacker placed un-located subs by matching their
# star patterns (`StackOptions.star_match_unsolved`). Off by default and hand-set,
# so this is a deliberate non-owner install; `output_name` rides along so the run
# still parses as a genuine stack the way every other fixture here does.
STAR_MATCH_OPTS = {"output_name": "m42", "star_match_unsolved": True}


def test_an_unsolved_restored_sub_counts_when_the_run_star_matched_unsolved_subs(
    client, built_library,
):
    """The sibling of ``…_is_not_promised`` above, for the install that turns the
    option on.

    With ``star_match_unsolved`` on, an un-located sub **is** one the stack would
    place — by matching its stars to the reference rather than by a solve of its
    own — so a target whose whole shortfall is un-located subs is a picture that
    really is behind the light it owns. Before this, the solved half of the bar was
    unconditional and the note could not see that install at all.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(built_library, safe, ts=RAN, options=STAR_MATCH_OPTS)
    _mark_restored(built_library, safe, when=AFTER, n=2, solved=False)

    body = client.get(f"/api/targets/{safe}/restored-subs").json()
    assert body is not None
    assert body["run_id"] == run_id
    assert body["n_restored"] == 2


def test_the_option_is_read_off_the_run_being_measured_against(
    client, built_library,
):
    """Not off the app's defaults, and not off any older run.

    The question is *"what would stacking this again fold in?"*, and a reprocess
    reuses the newest genuine run's settings — so that run is the one whose option
    decides. A target stacked once with star-matching and then re-stacked without
    it is back to the solved bar.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=BEFORE, options=STAR_MATCH_OPTS)
    _register_run(built_library, safe, ts=RAN)          # no star-matching
    _mark_restored(built_library, safe, when=AFTER, n=2, solved=False)

    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


def test_the_option_off_is_spelt_the_narrow_way(client, built_library):
    """Anything other than a recorded ``True`` reads as off, so the offer errs by
    saying *less* than it could — the safe direction for an offer to be wrong in.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN,
                  options={"output_name": "m42", "star_match_unsolved": "yes"})
    _mark_restored(built_library, safe, when=AFTER, n=2, solved=False)

    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


def test_a_star_matching_run_still_counts_the_solved_restored_subs(
    client, built_library,
):
    """Lifting the solved half of the bar widens it; it must not replace it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN, options=STAR_MATCH_OPTS)
    _mark_restored(built_library, safe, when=AFTER, n=2, solved=True)

    body = client.get(f"/api/targets/{safe}/restored-subs").json()
    assert body is not None
    assert body["n_restored"] == 2


def test_a_sub_the_user_set_aside_is_still_not_promised_under_star_matching(
    client, built_library,
):
    """The option lifts *one* half of the bar. Accepted is the other, and a sub
    the user rejected is not coming back into the picture whatever the stacker
    could align."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN, options=STAR_MATCH_OPTS)
    _mark_restored(built_library, safe, when=AFTER, n=2, solved=False, accept=False)

    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None


def test_an_empty_wcs_string_reads_as_unsolved_here_too(client, built_library):
    """One definition of "did the plate solve locate this sub?".

    ``FrameRow.solved`` is ``bool(wcs_json)``, and every other reader agrees, but
    this one query tested ``IS NOT NULL`` alone — so an empty string would have
    been promised here while counting as unsolved everywhere else. No writer
    stores ``''`` today; the point is that the two spellings of one bit cannot
    disagree if the column ever holds it.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts=RAN)
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for f in list(proj.iter_frames())[:2]:
                proj.update_frame(f.id, restored_utc=AFTER, accept=True,
                                  wcs_json="")
        finally:
            proj.close()
    finally:
        lib.close()

    assert client.get(f"/api/targets/{safe}/restored-subs").json() is None
