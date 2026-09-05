"""GET /api/targets/{safe}/nights — the per-target "Nights" breakdown.

The engine logic (session split, verdicts, best/soft/hazy) is exercised
exhaustively in tests/test_session_recap.py; here we confirm the endpoint wires
it up and serialises the shape the frontend consumes (newest-first, verdict,
reject buckets).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from seestack.io.library import Library


def _stamp(data_root: Path, safe: str, per_frame: dict[int, dict]) -> list[int]:
    """Stamp fields onto specific frames (by 0-based ordinal) of a target."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            ids = [f.id for f in proj.iter_frames()]
            for ordinal, fields in per_frame.items():
                proj.update_frame(ids[ordinal], **fields)
            return ids
        finally:
            proj.close()
    finally:
        lib.close()


def test_nights_default_is_one_night(client, solved_library):
    # The synth frames share one DATE-OBS, so M_42's subs are a single night.
    r = client.get("/api/targets/M_42/nights")
    assert r.status_code == 200
    nights = r.json()
    assert len(nights) == 1
    assert nights[0]["n_frames"] == 3
    assert nights[0]["n_set_aside"] == 0
    # No FWHM measured and no cloud problem → no sharpness verdict.
    assert nights[0]["median_fwhm_px"] is None
    assert nights[0]["verdict"] == ""
    assert nights[0]["is_best"] is False


def test_nights_lists_two_nights_newest_first(client, solved_library, data_root):
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-01T22:00:00+00:00"},               # night A
        1: {"timestamp_utc": "2026-07-08T22:00:00+00:00"},               # night B
        2: {"timestamp_utc": "2026-07-08T22:05:00+00:00"},               # night B
    })
    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 2
    assert nights[0]["start_utc"].startswith("2026-07-08")  # newest first
    assert nights[0]["n_frames"] == 2
    assert nights[1]["start_utc"].startswith("2026-07-01")
    assert nights[1]["n_frames"] == 1


def test_nights_serialises_verdict_and_reject_buckets(client, solved_library, data_root):
    # 2 of 3 subs set aside as cloudy (67% ≥ the 40% floor) → a "hazy" night.
    _stamp(data_root, "M_42", {
        0: {"accept": False, "reject_reason": "auto:grade:transparency"},
        1: {"accept": False, "reject_reason": "auto:grade:sky"},
    })
    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 1
    assert nights[0]["verdict"] == "hazy"
    assert nights[0]["reject_buckets"] == {"cloudy": 2}
    assert nights[0]["n_set_aside"] == 2
    assert nights[0]["n_kept"] == 1


def _add_measured_night(
    data_root: Path, safe: str, stamp_fmt: str, fwhm_px: float, n: int = 5,
) -> None:
    """Add ``n`` accepted, FWHM-measured subs one minute apart — enough for the
    night to be judgeable (the verdict refuses to judge sharpness on thin data)."""
    from seestack.io.project import FrameRow

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for i in range(n):
                proj.add_frame(FrameRow(
                    source_path=f"/dump/{safe}/{stamp_fmt % i}_{fwhm_px}.fit",
                    timestamp_utc=stamp_fmt % i,
                    fwhm_px=fwhm_px,
                    exposure_s=10.0,
                ))
        finally:
            proj.close()
    finally:
        lib.close()


def test_nights_serialises_the_baseline_each_verdict_was_judged_against(
    client, solved_library, data_root,
):
    """The badge the frontend draws from ``verdict`` sits beside a button that
    discards the night, so the number behind the judgement has to come with it.
    ``null`` on a lone night — there is nothing to compare against."""
    # One night, no other night to be judged against.
    _stamp(data_root, "M_42", {
        0: {"fwhm_px": 3.0}, 1: {"fwhm_px": 3.0},
        2: {"fwhm_px": 3.0},
    })
    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 1
    assert nights[0]["typical_fwhm_px"] is None

    # Now give the target two judgeable nights: each sees the OTHER's median.
    _add_measured_night(data_root, "M_42", "2026-07-01T22:%02d:00+00:00", 3.0)
    _add_measured_night(data_root, "M_42", "2026-07-08T22:%02d:00+00:00", 5.0)
    nights = client.get("/api/targets/M_42/nights").json()
    judgeable = [n for n in nights if n["median_fwhm_px"] is not None]
    assert len(judgeable) == 2
    newest, oldest = judgeable
    assert newest["median_fwhm_px"] == 5.0
    assert newest["typical_fwhm_px"] == 3.0   # the other night, not its own 5.0
    assert oldest["typical_fwhm_px"] == 5.0


