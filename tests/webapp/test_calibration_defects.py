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
    assert client.get("/api/calibration/defects").json() == {"masters": []}


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
