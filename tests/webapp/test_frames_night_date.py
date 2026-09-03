"""A sub is dated by the *night* it belongs to, not by its raw UTC day.

Regression cover for the frames table saying something different from the picture
directly above it. ``GET /api/targets/{safe}/frames`` sent only ``timestamp_utc``
— the raw instant out of the FITS header — so the Target page printed a column of
subs stamped ``2024-09-12`` underneath a picture captioned "Shot 11 Sep 2024",
with nothing on screen saying the two were the same night. The gap widens west of
Greenwich, where a whole *evening* of subs carries tomorrow's UTC date.

The rows now carry ``night_date``, bucketed noon-to-noon through the very same
:func:`seestack.activity_calendar.night_date_of` the imaging calendar, the Nights
card and every "Shot …" caption already go through, and resolved against the same
observer longitude — so the two surfaces cannot name different nights.

The fixture subs carry ``DATE-OBS`` of ``2024-09-12T03:14:55`` (``tests/synth.py``):
3 a.m., i.e. the small hours of the night that *started* on the 11th. That is what
makes the two facts differ at all, and it is the owner's own shape — a Seestar
back catalogue shot through the night.
"""

from __future__ import annotations

from seestack.io.library import Library

#: The UTC day the fixture's stamp falls on …
FIXTURE_UTC_DAY = "2024-09-12"
#: … and the observing night it actually belongs to (see the module docstring).
FIXTURE_NIGHT = "2024-09-11"


def _frames(client, safe: str = "M_42") -> list[dict]:
    r = client.get(f"/api/targets/{safe}/frames")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, "fixture target has no frames"
    return rows


def test_a_sub_is_dated_by_its_night_not_its_utc_day(client, built_library):
    # The bug, stated as the two facts disagreeing: every fixture sub's raw stamp
    # says the 12th, and every one of them was shot on the night of the 11th.
    for f in _frames(client):
        assert f["timestamp_utc"].startswith(FIXTURE_UTC_DAY)
        assert f["night_date"] == FIXTURE_NIGHT


def test_a_subs_night_follows_the_observers_longitude(client, built_library):
    # Same instant, two observers. West of Greenwich the fixture stamp is the
    # previous evening; far enough east it is the *following* afternoon, and so
    # belongs to the next night. Whatever the frames table says, it has to be the
    # answer the rest of the app would give for the same sub.
    client.put("/api/settings", json={"site_lon": -105.0})
    assert all(f["night_date"] == "2024-09-11" for f in _frames(client))

    client.put("/api/settings", json={"site_lon": 150.0})
    assert all(f["night_date"] == "2024-09-12" for f in _frames(client))


def test_the_frames_table_and_the_nights_card_name_the_same_night(client, built_library):
    # The point of the fix is agreement, not a particular string: whatever night a
    # sub reports, the Nights card must have a row for it.
    client.put("/api/settings", json={"site_lon": -105.0})
    nights = client.get("/api/targets/M_42/nights")
    assert nights.status_code == 200, nights.text
    card = {n["night_date"] for n in nights.json()}
    assert card, "fixture target has no nights"
    for f in _frames(client):
        assert f["night_date"] in card


def test_a_sub_with_no_capture_stamp_claims_no_night(client, built_library):
    # An undatable sub must send `null` rather than guess — the frontend then
    # shows the row as it always did instead of inventing a night for it.
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            first = next(iter(proj.iter_frames()))
            proj.update_frame(first.id, timestamp_utc=None)
        finally:
            proj.close()
    finally:
        lib.close()

    rows = {f["id"]: f for f in _frames(client)}
    assert rows[first.id]["timestamp_utc"] is None
    assert rows[first.id]["night_date"] is None
    # …and its neighbours are unaffected.
    assert any(f["night_date"] == FIXTURE_NIGHT for f in rows.values())


def test_one_frame_read_or_graded_reports_the_same_night_as_the_list(client, built_library):
    # `GET /frames/{id}` and `PATCH /frames/{id}` return the same model, and the
    # Target page reads them for the selected row — so a sub must not change
    # nights depending on which endpoint fetched it.
    client.put("/api/settings", json={"site_lon": -105.0})
    listed = _frames(client)[0]

    one = client.get(f"/api/targets/M_42/frames/{listed['id']}")
    assert one.status_code == 200, one.text
    assert one.json()["night_date"] == listed["night_date"]

    patched = client.patch(
        f"/api/targets/M_42/frames/{listed['id']}", json={"accept": False})
    assert patched.status_code == 200, patched.text
    assert patched.json()["night_date"] == listed["night_date"]
