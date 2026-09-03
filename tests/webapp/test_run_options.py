"""One verdict on "can I reuse this run's settings?", across all three surfaces.

The Gallery card, the History / Target run listing and the endpoint the "Reuse
settings" button calls each used to carry their own copy of the same rule, and
the copies disagreed about a run that recorded no settings: two called it
reusable, one didn't. So a listing could show a button the endpoint refuses.
These tests pin the shared predicate and, more importantly, pin the three
surfaces *agreeing* — which is the property a fourth copy would break."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp.run_options import parse_run_options, run_has_reusable_options


def _register_run(data_root, safe: str, options_json: str) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=7,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=7,
                options_json=options_json,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_parse_run_options_reads_every_unusable_shape_as_no_settings():
    assert parse_run_options(json.dumps({"sigma_clip": True})) == {"sigma_clip": True}
    assert parse_run_options(None) == {}
    assert parse_run_options("") == {}
    assert parse_run_options("{not json") == {}
    # Valid JSON that isn't an object is still "no settings", not a crash.
    assert parse_run_options("[1, 2, 3]") == {}
    assert parse_run_options('"a string"') == {}


def test_run_has_reusable_options_covers_the_three_no_cases():
    assert run_has_reusable_options(json.dumps({"sigma_clip": True})) is True
    # An editor export and a channel combine store something else entirely.
    assert run_has_reusable_options(json.dumps({"editor_recipe": {"ops": []}})) is False
    assert run_has_reusable_options(json.dumps({"channel_combine": {"mode": "RGB"}})) is False
    # ...and a run with nothing recorded has nothing to pre-fill a form with.
    assert run_has_reusable_options("{}") is False
    assert run_has_reusable_options("") is False
    assert run_has_reusable_options(None) is False
    assert run_has_reusable_options("not json at all") is False


def test_all_three_surfaces_agree_on_every_run(client, solved_library):
    """The property that matters: whatever a run's options look like, the
    Gallery, the run listing and the endpoint behind the button say the same
    thing. A run with no recorded settings is the case the hand-mirrored copies
    got wrong — the two listings called it reusable and the endpoint served an
    empty form, while the History listing said no."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    ids = {
        "plain": _register_run(safe=safe, data_root=solved_library,
                               options_json=json.dumps({"sigma_clip": True})),
        "editor": _register_run(safe=safe, data_root=solved_library,
                                options_json=json.dumps({"editor_recipe": {"ops": []}})),
        "combine": _register_run(safe=safe, data_root=solved_library,
                                 options_json=json.dumps({"channel_combine": {"mode": "RGB"}})),
        "empty": _register_run(safe=safe, data_root=solved_library, options_json=""),
        "garbage": _register_run(safe=safe, data_root=solved_library,
                                 options_json="{not json"),
    }

    gallery = {it["run_id"]: it["reusable"]
               for it in client.get("/api/gallery").json()["items"]}
    listing = {r["id"]: r["reusable"]
               for r in client.get(f"/api/targets/{safe}/stack-runs").json()}

    expected = {"plain": True, "editor": False, "combine": False,
                "empty": False, "garbage": False}
    for label, run_id in ids.items():
        want = expected[label]
        assert gallery[run_id] is want, f"gallery disagrees on {label}"
        assert listing[run_id] is want, f"run listing disagrees on {label}"
        # The endpoint the button calls: served iff the listings offered it.
        r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/options")
        assert (r.status_code == 200) is want, f"endpoint disagrees on {label}"


def test_a_settingless_run_is_never_offered_a_form_it_cannot_fill(
    client, solved_library
):
    """The concrete symptom of the disagreement, stated on its own so a
    regression names itself: an option-less run must not advertise "Reuse
    settings" anywhere, because there is nothing behind the button."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(safe=safe, data_root=solved_library, options_json="")

    gallery = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert gallery[run_id]["reusable"] is False
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/options")
    assert r.status_code == 400
    assert "reusable" in r.json()["detail"]