def _bounds(client, safe: str, ordinal: int = 0) -> dict:
    """The start/end bounds of the target's `ordinal`-th night (newest first)."""
    nights = client.get(f"/api/targets/{safe}/nights").json()
    n = nights[ordinal]
    return {"start_utc": n["start_utc"], "end_utc": n["end_utc"]}


def test_set_aside_night_rejects_only_that_nights_accepted_subs(
    client, solved_library, data_root,
):
    # Two nights: A (one sub) and B (two subs). Set aside night B only.
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-01T22:00:00+00:00"},  # night A
        1: {"timestamp_utc": "2026-07-08T22:00:00+00:00"},  # night B
        2: {"timestamp_utc": "2026-07-08T22:05:00+00:00"},  # night B
    })
    r = client.post("/api/targets/M_42/frames/set-aside-night",
                    json=_bounds(client, "M_42", 0))  # newest = night B
    assert r.status_code == 200
    body = r.json()
    assert body["changed"] == 2
    assert len(body["changed_ids"]) == 2

    nights = client.get("/api/targets/M_42/nights").json()
    # Night A untouched; night B's two subs now set aside (bucketed as "you").
    a = next(n for n in nights if n["start_utc"].startswith("2026-07-01"))
    b = next(n for n in nights if n["start_utc"].startswith("2026-07-08"))
    assert a["n_kept"] == 1 and a["n_set_aside"] == 0
    assert b["n_kept"] == 0 and b["n_set_aside"] == 2
    assert b["reject_buckets"] == {"set aside by you": 2}


def test_set_aside_night_leaves_already_rejected_subs_untouched(
    client, solved_library, data_root,
):
    # One sub already auto-rejected as cloudy; set-aside must not re-reason it.
    _stamp(data_root, "M_42", {
        0: {"accept": False, "reject_reason": "auto:grade:sky"},
    })
    r = client.post("/api/targets/M_42/frames/set-aside-night",
                    json=_bounds(client, "M_42", 0))
    assert r.json()["changed"] == 2  # only the 2 accepted subs, not the cloudy one
    nights = client.get("/api/targets/M_42/nights").json()
    # The cloudy sub keeps its own reason; only the 2 accepted flip to "you".
    assert nights[0]["reject_buckets"] == {"cloudy": 1, "set aside by you": 2}


def test_set_aside_night_is_undoable_via_bulk_accept(
    client, solved_library, data_root,
):
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-08T22:00:00+00:00"},
        1: {"timestamp_utc": "2026-07-08T22:05:00+00:00"},
        2: {"timestamp_utc": "2026-07-08T22:10:00+00:00"},
    })
    changed = client.post("/api/targets/M_42/frames/set-aside-night",
                          json=_bounds(client, "M_42", 0)).json()["changed_ids"]
    assert len(changed) == 3
    # Undo re-accepts exactly the touched subs (the shipped bulk-accept path).
    client.post("/api/targets/M_42/frames/bulk",
                json={"action": "accept", "ids": changed})
    nights = client.get("/api/targets/M_42/nights").json()
    assert nights[0]["n_kept"] == 3 and nights[0]["n_set_aside"] == 0


# ---------------------------------------------------------------------------
# Which night is it? — the observing-night date, not the raw UTC date
# ---------------------------------------------------------------------------

def test_night_date_is_the_local_evening_not_the_utc_date(
    client, solved_library, data_root
):
    """Regression: a session that starts at 21:00 local in the Americas is already
    *tomorrow* in UTC, so labelling the night from ``start_utc`` named the wrong
    day. The night is bucketed noon-to-noon in the observer's local time instead
    (the same convention the imaging calendar uses)."""
    client.put("/api/settings", json={"site_lon": -122.3})   # Seattle, UTC−8
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-09T05:00:00+00:00"},   # 8 Jul 21:00 local
        1: {"timestamp_utc": "2026-07-09T05:30:00+00:00"},
        2: {"timestamp_utc": "2026-07-09T06:00:00+00:00"},
    })
    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 1
    # The raw UTC stamp still says the 9th — that's the honest capture time...
    assert nights[0]["start_utc"].startswith("2026-07-09")
    # ...but the night the owner was out is the evening of the 8th.
    assert nights[0]["night_date"] == "2026-07-08"


def test_night_date_agrees_with_the_imaging_calendar(client, solved_library, data_root):
    """The Target page's Nights card and the Dashboard's imaging calendar must
    never name the same session's night differently — they now resolve the site
    longitude through one shared helper, so this holds by construction."""
    client.put("/api/settings", json={"site_lon": -122.3})
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-09T05:00:00+00:00"},
        1: {"timestamp_utc": "2026-07-09T05:30:00+00:00"},
        2: {"timestamp_utc": "2026-07-09T06:00:00+00:00"},
    })
    nights = client.get("/api/targets/M_42/nights").json()
    cal = client.get("/api/activity-calendar").json()
    cal_dates = {n["date"] for n in cal["nights"]}
    assert {n["night_date"] for n in nights} <= cal_dates


