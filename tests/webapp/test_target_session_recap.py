"""GET /api/targets/{safe}/session-recap — the "Last night" summary card."""

from __future__ import annotations


def test_session_recap_for_a_built_target(client, built_library):
    targets = client.get("/api/targets").json()
    m42 = next(t for t in targets if t["safe_name"] == "M_42")
    r = client.get(f"/api/targets/{m42['safe_name']}/session-recap")
    assert r.status_code == 200
    recap = r.json()
    assert recap is not None
    # The synthetic library ingests 3 frames per target, all accepted.
    assert recap["n_frames"] == 3
    assert recap["n_kept"] == 3
    assert recap["n_set_aside"] == 0
    assert recap["reject_buckets"] == {}
    assert recap["kept_exposure_s"] > 0
    assert recap["total_kept_exposure_s"] == recap["kept_exposure_s"]
    assert recap["start_utc"] is not None and recap["end_utc"] is not None
    # A single-session synthetic target has no prior night to compare against.
    assert recap["quality_drift"] is None


def test_session_recap_surfaces_a_quality_drift_nudge(client, built_library):
    """A soft second night on top of a sharp first surfaces the FWHM drift note
    through the endpoint (serialised nested object, not just the engine dataclass)."""
    import datetime as dt

    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    targets = client.get("/api/targets").json()
    m42 = next(t for t in targets if t["safe_name"] == "M_42")
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target(m42["safe_name"])
        try:
            # A sharp prior night, then a soft newest night — enough measured subs
            # each, and both after the synthetic 2024 frames so soft is the newest.
            # tz-aware to match the ingested frames' stored UTC timestamps.
            sharp = dt.datetime(2025, 1, 1, 22, 0, 0, tzinfo=dt.timezone.utc)
            soft = dt.datetime(2025, 1, 8, 22, 0, 0, tzinfo=dt.timezone.utc)
            for i in range(6):
                proj.add_frame(FrameRow(source_path=f"/x/sharp{i}.fit",
                                        timestamp_utc=(sharp + dt.timedelta(seconds=30 * i)).isoformat(),
                                        exposure_s=10.0, fwhm_px=3.2))
            for i in range(6):
                proj.add_frame(FrameRow(source_path=f"/x/soft{i}.fit",
                                        timestamp_utc=(soft + dt.timedelta(seconds=30 * i)).isoformat(),
                                        exposure_s=10.0, fwhm_px=5.4))
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get(f"/api/targets/{m42['safe_name']}/session-recap")
    assert r.status_code == 200
    drift = r.json()["quality_drift"]
    assert drift is not None
    assert drift["kind"] == "fwhm"
    assert drift["latest_fwhm_px"] == 5.4
    assert drift["baseline_fwhm_px"] == 3.2


def test_session_recap_null_for_an_empty_target(client):
    # A freshly created target has no frames → nothing datable → null card.
    client.post("/api/targets", json={"name": "empty field"})
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["name"] == "empty field")
    r = client.get(f"/api/targets/{safe}/session-recap")
    assert r.status_code == 200
    assert r.json() is None


def test_session_recap_unknown_target_404(client):
    r = client.get("/api/targets/does_not_exist/session-recap")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Which night was it? — the recap names its observing night, like the Nights card
# ---------------------------------------------------------------------------

def _stamp(data_root, safe: str, per_frame: dict[int, dict]) -> None:
    """Stamp fields onto specific frames (by 0-based ordinal) of a target."""
    from seestack.io.library import Library

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            ids = [f.id for f in proj.iter_frames()]
            for ordinal, fields in per_frame.items():
                proj.update_frame(ids[ordinal], **fields)
        finally:
            proj.close()
    finally:
        lib.close()


def test_session_recap_carries_the_observing_night_date(
    client, solved_library, data_root
):
    """The recap card says *which night* it is recapping — bucketed noon-to-noon
    in the observer's local time, so a session that starts at 21:00 local in the
    Americas (already tomorrow in UTC) is named as the evening it really was."""
    client.put("/api/settings", json={"site_lon": -122.3})   # Seattle, UTC−8
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-09T05:00:00+00:00"},   # 8 Jul 21:00 local
        1: {"timestamp_utc": "2026-07-09T05:30:00+00:00"},
        2: {"timestamp_utc": "2026-07-09T06:00:00+00:00"},
    })
    recap = client.get("/api/targets/M_42/session-recap").json()
    # The raw UTC stamp still says the 9th — that's the honest capture time...
    assert recap["start_utc"].startswith("2026-07-09")
    # ...but the night the owner was out is the evening of the 8th.
    assert recap["night_date"] == "2026-07-08"


