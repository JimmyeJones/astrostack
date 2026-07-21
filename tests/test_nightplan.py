"""Tests for the offline 'Tonight' night planner (``seestack.nightplan``).

Deterministic: fixed date + site → known altitude/window, so these pin the
astronomy, not a snapshot. Altitude tolerances allow for refraction and the
5-minute sampling grid.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from seestack import nightplan as np_plan
from seestack.nightplan import (
    HorizonProfile,
    LibraryTarget,
    Observer,
    load_catalog,
    moon_illumination,
    moon_is_waxing,
    next_observing_windows,
    plan_tonight,
)

# A clear January evening in London — Orion season, small waning Moon.
LONDON = Observer(lat_deg=51.5, lon_deg=-0.13, elevation_m=30.0)
JAN_EVENING = datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc)


def _transit_altitude(lat_deg: float, dec_deg: float) -> float:
    """Geometric upper-culmination altitude of a target at a given latitude."""
    return 90.0 - abs(lat_deg - dec_deg)


# The 88 canonical IAU three-letter constellation abbreviations. A catalog entry
# whose ``con`` isn't in here is a typo (and would render as junk in the UI).
_IAU_CONSTELLATIONS = {
    "And", "Ant", "Aps", "Aqr", "Aql", "Ara", "Ari", "Aur", "Boo", "Cae", "Cam",
    "Cnc", "CVn", "CMa", "CMi", "Cap", "Car", "Cas", "Cen", "Cep", "Cet", "Cha",
    "Cir", "Col", "Com", "CrA", "CrB", "Crv", "Crt", "Cru", "Cyg", "Del", "Dor",
    "Dra", "Equ", "Eri", "For", "Gem", "Gru", "Her", "Hor", "Hya", "Hyi", "Ind",
    "Lac", "Leo", "LMi", "Lep", "Lib", "Lup", "Lyn", "Lyr", "Men", "Mic", "Mon",
    "Mus", "Nor", "Oct", "Oph", "Ori", "Pav", "Peg", "Per", "Phe", "Pic", "Psc",
    "PsA", "Pup", "Pyx", "Ret", "Sge", "Sgr", "Sco", "Scl", "Sct", "Ser", "Sex",
    "Tau", "Tel", "Tri", "TrA", "Tuc", "UMa", "UMi", "Vel", "Vir", "Vol", "Vul",
}

# Types the planner/UI understand (shared with the Messier catalog vocabulary).
_KNOWN_TYPES = {
    "asterism", "double star", "galaxy", "globular cluster", "nebula",
    "open cluster", "planetary nebula", "star cloud", "supernova remnant",
}


def test_iers_offline_disables_the_staleness_check():
    """Regression: the planner must stay offline-safe as its astropy IERS data
    ages. Without ``auto_max_age = None`` astropy raises "predictive values that
    are more than 30.0 days old" once the bundled table passes 30 days (or when
    planning >30 days out), 500-ing the planner on a NAS that can't re-download.
    """
    np_plan._configure_iers_offline()
    from astropy.utils import iers
    assert iers.conf.auto_max_age is None
    assert iers.conf.auto_download is False


def test_catalog_loads_messier_plus_curated_extras():
    cat = load_catalog()
    ids = {o.id for o in cat}
    # The full Messier catalog is still present and canonical.
    messier = [o for o in cat if o.id.startswith("M") and o.id[1:].isdigit()]
    assert len(messier) == 110
    assert "M1" in ids and "M42" in ids and "M110" in ids
    m42 = next(o for o in cat if o.id == "M42")
    assert m42.name == "Orion Nebula"
    # The curated non-Messier set widens the catalog with popular NGC/IC targets.
    assert len(cat) > 110
    for expected in ("NGC 7000", "NGC 869", "NGC 6960", "NGC 7293", "IC 1805"):
        assert expected in ids, expected
    # Every coordinate is sane across the whole combined catalog.
    for o in cat:
        assert 0.0 <= o.ra_deg < 360.0
        assert -90.0 <= o.dec_deg <= 90.0


def test_curated_catalog_is_well_formed_and_disjoint_from_messier():
    """The bundled non-Messier file has unique, valid, non-duplicating entries."""
    cat = load_catalog()
    extras = [o for o in cat if not (o.id.startswith("M") and o.id[1:].isdigit())]
    assert len(extras) >= 40  # a curated set worth having

    # Ids are unique across the whole catalog (the loader de-dups; verify no
    # accidental Messier/NGC id collision slipped through).
    ids = [o.id for o in cat]
    assert len(ids) == len(set(ids))

    for o in extras:
        assert o.id.startswith(("NGC ", "IC ")), o.id
        assert o.name, o.id  # every curated target carries a recognisable name
        assert o.type in _KNOWN_TYPES, (o.id, o.type)
        assert o.con in _IAU_CONSTELLATIONS, (o.id, o.con)

    # No curated object sits on top of a Messier object (they should be a genuine
    # widening, not a rename) — nothing closer than 0.2° to any Messier entry.
    messier = [o for o in cat if o.id.startswith("M") and o.id[1:].isdigit()]
    for e in extras:
        for m in messier:
            assert np_plan._angular_sep_deg(e.ra_deg, e.dec_deg,
                                            m.ra_deg, m.dec_deg) > 0.2, (e.id, m.id)


def test_curated_extras_appear_in_a_plan():
    """A widely-observable curated target surfaces as a not-yet-targeted entry."""
    # The Double Cluster (Dec +57°) is well up from London in January — it should
    # show up in the ranked plan as a catalog suggestion.
    plan = plan_tonight(LONDON, JAN_EVENING)
    by_id = {t.id: t for t in plan.targets}
    assert "NGC 869" in by_id
    dbl = by_id["NGC 869"]
    assert dbl.already_targeted is False
    assert dbl.name == "Double Cluster"
    assert dbl.max_altitude_deg > 30.0  # genuinely up that night


def test_catalog_plan_rows_carry_a_framing_hint():
    """A sized catalog candidate surfaces its "will it fit?" verdict pre-capture."""
    plan = plan_tonight(LONDON, JAN_EVENING)
    by_id = {t.id: t for t in plan.targets}
    # M31 (~178', bigger than a single Seestar frame) → a mosaic framing hint.
    m31 = by_id["M31"]
    assert m31.size_arcmin == 178.0
    assert m31.framing is not None
    assert m31.framing.level == "mosaic"
    # A compact target fits comfortably (no mosaic nudge).
    m57 = by_id["M57"]
    assert m57.framing is not None
    assert m57.framing.level == "fits"


def test_dark_window_is_astronomical_in_winter():
    plan = plan_tonight(LONDON, JAN_EVENING)
    dw = plan.dark_window
    assert dw is not None
    assert dw["sun_alt_threshold_deg"] == -18.0
    assert dw["start_utc"] < dw["end_utc"]
    # London mid-January astronomical night is roughly 11.5 h.
    assert 600.0 < dw["duration_minutes"] < 780.0


def test_high_latitude_summer_degrades_then_vanishes():
    # London midsummer: no −18 darkness, so it falls back to a shallower window.
    w = np_plan._find_dark_window(LONDON, datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc))
    assert w is not None
    assert w.sun_alt_threshold_deg > -18.0
    # Svalbard midsummer: polar day, the Sun never sets → no window at all.
    svalbard = Observer(lat_deg=78.2, lon_deg=15.6, elevation_m=0.0)
    assert np_plan._find_dark_window(
        svalbard, datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc)) is None


def test_transit_altitude_matches_geometry():
    # A library target whose transit falls inside the dark window: its max
    # altitude over the night must equal the geometric culmination altitude.
    m42 = LibraryTarget(safe="M42", name="Orion Nebula", ra_deg=83.82,
                        dec_deg=-5.39, frames_accepted=100, total_exposure_s=1000.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[m42])
    entry = next(p for p in plan.targets if p.id == "M42")
    expected = _transit_altitude(LONDON.lat_deg, m42.dec_deg)  # ≈ 33.1°
    assert abs(entry.max_altitude_deg - expected) < 1.0
    assert entry.already_targeted is True
    assert entry.transit_utc is not None


def test_library_target_dedupes_matching_catalog_object():
    m42 = LibraryTarget(safe="M42", name="Orion Nebula", ra_deg=83.82,
                        dec_deg=-5.39, frames_accepted=100, total_exposure_s=1000.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[m42])
    m42_entries = [p for p in plan.targets if abs(p.ra_deg - 83.82) < 0.5
                   and abs(p.dec_deg - (-5.39)) < 0.5]
    assert len(m42_entries) == 1
    assert m42_entries[0].already_targeted is True


def test_never_rising_target_scores_zero():
    # A deep-southern target can never clear 30° from London.
    south = LibraryTarget(safe="deep-south", name="Deep South", ra_deg=90.0,
                         dec_deg=-70.0, frames_accepted=0, total_exposure_s=0.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[south],
                        include_catalog=False, min_altitude_deg=30.0)
    entry = next(p for p in plan.targets if p.id == "deep-south")
    assert entry.score == 0.0
    assert entry.minutes_above_min_alt == 0.0
    assert entry.transit_utc is None


def test_high_min_altitude_does_not_crash_the_score():
    # Regression: the score's altitude term divided by ``70 - min_alt``. With a
    # ``min_altitude_deg`` of 70 (a legal Settings/query value, ge=0 le=80) and a
    # target that transits above 70°, that denominator was zero → ZeroDivisionError
    # → 500 on GET /api/plan/tonight?min_alt=70. A target near the zenith is common
    # (dec ≈ observer latitude), so this was reachable.
    high = LibraryTarget(safe="high", name="High", ra_deg=90.0, dec_deg=51.5,
                         frames_accepted=0, total_exposure_s=0.0)
    for min_alt in (70.0, 80.0):
        plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[high],
                            include_catalog=False, min_altitude_deg=min_alt)
        entry = next(p for p in plan.targets if p.id == "high")
        # It clears the floor near the zenith, so it should score above zero, and
        # the altitude term saturates to "plenty high" rather than blowing up.
        assert entry.max_altitude_deg > min_alt
        assert entry.score > 0.0


def test_high_target_outranks_low_target():
    plan = plan_tonight(LONDON, JAN_EVENING)
    # Sorted best-first, and a near-zenith circumpolar target beats a low one.
    scores = [p.score for p in plan.targets]
    assert scores == sorted(scores, reverse=True)
    best = plan.targets[0]
    assert best.score > 50.0
    assert best.max_altitude_deg > 60.0


# --- next_observing_windows (the forward-looking per-target planner) ---------

# M42 (Orion) — well up on January nights from London, so it should produce
# usable windows for the next-session card; RA/Dec from the catalog.
_M42_RA, _M42_DEC = 83.82, -5.39


def test_next_observing_windows_finds_upcoming_nights_for_a_well_placed_target():
    wins = next_observing_windows(
        LONDON, _M42_RA, _M42_DEC, start_utc=JAN_EVENING,
        min_altitude_deg=30.0, nights=5, want=3)
    # Orion clears 30° from London on clear January nights, so several nights
    # qualify and we get the requested count.
    assert len(wins) == 3
    for w in wins:
        assert w.dark_start < w.dark_end
        assert w.usable_start is not None and w.usable_end is not None
        assert w.usable_start >= w.dark_start
        assert w.minutes_above_min_alt >= 45.0
        assert w.max_altitude_deg > 30.0
        assert 0.0 <= w.moon_illumination <= 1.0
    # Returned chronologically (next best time to shoot first).
    starts = [w.dark_start for w in wins]
    assert starts == sorted(starts)
    # Consecutive nights: each window's darkness is roughly a day after the last.
    for a, b in zip(starts, starts[1:]):
        gap_h = (b - a).total_seconds() / 3600.0
        assert 20.0 < gap_h < 28.0


def test_next_observing_windows_empty_for_a_never_rising_target():
    # A deep-southern object never clears 30° from London — no usable window on
    # any night, so the card self-hides (empty list).
    wins = next_observing_windows(
        LONDON, 90.0, -70.0, start_utc=JAN_EVENING,
        min_altitude_deg=30.0, nights=7, want=3)
    assert wins == []


def test_next_observing_windows_skips_a_night_already_past():
    # Start the scan at dawn (after tonight's darkness is spent). Tonight's window
    # is entirely behind us, so the first returned window must begin strictly in
    # the future, on a *later* night.
    dawn = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    wins = next_observing_windows(
        LONDON, _M42_RA, _M42_DEC, start_utc=dawn,
        min_altitude_deg=30.0, nights=3, want=1)
    assert len(wins) == 1
    assert wins[0].dark_end > dawn
    # It's the *coming* night, not the one whose darkness already ended before dawn.
    assert wins[0].dark_start > dawn


def test_next_observing_windows_clips_tonight_to_now():
    # Mid-darkness: the first window must be clipped to start at "now", never
    # reported as beginning earlier in the evening than the caller's reference.
    midnight = datetime(2026, 1, 16, 0, 30, tzinfo=timezone.utc)
    wins = next_observing_windows(
        LONDON, _M42_RA, _M42_DEC, start_utc=midnight,
        min_altitude_deg=30.0, nights=1, want=1)
    if wins:  # tonight still has usable darkness left for Orion
        assert wins[0].dark_start >= midnight


def test_moon_illumination_range_and_known_phase():
    illum = moon_illumination(JAN_EVENING)
    assert 0.0 <= illum <= 1.0
    # New Moon was ~2026-01-18, so a few days before it is a thin waning crescent.
    assert illum < 0.25
    # A full Moon (~2026-01-03) reads near-fully-lit.
    full = moon_illumination(datetime(2026, 1, 3, 22, 0, tzinfo=timezone.utc))
    assert full > 0.9


def test_moon_waxing_matches_the_phase_cycle():
    # Waning crescent a few days before the ~2026-01-18 new Moon.
    assert moon_is_waxing(JAN_EVENING) is False
    # Just after new Moon (2026-01-20) the Moon is growing again.
    assert moon_is_waxing(datetime(2026, 1, 20, 22, 0, tzinfo=timezone.utc)) is True
    # Rising toward the ~2026-02-01 full Moon — still waxing.
    assert moon_is_waxing(datetime(2026, 1, 25, 22, 0, tzinfo=timezone.utc)) is True
    # A day past the ~2026-01-03 full Moon — waning.
    assert moon_is_waxing(datetime(2026, 1, 4, 22, 0, tzinfo=timezone.utc)) is False


def test_plan_reports_moon_waxing_state():
    plan = plan_tonight(LONDON, JAN_EVENING)
    # The plan carries the same waxing verdict the standalone helper computes, so
    # the UI can label it "Waning crescent" rather than a bare "Crescent".
    assert plan.moon_waxing is moon_is_waxing(JAN_EVENING)
    assert plan.moon_waxing is False


def test_moon_window_full_moon_is_up_all_night():
    # The ~2026-01-03 full Moon rides opposite the Sun, so it clears the horizon
    # for the whole dark window — no rise/set inside it to report.
    obs = LONDON
    ref = datetime(2026, 1, 3, 22, 0, tzinfo=timezone.utc)
    win = np_plan._find_dark_window(obs, ref)
    mw = np_plan.moon_window(obs, win)
    assert mw.up_all_night is True
    assert mw.down_all_night is False
    assert mw.rise_utc is None and mw.set_utc is None


def test_moon_window_new_moon_is_down_all_night():
    # The ~2026-01-18 new Moon sits near the Sun, so it is below the horizon
    # through the entire (post-dusk) dark window — good, dark skies.
    obs = LONDON
    ref = datetime(2026, 1, 18, 22, 0, tzinfo=timezone.utc)
    win = np_plan._find_dark_window(obs, ref)
    mw = np_plan.moon_window(obs, win)
    assert mw.down_all_night is True
    assert mw.up_all_night is False
    assert mw.rise_utc is None and mw.set_utc is None


def test_moon_window_waxing_moon_sets_during_the_night():
    # A waxing half-Moon (~2026-01-25) leads the Sun and sets partway through the
    # night, clearing the sky for the later hours.
    obs = LONDON
    ref = datetime(2026, 1, 25, 22, 0, tzinfo=timezone.utc)
    win = np_plan._find_dark_window(obs, ref)
    mw = np_plan.moon_window(obs, win)
    assert mw.set_utc is not None
    assert mw.rise_utc is None
    assert not mw.up_all_night and not mw.down_all_night
    # The reported crossing lies inside the dark window and is a genuine
    # above→below transition of the Moon's altitude.
    cross = datetime.fromisoformat(mw.set_utc)
    assert win.start <= cross <= win.end
    _assert_is_setting_crossing(obs, cross)


def test_moon_window_waning_moon_rises_during_the_night():
    # A waning Moon (~2026-01-11) trails the Sun and rises after midnight, so it
    # only spoils the later part of the night.
    obs = LONDON
    ref = datetime(2026, 1, 11, 22, 0, tzinfo=timezone.utc)
    win = np_plan._find_dark_window(obs, ref)
    mw = np_plan.moon_window(obs, win)
    assert mw.rise_utc is not None
    assert mw.set_utc is None
    assert not mw.up_all_night and not mw.down_all_night
    cross = datetime.fromisoformat(mw.rise_utc)
    assert win.start <= cross <= win.end
    _assert_is_rising_crossing(obs, cross)


def _moon_alt(obs: Observer, when: datetime) -> float:
    from astropy.time import Time

    stamps_time = Time([when.replace(tzinfo=None)], scale="utc")
    return float(np_plan._moon_altitudes(stamps_time, obs.earth_location())[0])


def _assert_is_setting_crossing(obs: Observer, cross: datetime) -> None:
    from datetime import timedelta

    assert _moon_alt(obs, cross - timedelta(minutes=6)) > 0.0
    assert _moon_alt(obs, cross + timedelta(minutes=6)) < 0.0


def _assert_is_rising_crossing(obs: Observer, cross: datetime) -> None:
    from datetime import timedelta

    assert _moon_alt(obs, cross - timedelta(minutes=6)) < 0.0
    assert _moon_alt(obs, cross + timedelta(minutes=6)) > 0.0


def test_plan_reports_moon_window():
    # A dated plan carries the same moon-window verdict the standalone helper
    # computes, so the UI can show the concrete rise/set time under the phase.
    ref = datetime(2026, 1, 25, 22, 0, tzinfo=timezone.utc)
    plan = plan_tonight(LONDON, ref)
    assert plan.moon_window is not None
    win = np_plan._find_dark_window(LONDON, ref)
    expected = np_plan.moon_window(LONDON, win)
    assert plan.moon_window["set_utc"] == expected.set_utc
    assert plan.moon_window["rise_utc"] == expected.rise_utc
    assert plan.moon_window["up_all_night"] == expected.up_all_night
    assert plan.moon_window["down_all_night"] == expected.down_all_night


def test_plan_without_dark_window_has_no_moon_window():
    # Polar day: no dark window, so no moon-window cue either (rather than a
    # misleading all-night flag).
    svalbard = Observer(lat_deg=78.2, lon_deg=15.6, elevation_m=0.0)
    plan = plan_tonight(svalbard, datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc))
    assert plan.dark_window is None
    assert plan.moon_window is None


def test_moon_penalty_scales_with_moon_up_overlap():
    # The Moon penalty is weighted by how much of the target's usable window the
    # Moon is actually above the horizon. A bright, close Moon that has set (or
    # not yet risen) while the target is up shouldn't dock the score at all.
    args = dict(max_alt=60.0, minutes_above=300.0, dark_minutes=300.0,
                moon_sep=10.0, moon_illum=1.0, min_alt=30.0)
    full = np_plan._score(**args, moon_up_fraction=1.0)
    half = np_plan._score(**args, moon_up_fraction=0.5)
    none = np_plan._score(**args, moon_up_fraction=0.0)
    # No overlap → the bright-Moon penalty vanishes; partial overlap lands between.
    assert none > half > full
    # With zero overlap the score matches an unlit (new-Moon) sky — the penalty
    # is entirely gone, not merely reduced.
    assert none == pytest.approx(np_plan._score(**{**args, "moon_illum": 0.0}))
    # Omitting the fraction reproduces the old full-penalty behaviour exactly.
    assert np_plan._score(**args) == full


def _full_moon_penalty_score(p, dark_minutes: float, illum: float,
                             min_alt: float = 30.0) -> float:
    """Recompute a target's score as if the Moon were up for its whole window
    (the pre-overlap behaviour), from the plan's rounded public fields."""
    return np_plan._score(p.max_altitude_deg, p.minutes_above_min_alt,
                          dark_minutes, p.moon_separation_deg, illum, min_alt,
                          moon_up_fraction=1.0)


