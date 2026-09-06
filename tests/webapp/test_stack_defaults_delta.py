"""*Save as defaults* stores what you changed, not a snapshot of the form.

The Stack form seeds itself from every descriptor key and posts all of them
back, so storing the post verbatim pinned a value for every option that existed
on the day Save was pressed — including a string of ``false``\\ s for checkboxes
nobody opened. The blob then beats ``default_stack_options`` in *both* readers
(the form's own seed and ``pipeline._stack_target(auto=True)``), so a switch the
owner later flips globally never reached that target again.

These pin :func:`webapp.walkaway.stack_defaults_delta` (pure) and the endpoint
that uses it, including the two properties that decide whether this is safe:
an **existing** full-snapshot blob still wins byte-for-byte (§9 — nothing is
migrated), and a key whose *presence* is itself the decision is stored even when
it matches the default, so the unattended chain never starts choosing a
rejection method for a user who did.
"""

from __future__ import annotations

import json

from seestack.io.library import Library
from webapp.schemas import STACK_DEFAULTS_META_KEY
from webapp.walkaway import stack_defaults_delta

# What a target with no saved blob would be stacked with: the global blob filled
# out with each descriptor's own default.
UNSAVED = {"sigma_clip": True, "sigma_kappa": 3.0, "mosaic_canvas": "auto",
           "drizzle": False, "quick_look_interval": 0}


# --------------------------------------------------------------------------
# The pure helper
# --------------------------------------------------------------------------

def test_an_untouched_value_is_not_stored():
    # The whole point: posting the form back unchanged pins nothing.
    assert stack_defaults_delta(dict(UNSAVED), UNSAVED) == {}


def test_a_changed_value_is_stored():
    posted = {**UNSAVED, "sigma_kappa": 2.5}
    assert stack_defaults_delta(posted, UNSAVED) == {"sigma_kappa": 2.5}


def test_an_int_that_json_round_tripped_a_float_is_not_a_change():
    # The form posts 3 where the descriptor default is 3.0 — the same stack, so
    # it must not become a pin. Shared with pinned_stack_options, which already
    # takes the same view of the same pair.
    assert stack_defaults_delta({"sigma_kappa": 3}, UNSAVED) == {}


def test_a_checkbox_is_never_the_same_as_a_number():
    # False == 0 in Python; a bool is only ever the same as a bool, so an old
    # blob's 0 under a now-boolean field reads as a real difference and is kept
    # rather than silently dropped.
    assert stack_defaults_delta({"drizzle": 0}, UNSAVED) == {"drizzle": 0}


def test_a_key_the_baseline_does_not_know_is_kept():
    # A calibration-master pick, or an option from a newer version: with nothing
    # to compare against, remember what was posted.
    assert stack_defaults_delta({"future_option": 7}, UNSAVED) == {"future_option": 7}


def test_a_presence_is_the_decision_key_is_kept_even_when_it_matches():
    # sigma_clip's own engine default is True, so dropping a saved
    # ``sigma_clip: true`` would hand the unattended chain a target that "never
    # chose" and let it pick the method instead — the behaviour
    # auto_reject_on_unattended (v0.337.0) deliberately made opt-in.
    assert stack_defaults_delta({"sigma_clip": True}, UNSAVED) == {}
    assert stack_defaults_delta({"sigma_clip": True}, UNSAVED,
                                always_persist=("sigma_clip",)) == {"sigma_clip": True}


def test_the_delta_never_invents_a_value():
    # Only ever a subset of what was posted, with the posted values verbatim.
    posted = {"sigma_kappa": 2.5, "drizzle": True, "mosaic_canvas": "auto"}
    got = stack_defaults_delta(posted, UNSAVED)
    assert set(got) <= set(posted)
    assert all(got[k] == posted[k] for k in got)


# --------------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------------

def _put_form(client, safe, **overrides):
    """Save the Stack form the way the frontend does — every key it was seeded
    with, posted back, with ``overrides`` applied on top."""
    seed = client.get(f"/api/targets/{safe}/stack-defaults").json()
    seed.update(overrides)
    r = client.put(f"/api/targets/{safe}/stack-defaults", json=seed)
    assert r.status_code == 200, r.text
    return r.json()