def test_session_recap_night_agrees_with_the_nights_card(
    client, solved_library, data_root
):
    """The two cards sit side by side on the Target page, so they must never name
    the same session's night differently — both resolve the site longitude
    through the one shared helper."""
    client.put("/api/settings", json={"site_lon": -122.3})
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-09T05:00:00+00:00"},
        1: {"timestamp_utc": "2026-07-09T05:30:00+00:00"},
        2: {"timestamp_utc": "2026-07-09T06:00:00+00:00"},
    })
    recap = client.get("/api/targets/M_42/session-recap").json()
    nights = client.get("/api/targets/M_42/nights").json()
    assert recap["night_date"] == nights[0]["night_date"]


def test_session_recap_night_follows_the_configured_longitude(
    client, solved_library, data_root, monkeypatch
):
    """Proof the setting is honoured rather than the label being UTC by another
    name: the same UTC stamp lands on a different night for a far-east observer."""
    import webapp.site_location as site_location

    monkeypatch.setattr(site_location, "detect_site_from_library", lambda lib, **k: None)
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-09T05:00:00+00:00"},
        1: {"timestamp_utc": "2026-07-09T05:30:00+00:00"},
        2: {"timestamp_utc": "2026-07-09T06:00:00+00:00"},
    })
    # No location anywhere → UTC noon-to-noon: 05:00 UTC belongs to the 8th.
    assert client.get("/api/targets/M_42/session-recap").json()["night_date"] == "2026-07-08"
    # +150° (~UTC+10) → 15:00 local, i.e. the afternoon *of* the 9th's night.
    client.put("/api/settings", json={"site_lon": 150.0})
    assert client.get("/api/targets/M_42/session-recap").json()["night_date"] == "2026-07-09"


# ---------------------------------------------------------------------------
# "Was the Moon washing this out?" — the retrospective moonlight note
# ---------------------------------------------------------------------------

# 2026-01-02 22:00 UTC: a ~100%-lit Moon, high over London and ~34° from M 42 —
# the exact "bright, up and close" case the note exists for. Fixed rather than
# searched so the test says what sky it is describing.
_MOON_HIT_UTC = "2026-01-02T22:0{}:00+00:00"
_LONDON = {"site_lat": 51.5, "site_lon": -0.1}


def _shoot_at(data_root, stamps: list[str]) -> None:
    _stamp(data_root, "M_42", {i: {"timestamp_utc": s} for i, s in enumerate(stamps)})


def test_a_moon_hit_session_is_told_so_in_plain_language(
    client, solved_library, data_root
):
    """The whole point: a flat picture gets a sky-side explanation, not silence.

    A beginner who shot a faint target under a bright nearby Moon otherwise
    concludes their gear or their editing is at fault.
    """
    client.put("/api/settings", json=_LONDON)
    _shoot_at(data_root, [_MOON_HIT_UTC.format(i) for i in (0, 3, 6)])

    note = client.get("/api/targets/M_42/session-recap").json()["moon_note"]
    assert note is not None
    assert "Moon" in note
    assert "not your setup" in note
    assert "dark-Moon night" in note


def test_the_note_matches_the_engine_verdict_for_the_same_sky(
    client, solved_library, data_root
):
    """The router must not re-derive the astronomy — one helper, one sentence."""
    from datetime import datetime

    from seestack.nightplan import Observer, session_moon

    client.put("/api/settings", json=_LONDON)
    _shoot_at(data_root, [_MOON_HIT_UTC.format(i) for i in (0, 3, 6)])

    target = next(t for t in client.get("/api/targets").json()
                  if t["safe_name"] == "M_42")
    expected = session_moon(
        Observer(lat_deg=51.5, lon_deg=-0.1),
        target["ra_deg"], target["dec_deg"],
        datetime.fromisoformat(_MOON_HIT_UTC.format(0)),
        datetime.fromisoformat(_MOON_HIT_UTC.format(6)),
    ).text
    assert client.get("/api/targets/M_42/session-recap").json()["moon_note"] == expected


def test_a_dark_moon_session_says_nothing_at_all(client, solved_library, data_root):
    """Silence on a good night is the design, not a gap — this must never nag."""
    client.put("/api/settings", json=_LONDON)
    # 2026-01-18: new Moon, and below the horizon at this hour besides.
    _shoot_at(data_root, [f"2026-01-18T22:0{i}:00+00:00" for i in (0, 3, 6)])
    assert client.get("/api/targets/M_42/session-recap").json()["moon_note"] is None


def test_an_unknown_site_costs_the_note_not_the_card(
    client, solved_library, data_root, monkeypatch
):
    """No configured location and nothing in the headers → the rest still renders."""
    import webapp.site_location as site_location

    monkeypatch.setattr(site_location, "detect_site_from_library", lambda lib, **k: None)
    _shoot_at(data_root, [_MOON_HIT_UTC.format(i) for i in (0, 3, 6)])

    recap = client.get("/api/targets/M_42/session-recap").json()
    assert recap["moon_note"] is None
    assert recap["n_frames"] == 3          # the card itself is untouched