def test_moon_up_all_night_leaves_scores_unchanged():
    # Backward-compat guard: when the (full) Moon is above the horizon for the
    # whole dark window, every target's Moon overlap is 1.0, so scores match the
    # old full-penalty formula — a normal moonlit night isn't reshuffled.
    ref = datetime(2026, 1, 3, 22, 0, tzinfo=timezone.utc)  # full Moon, up all night
    plan = plan_tonight(LONDON, ref, include_catalog=False,
                        library_targets=list(_orion_belt_targets()))
    assert plan.moon_window["up_all_night"] is True
    dark_minutes = plan.dark_window["duration_minutes"]
    for p in plan.targets:
        old = _full_moon_penalty_score(p, dark_minutes, plan.moon_illumination)
        assert p.score == pytest.approx(old, abs=0.3)


def test_moon_that_sets_partway_relieves_post_moonset_targets():
    # On a night where a bright Moon sets partway through the dark window, targets
    # that are only usable after moonset get their penalty lifted — their score
    # can only rise above (never fall below) the old full-Moon-penalty value.
    ref = datetime(2026, 1, 25, 22, 0, tzinfo=timezone.utc)  # waxing Moon sets partway
    plan = plan_tonight(LONDON, ref)
    assert plan.moon_window["set_utc"] is not None
    assert plan.moon_window["up_all_night"] is False
    dark_minutes = plan.dark_window["duration_minutes"]
    relieved = 0
    for p in plan.targets:
        old = _full_moon_penalty_score(p, dark_minutes, plan.moon_illumination)
        # The new score never drops below the old full-penalty score.
        assert p.score >= old - 0.3
        if p.score > old + 1.0:
            relieved += 1
    # Some real targets are only up after the Moon sets, so the penalty is lifted.
    assert relieved > 0


