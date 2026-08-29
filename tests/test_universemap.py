"""Your universe — placing captured targets in true 3D by catalog distance."""

from __future__ import annotations

import math

import pytest

from seestack.lighttravel import friendly_amount, friendly_light_years
from seestack.nightplan import CatalogObject
from seestack.universemap import (
    PROVENANCE,
    CapturedTarget,
    build_universe_map,
)


def _obj(cid: str, ra: float, dec: float, distance_ly: float | None,
         name: str = "", otype: str = "galaxy") -> CatalogObject:
    return CatalogObject(id=cid, name=name, ra_deg=ra, dec_deg=dec,
                         type=otype, con="And", distance_ly=distance_ly)


CAT = (
    _obj("M31", 10.68, 41.27, 2_500_000, name="Andromeda Galaxy"),
    _obj("M57", 283.4, 33.03, 2_300, name="Ring Nebula", otype="planetary nebula"),
    _obj("M13", 250.4, 36.46, 22_200, name="Hercules Cluster", otype="globular cluster"),
    _obj("M74", 24.17, 15.78, 32_000_000, name="Phantom Galaxy"),
    _obj("NGC7000", 314.7, 44.5, None, name="North America Nebula", otype="nebula"),
)


def _target(name: str, safe: str | None = None) -> CapturedTarget:
    return CapturedTarget(safe=safe or name.replace(" ", "_"), name=name)


# ---------------------------------------------------------------- placement --

def test_far_objects_sit_further_out_than_near_ones():
    m = build_universe_map([_target("M57"), _target("M13"), _target("M31")],
                           catalog=CAT)
    by_id = {o.object_id: o for o in m.objects}
    assert by_id["M57"].depth < by_id["M13"].depth < by_id["M31"].depth
    # Nearest first, so the list beside the scene reads as a depth ladder.
    assert [o.object_id for o in m.objects] == ["M57", "M13", "M31"]


def test_depth_is_log_scaled_not_linear():
    """The whole point of the scale: three decades apart must not collapse.

    On a *linear* scale M57 (2.3 kly) and M13 (22 kly) both round to ~0 beside
    M31 (2.5 Mly) — the map would show one dot and two specks on the origin.
    """
    m = build_universe_map([_target("M57"), _target("M13"), _target("M31")],
                           catalog=CAT)
    by_id = {o.object_id: o for o in m.objects}
    linear = {k: v.distance_ly / by_id["M31"].distance_ly for k, v in by_id.items()}
    assert linear["M57"] < 0.01 and linear["M13"] < 0.01     # the failure mode
    # Log-scaled, each object gets a real share of the scene.
    assert by_id["M57"].depth > 0.05
    assert by_id["M13"].depth - by_id["M57"].depth > 0.15
    assert by_id["M31"].depth - by_id["M13"].depth > 0.15
    # Equal *ratios* are equal distances on the map — that's what "log" means.
    # M57→M13 is ×9.65, M13→M31 is ×112.6, so the second gap must be ~2.1× the
    # first, within a hair.
    gap_a = by_id["M13"].depth - by_id["M57"].depth
    gap_b = by_id["M31"].depth - by_id["M13"].depth
    ratio = math.log10(112.6) / math.log10(9.65)
    assert gap_b / gap_a == pytest.approx(ratio, rel=0.02)


def test_every_object_sits_strictly_inside_the_scale():
    m = build_universe_map(
        [_target("M57"), _target("M13"), _target("M31"), _target("M74")],
        catalog=CAT)
    assert all(0.0 < o.depth < 1.0 for o in m.objects)
    # Padded at both ends, so the nearest is clearly off the origin and the
    # furthest is clearly inside the outer shell.
    assert min(o.depth for o in m.objects) > 0.05
    assert max(o.depth for o in m.objects) < 0.95
    assert m.near_ly < min(o.distance_ly for o in m.objects)
    assert m.far_ly > max(o.distance_ly for o in m.objects)


def test_a_single_target_is_not_stretched_across_the_whole_scene():
    """One object has no spread, so it must not imply one."""
    m = build_universe_map([_target("M31")], catalog=CAT)
    assert len(m.objects) == 1
    assert m.objects[0].depth == pytest.approx(0.5, abs=1e-9)
    # ...and the scale it sits on still spans a real, honest decade.
    assert m.far_ly / m.near_ly > 10.0


def test_a_tight_collection_is_widened_to_at_least_a_decade():
    cat = (_obj("M57", 283.4, 33.03, 2_300), _obj("M27", 299.9, 22.72, 1_360))
    m = build_universe_map([_target("M57"), _target("M27")], catalog=cat)
    assert m.far_ly / m.near_ly > 10.0
    assert len({round(o.depth, 3) for o in m.objects}) == 2


def test_the_object_is_placed_at_its_catalog_position():
    """All of a target's pictures belong where the object actually is."""
    m = build_universe_map([_target("M31")], catalog=CAT)
    o = m.objects[0]
    assert (o.ra_deg, o.dec_deg) == (10.68, 41.27)
    assert o.object_name == "Andromeda Galaxy"
    assert o.type == "galaxy"


