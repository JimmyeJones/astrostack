"""The offline "will it fit in one Seestar frame?" framing hint."""

from __future__ import annotations

import pytest

from seestack.framing import (
    SEESTAR_FOV_LONG_ARCMIN,
    SEESTAR_FOV_SHORT_ARCMIN,
    framing_hint,
)
from seestack.nightplan import load_catalog


def test_unknown_or_nonpositive_size_never_guesses():
    # Absent a vetted size, we emit no hint rather than guessing.
    assert framing_hint(None) is None
    assert framing_hint(0) is None
    assert framing_hint(-5) is None


def test_small_object_fits_one_frame():
    # A compact target (well inside the short frame edge) fits comfortably.
    h = framing_hint(20)
    assert h is not None
    assert h.level == "fits"
    assert "single Seestar frame" in h.text
    assert "no mosaic needed" in h.text  # reassuring, not a mosaic nudge


def test_mid_size_object_is_tight():
    # Between the short and long frame edges: only fits if favourably rotated.
    h = framing_hint(60)
    assert h is not None
    assert h.level == "tight"
    assert "mosaic mode" in h.text


def test_large_object_needs_mosaic():
    # Bigger than the long frame edge (e.g. M31 at ~178'): won't fit at all.
    h = framing_hint(178)
    assert h is not None
    assert h.level == "mosaic"
    assert "mosaic mode" in h.text


def test_boundaries_are_inclusive_at_the_short_and_long_edges():
    # Exactly the short edge still counts as "fits"; exactly the long edge as
    # "tight"; a hair past the long edge flips to "mosaic".
    assert framing_hint(SEESTAR_FOV_SHORT_ARCMIN).level == "fits"
    assert framing_hint(SEESTAR_FOV_SHORT_ARCMIN + 0.01).level == "tight"
    assert framing_hint(SEESTAR_FOV_LONG_ARCMIN).level == "tight"
    assert framing_hint(SEESTAR_FOV_LONG_ARCMIN + 0.01).level == "mosaic"


def test_custom_fov_overrides_are_honoured():
    # The helper compares against whatever field is passed (e.g. a solved frame's
    # real size), not only the Seestar default.
    assert framing_hint(30, fov_short_arcmin=20, fov_long_arcmin=40).level == "tight"
    assert framing_hint(50, fov_short_arcmin=20, fov_long_arcmin=40).level == "mosaic"


@pytest.mark.parametrize(
    "obj_id,expected_level",
    [
        ("M31", "mosaic"),   # Andromeda, ~3° — the classic doesn't-fit surprise
        ("M45", "mosaic"),   # Pleiades, ~110'
        ("M33", "tight"),    # Triangulum, ~71' — right at the frame edge
        ("M13", "fits"),     # Hercules globular, ~20'
        ("M57", "fits"),     # Ring Nebula, tiny
    ],
)
def test_popular_catalog_targets_get_sensible_verdicts(obj_id, expected_level):
    cat = {o.id: o for o in load_catalog()}
    obj = cat[obj_id]
    assert obj.size_arcmin is not None
    hint = framing_hint(obj.size_arcmin)
    assert hint is not None
    assert hint.level == expected_level


def test_catalog_sizes_are_sane_when_present():
    # Every catalog size we vetted must be a positive, plausible arcmin value
    # (nothing absurd like a whole-sky degree slipped in), and unsized objects
    # stay None (never coerced to 0).
    for obj in load_catalog():
        if obj.size_arcmin is None:
            continue
        assert 0 < obj.size_arcmin <= 600, obj.id