def _orion_belt_targets():
    # A few well-placed January targets so the up-all-night test has a Moon-close
    # object to penalise (M42 sits near the January full Moon's path).
    yield LibraryTarget(safe="m42", name="Orion Nebula", ra_deg=83.82,
                        dec_deg=-5.39, frames_accepted=10, total_exposure_s=100.0)
    yield LibraryTarget(safe="m45", name="Pleiades", ra_deg=56.75,
                        dec_deg=24.12, frames_accepted=5, total_exposure_s=50.0)


def test_plan_reports_moon_up_fraction_per_target():
    # Each observable target carries the share of its usable window the Moon is
    # above the horizon, so the UI can explain why a bright-Moon night still
    # ranked it well. On an up-all-night full Moon every target's fraction is 1.0.
    ref = datetime(2026, 1, 3, 22, 0, tzinfo=timezone.utc)  # full Moon, up all night
    plan = plan_tonight(LONDON, ref, include_catalog=False,
                        library_targets=list(_orion_belt_targets()))
    assert plan.moon_window["up_all_night"] is True
    observable = [p for p in plan.targets if p.minutes_above_min_alt > 0]
    assert observable  # the fixtures are well placed in January
    for p in observable:
        assert p.moon_up_fraction == pytest.approx(1.0)


def test_moon_up_fraction_tracks_the_penalty_relief():
    # On a night where a waxing Moon sets partway through the dark window, a target
    # relieved of the Moon penalty (score risen above the full-penalty value) must
    # report a below-1 overlap — the field and the score tell a consistent story.
    ref = datetime(2026, 1, 25, 22, 0, tzinfo=timezone.utc)  # waxing Moon sets partway
    plan = plan_tonight(LONDON, ref)
    assert plan.moon_window["set_utc"] is not None
    dark_minutes = plan.dark_window["duration_minutes"]
    for p in plan.targets:
        if p.minutes_above_min_alt <= 0:
            continue
        old = _full_moon_penalty_score(p, dark_minutes, plan.moon_illumination)
        if p.score > old + 1.0:  # genuinely relieved by the Moon setting
            assert p.moon_up_fraction is not None
            assert p.moon_up_fraction < 1.0