# ------------------------------------------------------------- never guess ---

def test_a_target_with_no_catalog_distance_is_listed_not_placed():
    m = build_universe_map([_target("M31"), _target("NGC 7000")], catalog=CAT)
    assert [o.object_id for o in m.objects] == ["M31"]
    assert [u.name for u in m.unplaced] == ["NGC 7000"]
    assert "no distance" in m.unplaced[0].reason


def test_an_unrecognised_target_is_listed_not_placed():
    m = build_universe_map([_target("Backyard test frames")], catalog=CAT)
    assert m.objects == ()
    assert len(m.unplaced) == 1
    assert "catalogue" in m.unplaced[0].reason
    assert m.unplaced[0].safe == "Backyard_test_frames"


def test_nothing_placeable_gives_an_empty_map_not_a_fabricated_one():
    m = build_universe_map([_target("Nothing here")], catalog=CAT)
    assert m.objects == () and m.shells == ()
    assert m.near_ly == 0.0 and m.far_ly == 0.0
    assert len(m.unplaced) == 1


def test_no_targets_at_all():
    m = build_universe_map([], catalog=CAT)
    assert m == build_universe_map((), catalog=CAT)
    assert m.objects == () and m.shells == () and m.unplaced == ()


def test_provenance_is_always_carried():
    for targets in ([], [_target("M31")], [_target("Nothing here")]):
        assert build_universe_map(targets, catalog=CAT).provenance == PROVENANCE
    # It says the distance is catalogue-sourced, not measured — the one claim
    # this feature must never let a beginner get wrong.
    assert "catalogue" in PROVENANCE and "no backyard telescope" in PROVENANCE


# ----------------------------------------------------------------- shells ----

def test_shells_are_round_decades_inside_the_scale():
    m = build_universe_map(
        [_target("M57"), _target("M13"), _target("M31"), _target("M74")],
        catalog=CAT)
    assert [s.distance_ly for s in m.shells] == [1e3, 1e4, 1e5, 1e6, 1e7]
    assert [s.label for s in m.shells] == [
        "1,000 ly", "10 thousand ly", "100 thousand ly", "1 million ly",
        "10 million ly",
    ]
    assert all(0.0 <= s.depth <= 1.0 for s in m.shells)
    assert [s.depth for s in m.shells] == sorted(s.depth for s in m.shells)


def test_shell_count_is_capped_so_labels_cannot_collide():
    cat = tuple(_obj(f"M{i}", 10.0 + i, 20.0, 10.0 ** (i + 1)) for i in range(1, 10))
    m = build_universe_map([_target(f"M{i}") for i in range(1, 10)], catalog=cat)
    assert 2 <= len(m.shells) <= 6
    # Thinned, not truncated — the outermost rung is what gives "far" its scale.
    assert m.shells[-1].distance_ly >= 1e8


def test_a_collection_too_tight_for_two_decades_gets_its_own_extremes():
    cat = (_obj("M57", 283.4, 33.03, 2_300), _obj("M27", 299.9, 22.72, 1_360))
    m = build_universe_map([_target("M57"), _target("M27")], catalog=cat)
    assert [s.distance_ly for s in m.shells] == [1_360.0, 2_300.0]
    assert [s.label for s in m.shells] == ["1,360 ly", "2,300 ly"]


# -------------------------------------------------------------- read-out -----

def test_distance_and_light_travel_read_out_in_the_same_rounding():
    m = build_universe_map([_target("M31"), _target("M13")], catalog=CAT)
    by_id = {o.object_id: o for o in m.objects}
    assert by_id["M31"].distance_text == "2.5 million ly"
    assert by_id["M31"].years_text == "2.5 million years"
    assert by_id["M13"].distance_text == "22 thousand ly"
    assert by_id["M13"].years_text == "22 thousand years"


def test_friendly_amount_is_the_shared_rounding():
    assert friendly_amount(2_500_000) == "2.5"[:3] + " million"
    assert friendly_amount(83_500_000) == "84 million"
    assert friendly_amount(22_200) == "22 thousand"
    assert friendly_amount(2_300) == "2,300"
    assert friendly_amount(444) == "440"
    assert friendly_light_years(444) == "440 ly"


def test_the_real_bundled_catalog_places_the_owners_targets():
    """End-to-end on the shipped catalogs — no fixture, the real data."""
    m = build_universe_map([
        CapturedTarget(safe="M_31", name="M 31"),
        CapturedTarget(safe="M_57", name="M 57"),
        CapturedTarget(safe="M_42", name="M 42"),
    ])
    assert {o.object_id for o in m.objects} == {"M31", "M57", "M42"}
    assert m.unplaced == ()
    by_id = {o.object_id: o for o in m.objects}
    # Orion (~1.3 kly) and the Ring (~2.3 kly) really are foreground objects
    # against Andromeda (2.5 Mly) — the separation this feature exists to show.
    assert by_id["M42"].depth < by_id["M57"].depth < by_id["M31"].depth
    assert by_id["M31"].distance_ly > 1_000_000
