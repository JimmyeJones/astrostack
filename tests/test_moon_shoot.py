"""Tonight's Moon as a *subject* — ``seestack.nightplan.moon_shoot_tonight``.

Everything else in the planner treats the Moon as interference. This is the other
half a Seestar owner actually uses: the app plans a Moon session now, from the
same ephemeris, and says the one counter-intuitive thing about them — that a
**full** Moon is the worst night for surface detail, because nothing casts a
shadow when the Sun is behind you.

The verdict half is pure and pinned exactly. The window half is pinned on three
**real** January 2026 nights from London, each chosen because it exhibits a
different branch (measured before they were written in, and quoted in each test):

    2026-01-03  99.6% lit   up 18:38-06:38, peak 63 deg   -> a full-Moon session
    2026-01-25  45.9% lit   up 16:35-22:35, peak 53 deg   -> the *great* one
    2026-01-21   9.2% lit   up 16:31-16:46, peak 22 deg   -> 15 min: too short
    2026-01-15   8.5% lit   never above 20 deg in the dark -> nothing to say

Their windows are asserted by *property* (inside the night, above the floor, long
enough to be a session) rather than as a snapshot, so refraction and the sampling
grid can move a stamp a few minutes without the test lying about what it checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from seestack import nightplan as np_plan
from seestack.nightplan import (
    MOON_SHOOT_MIN_ALT_DEG,
    MOON_SHOOT_MIN_MINUTES,
    Observer,
    _find_dark_window,
    _moon_shoot_verdict,
    _widest_true_run,
    moon_illumination,
    moon_is_waxing,
    moon_shoot_tonight,
    plan_tonight,
)

LONDON = Observer(lat_deg=51.5, lon_deg=-0.13, elevation_m=30.0)

FULL_MOON_NIGHT = "2026-01-03T20:00:00"      # 99.6% lit — up most of the night
QUARTER_MOON_NIGHT = "2026-01-25T20:00:00"   # 45.9% lit — the terminator night
SLIVER_NIGHT = "2026-01-21T20:00:00"         # 9.2% lit — up for 15 minutes
MOONLESS_NIGHT = "2026-01-15T20:00:00"       # 8.5% lit — never clears the floor


def _at(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The verdict — the whole point of the feature, and pure


@pytest.mark.parametrize(("illum", "level"), [
    (0.00, "thin"),
    (0.05, "thin"),
    (0.14, "thin"),
    (0.15, "great"),
    (0.30, "great"),
    (0.50, "great"),
    (0.84, "great"),
    (0.85, "good"),
    (0.93, "good"),
    (0.97, "flat"),
    (1.00, "flat"),
])
def test_the_phase_decides_the_verdict_at_every_band(illum, level):
    assert _moon_shoot_verdict(illum, True)[0] == level


def test_a_full_moon_is_called_out_as_the_worst_night_for_detail():
    """The counter-intuitive fact, and the reason this feature exists: a beginner
    assumes a bright full Moon is the best Moon to photograph."""
    level, text = _moon_shoot_verdict(0.99, False)
    assert level == "flat"
    assert "99%" in text
    # It says *why* — no shadows — rather than just "not great".
    assert "shadow" in text
    # …and what to do instead, which is the actionable half.
    assert "either side of full" in text


def test_the_best_phases_point_at_the_terminator():
    _, text = _moon_shoot_verdict(0.45, True)
    assert "45%" in text
    assert "lit and unlit halves" in text
    assert "shadows" in text


def test_every_verdict_names_the_percentage_and_is_a_real_sentence():
    """No band may fall through to an empty or number-less sentence — the card
    renders this text verbatim."""
    for illum in (0.0, 0.1, 0.2, 0.5, 0.9, 0.96, 1.0):
        level, text = _moon_shoot_verdict(illum, True)
        assert level in {"thin", "great", "good", "flat"}
        assert f"{round(illum * 100)}%" in text
        assert text.endswith(".") and len(text) > 60


# ---------------------------------------------------------------------------
# The window, on real nights


def _window(when: str):
    w = _find_dark_window(LONDON, _at(when))
    assert w is not None, f"no dark window for {when}"
    return w


def _shoot(when: str):
    w = _window(when)
    at = _at(when)
    return w, moon_shoot_tonight(
        LONDON, w,
        illumination=moon_illumination(at), waxing=moon_is_waxing(at),
    )


def test_a_full_moon_night_offers_a_real_window_inside_the_night():
    """2026-01-03 from London: the Moon is 99.6% lit and up for essentially the
    whole night — unmistakably shootable, and the verdict says it will look
    flat."""
    window, shoot = _shoot(FULL_MOON_NIGHT)
    assert shoot is not None
    assert shoot.level == "flat"
    start = datetime.fromisoformat(shoot.start_utc)
    end = datetime.fromisoformat(shoot.end_utc)
    # A genuine session, not a graze past the floor…
    assert (end - start).total_seconds() / 60.0 >= MOON_SHOOT_MIN_MINUTES
    # …inside the span the scan is allowed to look at…
    assert window.start - timedelta(hours=6) <= start < end
    assert end <= window.end + timedelta(hours=6)
    # …and high enough to be worth pointing at (measured: 63 deg).
    assert shoot.peak_altitude_deg >= MOON_SHOOT_MIN_ALT_DEG


def test_the_terminator_night_is_the_one_it_calls_great():
    """2026-01-25: 45.9% lit, up 16:35-22:35, peak 53 deg. This is the night the
    feature exists to point at — an evening Moon with the day/night line straight
    across the face."""
    _, shoot = _shoot(QUARTER_MOON_NIGHT)
    assert shoot is not None
    assert shoot.level == "great"
    start = datetime.fromisoformat(shoot.start_utc)
    end = datetime.fromisoformat(shoot.end_utc)
    assert (end - start) >= timedelta(hours=4)
    assert shoot.peak_altitude_deg > 45.0


def test_the_window_is_never_daylight_and_never_below_the_floor():
    """The two conditions, re-checked against the real ephemeris rather than
    against the mask that built the answer: the Sun is down and the Moon is up
    throughout the stretch handed to the user."""
    _, shoot = _shoot(QUARTER_MOON_NIGHT)
    assert shoot is not None
    start = datetime.fromisoformat(shoot.start_utc)
    end = datetime.fromisoformat(shoot.end_utc)
    location = LONDON.earth_location()
    _stamps, times = np_plan._times_grid(start, end, 15.0)
    assert (np_plan._sun_altitudes(times, location) < 0.0).all()
    # The endpoints sit on the 15-minute grid the answer was sampled on, so allow
    # the one step of slack an interval boundary can carry.
    assert np_plan._moon_altitudes(times, location).min() >= \
        MOON_SHOOT_MIN_ALT_DEG - 3.0


def test_it_says_nothing_at_all_when_the_moon_never_clears_the_floor():
    """The self-hiding case, and a common one — 2026-01-15 from London is a
    waning crescent that is simply never 20 deg up while the Sun is down. A card
    with no window is not a card: the plan carries ``None`` and the UI renders
    nothing rather than an empty Moon panel."""
    _, shoot = _shoot(MOONLESS_NIGHT)
    assert shoot is None


def test_a_window_too_short_to_be_a_session_is_not_offered():
    """2026-01-21: the sliver clears 20 deg for **15 minutes** (16:31-16:46,
    measured) before setting. Offering "up 16:31-16:46" reads as a bug rather
    than a plan, so the minimum-duration guard declines it — and this is a real
    night exercising that branch, not an injected one."""
    _, shoot = _shoot(SLIVER_NIGHT)
    assert shoot is None
    # Pin *why* it declined: there really is a stretch above the floor, it is
    # just too short. Without this the test would also pass if the Moon were
    # simply down, which is a different branch.
    window = _window(SLIVER_NIGHT)
    location = LONDON.earth_location()
    stamps, times = np_plan._times_grid(
        window.start - timedelta(hours=6), window.end + timedelta(hours=6), 15.0)
    usable = ((np_plan._moon_altitudes(times, location) >= MOON_SHOOT_MIN_ALT_DEG)
              & (np_plan._sun_altitudes(times, location) < 0.0))
    lo, hi = _widest_true_run(usable)
    assert lo is not None
    span_min = (stamps[hi] - stamps[lo]).total_seconds() / 60.0
    assert 0 < span_min < MOON_SHOOT_MIN_MINUTES


def test_the_verdict_matches_the_nights_own_illumination():
    """The two halves must describe one Moon: the level the plan reports is the
    level that night's phase implies, not a second opinion computed elsewhere."""
    at = _at(QUARTER_MOON_NIGHT)
    _, shoot = _shoot(QUARTER_MOON_NIGHT)
    assert shoot is not None
    assert shoot.level == _moon_shoot_verdict(moon_illumination(at),
                                              moon_is_waxing(at))[0]
    assert shoot.illumination == round(moon_illumination(at), 3)
    assert shoot.waxing == moon_is_waxing(at)
    # The sentence never bakes a clock time — those render in the viewer's zone.
    assert ":" not in shoot.text