def _stored_blob(library_root, safe):
    lib = Library.open_or_create(library_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            raw = proj.get_meta(STACK_DEFAULTS_META_KEY)
        finally:
            proj.close()
    finally:
        lib.close()
    return json.loads(raw) if raw else None


def test_saving_the_form_unchanged_pins_only_the_rejection_choice(
        client, built_library):
    _put_form(client, "M_42")
    stored = _stored_blob(built_library, "M_42")
    # Not a snapshot of ~30 options: only the keys whose presence is itself the
    # decision survive an otherwise untouched save.
    assert set(stored) <= {"auto_reject", "sigma_clip", "min_max_reject",
                           "drizzle_reject"}


def test_a_later_global_change_reaches_a_target_that_saved_defaults(
        client, built_library):
    # The bug, end to end. Save the form untouched, then flip an option
    # *globally* — before this fix the target carried its own July copy of every
    # key and the global value never arrived.
    _put_form(client, "M_42")
    r = client.put("/api/settings",
                   json={"default_stack_options": {"sigma_kappa": 2.25}})
    assert r.status_code == 200
    assert client.get("/api/targets/M_42/stack-defaults").json()["sigma_kappa"] == 2.25


def test_what_the_user_actually_changed_still_wins_over_the_global(
        client, built_library):
    # The other half: a deliberate choice is still a pin, and a later global
    # change must NOT overwrite it.
    _put_form(client, "M_42", sigma_kappa=2.5)
    assert _stored_blob(built_library, "M_42")["sigma_kappa"] == 2.5
    client.put("/api/settings", json={"default_stack_options": {"sigma_kappa": 2.25}})
    assert client.get("/api/targets/M_42/stack-defaults").json()["sigma_kappa"] == 2.5
    # ...and the note that names what a target is holding back agrees, with the
    # user's own number in it. (``auto_reject`` rides along: the form seeded it
    # on for a never-configured target and the save kept it, so once a global
    # blob exists the target really is holding it — which is what the note says.)
    pinned = {p["key"]: (p["saved"], p["global_value"])
              for p in client.get(
                  "/api/targets/M_42/stack-defaults/pinned").json()["pinned"]}
    assert pinned["sigma_kappa"] == (2.5, 2.25)


def test_an_existing_full_snapshot_blob_is_left_alone(client, built_library):
    # §9: nothing is migrated. A blob written by an older version keeps every key
    # it has and keeps winning until the owner saves that form again.
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY,
                          json.dumps({"sigma_kappa": 2.75, "mosaic_canvas": "reference"}))
        finally:
            proj.close()
    finally:
        lib.close()
    client.put("/api/settings", json={"default_stack_options": {"sigma_kappa": 2.25}})
    seeded = client.get("/api/targets/M_42/stack-defaults").json()
    assert seeded["sigma_kappa"] == 2.75
    assert seeded["mosaic_canvas"] == "reference"
    assert _stored_blob(built_library, "M_42") == {"sigma_kappa": 2.75,
                                                   "mosaic_canvas": "reference"}


def test_a_saved_rejection_method_survives_a_form_save(client, built_library):
    # A user who ticked sigma-clip (the engine's own default value) must still
    # read as having chosen it, or the unattended chain would start picking the
    # method for them without auto_reject_on_unattended being on.
    _put_form(client, "M_42", sigma_clip=True, auto_reject=False,
              min_max_reject=False)
    stored = _stored_blob(built_library, "M_42")
    assert stored["sigma_clip"] is True
    assert client.get("/api/targets/M_42/rejection-outlook").json()["user_chose"] is True


def test_the_calibration_master_picks_still_round_trip(client, built_library):
    # They have no global default to follow, so they are stored as posted.
    _put_form(client, "M_42", dark_master_id=7, flat_master_id="3")
    saved = client.get("/api/targets/M_42/stack-defaults").json()
    assert saved["dark_master_id"] == 7
    assert saved["flat_master_id"] == 3
