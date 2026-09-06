""""Does my camera have broken pixels?" — the master defect census endpoint.

The engine has been able to repair hot/dead photosites since
``repair_sensor_defects`` shipped, but the switch lives in the Stack form's
*advanced* group, so nothing ever told a beginner either that their sensor has
broken pixels or that there is a one-switch fix. These tests pin what the
Calibration page is now told, and — just as importantly — what it is *not*: a
clean sensor gets no line, a flat is never censused, and one unreadable master
never takes the page down.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from webapp import calibration


def _synthetic_dark(h: int = 120, w: int = 160, seed: int = 7) -> np.ndarray:
    """A believable master dark: bias pedestal + corner amp glow + read noise.

    Deliberately the same scene as ``tests/test_defect_map.py`` — the endpoint
    must report the engine's own number, so they should be looking at the same
    sensor."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    dark = 500.0 + 60.0 * np.exp(-((yy - h) ** 2 + xx ** 2) / (2 * 40.0 ** 2))
    dark += rng.normal(0.0, 3.0, dark.shape)
    return dark.astype(np.float32)


def _register(root, kind, array, name=None):
    from seestack.calibrate.masters import MasterMeta

    h, w = array.shape
    return calibration.register_master(
        root, name=name or f"{kind} master",
        array=array,
        meta=MasterMeta(kind, 20, w, h, "median", exposure_s=30.0, gain=80.0,
                        bayer_pattern="RGGB"))


def _library_root(data_root: Path) -> Path:
    """Where the ``client`` fixture's app keeps its masters."""
    return data_root / "library"


def _rows(client):
    r = client.get("/api/calibration/defects")
    assert r.status_code == 200
    return {m["id"]: m for m in r.json()["masters"]}


# ---- the note itself (pure) ----------------------------------------------


def test_a_clean_sensor_gets_no_note_at_all():
    """Bias to silence: "0 broken pixels" invites no action and is one more line
    on a page the owner already calls busy."""
    assert calibration.defect_note(
        {"n_defects": 0, "n_pixels": 1000, "fraction": 0.0,
         "refused": False, "measurable": True}) is None


def test_a_master_that_could_not_be_measured_says_nothing():
    assert calibration.defect_note(None) is None
    assert calibration.defect_note({"measurable": False, "n_defects": 5}) is None
    # Tolerant of a shape it never emits rather than raising on one.
    assert calibration.defect_note("not a dict") is None  # type: ignore[arg-type]


def test_the_note_names_the_count_and_the_switch_that_fixes_it():
    note = calibration.defect_note(
        {"n_defects": 1204, "n_pixels": 2_073_600, "fraction": 1204 / 2_073_600,
         "refused": False, "measurable": True})
    assert note is not None and note["severity"] == "ok"
    # Grouped, because "1204" in a sentence about pixels reads as a coordinate.
    assert "1,204" in note["message"]
    # The whole point of the feature: name the one switch, in the words the
    # Stack form's own label uses, so a beginner can find it.
    assert "Repair hot/dead pixels from the dark" in note["detail"]


def test_a_refused_map_warns_and_explains_why_no_repair_will_happen():
    note = calibration.defect_note(
        {"n_defects": 960, "n_pixels": 19_200, "fraction": 0.05,
         "refused": True, "measurable": True})
    assert note is not None and note["severity"] == "warn"
    assert "5.00%" in note["detail"]
    # It must not read as an instruction to switch the repair on — the repair is
    # exactly what will *not* run here.
    assert "Repair hot/dead pixels" not in note["message"]


# ---- master_defect_census (the measurement) -------------------------------


def test_the_census_reads_a_real_master_file(tmp_path):
    from seestack.calibrate.masters import MasterMeta, save_master

    dark = _synthetic_dark()
    dark[30, 30] += 900.0
    dark[31, 33] += 900.0
    path = tmp_path / "dark.fits"
    save_master(path, dark, MasterMeta("dark", 20, 160, 120, "median"))

    census = calibration.master_defect_census(path)

    assert census is not None
    assert census["n_defects"] == 2
    assert census["n_pixels"] == dark.size
    assert census["measurable"] and not census["refused"]


