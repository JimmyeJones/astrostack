"""GET /api/last-night — the Dashboard "Last night" combined recap card."""

from __future__ import annotations

import datetime as dt

from seestack.io.project import FrameRow


def _add_night(lib, safe, start, *, n, exposure=10.0, accept=True, reject_reason=None):
    from seestack.io.project import FrameRow

    proj = lib.open_target(safe)
    try:
        for i in range(n):
            proj.add_frame(FrameRow(
                source_path=f"/x/{safe}-{start:%Y%m%d}-{i}-{accept}.fit",
                timestamp_utc=(start + dt.timedelta(seconds=30 * i)).isoformat(),
                exposure_s=exposure, accept=accept, reject_reason=reject_reason,
            ))
    finally:
        proj.close()


def test_last_night_null_for_an_empty_library(client):
    # No frames carry a capture time yet → nothing datable → null card.
    r = client.get("/api/last-night")
    assert r.status_code == 200
    assert r.json() is None


def test_last_night_combines_targets_shot_the_same_night(client, built_library):
    """Two targets shot back-to-back on one night combine into a single recap; the
    2024 synthetic frames (an earlier 'session') drop out of last night."""
    from seestack.io.library import Library

    safes = {t["safe_name"] for t in client.get("/api/targets").json()}
    m42, ngc = "M_42", "NGC_7000"
    assert {m42, ngc} <= safes

    night = dt.datetime(2026, 7, 8, 21, 0, 0, tzinfo=dt.timezone.utc)
    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, m42, night, n=6)                       # M42 first
        _add_night(lib, m42, night + dt.timedelta(minutes=4),  # one trailed sub
                   n=1, accept=False, reject_reason="auto:streak")
        _add_night(lib, ngc, night + dt.timedelta(hours=2), n=4)  # NGC 2 h later, same night
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert body is not None
    assert body["n_targets"] == 2
    assert body["n_frames"] == 11        # 7 (M42) + 4 (NGC); the 2024 synth night excluded
    assert body["n_kept"] == 10
    assert body["n_set_aside"] == 1
    assert body["reject_buckets"] == {"trailed": 1}
    assert {t["safe"] for t in body["targets"]} == {m42, ngc}
    # Biggest capture leads the card.
    assert body["targets"][0]["safe"] == m42
    assert body["targets"][0]["n_frames"] == 7
    assert body["session_exposure_s"] == 110.0
    assert body["kept_exposure_s"] == 100.0
    assert body["end_utc"] is not None


def test_last_night_excludes_a_target_not_shot_that_night(client, built_library):
    """A target whose last session was a week earlier is not part of last night."""
    from seestack.io.library import Library

    safes = {t["safe_name"] for t in client.get("/api/targets").json()}
    m42, ngc = "M_42", "NGC_7000"
    assert {m42, ngc} <= safes

    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, ngc, dt.datetime(2026, 7, 1, 22, 0, 0, tzinfo=dt.timezone.utc), n=5)
        _add_night(lib, m42, dt.datetime(2026, 7, 8, 22, 0, 0, tzinfo=dt.timezone.utc), n=6)
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert body is not None
    assert body["n_targets"] == 1        # only M42 was shot last night
    assert body["targets"][0]["safe"] == m42
    assert body["n_frames"] == 6


def test_last_night_counts_a_target_revisited_across_a_gap(client, built_library):
    """End-to-end regression: a target imaged at dusk and revisited near dawn (a
    >6 h gap on that target) keeps BOTH batches when another target shot in between
    bridges the night — the card used to undercount it (only the dawn batch)."""
    from seestack.io.library import Library

    safes = {t["safe_name"] for t in client.get("/api/targets").json()}
    m42, ngc = "M_42", "NGC_7000"
    assert {m42, ngc} <= safes

    dusk = dt.datetime(2026, 7, 8, 22, 0, 0, tzinfo=dt.timezone.utc)
    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, m42, dusk, n=3)                                # M42 at dusk
        _add_night(lib, ngc, dusk + dt.timedelta(hours=4), n=3)        # NGC bridges (02:00)
        _add_night(lib, m42, dusk + dt.timedelta(hours=7), n=3)        # M42 again near dawn (05:00)
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert body is not None
    assert body["n_targets"] == 2
    assert body["n_frames"] == 9         # M42 dusk (3) + NGC (3) + M42 dawn (3)
    m42_contrib = next(t for t in body["targets"] if t["safe"] == m42)
    assert m42_contrib["n_frames"] == 6  # both batches, not just the dawn one
    assert body["start_utc"] == dusk.isoformat()


# ---------------------------------------------------------------------------
# Which night was it? — the observing night, not the UTC date the session ended
# ---------------------------------------------------------------------------

