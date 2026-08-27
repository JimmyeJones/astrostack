"""My life list — matching the bundled catalog against captured targets.

Pure and offline, so these need no library on disk: the matcher is duck-typed
on the four target fields it reads.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from seestack.lifelist import (
    MATCH_RADIUS_DEG,
    catalog_capture_status,
    is_messier,
    life_list_summary,
)
from seestack.nightplan import CatalogObject, load_catalog


@dataclass
class FakeTarget:
    name: str
    safe_name: str
    ra_deg: float | None
    dec_deg: float | None
    n_frames: int = 12


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