def test_configured_longitude_decides_which_night_a_session_belongs_to(
    client, solved_library, data_root, monkeypatch
):
    """The same UTC stamp lands on a different observing night for a far-east
    observer than it does under the UTC fallback — proof the setting is honoured
    rather than the label being UTC by another name."""
    import webapp.site_location as site_location
    monkeypatch.setattr(site_location, "detect_site_from_library", lambda lib, **k: None)
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-09T05:00:00+00:00"},
        1: {"timestamp_utc": "2026-07-09T05:30:00+00:00"},
        2: {"timestamp_utc": "2026-07-09T06:00:00+00:00"},
    })
    # No location anywhere → UTC noon-to-noon: 05:00 UTC belongs to the 8th.
    assert client.get("/api/targets/M_42/nights").json()[0]["night_date"] == "2026-07-08"
    # +150° (~UTC+10) → 15:00 local, i.e. the afternoon *of* the 9th's night.
    client.put("/api/settings", json={"site_lon": 150.0})
    assert client.get("/api/targets/M_42/nights").json()[0]["night_date"] == "2026-07-09"


# ---------------------------------------------------------------------------
# A row is one observing night, not one capture session
# ---------------------------------------------------------------------------
#
# The 6 h session gap and an observing night disagree in one direction only: an
# evening run, bed, then a pre-dawn run are two sessions inside one night. The
# card is headed "Nights" and its per-row "Set aside" button is worded about the
# night, so the split showed two rows carrying the *identical* date and dropped
# only half a night when one was clicked.

def _split_night(data_root, client) -> None:
    """One observing night at Seattle's longitude, shot in two goes 8 h apart:
    an evening run, bed, then a pre-dawn run. Two sessions by the 6 h gap rule,
    one night by the noon-to-noon rule."""
    client.put("/api/settings", json={"site_lon": -122.3})   # UTC−8ish
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-09T01:00:00+00:00"},   # 8 Jul 17:00 local
        1: {"timestamp_utc": "2026-07-09T01:30:00+00:00"},
        2: {"timestamp_utc": "2026-07-09T09:00:00+00:00"},   # 9 Jul 01:00 local
    })


def test_a_night_shot_in_two_goes_is_one_row(client, solved_library, data_root):
    """Regression: this returned two rows both labelled 2026-07-08, beside a
    caption reading "over 1 night"."""
    _split_night(data_root, client)
    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 1
    assert nights[0]["night_date"] == "2026-07-08"
    assert nights[0]["n_frames"] == 3
    assert nights[0]["start_utc"].startswith("2026-07-09T01:00")
    assert nights[0]["end_utc"].startswith("2026-07-09T09:00")


def test_no_two_rows_ever_share_a_night_date(client, solved_library, data_root):
    """The invariant the card's own heading promises, stated directly: a date
    names one row. This is what the "Set aside" copy relies on to be true."""
    _split_night(data_root, client)
    nights = client.get("/api/targets/M_42/nights").json()
    dates = [n["night_date"] for n in nights]
    assert len(dates) == len(set(dates))


def test_setting_aside_a_split_night_drops_all_of_it(
    client, solved_library, data_root,
):
    """The user-visible cost of the bug: a beginner decides the night was
    clouded out, clicks once, and every sub from it goes — not just the half
    that happened to be on the row they clicked."""
    _split_night(data_root, client)
    r = client.post("/api/targets/M_42/frames/set-aside-night",
                    json=_bounds(client, "M_42", 0))
    assert r.status_code == 200
    assert r.json()["changed"] == 3          # was 2 — the pre-dawn sub survived
    nights = client.get("/api/targets/M_42/nights").json()
    assert nights[0]["n_kept"] == 0
    assert nights[0]["n_set_aside"] == 3


def test_the_card_and_the_frames_table_name_the_same_nights(
    client, solved_library, data_root,
):
    """The mismatch that started this, stated as the agreement it should be: the
    frames table dates each sub by its observing night, so the set of nights the
    subs claim and the set of rows on the card are now the *same* set — not
    merely overlapping, which is all the split version could manage."""
    _split_night(data_root, client)
    nights = client.get("/api/targets/M_42/nights").json()
    frames = client.get("/api/targets/M_42/frames").json()
    assert {n["night_date"] for n in nights} == {f["night_date"] for f in frames}


