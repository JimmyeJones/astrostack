"""A target's saved stack options that hold it away from the global defaults.

"Save as defaults" on the Stack form persists the **whole** form, so a target
saved months ago carries an explicit value for every option that existed that
day — including checkboxes nobody opened the advanced group to look at. Its blob
then wins over ``default_stack_options`` in both readers (the form's seed and
``pipeline._stack_target(auto=True)``), so a switch the owner later flips
globally silently never reaches that target.

These pin :func:`webapp.walkaway.pinned_stack_options` (pure) and
``GET /api/targets/{safe}/stack-defaults/pinned`` (the surface), including the
property that actually matters: what the endpoint reports and what
``GET .../stack-defaults`` would seed the form with never disagree.
"""

from __future__ import annotations

from webapp.walkaway import PinnedOption, pinned_stack_options

# (key, label, app_default) triples, the shape the router passes in.
FIELDS = [
    ("sigma_clip", "Sigma clip", False),
    ("sigma_kappa", "Kappa", 3.0),
    ("mosaic_canvas", "Canvas mode", "auto"),
    ("quick_look_interval", "Quick-look every N frames", 0),
]


# --------------------------------------------------------------------------
# The pure helper
# --------------------------------------------------------------------------

def test_nothing_saved_pins_nothing():
    assert pinned_stack_options({}, {"sigma_clip": True}, FIELDS) == []


def test_a_saved_value_that_agrees_with_the_global_is_not_a_pin():
    """The whole point of biasing toward silence: a target saved back when the
    global agreed with it is not overriding anything, and must not be named."""
    saved = {"sigma_clip": True, "sigma_kappa": 3.0}
    assert pinned_stack_options(saved, {"sigma_clip": True}, FIELDS) == []


def test_a_saved_false_pins_a_switch_the_owner_later_turned_on():
    """The reported mechanism, exactly: a target saved before the option was
    switched on carries ``false``, and that false wins for ever."""
    got = pinned_stack_options({"sigma_clip": False}, {"sigma_clip": True}, FIELDS)

    assert got == [PinnedOption(key="sigma_clip", label="Sigma clip",
                                saved=False, global_value=True)]


def test_a_global_that_never_mentions_the_key_falls_back_to_the_app_default():
    """``get_stack_defaults`` fills unmentioned keys from the descriptors, so the
    comparison has to as well — otherwise every saved option would read as a pin
    against ``None`` on an install that never set a global default."""
    # Saved matches the app default → silent, even with an empty global blob.
    assert pinned_stack_options({"sigma_kappa": 3.0}, {}, FIELDS) == []
    # Saved differs from the app default → named, with the app default quoted.
    got = pinned_stack_options({"sigma_kappa": 2.0}, {}, FIELDS)
    assert [(p.key, p.saved, p.global_value) for p in got] == [("sigma_kappa", 2.0, 3.0)]


def test_a_global_holding_an_explicit_none_falls_back_too():
    """``None`` in the stored global blob means "use the default" everywhere else
    in this app; it must not read as a value the target is pinned away from."""
    assert pinned_stack_options({"sigma_kappa": 3.0}, {"sigma_kappa": None}, FIELDS) == []


def test_a_saved_none_is_skipped_the_way_the_writer_skips_it():
    """``put_stack_defaults`` refuses to persist a ``None`` (a cleared numeric
    field), so a hand-edited blob carrying one is "no opinion", not a pin."""
    assert pinned_stack_options({"sigma_kappa": None}, {"sigma_kappa": 2.0}, FIELDS) == []


def test_an_int_and_a_float_of_the_same_number_are_the_same_stack():
    """A JSON round-trip can hand a float-typed field back as ``3`` — the same
    stack, and nagging about it would be a false positive."""
    assert pinned_stack_options({"sigma_kappa": 3}, {"sigma_kappa": 3.0}, FIELDS) == []


def test_a_bool_is_never_the_same_as_a_number():
    """``False == 0`` in Python. A blob whose key changed type between versions
    must not be silently glossed as agreeing — nor as a deliberate pin the user
    made, which is why the *checkbox* case (both bools) is what gets reported."""
    got = pinned_stack_options({"sigma_clip": False},
                               {"sigma_clip": 0}, FIELDS)
    assert [p.key for p in got] == ["sigma_clip"]
    # And the ordinary bool-vs-bool agreement is still silent.
    assert pinned_stack_options({"sigma_clip": True}, {"sigma_clip": True},
                               FIELDS) == []