def test_moon_up_fraction_is_none_for_a_never_usable_target():
    # A deep-southern target never clears the floor → no usable window → the
    # overlap is unknown (None), so the UI shows no misleading Moon cue.
    south = LibraryTarget(safe="deep-south", name="Deep South", ra_deg=90.0,
                          dec_deg=-70.0, frames_accepted=0, total_exposure_s=0.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[south],
                        include_catalog=False, min_altitude_deg=30.0)
    entry = next(p for p in plan.targets if p.id == "deep-south")
    assert entry.score == 0.0
    assert entry.moon_up_fraction is None


def test_plan_reports_usable_window_bounds():
    # An observable target carries the clock bounds of its usable window, so the
    # UI can say *when* tonight to shoot it. The bounds enclose the transit and
    # fall inside the dark window, and the span is consistent with the reported
    # usable minutes (equal for the common contiguous, no-mask case).
    m42 = LibraryTarget(safe="m42", name="Orion Nebula", ra_deg=83.82,
                        dec_deg=-5.39, frames_accepted=10, total_exposure_s=100.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[m42],
                        include_catalog=False, min_altitude_deg=30.0)
    entry = next(p for p in plan.targets if p.id == "m42")
    assert entry.minutes_above_min_alt > 0
    start = datetime.fromisoformat(entry.usable_start_utc)
    end = datetime.fromisoformat(entry.usable_end_utc)
    transit = datetime.fromisoformat(entry.transit_utc)
    dw_start = datetime.fromisoformat(plan.dark_window["start_utc"])
    dw_end = datetime.fromisoformat(plan.dark_window["end_utc"])
    assert dw_start <= start <= transit <= end <= dw_end
    # Contiguous window (no horizon mask): span + one 5-min step ≈ usable minutes.
    span_min = (end - start).total_seconds() / 60.0
    assert span_min == pytest.approx(entry.minutes_above_min_alt - 5.0, abs=0.1)


