"""Night-by-night sky-brightness read (the "was last night's sky bright?" card)."""

from seestack.qc.sky_quality import (
    MIN_FRAMES_PER_NIGHT,
    MIN_NIGHTS,
    SkySample,
    night_sky_rates,
    sky_brightness,
)


def _night(day: str, *, sky: float, n: int = MIN_FRAMES_PER_NIGHT,
           exposure: float = 10.0, gain: float = 80.0) -> list[SkySample]:
    """``n`` subs captured on the night of ``day`` at a given sky level."""
    return [
        SkySample(timestamp_utc=f"{day}T2{i % 4}:0{i % 6}:00Z", sky_adu_median=sky,
                  exposure_s=exposure, gain=gain)
        for i in range(n)
    ]


def _three_typical_nights(sky: float = 1000.0) -> list[SkySample]:
    return (_night("2026-07-20", sky=sky) + _night("2026-07-21", sky=sky)
            + _night("2026-07-22", sky=sky))


def test_hidden_without_enough_nights():
    """With no "usual" to compare against there is no honest answer, so the card
    stays hidden rather than guessing from one night."""
    assert sky_brightness([]) is None
    assert sky_brightness(_night("2026-07-20", sky=1000.0)) is None
    assert sky_brightness(_night("2026-07-20", sky=1000.0)
                          + _night("2026-07-21", sky=1000.0)) is None


def test_hidden_when_a_night_has_too_few_measured_subs():
    """One hazy patch of sky must not set a whole night's verdict."""
    thin = []
    for day in ("2026-07-20", "2026-07-21", "2026-07-22"):
        thin += _night(day, sky=1000.0, n=MIN_FRAMES_PER_NIGHT - 1)
    assert sky_brightness(thin) is None
    assert night_sky_rates(thin) == {}


def test_typical_night_reads_as_typical():
    read = sky_brightness(_three_typical_nights())
    assert read is not None
    assert read.level == "typical"
    assert read.nights == MIN_NIGHTS
    assert read.night == "2026-07-22"
    assert 0.95 < read.ratio < 1.05
    assert "as bright as your other" in read.text


def test_a_much_brighter_night_is_called_out_with_advice():
    read = sky_brightness(_three_typical_nights() + _night("2026-07-23", sky=2500.0))
    assert read is not None
    assert read.level == "much_brighter"
    assert read.night == "2026-07-23"
    assert read.ratio > 1.8
    # Actionable, and honest about what more subs can't fix.
    assert "darker night" in read.text
    assert "%" in read.text


def test_a_moderately_brighter_night_is_a_gentler_warning():
    read = sky_brightness(_three_typical_nights() + _night("2026-07-23", sky=1450.0))
    assert read is not None
    assert read.level == "brighter"
    assert "washed-out" in read.text


def test_a_darker_night_is_encouraged():
    read = sky_brightness(_three_typical_nights() + _night("2026-07-23", sky=600.0))
    assert read is not None
    assert read.level == "darker"
    assert "best chance" in read.text


def test_exposure_is_normalised_out():
    """A longer sub collects proportionally more sky, so doubling the exposure and
    the measured sky is the *same* sky — it must not read as a brighter night."""
    samples = _three_typical_nights()
    samples += _night("2026-07-23", sky=2000.0, exposure=20.0, gain=80.0)
    # The 20 s frames are their own (gain, exposure) group and are the minority,
    # so they're excluded entirely; the answer comes from the 10 s nights.
    read = sky_brightness(samples)
    assert read is not None
    assert read.night == "2026-07-22"

    # When the long subs dominate instead, they set the baseline themselves and
    # still read as an ordinary sky (rate 100 ADU/s either way).
    long_dominant = (_night("2026-07-20", sky=2000.0, exposure=20.0)
                     + _night("2026-07-21", sky=2000.0, exposure=20.0)
                     + _night("2026-07-22", sky=2000.0, exposure=20.0)
                     + _night("2026-07-23", sky=1000.0, exposure=10.0))
    read = sky_brightness(long_dominant)
    assert read is not None
    assert read.level == "typical"
    assert read.night == "2026-07-22"


