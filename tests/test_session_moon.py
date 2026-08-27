""""Was the Moon washing this out?" — the retrospective moonlight verdict.

The planner already warns about the Moon *before* a night. This is the missing
other half: after the fact, when a beginner is looking at a flat, low-contrast
picture and quietly concluding their gear or their editing is at fault. The
whole design goal is that it stays **silent** unless the Moon genuinely hurt the
session — so most of these tests pin the silence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from astropy.coordinates import get_body
from astropy.time import Time

from seestack.nightplan import Observer, session_moon

LONDON = Observer(lat_deg=51.5, lon_deg=-0.1)

# 2026-01-03 02:00 UTC is a ~100%-lit Moon, high in the London sky.
FULL_MOON_UP = datetime(2026, 1, 3, 2, 0, tzinfo=timezone.utc)
# 2026-01-19 02:00 UTC is a new Moon, and below the horizon there besides.
NEW_MOON_DOWN = datetime(2026, 1, 19, 2, 0, tzinfo=timezone.utc)


def _moon_radec(when: datetime) -> tuple[float, float]:
    """Where the Moon actually was, so a test can place a target relative to it."""
    t = Time(when.replace(tzinfo=None), scale="utc")
    m = get_body("moon", t, LONDON.earth_location()).icrs
    return float(m.ra.deg), float(m.dec.deg)


def _near_the_moon(when: datetime, sep_deg: float = 20.0) -> tuple[float, float]:
    ra, dec = _moon_radec(when)
    return ra, dec - sep_deg


def _away_from_the_moon(when: datetime) -> tuple[float, float]:
    ra, dec = _moon_radec(when)
    return (ra + 180.0) % 360.0, -dec


def test_a_bright_moon_close_by_earns_the_note():
    """The one case worth speaking up about."""
    ra, dec = _near_the_moon(FULL_MOON_UP)
    verdict = session_moon(LONDON, ra, dec, FULL_MOON_UP)

    assert verdict.level == "poor"
    assert verdict.text is not None
    # The numbers are in the sentence, so it reads as an observation and not a
    # canned warning.
    assert "100%-lit Moon" in verdict.text
    assert "20°" in verdict.text
    # It names the cause, absolves the user, and points at the fix.
    assert "not your setup" in verdict.text
    assert "dark-Moon night" in verdict.text
    # ...and it is never phrased as something the user did wrong.
    lowered = verdict.text.lower()
    assert "should have" not in lowered
    assert "mistake" not in lowered


def test_a_moon_on_the_other_side_of_the_sky_says_nothing():
    """Bright, but far — a beginner shooting there wasn't hurt by it."""
    ra, dec = _away_from_the_moon(FULL_MOON_UP)
    verdict = session_moon(LONDON, ra, dec, FULL_MOON_UP)
    assert verdict.level != "poor"
    assert verdict.text is None


def test_a_new_moon_below_the_horizon_says_nothing():
    """The common case. Silence is the whole point — this must never nag."""
    ra, dec = _near_the_moon(NEW_MOON_DOWN)
    verdict = session_moon(LONDON, ra, dec, NEW_MOON_DOWN)
    assert verdict.level == "good"
    assert verdict.text is None
    assert verdict.moon_altitude_deg < 0


def test_a_moon_that_had_already_set_says_nothing_however_bright_it_was():
    """Altitude gates everything: a Moon below the horizon can't wash anything out."""
    # Half a day from the full-Moon instant puts it under the horizon at the same
    # illumination.
    when = FULL_MOON_UP + timedelta(hours=12)
    ra, dec = _near_the_moon(when)
    verdict = session_moon(LONDON, ra, dec, when)
    assert verdict.moon_altitude_deg < 0
    assert verdict.level == "good"
    assert verdict.text is None


def test_the_readout_describes_the_session_midpoint():
    """A Seestar session runs for hours; the midpoint is the honest single sample."""
    start = FULL_MOON_UP
    end = FULL_MOON_UP + timedelta(hours=4)
    ra, dec = _near_the_moon(start)
    verdict = session_moon(LONDON, ra, dec, start, end)
    assert verdict.at_utc == (start + timedelta(hours=2)).isoformat()


def test_a_backwards_session_is_taken_as_written_not_as_an_error():
    """A frames table can hand us end < start; that must not move the answer."""
    start = FULL_MOON_UP
    end = FULL_MOON_UP + timedelta(hours=4)
    ra, dec = _near_the_moon(start)
    forwards = session_moon(LONDON, ra, dec, start, end)
    backwards = session_moon(LONDON, ra, dec, end, start)
    assert backwards.at_utc == forwards.at_utc
    assert backwards.text == forwards.text


def test_an_instant_session_needs_no_end():
    ra, dec = _near_the_moon(FULL_MOON_UP)
    assert (session_moon(LONDON, ra, dec, FULL_MOON_UP).at_utc
            == session_moon(LONDON, ra, dec, FULL_MOON_UP, FULL_MOON_UP).at_utc)


def test_a_naive_local_time_is_read_as_the_zone_it_carries():
    """Callers hand us aware datetimes; a non-UTC zone must still land right."""
    aware_ny = FULL_MOON_UP.astimezone(timezone(timedelta(hours=-5)))
    ra, dec = _near_the_moon(FULL_MOON_UP)
    assert (session_moon(LONDON, ra, dec, aware_ny).at_utc
            == session_moon(LONDON, ra, dec, FULL_MOON_UP).at_utc)


@pytest.mark.parametrize("when", [FULL_MOON_UP, NEW_MOON_DOWN])
def test_the_numbers_are_always_reported_even_when_the_sentence_is_not(when):
    """The verdict object is complete either way, so a caller can show its own copy."""
    ra, dec = _near_the_moon(when)
    verdict = session_moon(LONDON, ra, dec, when)
    assert 0.0 <= verdict.illumination <= 1.0
    assert -90.0 <= verdict.moon_altitude_deg <= 90.0
    assert 0.0 <= verdict.separation_deg <= 180.0
    assert verdict.level in {"good", "ok", "poor"}


def test_it_agrees_with_the_forward_looking_readout_on_the_same_instant():
    """One geometry helper feeds both, so tonight's warning and the retrospective
    note can never grade the same sky differently."""
    from seestack.nightplan import _moon_geometry, _moon_verdict

    ra, dec = _near_the_moon(FULL_MOON_UP)
    illum, alt, sep = _moon_geometry(LONDON, ra, dec, FULL_MOON_UP)
    level, _ = _moon_verdict(illum, alt, sep)
    assert session_moon(LONDON, ra, dec, FULL_MOON_UP).level == level