def test_an_unreadable_master_censuses_to_none_rather_than_raising(tmp_path):
    missing = tmp_path / "gone.fits"
    assert calibration.master_defect_census(missing) is None
    junk = tmp_path / "junk.fits"
    junk.write_bytes(b"not a FITS file at all")
    assert calibration.master_defect_census(junk) is None


# ---- the endpoint ---------------------------------------------------------


def test_a_dark_with_broken_photosites_is_reported_with_its_note(client, data_root):
    root = _library_root(data_root)
    dark = _synthetic_dark()
    for y, x in ((10, 20), (11, 21), (55, 90)):
        dark[y, x] += 900.0
    entry = _register(root, "dark", dark)

    row = _rows(client)[entry["id"]]

    assert row["n_defects"] == 3
    assert row["note"]["severity"] == "ok"
    assert "3 hot or dead pixels" in row["note"]["message"]


def test_a_clean_dark_is_listed_but_carries_no_note(client, data_root):
    """The row exists (so a caller can tell "measured" from "not measured"), and
    the page renders nothing for it."""
    entry = _register(_library_root(data_root), "dark", _synthetic_dark())

    row = _rows(client)[entry["id"]]

    assert row["measurable"] and row["n_defects"] == 0
    assert row["note"] is None


def test_a_flat_is_never_censused(client, data_root):
    """A flat is a multiplicative field — its outliers are dust, not broken
    photosites — and no defect map is ever derived from one."""
    root = _library_root(data_root)
    flat = np.full((120, 160), 1000.0, dtype=np.float32)
    flat[40, 40] = 100_000.0
    flat_entry = _register(root, "flat", flat)
    bias_entry = _register(root, "bias", _synthetic_dark())

    rows = _rows(client)

    assert flat_entry["id"] not in rows
    # The bias *is* censused: it is the pedestal master a no-dark workflow uses.
    assert bias_entry["id"] in rows


def test_a_master_whose_file_vanished_is_absent_not_a_500(client, data_root):
    root = _library_root(data_root)
    entry = _register(root, "dark", _synthetic_dark())
    (calibration.calibration_dir(root) / entry["filename"]).unlink()

    r = client.get("/api/calibration/defects")

    assert r.status_code == 200
    assert entry["id"] not in {m["id"] for m in r.json()["masters"]}


def test_an_empty_library_answers_with_an_empty_list(client, data_root):
    # Still exact, so a stray field can't creep into this response unnoticed —
    # ``repair`` is the offer beside the census, and with no master at all there
    # is nothing to repair and nothing to offer.
    assert client.get("/api/calibration/defects").json() == {
        "masters": [], "repair": None}


def test_the_census_is_computed_once_per_master_file(client, data_root, monkeypatch):
    """Reading a master means loading its FITS and running four median filters,
    so a 60 s poll must not pay for it every time. A master file never changes
    once written, so the cache is keyed on the file's own identity."""
    entry = _register(_library_root(data_root), "dark", _synthetic_dark())
    calls = []
    real = calibration.master_defect_census

    def counting(path):
        calls.append(str(path))
        return real(path)

    monkeypatch.setattr(calibration, "master_defect_census", counting)

    assert entry["id"] in _rows(client)
    assert entry["id"] in _rows(client)
    assert len(calls) == 1, f"censused {len(calls)} times, expected 1: {calls}"


def test_a_rebuilt_master_is_censused_again(client, data_root):
    """The cache is keyed on (path, mtime, size), not on the id — so a master
    written afresh at the same path is measured again rather than serving the
    old sensor's answer. (Registered builds take a new id, but nothing in the
    key relies on that.)"""
    root = _library_root(data_root)
    entry = _register(root, "dark", _synthetic_dark())
    assert _rows(client)[entry["id"]]["n_defects"] == 0

    from seestack.calibrate.masters import MasterMeta, save_master

    dark = _synthetic_dark()
    dark[30, 30] += 900.0
    save_master(calibration.calibration_dir(root) / entry["filename"], dark,
                MasterMeta("dark", 20, 160, 120, "median"))

    assert _rows(client)[entry["id"]]["n_defects"] == 1