def test_usable_window_is_none_for_a_never_usable_target():
    south = LibraryTarget(safe="deep-south", name="Deep South", ra_deg=90.0,
                          dec_deg=-70.0, frames_accepted=0, total_exposure_s=0.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[south],
                        include_catalog=False, min_altitude_deg=30.0)
    entry = next(p for p in plan.targets if p.id == "deep-south")
    assert entry.usable_start_utc is None
    assert entry.usable_end_utc is None


def test_plan_is_deterministic():
    a = plan_tonight(LONDON, JAN_EVENING)
    b = plan_tonight(LONDON, JAN_EVENING)
    assert [(p.id, p.score, p.max_altitude_deg) for p in a.targets] == \
           [(p.id, p.score, p.max_altitude_deg) for p in b.targets]


def test_horizon_profile_from_pairs_sanitises_input():
    # Malformed / non-finite / short entries are dropped; azimuth wraps into
    # [0, 360); altitude clamps into [0, 90]; a repeated azimuth keeps the taller
    # obstruction; the survivors come out sorted by azimuth.
    prof = HorizonProfile.from_pairs([
        [370.0, 15.0],     # az wraps to 10
        ["x", "y"],        # non-numeric → dropped
        [90.0],            # too short → dropped
        [45.0, 200.0],     # alt clamps to 90
        [45.0, 30.0],      # same az → keep the taller (90)
        [180.0, -5.0],     # alt clamps to 0
        None,              # not a pair → dropped
    ])
    assert prof.points == ((10.0, 15.0), (45.0, 90.0), (180.0, 0.0))
    assert not prof.is_empty()
    assert HorizonProfile.from_pairs([]).is_empty()
    assert HorizonProfile.from_pairs(None).is_empty()