# ---------------------------------------------------------------------------
# Wiring into the plan


def test_the_plan_carries_tonights_moon_session():
    plan = plan_tonight(LONDON, _at(QUARTER_MOON_NIGHT), include_catalog=False)
    assert plan.moon_shoot is not None
    assert plan.moon_shoot["level"] == "great"
    assert plan.moon_shoot["start_utc"] < plan.moon_shoot["end_utc"]


def test_the_plan_offers_no_session_on_a_moonless_night():
    plan = plan_tonight(LONDON, _at(MOONLESS_NIGHT), include_catalog=False)
    assert plan.dark_window is not None
    assert plan.moon_shoot is None


def test_a_plan_with_no_dark_window_offers_no_moon_session():
    """Polar summer: the Sun never sets, the planner returns early, and nothing
    downstream may invent a session out of a window that does not exist."""
    svalbard = Observer(lat_deg=78.2, lon_deg=15.6, elevation_m=0.0)
    plan = plan_tonight(svalbard, _at("2026-06-21T22:00:00"), include_catalog=False)
    assert plan.dark_window is None
    assert plan.moon_shoot is None


# ---------------------------------------------------------------------------
# The run-finder now shared with the dark-window scan


def test_the_widest_run_is_found_and_ties_go_to_the_later_one():
    """Extracted verbatim from ``_dark_window_after_noon`` so the two scans share
    one definition; this pins the behaviour that extraction had to preserve,
    including its ``>=`` tie-break (the *later* of two equal runs wins)."""
    assert _widest_true_run(np.array([False, True, True, False, True])) == (1, 2)
    # Two runs of equal length → the later one.
    assert _widest_true_run(np.array([True, False, True])) == (2, 2)
    assert _widest_true_run(np.array([True, True, False, True, True])) == (3, 4)


def test_the_widest_run_of_nothing_is_nothing():
    assert _widest_true_run(np.array([], dtype=bool)) == (None, None)
    assert _widest_true_run(np.array([False, False])) == (None, None)


def test_the_dark_window_is_unchanged_by_the_extraction():
    """The shared helper came out of the dark-window scan, which is behind every
    planner page. A fixed winter night in London still yields the astronomical
    dark window it always has (measured: 18:23-05:55 UTC)."""
    w = _window(MOONLESS_NIGHT)
    assert w.sun_alt_threshold_deg == -18.0
    assert w.start.hour == 18 and w.start.minute == 23
    assert w.end.hour == 5 and w.end.minute == 55
