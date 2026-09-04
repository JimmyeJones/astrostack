"""Offline catalog identification for the "What am I looking at?" card."""

from __future__ import annotations

from seestack.objectinfo import (
    CONSTELLATION_NAMES,
    identify_object,
)


def test_matches_messier_designation_from_folder_name():
    # A bare Seestar folder name like "M_31" must resolve to Andromeda.
    info = identify_object("M_31")
    assert info is not None
    assert info.id == "M31"
    assert info.name == "Andromeda Galaxy"
    assert info.type == "galaxy"
    assert info.constellation == "Andromeda"
    assert info.matched_by == "name"


def test_designation_normalisation_is_separator_and_zero_insensitive():
    for name in ("NGC7000", "ngc 7000", "NGC_7000", "NGC-7000", "ngc 07000"):
        info = identify_object(name)
        assert info is not None, name
        assert info.id == "NGC 7000"
        assert info.name == "North America Nebula"


def test_matches_common_name():
    info = identify_object("Crab Nebula")
    assert info is not None
    assert info.id == "M1"
    assert info.constellation == "Taurus"


def test_designation_inside_a_longer_name_still_matches():
    info = identify_object("M 42 Orion Nebula test")
    assert info is not None
    assert info.id == "M42"


def test_no_match_returns_none():
    assert identify_object("my_backyard_test") is None
    assert identify_object("") is None
    assert identify_object(None) is None


def test_cone_match_by_solved_centre_when_name_unknown():
    # An unrecognised folder name but a solved centre on M31 must match by coords.
    info = identify_object("random_capture_01", ra_deg=10.68, dec_deg=41.27)
    assert info is not None
    assert info.id == "M31"
    assert info.matched_by == "coords"


def test_cone_match_rejects_a_far_field():
    # A blank patch of sky far from any catalog object matches nothing.
    assert identify_object("blank", ra_deg=0.0, dec_deg=0.0) is None


def test_name_match_takes_precedence_over_coords():
    # If the name resolves, we trust it even when coords are also supplied.
    info = identify_object("M31", ra_deg=83.6, dec_deg=-5.4)
    assert info is not None
    assert info.id == "M31"
    assert info.matched_by == "name"


def test_constellation_abbr_map_is_complete_88():
    # The IAU has 88 constellations; the map must cover them so a widened catalog
    # never shows a blank constellation for a standard abbreviation.
    assert len(CONSTELLATION_NAMES) == 88


def test_every_catalog_object_resolves_a_constellation_name():
    from seestack.nightplan import load_catalog

    for obj in load_catalog():
        assert obj.con in CONSTELLATION_NAMES, obj.con


def test_identify_carries_size_and_framing_when_the_catalog_has_a_size():
    # A large, sized target (M31, ~178') surfaces its size + a "mosaic" verdict.
    info = identify_object("M31")
    assert info is not None
    assert info.size_arcmin == 178.0
    assert info.framing is not None
    assert info.framing.level == "mosaic"


def test_identify_carries_the_panel_count_for_a_target_bigger_than_one_frame():
    # "Shoot it in mosaic mode" stops exactly where the beginner's next question
    # starts, so identify carries the grid too: M 31 (178' x 63') is a 3x2.
    info = identify_object("M31")
    assert info is not None and info.mosaic is not None
    assert (info.mosaic.cols, info.mosaic.rows, info.mosaic.panels) == (3, 2, 6)
    assert "3×2 mosaic (6 panels)" in info.mosaic.text


def test_identify_plans_no_mosaic_for_a_target_that_fits_one_frame():
    # M 13 (~20') fits comfortably — no plan, so the card says nothing about
    # mosaics rather than proposing a one-panel one.
    info = identify_object("M13")
    assert info is not None and info.framing is not None
    assert info.framing.level == "fits"
    assert info.mosaic is None


def test_identify_omits_framing_when_the_catalog_has_no_size():
    # An object we haven't vetted a size for identifies fine but carries no
    # framing hint (we never guess a size). The bundled catalog is now fully
    # sized, so exercise the no-size wiring with a synthetic sizeless entry.
    from seestack.nightplan import CatalogObject

    unsized = CatalogObject(
        id="NGC 99999", name="Testium Nebula", ra_deg=10.0, dec_deg=20.0,
        type="galaxy", con="And", size_arcmin=None,
    )
    info = identify_object("Testium Nebula", catalog=(unsized,))
    assert info is not None
    assert info.size_arcmin is None
    assert info.framing is None
    assert info.mosaic is None


def test_identify_carries_the_beginner_blurb_when_the_catalog_has_one():
    # A curated popular target (M42) surfaces its plain-language "what am I
    # looking at?" one-liner all the way through identify.
    info = identify_object("M42")
    assert info is not None
    assert info.blurb
    assert "nebula" in info.blurb.lower()


def test_identify_blurb_is_empty_when_the_catalog_has_none():
    # An object without a curated blurb identifies fine but carries "" (the card
    # then reads from type + constellation alone — no missing/None crash).
    from seestack.nightplan import CatalogObject

    plain = CatalogObject(
        id="NGC 99999", name="Testium Nebula", ra_deg=10.0, dec_deg=20.0,
        type="galaxy", con="And",
    )
    info = identify_object("Testium Nebula", catalog=(plain,))
    assert info is not None
    assert info.blurb == ""


def test_popular_iconic_targets_all_carry_a_blurb():
    # The showpiece beginner targets a Seestar owner actually shoots must each
    # have a curated one-liner (guards against a future catalog edit dropping one).
    for name in ("M31", "M42", "M45", "M51", "M13", "NGC 7000", "IC 434"):
        info = identify_object(name)
        assert info is not None, name
        assert info.blurb, f"{name} lost its blurb"