def test_horizon_profile_interpolates_with_wraparound():
    prof = HorizonProfile.from_pairs([[0.0, 10.0], [180.0, 40.0]])
    # Exact points, the linear midpoint, and the wrap-around seam (180→360≡0).
    assert float(prof.altitude_at(0.0)) == pytest.approx(10.0)
    assert float(prof.altitude_at(180.0)) == pytest.approx(40.0)
    assert float(prof.altitude_at(90.0)) == pytest.approx(25.0)
    assert float(prof.altitude_at(270.0)) == pytest.approx(25.0)
    # Empty profile blocks nothing (0° everywhere), array in / array out.
    empty = HorizonProfile.from_pairs([])
    assert list(empty.altitude_at([12.0, 200.0])) == [0.0, 0.0]


# Orion transits around 33° from London — high enough to clear a 20° floor for
# hours, but a wall raised above its peak hides it entirely.
_M42 = LibraryTarget(safe="M42", name="Orion Nebula", ra_deg=83.82, dec_deg=-5.39,
                     frames_accepted=1, total_exposure_s=1.0)


def _m42_entry(horizon, min_alt=20.0):
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[_M42],
                        include_catalog=False, min_altitude_deg=min_alt,
                        horizon=horizon)
    return plan, next(p for p in plan.targets if p.id == "M42")


