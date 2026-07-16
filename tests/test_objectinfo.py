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


def test_identify_omits_framing_when_the_catalog_has_no_size():
    # An object we didn't vet a size for identifies fine but carries no framing
    # hint (we never guess a size).
    from seestack.nightplan import load_catalog

    unsized = next(o for o in load_catalog() if o.size_arcmin is None)
    info = identify_object(unsized.id)
    assert info is not None
    assert info.size_arcmin is None
    assert info.framing is None