def test_a_far_east_observers_night_splits_where_his_noon_falls(
    client, solved_library, data_root, monkeypatch,
):
    """Merging is done with the *observer's* longitude, not UTC: the same three
    stamps that are one night in Seattle straddle local noon at +150°, so they
    are honestly two nights there. Proof the grouping key isn't UTC by another
    name."""
    import webapp.site_location as site_location
    monkeypatch.setattr(site_location, "detect_site_from_library", lambda lib, **k: None)
    _split_night(data_root, client)
    assert len(client.get("/api/targets/M_42/nights").json()) == 1
    client.put("/api/settings", json={"site_lon": 150.0})   # ~UTC+10
    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 2
    assert [n["night_date"] for n in nights] == ["2026-07-09", "2026-07-08"]


# --- "this night stopped early", on the target's own page -------------------


def _night_run(lib, safe, start, *, hours, every_min=10):
    """A night's worth of subs from ``start``, ending ``hours`` later."""
    from seestack.io.project import FrameRow

    n = int(hours * 60 / every_min) + 1
    proj = lib.open_target(safe)
    try:
        for i in range(n):
            proj.add_frame(FrameRow(
                source_path=f"/x/{safe}-{start:%Y%m%d%H%M}-{i}.fit",
                timestamp_utc=(start + timedelta(minutes=every_min * i)).isoformat(),
                exposure_s=10.0, accept=True,
            ))
    finally:
        proj.close()


def _five_nights(data_root: Path, *, last_hours: float) -> None:
    """Four nights that ran 21:00 → 02:00, then one of ``last_hours``."""
    lib = Library.open_or_create(data_root / "library")
    try:
        for d in range(4):
            _night_run(lib, "M_42",
                       datetime(2026, 7, 1 + d, 21, 0, tzinfo=timezone.utc), hours=5)
        _night_run(lib, "M_42",
                   datetime(2026, 7, 5, 21, 0, tzinfo=timezone.utc), hours=last_hours)
    finally:
        lib.close()


def test_nights_newest_row_says_when_the_night_stopped_early(
    client, solved_library, data_root,
):
    """The Dashboard's "Last night" card speaks only for the library's most
    recent capture night, so by Thursday a Tuesday target's early stop has
    nowhere to be said. Its own newest night row keeps it."""
    _five_nights(data_root, last_hours=1)
    nights = client.get("/api/targets/M_42/nights").json()
    early = nights[0]["ended_early"]
    assert early is not None
    assert early["minutes_earlier"] == 240.0
    assert early["n_nights_compared"] == 4
    assert early["stopped_utc"].startswith("2026-07-05T22:00")
    # Only the newest row is annotated — an older night ending early is history.
    assert all(n["ended_early"] is None for n in nights[1:])


def test_nights_say_nothing_when_the_night_ended_at_the_usual_hour(
    client, solved_library, data_root,
):
    """Silence is the default: five nights that all ran to 02:00 report nothing,
    because a wrong "you lost half a night" costs far more than a missed one."""
    _five_nights(data_root, last_hours=5)
    nights = client.get("/api/targets/M_42/nights").json()
    assert all(n["ended_early"] is None for n in nights)


def test_nights_early_stop_agrees_with_the_dashboard_last_night_card(
    client, solved_library, data_root,
):
    """Two surfaces, one measurement. The Nights row groups by *observing night*
    and the Dashboard by *session*, so the judgement is deliberately taken from
    the session stamps on both — otherwise a night shot in two goes would be
    reported two different ways by two screens the owner reads minutes apart."""
    _five_nights(data_root, last_hours=1)
    row = client.get("/api/targets/M_42/nights").json()[0]["ended_early"]
    card = client.get("/api/last-night").json()["early_stop"]
    assert row is not None and card is not None
    assert card["safe"] == "M_42"
    for key in ("stopped_utc", "minutes_earlier", "n_nights_compared"):
        assert row[key] == card[key]


# ---------------------------------------------------------------------------
# "Which of my nights did the Moon wash out?" — the per-row Moon reading
# ---------------------------------------------------------------------------

_LONDON = {"site_lat": 51.5, "site_lon": -0.1}
# A bright Moon close to M 42 (the same night the "Last night" card's Moon note
# is pinned on), and a new-Moon night two weeks later that is below the horizon
# at this hour besides.
_MOON_HIT = "2026-01-02T22:0{}:00+00:00"
_DARK_MOON = "2026-01-18T22:0{}:00+00:00"


