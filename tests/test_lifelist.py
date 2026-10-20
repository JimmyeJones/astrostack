"""My life list — matching the bundled catalog against captured targets.

Pure and offline, so these need no library on disk: the matcher is duck-typed
on the four target fields it reads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from seestack.lifelist import (
    FIELD_MATCH_FRACTION,
    MATCH_RADIUS_DEG,
    LifeListEntry,
    catalog_capture_status,
    is_messier,
    life_list_summary,
    match_radius_deg,
    nearly_complete_constellations,
)
from seestack.nightplan import CatalogObject, load_catalog


@dataclass
class FakeTarget:
    name: str
    safe_name: str
    ra_deg: float | None
    dec_deg: float | None
    n_frames: int = 12
    frame_short_deg: float | None = None
    panel_footprint: object = None


def _obj(cid: str, ra: float, dec: float, name: str = "") -> CatalogObject:
    return CatalogObject(
        id=cid, name=name, ra_deg=ra, dec_deg=dec, type="galaxy", con="And",
    )


def test_an_object_at_a_targets_centre_is_captured():
    cat = [_obj("M31", 10.6847, 41.269, "Andromeda Galaxy")]
    targets = [FakeTarget("M 31", "M_31", 10.6847, 41.269)]

    (entry,) = catalog_capture_status(cat, targets)
    assert entry.captured is True
    assert entry.safe_name == "M_31"
    assert entry.target_name == "M 31"
    assert entry.sep_deg == pytest.approx(0.0, abs=1e-6)
    # The catalog's own descriptive fields come through for the tile.
    assert entry.name == "Andromeda Galaxy"
    assert entry.con == "And"


def test_an_object_a_couple_of_degrees_away_is_not_claimed():
    """Erring small is deliberate: claiming M65 when the owner pointed at M66
    next door would make the whole list untrustworthy."""
    cat = [_obj("M31", 10.6847, 41.269)]
    targets = [FakeTarget("Something else", "Other", 12.6847, 41.269)]

    (entry,) = catalog_capture_status(cat, targets)
    assert entry.captured is False
    assert entry.safe_name is None
    assert entry.target_name is None
    assert entry.sep_deg is None


def test_the_match_radius_sits_inside_one_seestar_frame():
    """A Seestar frame is roughly 1.3° x 0.7°, so the radius must be well inside
    it — an object that matches is genuinely in the picture."""
    assert 0.1 < MATCH_RADIUS_DEG < 0.35001
    cat = [_obj("M31", 10.0, 40.0)]
    just_inside = [FakeTarget("A", "A", 10.0, 40.0 + MATCH_RADIUS_DEG * 0.9)]
    just_outside = [FakeTarget("B", "B", 10.0, 40.0 + MATCH_RADIUS_DEG * 1.1)]

    assert catalog_capture_status(cat, just_inside)[0].captured is True
    assert catalog_capture_status(cat, just_outside)[0].captured is False


def test_the_closest_of_several_nearby_targets_wins():
    """The Seestar writes a new folder per night, so three nights on M31 is
    three targets until they are merged — the list must show one capture, and a
    deterministic one."""
    cat = [_obj("M31", 10.0, 40.0)]
    targets = [
        FakeTarget("M 31 night 1", "M_31", 10.0, 40.2),
        FakeTarget("M 31 night 2", "M_31_2", 10.0, 40.02),
        FakeTarget("M 31 night 3", "M_31_3", 10.0, 40.1),
    ]

    entry = catalog_capture_status(cat, targets)[0]
    assert entry.captured is True
    assert entry.safe_name == "M_31_2"
    assert entry.sep_deg == pytest.approx(0.02, abs=1e-3)


def test_an_unsolved_target_cannot_light_a_tile():
    """No plate-solved centre means there is nothing to match on — the tile
    stays grey rather than guessing from the folder name."""
    cat = [_obj("M31", 10.6847, 41.269)]
    targets = [FakeTarget("M 31", "M_31", None, None)]

    assert catalog_capture_status(cat, targets)[0].captured is False


def test_a_registered_but_empty_target_is_not_a_capture():
    """"Have I got a picture of this?" — a folder with no frames in it is not a
    yes, and lighting the tile would be a lie the owner would catch."""
    cat = [_obj("M31", 10.6847, 41.269)]
    targets = [FakeTarget("M 31", "M_31", 10.6847, 41.269, n_frames=0)]

    assert catalog_capture_status(cat, targets)[0].captured is False


def test_matching_is_safe_across_the_ra_seam():
    """A target at RA 359.9 and an object at RA 0.1 are 0.2 degrees apart, not
    359.8 — the haversine handles the wrap."""
    cat = [_obj("NGC 7822", 0.1, 60.0)]
    targets = [FakeTarget("T", "T", 359.95, 60.0)]

    entry = catalog_capture_status(cat, targets)[0]
    assert entry.captured is True
    assert entry.sep_deg < MATCH_RADIUS_DEG


def test_entries_are_ordered_messier_numerically_then_the_rest():
    """A beginner reads it as "M1, M2, M3…" — a plain string sort puts M10
    before M9, which looks broken."""
    cat = [
        _obj("NGC 7000", 314.7, 44.3),
        _obj("M10", 251.8, -4.1),
        _obj("M9", 259.8, -18.5),
        _obj("M1", 83.6, 22.0),
        _obj("IC 1805", 38.2, 61.5),
    ]

    ids = [e.catalog_id for e in catalog_capture_status(cat, [])]
    assert ids == ["M1", "M9", "M10", "IC 1805", "NGC 7000"]


def test_an_unparseable_id_sorts_to_the_back_rather_than_raising():
    cat = [_obj("Sh2-155", 350.2, 62.6), _obj("M1", 83.6, 22.0)]
    ids = [e.catalog_id for e in catalog_capture_status(cat, [])]
    assert ids == ["M1", "Sh2-155"]


def test_summary_counts_messier_and_the_rest_separately():
    cat = [
        _obj("M1", 83.6, 22.0),
        _obj("M2", 323.4, -0.8),
        _obj("NGC 7000", 314.7, 44.3),
    ]
    targets = [FakeTarget("M 1", "M_1", 83.6, 22.0)]

    counts = life_list_summary(catalog_capture_status(cat, targets))
    assert counts == {
        "messier_captured": 1, "messier_total": 2,
        "other_captured": 0, "other_total": 1,
    }


def test_is_messier_only_matches_the_numbered_ids():
    assert is_messier("M1") and is_messier("M110")
    assert not is_messier("NGC 7000")
    assert not is_messier("Mel 15")


def test_the_bundled_catalog_yields_the_full_110_object_milestone():
    """The whole point of the feature: the real bundled catalog must offer the
    complete Messier list, not a subset — a beginner counting to 110 would
    notice at once."""
    entries = catalog_capture_status(load_catalog(), [])
    counts = life_list_summary(entries)

    assert counts["messier_total"] == 110
    assert counts["messier_captured"] == 0        # an empty library captures nothing
    assert counts["other_total"] > 0
    # Every Messier number 1..110 is present exactly once.
    messier = [e.catalog_id for e in entries if is_messier(e.catalog_id)]
    assert messier == [f"M{n}" for n in range(1, 111)]
    # ...and nothing is duplicated across the two bundled files.
    ids = [e.catalog_id for e in entries]
    assert len(ids) == len(set(ids))


# --- "One away from Orion" — nearly-finished constellations -----------------


def _entry(cid: str, con: str, *, captured: bool) -> LifeListEntry:
    """A life-list entry with only the fields the grouping reads."""
    return LifeListEntry(
        catalog_id=cid, name="", type="galaxy", con=con,
        ra_deg=0.0, dec_deg=0.0, size_arcmin=None, blurb="",
        captured=captured,
    )


def test_one_missing_object_ranks_ahead_of_two():
    entries = [
        _entry("M42", "Ori", captured=True),
        _entry("M43", "Ori", captured=True),
        _entry("M78", "Ori", captured=False),          # Orion: 1 missing
        _entry("M36", "Aur", captured=True),
        _entry("M37", "Aur", captured=False),
        _entry("M38", "Aur", captured=False),          # Auriga: 2 missing
    ]
    got = nearly_complete_constellations(entries)
    assert [p.con for p in got] == ["Ori", "Aur"]
    assert got[0].captured == 2 and got[0].total == 3
    assert [e.catalog_id for e in got[0].missing] == ["M78"]


def test_an_unstarted_constellation_is_not_nearly_finished():
    """Nothing captured isn't 'nearly done' — it's just unshot sky, which is
    what the existing 'start something new tonight' suggestions are for."""
    entries = [_entry("M78", "Ori", captured=False)]
    assert nearly_complete_constellations(entries) == []


def test_a_finished_constellation_drops_out():
    entries = [_entry("M42", "Ori", captured=True), _entry("M43", "Ori", captured=True)]
    assert nearly_complete_constellations(entries) == []


def test_too_many_missing_is_not_a_nudge():
    entries = [_entry("M42", "Ori", captured=True)] + [
        _entry(f"M{n}", "Ori", captured=False) for n in (43, 78, 79)
    ]
    assert nearly_complete_constellations(entries) == []
    # …but raising the bar does include it, so the threshold is the only gate.
    assert [p.con for p in nearly_complete_constellations(entries, max_missing=3)] == ["Ori"]


def test_ties_break_on_most_captured_then_alphabetically():
    entries = [
        _entry("M42", "Ori", captured=True), _entry("M78", "Ori", captured=False),
        _entry("M36", "Aur", captured=True), _entry("M31", "Aur", captured=True),
        _entry("M37", "Aur", captured=False),
        _entry("M1", "Tau", captured=True), _entry("M45", "Tau", captured=False),
    ]
    # All three have exactly 1 missing: Auriga (2 captured) first, then the
    # 1-captured pair in alphabetical order.
    assert [p.con for p in nearly_complete_constellations(entries)] == ["Aur", "Ori", "Tau"]


def test_entries_without_a_constellation_are_skipped():
    entries = [_entry("X1", "", captured=True), _entry("X2", "", captured=False)]
    assert nearly_complete_constellations(entries) == []


# ---- the target's own field -------------------------------------------------


def test_a_wide_field_target_holds_a_neighbour_the_floor_would_leave_grey():
    """The owner's S30 field is ~2.1° x 1.2°, so M32 (0.40° from M31) is in every
    M31 frame he takes — the S50-sized floor alone left it grey."""
    cat = [_obj("M31", 10.685, 41.269), _obj("M32", 10.674, 40.866)]
    s30 = [FakeTarget("M 31", "M_31", 10.685, 41.269, frame_short_deg=1.197)]
    unknown = [FakeTarget("M 31", "M_31", 10.685, 41.269)]

    by_id = {e.catalog_id: e for e in catalog_capture_status(cat, s30)}
    assert by_id["M32"].captured and by_id["M32"].safe_name == "M_31"
    assert by_id["M32"].sep_deg == pytest.approx(0.403, abs=0.002)
    assert not {e.catalog_id: e for e in catalog_capture_status(cat, unknown)}["M32"].captured


@pytest.mark.parametrize("short", [None, 0.0, -1.0, float("nan"), float("inf"), "junk"])
def test_an_unknown_or_nonsense_field_keeps_the_floor(short):
    assert match_radius_deg(FakeTarget("A", "A", 0.0, 0.0, frame_short_deg=short)) == MATCH_RADIUS_DEG


def test_the_field_radius_stays_inside_the_frame_and_never_below_the_floor():
    s30 = FakeTarget("A", "A", 0.0, 0.0, frame_short_deg=1.2)
    s50 = FakeTarget("B", "B", 0.0, 0.0, frame_short_deg=0.717)
    assert match_radius_deg(s30) == pytest.approx(FIELD_MATCH_FRACTION * 0.6)
    assert match_radius_deg(s30) < 0.6  # strictly inside the inscribed circle
    assert match_radius_deg(s50) == MATCH_RADIUS_DEG

    cat = [_obj("X", 10.0, 40.0)]
    inside = FakeTarget("A", "A", 10.0, 40.0 + 0.47, frame_short_deg=1.2)
    outside = FakeTarget("A", "A", 10.0, 40.0 + 0.49, frame_short_deg=1.2)
    assert catalog_capture_status(cat, [inside])[0].captured is True
    assert catalog_capture_status(cat, [outside])[0].captured is False


def test_the_closest_target_still_wins_across_different_fields():
    """A wide target farther away does not beat a narrow one sitting on it."""
    cat = [_obj("M32", 10.674, 40.866)]
    wide = FakeTarget("M 31", "M_31", 10.685, 41.269, frame_short_deg=1.197)
    on_it = FakeTarget("M 32", "M_32", 10.674, 40.870)
    (entry,) = catalog_capture_status(cat, [wide, on_it])
    assert entry.safe_name == "M_32"


# ---- a mosaic's own panels --------------------------------------------------


def _footprint_json(panels, *, w=1.197, h=2.128) -> str:
    import json
    return json.dumps({"w_deg": w, "h_deg": h, "panels": panels})


@pytest.mark.parametrize("rot", [0.0, 17.0, -63.0, 90.0, 151.0])
def test_a_panel_is_the_frame_a_solved_sub_with_that_crota2_covers(rot):
    """Pin the rotation sense against astropy: a point is in the panel exactly
    when it lands on the pixel grid of a Seestar-style header (``CDELT1 < 0``)
    carrying that ``CROTA2``."""
    import random

    from astropy.wcs import WCS

    from seestack.lifelist import _in_panel, parse_footprint

    scale = 3.99 / 3600.0
    width, height = 1080, 1920
    ra0, dec0 = 200.0, 48.0
    fp = parse_footprint(_footprint_json([[ra0, dec0, rot, rot, 0.0]],
                                         w=width * scale, h=height * scale))
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [ra0, dec0]
    wcs.wcs.crpix = [(width + 1) / 2, (height + 1) / 2]
    wcs.wcs.cdelt = [-scale, scale]
    wcs.wcs.crota = [rot, rot]
    rng = random.Random(3)
    for _ in range(400):
        px, py = rng.uniform(-400, width + 400), rng.uniform(-400, height + 400)
        ra, dec = wcs.wcs_pix2world([[px, py]], 1)[0]
        on_grid = 0.5 <= px <= width + 0.5 and 0.5 <= py <= height + 0.5
        assert _in_panel(float(ra), float(dec), fp.panels[0], fp) is on_grid


@pytest.mark.parametrize("raw", [
    None, "", "{", "[]", 5, '{"w_deg": 1, "h_deg": 2}',
    _footprint_json([]),
    _footprint_json([[10.0, 40.0, 0.0, 0.0]]),                 # no spread
    _footprint_json([[10.0, 40.0, 0.0, 0.0, "x"]]),
    _footprint_json([[10.0, 95.0, 0.0, 0.0, 0.0]]),            # off the sky
    _footprint_json([[10.0, 40.0, 5.0, 1.0, 0.0]]),            # range backwards
    _footprint_json([[10.0, 40.0, 0.0, 0.0, -1.0]]),
    _footprint_json([[10.0, 40.0, 0.0, 0.0, 0.0]], w=0.0),
    _footprint_json([[10.0, 40.0, 0.0, 0.0, 0.0]], w=float("nan")),
    _footprint_json([[float("inf"), 40.0, 0.0, 0.0, 0.0]]),
])
def test_a_malformed_footprint_falls_back_to_the_circle(raw):
    from seestack.lifelist import parse_footprint

    assert parse_footprint(raw) is None
    cat = [_obj("X", 10.0, 40.0)]
    t = FakeTarget("A", "A", 10.0, 40.0, frame_short_deg=1.2, panel_footprint=raw)
    assert catalog_capture_status(cat, [t])[0].captured is True


def test_the_margin_is_the_panels_measured_spread_within_bounds():
    from seestack.lifelist import MIN_PANEL_MARGIN_DEG, parse_footprint

    tight = parse_footprint(_footprint_json([[10.0, 40.0, 0.0, 0.0, 0.001]]))
    loose = parse_footprint(_footprint_json([[10.0, 40.0, 0.0, 0.0, 0.05],
                                             [11.0, 40.0, 0.0, 0.0, 0.02]]))
    wild = parse_footprint(_footprint_json([[10.0, 40.0, 0.0, 0.0, 0.9]]))
    assert tight.margin_deg == MIN_PANEL_MARGIN_DEG
    assert loose.margin_deg == pytest.approx(0.05)
    # Never asks more than the single field's own circle leaves of the half-field.
    assert wild.margin_deg == pytest.approx((1 - FIELD_MATCH_FRACTION) * 1.197 / 2)
    # …and each panel carries its own, so a wobbly one cannot widen a tight one.
    assert [p.margin_deg for p in loose.panels] == pytest.approx([0.05, 0.02])
    assert tight.panels[0].margin_deg == MIN_PANEL_MARGIN_DEG


def test_a_wide_rotation_spread_shrinks_a_panel_to_what_every_angle_holds():
    """Alt-az field rotation across a night turns a panel's subs: a point near a
    corner at one angle is outside at another, so it is not claimed."""
    from seestack.lifelist import footprint_covers, parse_footprint

    corner = (10.0 + 0.5 / math.cos(math.radians(40.0)), 40.9)
    steady = parse_footprint(_footprint_json([[10.0, 40.0, 0.0, 0.0, 0.0]]))
    turning = parse_footprint(_footprint_json([[10.0, 40.0, -40.0, 40.0, 0.0]]))
    assert footprint_covers(steady, *corner)
    assert not footprint_covers(turning, *corner)
    assert footprint_covers(turning, 10.0, 40.0)