def test_the_number_shown_is_the_number_a_run_would_repair(client, data_root):
    """The endpoint and the stack must not describe two different sensors: the
    census is asserted against the engine's own map, built the way a run builds
    it (sanitized master + the no-data ``exclude``), not against a restatement
    of the threshold."""
    pytest.importorskip("astropy")
    from seestack.calibrate.apply import CalibrationMasters

    root = _library_root(data_root)
    dark = _synthetic_dark()
    dark[30, 30] += 900.0
    dark[31, 33] += 900.0
    dark[70:74, 70:74] = np.nan  # a no-data patch, where the two paths could differ
    entry = _register(root, "dark", dark)

    row = _rows(client)[entry["id"]]
    masters = CalibrationMasters.load(
        str(calibration.calibration_dir(root) / entry["filename"]),
        repair_sensor_defects=True)

    assert row["n_defects"] == masters.n_sensor_defects == 2


# ---- the one-click repair (the action beside the measurement) --------------
#
# The census names the switch; naming is not reaching. ``repair_sensor_defects``
# is a checkbox in the Stack form's *advanced* group, so acting on the sentence
# means finding a named setting inside a collapsed disclosure — once per stack,
# and never at all on the hands-off path, which stacks from
# ``default_stack_options`` and sees no form. These pin the button that closes
# that gap, and the silences that keep it honest.


def _offer(client):
    r = client.get("/api/calibration/defects")
    assert r.status_code == 200
    return r.json()["repair"]


def test_nothing_repairable_offers_no_button():
    """A clean sensor has nothing to turn on, so the whole control is absent —
    the same silence ``defect_note`` keeps for the same reason."""
    assert calibration.defect_repair_offer([], enabled=False) is None
    assert calibration.defect_repair_offer(
        [{"measurable": True, "n_defects": 0, "refused": False}],
        enabled=False) is None
    # Unmeasurable, and a non-dict from a hand-edited payload, both read as
    # "nothing to say" rather than raising.
    assert calibration.defect_repair_offer(
        [{"measurable": False, "n_defects": 9, "refused": False}],
        enabled=False) is None
    assert calibration.defect_repair_offer([None, "junk"], enabled=False) is None  # type: ignore[list-item]


def test_a_refused_map_never_offers_the_repair():
    """The one case where turning the switch on would provably do nothing: the
    ceiling refused that master's map, so the run repairs no pixel. Offering the
    button there would be the same untruth the refusal warning exists to
    prevent."""
    assert calibration.defect_repair_offer(
        [{"measurable": True, "n_defects": 50_000, "refused": True}],
        enabled=False) is None
    # ...but a repairable master beside a refused one still gets the offer.
    offer = calibration.defect_repair_offer(
        [{"measurable": True, "n_defects": 50_000, "refused": True},
         {"measurable": True, "n_defects": 12, "refused": False}],
        enabled=False)
    assert offer is not None and offer["state"] == "off"


def test_the_offer_says_it_reaches_the_hands_off_path_and_quotes_no_count():
    offer = calibration.defect_repair_offer(
        [{"measurable": True, "n_defects": 1204, "refused": False}],
        enabled=False)

    assert offer["state"] == "off"
    assert offer["action"] == "Repair them"
    # Names the Stack form's own switch, so the two surfaces can't drift.
    assert "Repair hot/dead pixels from the dark" in offer["detail"]
    # The whole point of writing a *default* rather than ticking a form.
    assert "hands-off" in offer["detail"]
    # No count: which master a run derives its map from depends on what is bound
    # at stack time, so any single total here would be wrong half the time. The
    # per-master rows carry the measured numbers.
    assert "1,204" not in offer["message"] and "1,204" not in offer["detail"]