def test_last_night_names_the_local_observing_night_not_the_utc_roll_over(
    client, built_library
):
    """Regression: the card labelled the night by slicing ``end_utc``, so a
    session that ran past local midnight — which *ends* on the following UTC day
    — named tomorrow, and disagreed with the imaging calendar squares beside it.
    The night is now bucketed noon-to-noon in the observer's local time."""
    from seestack.io.library import Library

    client.put("/api/settings", json={"site_lon": -122.3})   # Seattle, UTC−8
    start = dt.datetime(2026, 7, 9, 5, 0, 0, tzinfo=dt.timezone.utc)  # 8 Jul 21:00 local
    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, "M_42", start, n=6)
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert body is not None
    # The raw stamps still say the 9th — that's the honest capture time...
    assert body["start_utc"].startswith("2026-07-09")
    # ...but the night the owner was out is the evening of the 8th.
    assert body["night_date"] == "2026-07-08"


def test_last_night_agrees_with_the_imaging_calendar(client, built_library):
    """The Dashboard shows this card and the imaging calendar on one screen, so
    they must never name the same session's night differently."""
    from seestack.io.library import Library

    client.put("/api/settings", json={"site_lon": -122.3})
    start = dt.datetime(2026, 7, 9, 5, 0, 0, tzinfo=dt.timezone.utc)
    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, "M_42", start, n=6)
    finally:
        lib.close()

    night_date = client.get("/api/last-night").json()["night_date"]
    cal_dates = {n["date"] for n in client.get("/api/activity-calendar").json()["nights"]}
    assert night_date in cal_dates


def test_last_night_date_follows_a_longitude_change_without_waiting_out_the_cache(
    client, built_library, monkeypatch
):
    """The recap itself is cached for a minute, but the night label must not be:
    changing the site longitude re-buckets the same session immediately."""
    import webapp.site_location as site_location

    from seestack.io.library import Library

    monkeypatch.setattr(site_location, "detect_site_from_library", lambda lib, **k: None)
    start = dt.datetime(2026, 7, 9, 5, 0, 0, tzinfo=dt.timezone.utc)
    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, "M_42", start, n=6)
    finally:
        lib.close()

    # No location anywhere → UTC noon-to-noon: 05:00 UTC belongs to the 8th.
    assert client.get("/api/last-night").json()["night_date"] == "2026-07-08"
    # +150° (~UTC+10) → 15:00 local, i.e. the afternoon *of* the 9th's night.
    client.put("/api/settings", json={"site_lon": 150.0})
    assert client.get("/api/last-night").json()["night_date"] == "2026-07-09"


def _night_run(lib, safe, start, *, hours, every_min=10):
    """A night's worth of subs from ``start``, ending ``hours`` later."""
    n = int(hours * 60 / every_min) + 1
    proj = lib.open_target(safe)
    try:
        for i in range(n):
            proj.add_frame(FrameRow(
                source_path=f"/x/{safe}-{start:%Y%m%d%H%M}-{i}.fit",
                timestamp_utc=(start + dt.timedelta(minutes=every_min * i)).isoformat(),
                exposure_s=10.0, accept=True,
            ))
    finally:
        proj.close()


def test_last_night_counts_both_halves_of_a_night_shot_in_two_goes(
    client, built_library, monkeypatch
):
    """The card is headed "Last night", so it must count the night.

    One target, one observing night, shot 21:00 → 23:00 and again 05:30 → 07:30
    with nothing else running through the gap to bridge it. The six-hour session
    walk holds only the pre-dawn half, so the card used to report 13 of the 26
    subs and half the integration — on the Dashboard's headline card, about the
    owner's own night.
    """
    import webapp.site_location as site_location

    from seestack.io.library import Library

    monkeypatch.setattr(site_location, "detect_site_from_library", lambda lib, **k: None)
    lib = Library.open_or_create(built_library / "library")
    try:
        _night_run(lib, "M_42",
                   dt.datetime(2026, 7, 1, 21, 0, tzinfo=dt.timezone.utc), hours=2)
        _night_run(lib, "M_42",
                   dt.datetime(2026, 7, 2, 5, 30, tzinfo=dt.timezone.utc), hours=2)
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert body is not None
    assert body["n_frames"] == 26
    assert body["session_exposure_s"] == 260.0
    assert body["targets"][0]["n_frames"] == 26
    assert body["start_utc"].startswith("2026-07-01T21:00")
    # …and it is still one night, named once.
    assert body["night_date"] == "2026-07-01"