def test_every_catalog_blurb_is_a_clean_sentence():
    # A curated blurb, when present, should be a non-trivial sentence (real
    # content, ends with a period) — catches an accidental blank/stub entry.
    from seestack.nightplan import load_catalog

    for obj in load_catalog():
        if obj.blurb:
            assert len(obj.blurb) >= 20, obj.id
            assert obj.blurb.rstrip().endswith("."), obj.id


def test_every_bundled_catalog_object_carries_a_blurb():
    """The "what am I looking at?" card's whole job is to say something when a
    beginner opens a target, and for most of the catalog's life it said nothing:
    only 36 of 110 Messier objects and 34 of 47 popular NGC/IC objects had a
    blurb, so M2, M3, M5 and named nebulae like the Wizard and the Seagull
    opened an empty card at exactly the moment it exists to serve.

    Now every object has one, and this pins that shut: a future catalog addition
    without a blurb fails here rather than quietly reopening the gap."""
    from seestack.nightplan import load_catalog

    catalog = load_catalog()
    assert len(catalog) >= 157  # both bundled files loaded, not just one
    without = [o.id for o in catalog if not (o.blurb or "").strip()]
    assert without == [], f"catalog objects with no beginner blurb: {without}"


def test_a_blurb_stays_a_one_liner():
    """It renders as a single line on a card that already carries up to six, and
    the owner's standing complaint is that the pages are too busy. The longest
    curated blurb today is under 200 characters; the bound leaves room to write
    a good one without letting a paragraph in."""
    from seestack.nightplan import load_catalog

    for obj in load_catalog():
        assert len(obj.blurb) <= 260, (obj.id, len(obj.blurb))


def test_the_previously_blank_targets_now_say_something_real():
    """Spot-check the objects the gap was measured on — a beginner who shoots
    any of these used to get an empty card."""
    for name in ("M2", "M3", "M5", "NGC 7380", "IC 405", "IC 2177", "NGC 2174"):
        info = identify_object(name)
        assert info is not None, name
        assert info.blurb, f"{name} still has no blurb"
        assert len(info.blurb) >= 60, name


# --- confident_object_title: what a *shared* picture may be captioned ---------
#
# The card can afford a wider cone than a baked caption can: a bad guess on a
# card is dismissed in a glance, a bad name printed into shared pixels is a wrong
# fact that outlives the session. These pin both sides of that line.

def test_a_folder_name_that_identifies_nothing_takes_the_catalog_name():
    from seestack.objectinfo import confident_object_title

    assert confident_object_title("MyWorks_2026-08-14", 10.685, 41.269) == (
        "Andromeda Galaxy")
    assert confident_object_title("Unsorted", 83.822, -5.391) == "Orion Nebula"
    # No name at all is the same case — the sky is all there is to go on.
    assert confident_object_title(None, 83.822, -5.391) == "Orion Nebula"


def test_a_name_that_identifies_the_object_is_left_alone():
    from seestack.objectinfo import confident_object_title

    for name in ("M 31", "M31", "M_31", "Andromeda Galaxy"):
        assert confident_object_title(name, 10.685, 41.269) is None, name
    # A designation the bundled catalog doesn't carry (it lists M31, not its NGC
    # alias) reads as "identifies nothing", so the coordinates decide — and what
    # they say is still true, which is the bar for a baked caption.
    assert confident_object_title("NGC 224", 10.685, 41.269) == "Andromeda Galaxy"


def test_the_title_cone_is_tighter_than_the_cards():
    """0.5° away is a neighbour. The card would still claim it; the caption
    must not."""
    from seestack.objectinfo import _CONE_MATCH_DEG, _TITLE_MATCH_DEG

    assert _TITLE_MATCH_DEG < _CONE_MATCH_DEG
    from seestack.objectinfo import confident_object_title

    assert identify_object("Unsorted", 10.685, 41.269 + 0.5) is not None
    assert confident_object_title("Unsorted", 10.685, 41.269 + 0.5) is None


def test_no_solved_centre_and_bad_numbers_say_nothing():
    import math

    from seestack.objectinfo import confident_object_title

    assert confident_object_title("Unsorted") is None
    assert confident_object_title("Unsorted", 10.685, None) is None
    assert confident_object_title("Unsorted", math.nan, 41.269) is None
    assert confident_object_title("Unsorted", "not a number", 41.269) is None


def test_the_fills_each_sub_clause_reads_the_same_telescope_as_the_framing_line():
    """`background_mode_hint`'s extra sentence is the same field-of-view
    comparison the framing verdict makes, so it has to be made against the same
    field — a 90' nebula fills an S50's 77' frame and does not fill an S30's
    128' one, and the card must not say both things at once."""
    from seestack.framing import FrameField
    from seestack.objectinfo import identify_object

    s30 = FrameField(127.6, 71.8)
    # M 8 (Lagoon, 90' x 40', a nebula) — big enough for the luminance advice
    # either way, but only bigger than the *S50's* frame.
    fallback = identify_object("M8")
    derived = identify_object("M8", field=s30)
    assert fallback is not None and derived is not None
    assert fallback.size_arcmin == derived.size_arcmin
    assert fallback.background_mode_hint is not None
    assert derived.background_mode_hint is not None
    assert "fills each sub" in fallback.background_mode_hint.text
    assert "fills each sub" not in derived.background_mode_hint.text
    # …and the framing line agrees with it in the same breath.
    assert fallback.framing.level == "mosaic"
    assert derived.framing.level == "tight"