def test_when_it_is_already_on_the_offer_turns_into_the_way_back_off():
    offer = calibration.defect_repair_offer(
        [{"measurable": True, "n_defects": 12, "refused": False}], enabled=True)

    assert offer["state"] == "on" and offer["action"] == "Turn off"
    # It must not claim to have improved a picture that already exists.
    assert "re-stack" in offer["detail"].lower()


def test_the_button_writes_the_switch_into_the_global_stack_defaults(
        client, data_root):
    """The click's whole value: the option lands where *both* the Stack form's
    seed and the unattended auto-stack chain read it, not in a form."""
    root = _library_root(data_root)
    dark = _synthetic_dark()
    dark[10, 20] += 900.0
    _register(root, "dark", dark)

    assert _offer(client)["state"] == "off"

    r = client.post("/api/calibration/defects/repair", json={"enabled": True})
    assert r.status_code == 200 and r.json() == {"enabled": True}

    settings = client.get("/api/settings").json()
    assert settings["default_stack_options"]["repair_sensor_defects"] is True
    # And the page it was clicked from now shows the on state.
    assert _offer(client)["state"] == "on"


def test_turning_it_off_again_leaves_no_residue(client, data_root):
    """Exactly reversible (AGENTS.md §9/§10): the key is removed rather than
    stored as ``False``, so an on-then-off round trip leaves the options blob
    byte-for-byte as it was — and every other default the user set survives."""
    root = _library_root(data_root)
    dark = _synthetic_dark()
    dark[10, 20] += 900.0
    _register(root, "dark", dark)
    client.put("/api/settings", json={"default_stack_options": {"drizzle": True}})
    before = client.get("/api/settings").json()["default_stack_options"]

    client.post("/api/calibration/defects/repair", json={"enabled": True})
    mid = client.get("/api/settings").json()["default_stack_options"]
    assert mid["drizzle"] is True and mid["repair_sensor_defects"] is True

    r = client.post("/api/calibration/defects/repair", json={"enabled": False})
    assert r.status_code == 200 and r.json() == {"enabled": False}
    after = client.get("/api/settings").json()["default_stack_options"]
    assert after == before
    assert _offer(client)["state"] == "off"


def test_an_empty_body_means_turn_it_on(client, data_root):
    """The button's ordinary call. Posting nothing must not 422 or turn it off."""
    root = _library_root(data_root)
    dark = _synthetic_dark()
    dark[10, 20] += 900.0
    _register(root, "dark", dark)

    r = client.post("/api/calibration/defects/repair")

    assert r.status_code == 200 and r.json() == {"enabled": True}
    assert client.get("/api/settings").json()[
        "default_stack_options"]["repair_sensor_defects"] is True


def test_a_library_with_no_repairable_master_offers_nothing(client, data_root):
    """End to end: a clean sensor's page carries no button at all."""
    _register(_library_root(data_root), "dark", _synthetic_dark())

    assert _offer(client) is None


def test_the_switch_reaches_the_stack_form_a_target_would_be_stacked_with(
        built_library, client, data_root):
    """Not "a setting was stored" but "a stack would use it": asserted through
    ``GET .../stack-defaults``, the endpoint that seeds the Stack form and reads
    the same global blob the unattended chain merges. A rename on either side
    would strand the button, and this is what catches it."""
    root = _library_root(data_root)
    dark = _synthetic_dark()
    dark[10, 20] += 900.0
    _register(root, "dark", dark)
    safe = client.get("/api/targets").json()[0]["safe_name"]

    before = client.get(f"/api/targets/{safe}/stack-defaults").json()
    assert before["repair_sensor_defects"] is False

    client.post("/api/calibration/defects/repair", json={"enabled": True})

    after = client.get(f"/api/targets/{safe}/stack-defaults").json()
    assert after["repair_sensor_defects"] is True