def test_a_gain_change_is_not_mistaken_for_a_brighter_sky():
    """Sky ADU scales with gain too, so mixing gains would read as a sky change."""
    samples = _three_typical_nights()
    samples += _night("2026-07-23", sky=4000.0, gain=200.0)   # minority setting
    read = sky_brightness(samples)
    assert read is not None
    assert read.night == "2026-07-22"          # the gain-200 night is excluded
    assert read.level == "typical"


def test_subs_across_midnight_count_as_one_night():
    """A session that runs past midnight is one observing night, not two — else
    the after-midnight half becomes its own sparse, untrustworthy 'night'."""
    samples = _three_typical_nights()
    late = [SkySample(f"2026-07-23T23:{i:02d}:00Z", 1000.0, 10.0, 80.0) for i in range(3)]
    early = [SkySample(f"2026-07-24T00:{i:02d}:00Z", 1000.0, 10.0, 80.0) for i in range(3)]
    rates = night_sky_rates(samples + late + early)
    # 6 subs straddling midnight form one qualifying night (dated the 23rd), not
    # two 3-sub nights that would both fall under MIN_FRAMES_PER_NIGHT.
    assert [n.isoformat() for n in sorted(rates)][-1] == "2026-07-23"


def test_unusable_rows_are_skipped_not_fatal():
    """Missing/zero exposure, missing sky, a bad timestamp or a negative sky are
    dropped rows, never an exception."""
    junk = [
        SkySample(None, 1000.0, 10.0, 80.0),
        SkySample("2026-07-22T22:00:00Z", None, 10.0, 80.0),
        SkySample("2026-07-22T22:00:00Z", 1000.0, None, 80.0),
        SkySample("2026-07-22T22:00:00Z", 1000.0, 0.0, 80.0),
        SkySample("2026-07-22T22:00:00Z", 1000.0, -5.0, 80.0),
        SkySample("2026-07-22T22:00:00Z", -3.0, 10.0, 80.0),
        SkySample("not a timestamp", 1000.0, 10.0, 80.0),
        SkySample("2026-07-22T22:00:00Z", float("nan"), 10.0, 80.0),
    ]
    assert night_sky_rates(junk) == {}
    assert sky_brightness(junk) is None
    # Mixed in with real data they simply don't contribute.
    read = sky_brightness(_three_typical_nights() + junk)
    assert read is not None and read.level == "typical"


def test_a_missing_gain_still_groups():
    """Older frames may carry no gain; they must still form a usable group."""
    samples = []
    for day in ("2026-07-20", "2026-07-21", "2026-07-22"):
        samples += [SkySample(f"{day}T22:0{i}:00Z", 1000.0, 10.0, None)
                    for i in range(MIN_FRAMES_PER_NIGHT)]
    read = sky_brightness(samples)
    assert read is not None and read.level == "typical"


def test_serialises_to_json_safe_primitives():
    read = sky_brightness(_three_typical_nights() + _night("2026-07-23", sky=2500.0))
    assert read is not None
    d = read.as_dict()
    assert set(d) == {"level", "label", "text", "night", "nights", "ratio"}
    assert isinstance(d["ratio"], float) and isinstance(d["nights"], int)
    assert all(isinstance(d[k], str) for k in ("level", "label", "text", "night"))


def test_longitude_shifts_the_night_boundary():
    """The night key follows the observer's local noon-to-noon window, so a
    far-east site groups its after-midnight subs the same way its clock does."""
    samples = [SkySample(f"2026-07-23T02:0{i}:00Z", 1000.0, 10.0, 80.0) for i in range(5)]
    utc = night_sky_rates(samples)
    east = night_sky_rates(samples, lon_deg=150.0)   # ~UTC+10
    # 02:00 UTC is the small hours of the night of the 22nd for a UTC observer,
    # but midday-following-the-night-of-the-23rd for a site 10 h ahead.
    assert [n.isoformat() for n in utc] == ["2026-07-22"]
    assert [n.isoformat() for n in east] == ["2026-07-23"]
