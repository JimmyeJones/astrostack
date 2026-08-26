"""The "how far did you see?" light-travel line (:mod:`seestack.lighttravel`).

Pure and offline, so these are exact-string tests: the sentence *is* the
feature. The catalog half is checked too — that the vetted distances actually
load, and that a beginner's favourite targets get a line rather than silence.
"""

import pytest

from seestack.lighttravel import light_travel
from seestack.nightplan import load_catalog
from seestack.objectinfo import identify_object


def test_no_distance_means_no_line():
    # Never guess: an object the catalog has no vetted distance for renders
    # nothing at all, exactly as size_arcmin/framing already do.
    assert light_travel(None) is None
    assert light_travel(0) is None
    assert light_travel(-5) is None


def test_the_headline_case_reads_the_way_the_feature_was_pitched():
    lt = light_travel(2_500_000)
    assert lt is not None
    assert lt.text == (
        "The light in this picture left about 2.5 million years ago — "
        "before our species existed."
    )
    assert lt.years == "2.5 million years"
    assert lt.distance_ly == 2_500_000


@pytest.mark.parametrize(("distance_ly", "years"), [
    (444, "440 years"),            # nearest ten under a thousand
    (1_344, "1,340 years"),        # comma-grouped, NOT "1.3 thousand years"
    (9_500, "9,500 years"),        # still plain: "thousand" starts at 10k
    (10_000, "10 thousand years"),
    (22_200, "22 thousand years"),
    (655_000, "655 thousand years"),
    (1_000_000, "1 million years"),
    (11_800_000, "12 million years"),   # whole numbers once past ten of a unit
    (83_500_000, "84 million years"),
])
def test_the_duration_is_rounded_to_something_a_beginner_reads_at_a_glance(
        distance_ly, years):
    lt = light_travel(distance_ly)
    assert lt is not None and lt.years == years


@pytest.mark.parametrize(("distance_ly", "anchor"), [
    (440, None),                                    # no anchor holds this close
    (500, "before the telescope was invented"),
    (1_999, "before the telescope was invented"),
    (2_000, "before the Roman Empire fell"),
    (9_999, "before the Roman Empire fell"),
    (10_000, "before the first cities were built"),
    (99_999, "before the first cities were built"),
    (100_000, "long before recorded history"),
    (999_999, "long before recorded history"),
    (1_000_000, "before our species existed"),
])
def test_each_band_gets_the_strongest_anchor_that_is_still_true(distance_ly, anchor):
    lt = light_travel(distance_ly)
    assert lt is not None
    if anchor is None:
        # Nothing claimed — just the number, and the sentence still ends cleanly.
        assert lt.text.endswith("years ago.")
        assert "—" not in lt.text
    else:
        assert lt.text.endswith(f" — {anchor}.")


def test_the_anchors_never_overstate_at_their_own_floor():
    """The safety property: every anchor must be true at the *lowest* distance
    that can reach it, not just at a comfortable example. These are the margins
    the bands were chosen for — a band whose floor is younger than its claim
    would tell a beginner something false."""
    from seestack.lighttravel import _ANCHORS

    # (floor, the age of the thing the phrase points at, in years).
    ages = {
        "before our species existed": 300_000,
        "long before recorded history": 6_000,
        "before the first cities were built": 6_000,
        "before the Roman Empire fell": 1_550,
        "before the telescope was invented": 420,
    }
    for floor, phrase in _ANCHORS:
        assert floor > ages[phrase], f"{phrase!r} is not true at {floor} ly"


def test_the_bundled_catalogs_carry_vetted_distances():
    cat = load_catalog()
    with_distance = [o for o in cat if o.distance_ly is not None]
    # Not a coverage quota — just proof the field loads and reached the entries.
    assert len(with_distance) >= 100
    assert all(o.distance_ly > 0 for o in with_distance)
    by_id = {o.id: o for o in cat}
    # Anchor a couple of well-known values, so a bad bulk edit can't slip past.
    assert by_id["M31"].distance_ly == pytest.approx(2_500_000, rel=0.05)
    assert by_id["M45"].distance_ly == pytest.approx(444, rel=0.05)


def test_a_beginners_favourite_target_gets_a_line_end_to_end():
    info = identify_object("M_31")
    assert info is not None and info.light_travel is not None
    assert "before our species existed" in info.light_travel.text
    # The Pleiades are close enough that no anchor applies — still a line, just
    # the number, which is the "never guess" path staying friendly.
    pleiades = identify_object("M 45")
    assert pleiades is not None and pleiades.light_travel is not None
    assert pleiades.light_travel.text.endswith("about 440 years ago.")


def test_an_object_outside_the_catalog_has_no_line_and_no_error():
    assert identify_object("some folder of mine") is None


def test_the_distance_field_agrees_with_every_blurb_that_states_one():
    """Six curated blurbs already tell the reader a distance ("about 2.5 million
    light-years away"). The new field must never contradict the sentence right
    above it on the same card — and this is the one internal cross-check
    available for a hand-curated data set, so it guards future edits to either
    side."""
    import re

    pattern = re.compile(r"([\d,.]+)\s*(million|billion)?\s*light-?years", re.I)
    checked = 0
    for obj in load_catalog():
        m = pattern.search(obj.blurb or "")
        if m is None:
            continue
        stated = float(m.group(1).replace(",", ""))
        if m.group(2) == "million":
            stated *= 1e6
        elif m.group(2) == "billion":
            stated *= 1e9
        assert obj.distance_ly is not None, f"{obj.id}: blurb states a distance, field is missing"
        assert obj.distance_ly == pytest.approx(stated, rel=0.1), obj.id
        checked += 1
    assert checked >= 5, "expected the curated blurbs that state a distance"