def test_last_night_says_when_a_target_stopped_earlier_than_it_usually_does(
    client, built_library,
):
    """The morning half of the live "capture has gone quiet" note. The live one
    self-hides once the silence outlasts the session gap, so an owner who was
    asleep never sees it — this is the same fact, past tense, on the Dashboard
    card they actually open."""
    from seestack.io.library import Library

    lib = Library.open_or_create(built_library / "library")
    try:
        # Four nights that ran 21:00 → 02:00, then one that stopped at 22:00.
        for d in range(4):
            _night_run(lib, "M_42",
                       dt.datetime(2026, 7, 1 + d, 21, 0, tzinfo=dt.timezone.utc),
                       hours=5)
        _night_run(lib, "M_42",
                   dt.datetime(2026, 7, 5, 21, 0, tzinfo=dt.timezone.utc), hours=1)
    finally:
        lib.close()

    early = client.get("/api/last-night").json()["early_stop"]
    assert early is not None
    assert early["safe"] == "M_42"
    assert early["minutes_earlier"] == 240.0
    assert early["n_nights_compared"] == 4
    assert early["stopped_utc"].startswith("2026-07-05T22:00")


def test_last_night_counts_a_split_night_once_before_judging_it(
    client, built_library,
):
    """A night shot in two goes is one night, and the card says so.

    Two evenings-plus-pre-dawns are four capture sessions but **two** nights —
    not the three ``EARLY_STOP_MIN_PRIOR_NIGHTS`` demands before there is a
    habit to judge against. Counting sessions defeated that floor and let the
    card announce an early stop on a target the owner had shot twice.
    """
    from seestack.io.library import Library

    lib = Library.open_or_create(built_library / "library")
    try:
        for d in range(2):
            # 21:00 → 23:00, bed, then 05:30 → 07:30: one night, and — the
            # 6 h gap cleared — two capture sessions.
            _night_run(lib, "M_42",
                       dt.datetime(2026, 7, 1 + d, 21, 0, tzinfo=dt.timezone.utc),
                       hours=2)
            _night_run(lib, "M_42",
                       dt.datetime(2026, 7, 2 + d, 5, 30, tzinfo=dt.timezone.utc),
                       hours=2)
        # …then a third night that stopped at 22:00.
        _night_run(lib, "M_42",
                   dt.datetime(2026, 7, 3, 21, 0, tzinfo=dt.timezone.utc), hours=1)
    finally:
        lib.close()

    assert client.get("/api/last-night").json()["early_stop"] is None


def test_last_night_judges_a_split_night_against_when_the_night_ended(
    client, built_library,
):
    """…and with three real nights of habit, the yardstick is when those nights
    *ended* (07:30), not the 23:00 bedtime halfway through each of them."""
    from seestack.io.library import Library

    lib = Library.open_or_create(built_library / "library")
    try:
        for d in range(3):
            _night_run(lib, "M_42",
                       dt.datetime(2026, 7, 1 + d, 21, 0, tzinfo=dt.timezone.utc),
                       hours=2)
            _night_run(lib, "M_42",
                       dt.datetime(2026, 7, 2 + d, 5, 30, tzinfo=dt.timezone.utc),
                       hours=2)
        _night_run(lib, "M_42",
                   dt.datetime(2026, 7, 4, 21, 0, tzinfo=dt.timezone.utc), hours=1)
    finally:
        lib.close()

    early = client.get("/api/last-night").json()["early_stop"]
    assert early is not None
    # 22:00 against a usual 07:30 — and three nights compared, not six sessions.
    assert early["minutes_earlier"] == 570.0
    assert early["n_nights_compared"] == 3
    assert early["stopped_utc"].startswith("2026-07-04T22:00")


def test_last_night_stays_quiet_when_the_night_ended_at_the_usual_hour(
    client, built_library,
):
    """The silence that makes the line trustworthy: five identical nights say
    nothing at all, however short they each were."""
    from seestack.io.library import Library

    lib = Library.open_or_create(built_library / "library")
    try:
        for d in range(5):
            _night_run(lib, "M_42",
                       dt.datetime(2026, 7, 1 + d, 21, 0, tzinfo=dt.timezone.utc),
                       hours=2)
    finally:
        lib.close()

    assert client.get("/api/last-night").json()["early_stop"] is None


def test_last_night_never_speaks_for_a_target_that_was_not_shot_that_night(
    client, built_library,
):
    """A target whose own newest night is a fortnight old must not colour in
    *this* night's card — its early stop, if any, is old news."""
    from seestack.io.library import Library

    lib = Library.open_or_create(built_library / "library")
    try:
        for d in range(4):
            _night_run(lib, "NGC_7000",
                       dt.datetime(2026, 6, 1 + d, 21, 0, tzinfo=dt.timezone.utc),
                       hours=5)
        _night_run(lib, "NGC_7000",
                   dt.datetime(2026, 6, 5, 21, 0, tzinfo=dt.timezone.utc), hours=1)
        # …and a different target shot much later, which is what "last night" is.
        _night_run(lib, "M_42",
                   dt.datetime(2026, 7, 20, 21, 0, tzinfo=dt.timezone.utc), hours=3)
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert {t["safe"] for t in body["targets"]} == {"M_42"}
    assert body["early_stop"] is None