def _two_nights_one_moonlit(data_root) -> None:
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": _MOON_HIT.format(0)},
        1: {"timestamp_utc": _MOON_HIT.format(6)},
        2: {"timestamp_utc": _DARK_MOON.format(0)},
    })


def test_a_moonlit_night_is_marked_and_a_dark_one_is_not(
    client, solved_library, data_root,
):
    """The whole point: with ten nights on one target, the beginner can see which
    of them the Moon hurt — not only the most recent, which is all the "Last
    night" card can ever speak for."""
    client.put("/api/settings", json=_LONDON)
    _two_nights_one_moonlit(data_root)

    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 2
    dark, moonlit = nights[0], nights[1]        # newest first: 18 Jan, then 2 Jan
    assert moonlit["start_utc"].startswith("2026-01-02")
    assert moonlit["moon"]["level"] == "poor"
    assert "Moon" in moonlit["moon"]["text"]
    assert moonlit["moon"]["illumination"] > 0.65
    # A dark-Moon night carries its numbers and says nothing — silence on a good
    # night is the design, so this can never become a nag.
    assert dark["start_utc"].startswith("2026-01-18")
    assert dark["moon"]["level"] == "good"
    assert dark["moon"]["text"] is None


def test_the_row_matches_the_engine_verdict_for_the_same_sky(
    client, solved_library, data_root,
):
    """The router must not re-derive the astronomy: every number on the row comes
    from the same helper the "Last night" note is built from."""
    from datetime import datetime

    from seestack.nightplan import Observer, session_moon

    client.put("/api/settings", json=_LONDON)
    _two_nights_one_moonlit(data_root)

    target = next(t for t in client.get("/api/targets").json()
                  if t["safe_name"] == "M_42")
    expected = session_moon(
        Observer(lat_deg=51.5, lon_deg=-0.1),
        target["ra_deg"], target["dec_deg"],
        datetime.fromisoformat(_MOON_HIT.format(0)),
        datetime.fromisoformat(_MOON_HIT.format(6)),
    )
    row = client.get("/api/targets/M_42/nights").json()[1]["moon"]
    assert row["level"] == expected.level
    assert row["text"] == expected.text
    assert row["illumination"] == expected.illumination
    assert row["moon_altitude_deg"] == expected.moon_altitude_deg
    assert row["separation_deg"] == expected.separation_deg


def test_the_whole_table_costs_one_ephemeris_pass(
    client, solved_library, data_root, monkeypatch,
):
    """The cost note this was filed with: one ephemeris evaluation per row would
    put ~25 ms × N on a card that renders on every Target page view. The batched
    helper does the whole table in one pass, and this pins that it stays one."""
    import seestack.nightplan as nightplan

    calls: list[int] = []
    real = nightplan._moon_geometry_many

    def counting(observer, ra, dec, ats):  # noqa: ANN001, ANN202
        calls.append(len(ats))
        return real(observer, ra, dec, ats)

    monkeypatch.setattr(nightplan, "_moon_geometry_many", counting)
    client.put("/api/settings", json=_LONDON)
    _two_nights_one_moonlit(data_root)

    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 2
    assert calls == [2]


def test_an_unknown_site_costs_the_marker_not_the_card(
    client, solved_library, data_root, monkeypatch,
):
    """No configured location and nothing in the headers → the rows still render,
    just without a Moon reading. It must read as "unknown", never as "fine"."""
    import webapp.site_location as site_location

    monkeypatch.setattr(site_location, "detect_site_from_library", lambda lib, **k: None)
    _two_nights_one_moonlit(data_root)

    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 2
    assert all(n["moon"] is None for n in nights)
    assert sum(n["n_frames"] for n in nights) == 3      # the table itself is intact


def test_an_unsolved_target_costs_the_marker_not_the_card(client, built_library):
    """`built_library` is ingested but never plate-solved, so there is no position
    to measure a separation from — and the Nights table still works."""
    client.put("/api/settings", json=_LONDON)
    nights = client.get("/api/targets/M_42/nights").json()
    assert all(n["moon"] is None for n in nights)


def test_an_ephemeris_failure_never_costs_the_table(
    client, solved_library, data_root, monkeypatch,
):
    """An ephemeris hiccup must degrade to "nothing to say" rather than 500 the
    card — the same contract the single-session note already holds to."""
    import seestack.nightplan as nightplan

    def boom(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("ephemeris unavailable")

    monkeypatch.setattr(nightplan, "_moon_geometry_many", boom)
    client.put("/api/settings", json=_LONDON)
    _two_nights_one_moonlit(data_root)

    r = client.get("/api/targets/M_42/nights")
    assert r.status_code == 200
    assert all(n["moon"] is None for n in r.json())