def test_empty_horizon_matches_no_horizon():
    # An empty / absent mask must leave the plan byte-for-byte unchanged.
    base_plan, base = _m42_entry(None)
    empty_plan, empty = _m42_entry(HorizonProfile.from_pairs([]))
    assert base_plan.horizon_active is False
    assert empty_plan.horizon_active is False
    assert (empty.minutes_above_min_alt, empty.score, empty.max_altitude_deg) == \
           (base.minutes_above_min_alt, base.score, base.max_altitude_deg)


def test_horizon_below_min_altitude_changes_nothing():
    # A wall lower than the numeric min-altitude floor is subsumed by it.
    _, base = _m42_entry(None)
    plan, low = _m42_entry(HorizonProfile.from_pairs([[0.0, 10.0]]))
    assert plan.horizon_active is True  # a mask *is* set …
    # … but it doesn't touch a target that already clears the min-altitude floor.
    assert low.minutes_above_min_alt == base.minutes_above_min_alt
    assert low.score == base.score


def test_horizon_wall_trims_usable_window_and_score():
    # A 30° wall (above the 20° floor, below Orion's ~33° peak) leaves only the
    # slice of the night Orion spends above 30° — fewer minutes, lower score,
    # but the honest physical peak altitude is unchanged.
    _, base = _m42_entry(None)
    _, walled = _m42_entry(HorizonProfile.from_pairs([[0.0, 30.0]]))
    assert walled.max_altitude_deg == base.max_altitude_deg
    assert 0.0 < walled.minutes_above_min_alt < base.minutes_above_min_alt
    assert 0.0 < walled.score < base.score
    assert walled.transit_utc is not None


def test_horizon_wall_above_peak_hides_target():
    # A 40° wall everywhere is above Orion's transit, so it never clears the
    # trees tonight: no usable window, no transit, score 0.
    plan, hidden = _m42_entry(HorizonProfile.from_pairs([[0.0, 40.0]]))
    assert plan.horizon_active is True
    assert hidden.minutes_above_min_alt == 0.0
    assert hidden.score == 0.0
    assert hidden.transit_utc is None
    assert hidden.max_altitude_deg == pytest.approx(33.1, abs=1.0)


def test_polar_day_returns_empty_plan_gracefully():
    svalbard = Observer(lat_deg=78.2, lon_deg=15.6, elevation_m=0.0)
    plan = plan_tonight(svalbard, datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc))
    assert plan.dark_window is None
    assert plan.targets == []
    # Still reports the Moon and observer so the UI can explain why it's empty.
    assert 0.0 <= plan.moon_illumination <= 1.0
    assert plan.observer["lat_deg"] == pytest.approx(78.2)
