"""Tests for the 'Tonight' night-planner endpoint (``/api/plan/tonight``)."""

from __future__ import annotations

from pathlib import Path

from webapp.routers.plan import _parse_angle, _site_from_header

# A fixed winter evening in the northern hemisphere → a real dark window.
JAN_EVENING = "2026-01-15T20:00:00+00:00"


def test_parse_angle_handles_float_and_sexagesimal():
    assert _parse_angle(51.5) == 51.5
    assert _parse_angle("51.5") == 51.5
    assert abs(_parse_angle("51:30:00") - 51.5) < 1e-6
    assert abs(_parse_angle("-0:07:48") - (-0.13)) < 1e-3
    assert _parse_angle(None) is None
    assert _parse_angle("") is None
    assert _parse_angle("not-an-angle") is None


def test_site_from_header():
    assert _site_from_header({"SITELAT": 51.5, "SITELONG": -0.13}) == (51.5, -0.13)
    assert _site_from_header({"SITELAT": 51.5}) is None          # no longitude
    assert _site_from_header({"SITELAT": 999, "SITELONG": 0}) is None  # out of range


def test_tonight_without_location_prompts_for_one(client, solved_library):
    # Synth frames carry no SITELAT and no site is configured → the planner
    # can't run and asks the user to set a location, rather than 500-ing.
    r = client.get("/api/plan/tonight", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "none"
    assert body["observer"] is None
    assert body["dark_window"] is None
    assert body["targets"] == []


def test_tonight_with_settings_location(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/tonight", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "settings"
    assert body["observer"]["lat_deg"] == 51.5
    assert body["dark_window"] is not None
    assert body["dark_window"]["sun_alt_threshold_deg"] == -18.0
    assert 0.0 <= body["moon_illumination"] <= 1.0

    targets = body["targets"]
    assert targets, "expected a ranked target list"
    # Scores are sorted best-first.
    scores = [t["score"] for t in targets]
    assert scores == sorted(scores, reverse=True)
    # The library target M_42 (ra 83.6 / dec −5.4) is present, deduped from the
    # catalog's M42, and flagged as already targeted with its capture stats.
    already = [t for t in targets if t["already_targeted"]]
    assert any(t["target_safe"] == "M_42" for t in already)
    m42 = next(t for t in already if t["target_safe"] == "M_42")
    assert m42["frames_accepted"] >= 1
    # No *catalog* duplicate is emitted near a library target's position (the
    # fixture's two library targets happen to share M42's coords, so both of
    # those legitimately show — dedup only suppresses the bundled-catalog copy).
    near_m42 = [t for t in targets if abs(t["ra_deg"] - 83.6) < 1.0
                and abs(t["dec_deg"] - (-5.4)) < 1.0]
    assert near_m42 and all(t["already_targeted"] for t in near_m42)
    # The catalog fills in "not yet targeted" candidates too.
    assert any(not t["already_targeted"] for t in targets)


def test_tonight_min_alt_override_changes_usable_window(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    low = client.get("/api/plan/tonight", params={"when": JAN_EVENING, "min_alt": 10}).json()
    high = client.get("/api/plan/tonight", params={"when": JAN_EVENING, "min_alt": 60}).json()
    assert low["min_altitude_deg"] == 10
    assert high["min_altitude_deg"] == 60
    # A stricter altitude floor can only shrink each target's usable window.
    low_by_id = {t["id"]: t["minutes_above_min_alt"] for t in low["targets"]}
    for t in high["targets"]:
        if t["id"] in low_by_id:
            assert t["minutes_above_min_alt"] <= low_by_id[t["id"]] + 1e-6


def test_tonight_rejects_bad_when(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/tonight", params={"when": "not-a-timestamp"})
    assert r.status_code == 422


def test_tonight_detects_site_from_fits_header(tmp_path: Path, monkeypatch):
    """With no configured site, the planner sniffs SITELAT/SITELONG from a frame."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi.testclient import TestClient
    from synth import write_seestar_fits

    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize
    from webapp.main import create_app

    data_root = tmp_path / "data"
    incoming = data_root / "incoming" / "M_13"
    incoming.mkdir(parents=True)
    for i in range(2):
        write_seestar_fits(
            incoming / f"frame_{i:03d}.fit", add_wcs=True,
            ra_center_deg=250.4, dec_center_deg=36.5,
            site_lat=48.0, site_lon=11.0, seed=200 + i,
        )
    lib = Library.open_or_create(data_root / "library")
    try:
        scan_and_organize(lib, data_root / "incoming", copy_to_cache=False)
    finally:
        lib.close()

    monkeypatch.setenv("ASTROSTACK_DATA", str(data_root))
    app = create_app()
    with TestClient(app) as c:
        c.put("/api/settings", json={"watcher_enabled": False})
        body = c.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    assert body["location_source"] == "fits"
    assert abs(body["observer"]["lat_deg"] - 48.0) < 1e-6
    assert abs(body["observer"]["lon_deg"] - 11.0) < 1e-6
