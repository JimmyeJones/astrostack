"""A saved-but-never-exported editor edit is flagged, and can be finished in one
call.

Someone who opens the editor, dials in a look and presses **Save** without
pressing **Export** ends up with their edit in the project DB and nowhere else:
every surface that shows "your picture" — the Target page's hero, History, the
Gallery — serves the run's *baked* preview PNG, which is still the plain
auto-stretch of the linear stack. The app was therefore showing an image the user
hadn't made, with no hint that their work existed. These cover the flag that lets
those surfaces say so, and the "finish the edit I already saved" export path.
"""

from __future__ import annotations

import json

from webapp.routers.stack import _unexported_edit

from .test_editor import _make_run, _wait_job

STRETCH = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}


# ---- the predicate, in isolation -------------------------------------------

def test_unexported_edit_predicate():
    saved = json.dumps(STRETCH)
    # A saved recipe on an ordinary (linear-preview) run: the picture on screen
    # is not the picture the user made.
    assert _unexported_edit("{}", saved) is True
    assert _unexported_edit(None, saved) is True
    # No recipe at all — the overwhelmingly common case.
    assert _unexported_edit("{}", None) is False
    assert _unexported_edit("{}", "") is False
    # An in-place "Process target" Auto edit stamps the recipe it just baked onto
    # the same run, so its preview already shows it. Nothing is unfinished.
    assert _unexported_edit('{"preview_display_space": true}', saved) is False


def test_a_re_edited_export_is_still_flagged():
    """An editor *export* writes a new run and stores no recipe on it, so a recipe
    on a display-space run can only have come from the user re-opening that export,
    editing it further and saving. That second-round edit is just as invisible as
    the first, and must not be excluded by the display-space marker."""
    saved = json.dumps(STRETCH)
    assert _unexported_edit('{"display_space": true}', saved) is True
    # …but the export itself, which carries no recipe, stays quiet.
    assert _unexported_edit('{"display_space": true}', None) is False


def test_unexported_edit_ignores_recipes_that_change_nothing():
    """A recipe is only an unfinished edit if it would actually alter the look —
    otherwise the app would nag about an empty or fully-disabled one."""
    assert _unexported_edit("{}", json.dumps({"ops": []})) is False
    assert _unexported_edit("{}", json.dumps(
        {"ops": [{"id": "tone.stretch", "enabled": False, "params": {}}]})) is False
    # One enabled op among disabled ones still counts.
    assert _unexported_edit("{}", json.dumps({"ops": [
        {"id": "tone.stretch", "enabled": False, "params": {}},
        {"id": "tone.saturation", "enabled": True, "params": {}},
    ]})) is True
    # Garbage never crashes and never nags.
    assert _unexported_edit("{}", "not json") is False
    assert _unexported_edit("{}", "[1, 2, 3]") is False
    assert _unexported_edit("{}", json.dumps({"ops": "nope"})) is False


# ---- the flag on the runs listing ------------------------------------------

def test_run_listing_flags_a_saved_but_unexported_edit(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="linear_src")

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    assert next(x for x in runs if x["id"] == rid)["unexported_edit"] is False

    r = client.put(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe", json=STRETCH)
    assert r.status_code == 200

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    assert next(x for x in runs if x["id"] == rid)["unexported_edit"] is True


def test_exporting_clears_the_flag_for_the_new_run(client, solved_library):
    """The exported run *is* the user's picture, so it must not be flagged — only
    the linear source run it came from keeps the marker."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="exp_src")
    client.put(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe", json=STRETCH)

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": STRETCH, "output_name": "exp_done"})
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "exp_done")
    assert edited["unexported_edit"] is False


# ---- "finish the edit I already saved" -------------------------------------

def test_export_without_a_recipe_uses_the_saved_one(client, solved_library):
    """The Target page's one-click finish sends no recipe — the server reads the
    run's stored one, so the browser never round-trips an edit it isn't editing."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="saved_src")
    client.put(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe", json=STRETCH)

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"output_name": "finished"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    finished = next(x for x in runs if x["output_basename"] == "finished")
    assert finished["has_fits"] and finished["notes"] == "edited"
    assert finished["unexported_edit"] is False
    # Non-destructive, as every editor export is: the source run is still there.
    assert any(x["id"] == rid for x in runs)


def test_export_without_a_recipe_and_nothing_saved_is_a_clean_400(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="nothing_saved")
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"output_name": "nope"})
    assert r.status_code == 400
    assert "no saved edit" in r.json()["detail"]


def test_re_editing_an_export_and_saving_flags_the_exported_run(client, solved_library):
    """End to end: export, then edit the export and press Save without exporting
    again. The exported run's preview is the *first* edit, so the second one is
    invisible and has to be flagged — the case the display-space marker would have
    swallowed."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="round1_src")
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": STRETCH, "output_name": "round1"})
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"
    exported = next(x for x in client.get(f"/api/targets/{safe}/stack-runs").json()
                    if x["output_basename"] == "round1")
    assert exported["unexported_edit"] is False   # nothing saved on it yet

    client.put(f"/api/targets/{safe}/stack-runs/{exported['id']}/editor/recipe",
               json={"ops": [{"id": "tone.saturation", "params": {"amount": 1.3}}]})

    again = next(x for x in client.get(f"/api/targets/{safe}/stack-runs").json()
                 if x["id"] == exported["id"])
    assert again["unexported_edit"] is True
