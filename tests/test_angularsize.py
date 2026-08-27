"""The "how big is it, really?" full-Moon line (:mod:`seestack.angularsize`).

Pure and offline, so these are exact-string tests: the sentence *is* the
feature. The catalog half is checked too — that a beginner's favourite big
targets actually get a line rather than silence, and that the small ones stay
quiet.
"""

import math

import pytest

from seestack.angularsize import MOON_DIAMETER_ARCMIN, angular_size
from seestack.nightplan import load_catalog
from seestack.objectinfo import identify_object


def test_no_size_means_no_line():
    # Never guess: an object the catalog has no vetted size for renders nothing
    # at all, exactly as the framing hint and light-travel line already do.
    assert angular_size(None) is None
    assert angular_size(0) is None
    assert angular_size(-5) is None
    assert angular_size(float("nan")) is None
    assert angular_size(float("inf")) is None


def test_the_headline_case_reads_the_way_the_feature_was_pitched():
    # M 31's catalog major axis. "Andromeda is six Moons across" is the whole
    # point of the feature.
    a = angular_size(178)
    assert a is not None
    assert a.text == "In the sky it's about as wide as 6 full Moons."
    assert a.size_arcmin == 178
    assert a.moons == pytest.approx(178 / 31.0)


@pytest.mark.parametrize(("size_arcmin", "text"), [
    # Counting Moons, rounded hard — never a decimal.
    (178, "In the sky it's about as wide as 6 full Moons."),
    (120, "In the sky it's about as wide as 4 full Moons."),
    (77.5, "In the sky it's about as wide as 2½ full Moons."),
    (62, "In the sky it's about as wide as 2 full Moons."),
    (46.5, "In the sky it's about as wide as 1½ full Moons."),
    (41, "In the sky it's about as wide as 1½ full Moons."),     # just into the count band
    # Fractions of one Moon.
    (40, "In the sky it's roughly as wide as the full Moon."),    # just below it
    (31, "In the sky it's roughly as wide as the full Moon."),
    (25, "In the sky it's roughly as wide as the full Moon."),
    (22, "In the sky it's about three-quarters as wide as the full Moon."),
    (15, "In the sky it's about half as wide as the full Moon."),
    (10, "In the sky it's about a third as wide as the full Moon."),
])
def test_each_band_says_the_thing_that_is_true_across_it(size_arcmin, text):
    a = angular_size(size_arcmin)
    assert a is not None and a.text == text


@pytest.mark.parametrize("size_arcmin", [8.6, 4, 1.4, 0.5])
def test_a_small_target_stays_quiet_rather_than_saying_nothing_useful(size_arcmin):
    # Below about a third of a Moon the comparison stops being illuminating, and
    # the framing line above already says it fits comfortably in one frame.
    assert angular_size(size_arcmin) is None


def test_the_quiet_threshold_is_exactly_where_the_lowest_band_starts():
    """No gap and no overlap between "say nothing" and the smallest phrase — a
    size a hair above the floor must get the "a third" line, one a hair below
    must get silence."""
    from seestack.angularsize import _QUIET_BELOW_MOONS

    floor = _QUIET_BELOW_MOONS * MOON_DIAMETER_ARCMIN
    assert angular_size(floor * 0.999) is None
    just_above = angular_size(floor * 1.001)
    assert just_above is not None
    assert "a third" in just_above.text


def test_the_count_is_never_a_decimal_and_never_ungrammatical():
    """The rounding property, swept across the whole range the catalog can
    produce: a beginner wants "6 Moons", never "5.74 Moons" — and never
    "1 full Moons" either."""
    size = MOON_DIAMETER_ARCMIN * 0.28
    while size < MOON_DIAMETER_ARCMIN * 60:
        a = angular_size(size)
        assert a is not None, size
        assert "." not in a.text.removesuffix("."), a.text
        assert " 1 full Moons" not in a.text, a.text
        size *= 1.01


def test_halves_stop_where_they_stop_meaning_anything():
    # Below three Moons a half is picturable; above it, halves are false
    # precision, so the count is whole.
    assert angular_size(MOON_DIAMETER_ARCMIN * 2.5) is not None
    assert "2½" in angular_size(MOON_DIAMETER_ARCMIN * 2.5).text
    assert "½" not in angular_size(MOON_DIAMETER_ARCMIN * 3.5).text
    assert "4 full Moons" in angular_size(MOON_DIAMETER_ARCMIN * 3.5).text


def test_the_moon_reference_can_be_overridden_and_stays_grammatical():
    # The Moon's apparent diameter really does vary over the month (~29.4' at
    # apogee to ~33.5' at perigee), so the reference is a parameter — but the
    # sentence must stay well-formed at either extreme, and a nonsensical
    # reference must produce silence rather than a divide-by-zero.
    for moon in (29.4, 31.0, 33.5):
        a = angular_size(178, moon_arcmin=moon)
        assert a is not None and a.text.endswith("full Moons.")
    assert angular_size(178, moon_arcmin=0) is None
    assert angular_size(178, moon_arcmin=-1) is None
    assert angular_size(178, moon_arcmin=float("nan")) is None


def test_moons_is_the_honest_unrounded_ratio():
    a = angular_size(178)
    assert a is not None
    assert a.moons == pytest.approx(5.741935, rel=1e-5)
    assert math.isfinite(a.moons)


def test_a_beginners_favourite_big_target_gets_a_line_end_to_end():
    info = identify_object("M_31")
    assert info is not None and info.angular_size is not None
    assert info.angular_size.text == "In the sky it's about as wide as 6 full Moons."
    # The Pleiades are ~110' — another classic "bigger than you think" target.
    pleiades = identify_object("M 45")
    assert pleiades is not None and pleiades.angular_size is not None
    assert "full Moons" in pleiades.angular_size.text


def test_a_small_catalog_target_gets_no_line_end_to_end():
    # M 57 (the Ring) is ~1.4' — well below the quiet floor, so the card simply
    # says nothing rather than an unhelpful "well under the full Moon".
    ring = identify_object("M 57")
    assert ring is not None
    assert ring.angular_size is None


def test_the_line_never_contradicts_the_framing_hint_on_a_real_catalog_object():
    """The two lines sit one above the other on the same card, so they must
    agree: anything the framing hint calls bigger than a single Seestar frame
    (77') is more than two Moons, and must therefore be counting Moons."""
    for obj in load_catalog():
        a = angular_size(obj.size_arcmin)
        if obj.size_arcmin is not None and obj.size_arcmin > 77.0:
            assert a is not None, obj.id
            assert "full Moons" in a.text, (obj.id, a.text)