def test_a_target_that_saved_its_own_defaults_is_named_not_glossed_over(
        built_library, client, data_root):
    """The honesty guard on the on-state's sentence. A target saved before this
    option was switched on carries an explicit ``false`` in its blob — and a
    target's own blob wins over the global one in both readers. Claiming "every
    stack" there would be exactly the confident untruth the census's silences
    exist to avoid.

    The pinned-off blob is written the way an *older version* wrote it — a full
    snapshot of the Stack form (v0.374.0 stores only what the user changed, so
    saving a ``false`` that already matches the global switch pins nothing, and
    the target correctly follows a later flip). That is the shape a live install
    upgraded in place actually carries, which is the case this sentence has to
    stay honest about."""
    import json as _json

    from seestack.io.library import Library
    from webapp.schemas import STACK_DEFAULTS_META_KEY

    root = _library_root(data_root)
    dark = _synthetic_dark()
    dark[10, 20] += 900.0
    _register(root, "dark", dark)
    safes = [t["safe_name"] for t in client.get("/api/targets").json()]
    assert len(safes) >= 2, "fixture should give more than one target"
    # One target pins it off (an older version's whole-form snapshot), one pins
    # it on, and any remaining target saved nothing at all.
    lib = Library.open_or_create(_library_root(Path(data_root)))
    try:
        proj = lib.open_target(safes[0])
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY,
                          _json.dumps({"repair_sensor_defects": False,
                                       "sigma_kappa": 3.0}))
        finally:
            proj.close()
    finally:
        lib.close()
    client.put(f"/api/targets/{safes[1]}/stack-defaults",
               json={"repair_sensor_defects": True})

    # With the switch off nothing is claimed, so nothing is counted or said.
    assert "except" not in _offer(client)["message"]

    client.post("/api/calibration/defects/repair", json={"enabled": True})
    offer = _offer(client)

    assert offer["state"] == "on"
    # Exactly one: the pinned-on target and the never-saved ones follow the
    # global switch and are not exceptions to it.
    assert "except 1 target" in offer["message"]
    assert "Save as defaults" in offer["detail"]
    # And it says what to do about it rather than only that it happened.
    assert "Repair hot/dead pixels from the dark" in offer["detail"]


def test_the_override_count_is_only_paid_for_when_it_changes_a_sentence(
        built_library, client, data_root, monkeypatch):
    """A per-target walk on a 60 s poll has to earn itself: with the switch off,
    or with nothing repairable, the count changes no wording, so it is never
    asked for."""
    from webapp.routers import calibration as router

    calls = {"n": 0}
    real = router._targets_overriding_defect_repair

    def counted(request):
        calls["n"] += 1
        return real(request)

    monkeypatch.setattr(router, "_targets_overriding_defect_repair", counted)

    # A clean sensor: no offer at all, so no walk even once it is switched on.
    _register(_library_root(data_root), "dark", _synthetic_dark(), name="clean")
    client.post("/api/calibration/defects/repair", json={"enabled": True})
    client.get("/api/calibration/defects")
    assert calls["n"] == 0

    # Switch it back off with a repairable master present: still nothing to say.
    dark = _synthetic_dark(seed=11)
    dark[10, 20] += 900.0
    _register(_library_root(data_root), "dark", dark, name="broken")
    client.post("/api/calibration/defects/repair", json={"enabled": False})
    client.get("/api/calibration/defects")
    assert calls["n"] == 0

    # Both true: now the sentence depends on it.
    client.post("/api/calibration/defects/repair", json={"enabled": True})
    client.get("/api/calibration/defects")
    assert calls["n"] == 1


def test_the_plural_and_the_no_exception_wording_both_hold():
    rows = [{"measurable": True, "n_defects": 12, "refused": False}]

    assert "except" not in calibration.defect_repair_offer(
        rows, enabled=True, n_overridden=0)["message"]
    assert "except 1 target" in calibration.defect_repair_offer(
        rows, enabled=True, n_overridden=1)["message"]
    assert "except 4 targets" in calibration.defect_repair_offer(
        rows, enabled=True, n_overridden=4)["message"]
    # A nonsense count degrades to "no exceptions" rather than a negative one.
    assert "except" not in calibration.defect_repair_offer(
        rows, enabled=True, n_overridden=-3)["message"]
    # It is only ever an on-state qualifier; the off-state is about turning it on.
    assert "except" not in calibration.defect_repair_offer(
        rows, enabled=False, n_overridden=9)["message"]