def test_pins_are_reported_in_descriptor_order_not_dict_order():
    """The form reads top-down; a list in whatever order the JSON blob happened
    to serialise would be unreadable beside it."""
    saved = {"mosaic_canvas": "union", "sigma_clip": True}
    got = pinned_stack_options(saved, {}, FIELDS)

    assert [p.key for p in got] == ["sigma_clip", "mosaic_canvas"]


def test_a_key_with_no_descriptor_is_never_reported():
    """The saved blob also carries the calibration master picks, which are not
    stack options and have no label to show."""
    assert pinned_stack_options({"dark_master_id": 4}, {}, FIELDS) == []


# --------------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------------

def _pinned(client, safe: str) -> dict:
    r = client.get(f"/api/targets/{safe}/stack-defaults/pinned")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_target_that_never_saved_defaults_says_nothing(built_library, client):
    safe = client.get("/api/targets").json()[0]["safe_name"]

    body = _pinned(client, safe)

    assert body == {"has_saved": False, "pinned": []}


def test_the_reported_pin_is_what_the_stack_form_would_actually_be_seeded_with(
        built_library, client):
    """The property worth pinning: the report and the merge can't disagree. Save
    a target with the option off, then flip it on globally — the form still seeds
    ``False`` for that target, and *that* is what the endpoint names."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    client.put(f"/api/targets/{safe}/stack-defaults", json={"sigma_clip": False})
    client.put("/api/settings", json={"default_stack_options": {"sigma_clip": True}})

    body = _pinned(client, safe)
    seeded = client.get(f"/api/targets/{safe}/stack-defaults").json()

    assert body["has_saved"] is True
    assert len(body["pinned"]) == 1
    entry = body["pinned"][0]
    assert entry["key"] == "sigma_clip"
    assert entry["saved"] is False and entry["global_value"] is True
    # The form really is seeded with the pinned value, not the global one.
    assert seeded["sigma_clip"] is False
    assert entry["saved"] == seeded["sigma_clip"]
    # And it carries the descriptor's own label, so the sentence names the
    # control the user can see rather than the engine key.
    assert entry["label"] and entry["label"] != entry["key"]


def test_a_target_saved_while_the_global_agreed_stays_silent(built_library, client):
    """The false-positive guard: saving the whole form must not, on its own,
    produce a wall of "you are overriding N options"."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    seeded = client.get(f"/api/targets/{safe}/stack-defaults").json()
    # Save the form exactly as it was handed to us — the common case.
    assert client.put(f"/api/targets/{safe}/stack-defaults",
                      json=seeded).status_code == 200

    body = _pinned(client, safe)

    assert body["has_saved"] is True
    assert body["pinned"] == [], body["pinned"]


def test_one_targets_pin_never_leaks_onto_another(built_library, client):
    safes = [t["safe_name"] for t in client.get("/api/targets").json()]
    assert len(safes) >= 2
    client.put(f"/api/targets/{safes[0]}/stack-defaults", json={"sigma_clip": False})
    client.put("/api/settings", json={"default_stack_options": {"sigma_clip": True}})

    assert [p["key"] for p in _pinned(client, safes[0])["pinned"]] == ["sigma_clip"]
    assert _pinned(client, safes[1]) == {"has_saved": False, "pinned": []}


def test_the_endpoint_changes_nothing(built_library, client):
    """Read-only, asserted rather than asserted-in-a-docstring: neither the saved
    blob nor the global defaults move because somebody opened the page."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    client.put(f"/api/targets/{safe}/stack-defaults", json={"sigma_kappa": 2.0})
    before_saved = client.get(f"/api/targets/{safe}/stack-defaults").json()
    before_global = client.get("/api/settings").json()["default_stack_options"]

    _pinned(client, safe)

    assert client.get(f"/api/targets/{safe}/stack-defaults").json() == before_saved
    assert client.get("/api/settings").json()["default_stack_options"] == before_global


def test_a_malformed_saved_blob_degrades_to_silence(built_library, client, data_root):
    """Every reader of this meta row has to survive a legacy / hand-edited value;
    a new one must not be the exception that 500s the Stack page."""
    from seestack.io.library import Library
    from webapp.schemas import STACK_DEFAULTS_META_KEY

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY, "[1, 2, 3]")
        finally:
            proj.close()
    finally:
        lib.close()

    assert _pinned(client, safe) == {"has_saved": False, "pinned": []}