def test_an_unsolved_target_costs_the_note_not_the_card(client, built_library):
    """`built_library` is ingested but never plate-solved, so there is no position
    to measure a separation from — and the recap still works."""
    client.put("/api/settings", json=_LONDON)
    recap = client.get("/api/targets/M_42/session-recap").json()
    assert recap["moon_note"] is None
    assert recap["n_frames"] == 3


# ---------------------------------------------------------------------------
# "A six-hour gap is not a night" — the card and the Nights row beneath it
#
# The recap is dated with an observing night and rendered directly above the
# Nights rows. It used to be *session*-shaped, so a night shot in two goes —
# an evening run, bed, a pre-dawn run — put half the night's subs on the card
# and all of them on the row, under the identical date.
# ---------------------------------------------------------------------------

def _add_frames(root, safe: str, stamps: list[str], *, exposure_s: float = 10.0):
    """Append accepted frames at the given UTC stamps to an existing target."""
    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    lib = Library.open_or_create(root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for i, ts in enumerate(stamps):
                proj.add_frame(FrameRow(
                    source_path=f"/x/{safe}-{ts}-{i}.fit",
                    timestamp_utc=ts, exposure_s=exposure_s))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def _split_night_target(client, root):
    """M 42 shot in two goes on one UTC observing night: three subs at 21:00 and
    three more at 05:00 the next morning."""
    client.put("/api/settings", json={"site_lon": 0.0})
    _stamp(root, "M_42", {
        0: {"timestamp_utc": "2026-07-01T21:00:00+00:00"},
        1: {"timestamp_utc": "2026-07-01T21:10:00+00:00"},
        2: {"timestamp_utc": "2026-07-01T21:20:00+00:00"},
    })
    _add_frames(root, "M_42", [
        "2026-07-02T05:00:00+00:00",
        "2026-07-02T05:10:00+00:00",
        "2026-07-02T05:20:00+00:00",
    ])


def test_recap_of_a_split_night_covers_the_whole_night(client, solved_library,
                                                       data_root):
    _split_night_target(client, data_root)
    recap = client.get("/api/targets/M_42/session-recap").json()
    assert recap["night_date"] == "2026-07-01"
    assert recap["n_frames"] == 6          # both halves, not the trailing three
    assert recap["n_kept"] == 6
    # …and the span it reports is the night's, evening through pre-dawn.
    assert recap["start_utc"].startswith("2026-07-01T21:00")
    assert recap["end_utc"].startswith("2026-07-02T05:20")


def test_recap_and_the_nights_row_beneath_it_count_the_same_subs(
    client, solved_library, data_root
):
    """The two cards render one above the other. Same date, same night, same
    numbers — this is the contradiction the change exists to remove."""
    _split_night_target(client, data_root)
    recap = client.get("/api/targets/M_42/session-recap").json()
    nights = client.get("/api/targets/M_42/nights").json()
    assert recap["night_date"] == nights[0]["night_date"] == "2026-07-01"
    assert recap["n_frames"] == nights[0]["n_frames"]
    assert recap["n_kept"] == nights[0]["n_kept"]
    assert recap["session_exposure_s"] == nights[0]["exposure_s"]


def test_a_split_night_is_still_one_night_at_a_western_longitude(
    client, solved_library, data_root
):
    """The merge uses the observer's own night boundary, not UTC's: at UTC−8 the
    same two stamps are an evening and a pre-dawn run of one local night."""
    client.put("/api/settings", json={"site_lon": -122.3})   # Seattle
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-09T05:00:00+00:00"},   # 8 Jul 21:00 local
        1: {"timestamp_utc": "2026-07-09T05:30:00+00:00"},
        2: {"timestamp_utc": "2026-07-09T06:00:00+00:00"},
    })
    _add_frames(data_root, "M_42", [
        "2026-07-09T12:30:00+00:00",                         # 9 Jul 04:30 local
        "2026-07-09T13:00:00+00:00",
    ])
    recap = client.get("/api/targets/M_42/session-recap").json()
    nights = client.get("/api/targets/M_42/nights").json()
    assert recap["night_date"] == "2026-07-08"
    assert recap["n_frames"] == 5
    assert nights[0]["n_frames"] == 5


def test_two_nights_running_are_still_two(client, solved_library, data_root):
    """The merge only ever rolls up *within* a night — the recap must still be
    about the newest night alone."""
    client.put("/api/settings", json={"site_lon": 0.0})
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-01T21:00:00+00:00"},
        1: {"timestamp_utc": "2026-07-01T21:10:00+00:00"},
        2: {"timestamp_utc": "2026-07-01T21:20:00+00:00"},
    })
    _add_frames(data_root, "M_42", [
        "2026-07-02T21:00:00+00:00",
        "2026-07-02T21:10:00+00:00",
    ])
    recap = client.get("/api/targets/M_42/session-recap").json()
    assert recap["night_date"] == "2026-07-02"
    assert recap["n_frames"] == 2
