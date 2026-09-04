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
