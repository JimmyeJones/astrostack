"""The share caption, the baked nameplate and the Sky map date a run by the
observer's own night even when Settings has no location.

Every other night surface (the Nights card, the frames table, the calendar, the
Gallery) resolves the longitude through ``webapp.site_location.resolve_site_lon``
— Settings, else the subs' own ``SITELONG``. The share/print exports and the
direct JPEG download handed the raw ``Settings.site_lon`` to the job instead, so
on an install with no Settings location they fell back to UTC noon-to-noon and
baked a different date range into a shared picture than the app shows.

The shape: three sessions at longitude −120° (local 22:00 → 04:50, i.e. 06:00 →
12:50 UTC). The last one ends *after* UTC noon, so UTC bucketing calls it a
fourth night (20–23 Jul) while the observer's own nights are 20–22 Jul.
"""

from __future__ import annotations

import pytest
from astropy.io import fits

from seestack.io.library import Library
from webapp import pipeline, site_location

from .test_editor import _make_run, _wait_job

LON = -120.0
START = "2026-07-21T06:00:00Z"
END = "2026-07-23T12:50:00Z"


@pytest.fixture
def frames_carry_a_site(monkeypatch):
    """No Settings location; the subs' header says −120°."""
    monkeypatch.setattr(site_location, "detect_site_from_library",
                        lambda lib, **k: (35.0, LON))


@pytest.fixture
def plates(monkeypatch):
    """Every ``NameplateFields`` a route builds, as ``(date, date_end)``."""
    seen: list[tuple[str | None, str | None]] = []
    real = pipeline._nameplate_fields

    def spy(*a, **k):
        fields = real(*a, **k)
        seen.append((fields.date_iso, fields.date_end_iso))
        return fields

    monkeypatch.setattr(pipeline, "_nameplate_fields", spy)
    return seen


def _run(solved_library, safe, **kw):
    return _make_run(solved_library, safe, capture_start_utc=START,
                     capture_end_utc=END, **kw)


def test_the_utc_fallback_really_differs_for_this_shape():
    """Guard on the fixture itself: without a longitude the window is a night
    longer, so the tests below can only pass by using the subs' site."""
    from webapp.capture_nights import capture_night_range

    assert capture_night_range(START, END, None) == ("2026-07-20", "2026-07-23")
    assert capture_night_range(START, END, LON) == ("2026-07-20", "2026-07-22")


def test_the_share_caption_and_nameplate_use_the_subs_longitude(
        client, solved_library, frames_carry_a_site, plates):
    assert client.get("/api/settings").json()["site_lon"] is None
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _run(solved_library, safe)

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/share",
                    json={"recipe": {"ops": []}, "nameplate": True})
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    blurb = job["result"]["blurb"]
    assert "20–22 Jul 2026" in blurb, blurb
    assert plates == [("2026-07-20", "2026-07-22")]


def test_the_print_nameplate_uses_the_subs_longitude(
        client, solved_library, frames_carry_a_site, plates):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # 1200x800 prints 6x4 sharply.
    rid = _run(solved_library, safe, basename="printed", h=800, w=1200)

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/print",
                    json={"recipe": {"ops": []}, "nameplate": True})
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert plates == [("2026-07-20", "2026-07-22")]


def test_the_jpeg_download_nameplate_uses_the_subs_longitude(
        client, solved_library, frames_carry_a_site, plates):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _run(solved_library, safe, basename="downloaded", with_preview=True)

    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/jpeg?nameplate=true")
    assert r.status_code == 200
    assert plates == [("2026-07-20", "2026-07-22")]


def test_the_sky_map_tile_uses_the_subs_longitude(
        client, solved_library, frames_carry_a_site):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _run(solved_library, safe, basename="sky", with_preview=True)
    # The map only places a target that has a position and a picture it can size.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            fp = next(r for r in proj.iter_stack_runs() if r.id == rid).fits_path
        finally:
            proj.close()
        with fits.open(fp, mode="update") as hdul:
            hdr = hdul[0].header
            hdr.update(CTYPE1="RA---TAN", CTYPE2="DEC--TAN", CRVAL1=83.8,
                       CRVAL2=-5.4, CRPIX1=50.0, CRPIX2=40.0,
                       CDELT1=-0.001, CDELT2=0.001)
        lib._conn.execute("UPDATE targets SET ra_deg = 83.8, dec_deg = -5.4 "
                          "WHERE safe_name = ?", (safe,))
        lib._conn.commit()
    finally:
        lib.close()

    img = next(i for i in client.get("/api/sky").json()["images"]
               if i["run_id"] == rid)
    assert (img["capture_night_start"], img["capture_night_end"]) == (
        "2026-07-20", "2026-07-22")


def test_a_settings_location_still_wins(client, solved_library, frames_carry_a_site):
    """Settings is the explicit answer; the header sniff only fills a blank.
    At +0° the UTC bucketing is the observer's own, so the fourth night returns."""
    assert client.put("/api/settings",
                      json={"site_lat": 51.5, "site_lon": 0.0}).status_code == 200
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _run(solved_library, safe)

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/share",
                    json={"recipe": {"ops": []}})
    blurb = _wait_job(client, r.json()["job_id"])["result"]["blurb"]
    assert "20–23 Jul 2026" in blurb, blurb
