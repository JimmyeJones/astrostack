"""Tests for the pure angular scale-bar helper (``seestack/scalebar.py``)."""

from seestack.scalebar import (
    MOON_DIAMETER_ARCSEC,
    scale_bar_for,
    _MAX_BAR_FRACTION,
)


def test_picks_a_round_bar_within_the_width_limit():
    # A Seestar-ish frame: ~1.5″/px over 1920 px → ~48′ wide. A 15% target lands
    # near ~7′; the largest nice rung under 25% (720″=12′) is chosen.
    bar = scale_bar_for(1.5, 1920, 1080)
    assert bar is not None
    frame_arcsec = 1.5 * 1920
    # The bar never exceeds the width limit and is a labelled round number.
    assert bar.arcsec <= frame_arcsec * _MAX_BAR_FRACTION
    assert bar.label.endswith("′") or bar.label.endswith("°") or bar.label.endswith("″")
    # fraction is the bar length / image width.
    assert abs(bar.fraction - bar.arcsec / frame_arcsec) < 1e-9
    assert 0 < bar.fraction <= _MAX_BAR_FRACTION


def test_labels_scale_with_the_unit():
    # A wide, coarse field (10″/px × 3600 px = 10° wide) picks a degree-scale bar.
    wide = scale_bar_for(10.0, 3600)
    assert wide is not None
    assert wide.label.endswith("°")
    # A narrow, fine field (0.2″/px × 1000 px = 200″ wide) picks an arcsecond bar.
    narrow = scale_bar_for(0.2, 1000)
    assert narrow is not None
    assert narrow.label.endswith("″")


def test_chooses_the_largest_rung_under_the_limit():
    # frame = 1″/px × 4000 px = 4000″; limit = 25% = 1000″. Largest rung ≤1000 is
    # 900″ (15′).
    bar = scale_bar_for(1.0, 4000)
    assert bar is not None
    assert bar.arcsec == 900.0
    assert bar.label == "15′"


def test_moon_comparison_bands():
    # A frame exactly one Moon wide reads "about as wide as the full Moon".
    one_moon = scale_bar_for(MOON_DIAMETER_ARCSEC / 1000, 1000)
    assert one_moon is not None
    assert "as wide as the full Moon" in one_moon.moon_comparison
    # A big frame (5 Moons) counts Moons.
    big = scale_bar_for(5 * MOON_DIAMETER_ARCSEC / 1000, 1000)
    assert big is not None
    assert "full Moons wide" in big.moon_comparison
    assert "5.0" in big.moon_comparison
    # A small frame (¼ Moon) reads as a percentage of the Moon's width.
    small = scale_bar_for(0.25 * MOON_DIAMETER_ARCSEC / 1000, 1000)
    assert small is not None
    assert "% the width of the full Moon" in small.moon_comparison
    assert "25%" in small.moon_comparison


def test_frame_arcmin_reported():
    bar = scale_bar_for(1.0, 1800)  # 1800″ = 30′ wide
    assert bar is not None
    assert abs(bar.frame_arcmin - 30.0) < 1e-9


def test_none_for_unusable_inputs():
    assert scale_bar_for(0.0, 1000) is None
    assert scale_bar_for(-1.0, 1000) is None
    assert scale_bar_for(1.0, 0) is None
    assert scale_bar_for(float("nan"), 1000) is None
    assert scale_bar_for(float("inf"), 1000) is None


def test_falls_back_to_smallest_rung_on_a_tiny_frame():
    # A frame narrower than 4× the smallest rung: even 1″ overflows 25%, so we
    # still offer the smallest rung rather than nothing.
    bar = scale_bar_for(1.0, 3)  # 3″ wide, limit 0.75″ < 1″
    assert bar is not None
    assert bar.arcsec == 1.0
    assert bar.label == "1″"
    assert bar.fraction > _MAX_BAR_FRACTION  # honestly wider than the target


def test_to_dict_shape():
    bar = scale_bar_for(1.5, 1920)
    assert bar is not None
    d = bar.to_dict()
    assert set(d) == {"arcsec", "label", "fraction", "frame_arcmin", "moon_comparison"}
