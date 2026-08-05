"""The offline "which background-flatten mode suits this target?" advice."""

from __future__ import annotations

from seestack.bg_advice import (
    EXTENDED_EMISSION_TYPES,
    MIN_EXTENDED_ARCMIN,
    background_mode_hint,
)
from seestack.framing import SEESTAR_FOV_LONG_ARCMIN
from seestack.nightplan import load_catalog
from seestack.objectinfo import identify_object


def test_unknown_type_or_size_never_guesses():
    # Absent a catalog type or a vetted size we say nothing at all, rather than
    # nudging a beginner toward a mode their target may not want.
    assert background_mode_hint(None, 120) is None
    assert background_mode_hint("nebula", None) is None
    assert background_mode_hint(None, None) is None


def test_large_emission_nebula_is_advised_to_use_luminance():
    h = background_mode_hint("nebula", 120)
    assert h is not None
    assert h.mode == "luminance"
    # Plain language, and it names the visible symptom the mode prevents.
    assert "cyan cores" in h.text
    assert "red halos" in h.text


def test_supernova_remnant_counts_as_extended_emission():
    # The Veil / Crab are filamentary Ha/OIII structure — optically the same
    # per-channel-morphology problem as an emission nebula.
    h = background_mode_hint("supernova remnant", 180)
    assert h is not None
    assert h.mode == "luminance"


def test_galaxies_clusters_and_planetaries_are_left_on_the_default():
    # A galaxy is extended but its channels share one shape (per-channel mode
    # handles it correctly); clusters are point sources; a planetary nebula is
    # compact. None of them should be nudged off the default.
    for otype in ("galaxy", "open cluster", "globular cluster",
                  "planetary nebula", "star cloud", "double star", "asterism"):
        assert background_mode_hint(otype, 200) is None, otype


def test_small_nebula_stays_on_the_default():
    # Below the size floor there is plenty of genuine sky around the object in
    # every channel, so the per-channel fit is not at risk.
    assert background_mode_hint("nebula", MIN_EXTENDED_ARCMIN - 0.1) is None
    assert background_mode_hint("nebula", MIN_EXTENDED_ARCMIN) is not None


def test_type_matching_is_case_and_whitespace_insensitive():
    h = background_mode_hint("  Nebula ", 120)
    assert h is not None
    assert h.mode == "luminance"


def test_object_bigger_than_one_frame_gets_the_extra_box_size_caveat():
    # It fills every sub, so even the shared luminance model can absorb some of
    # its faint outer glow — say so honestly and point at the gentler knob,
    # rather than recommending the flatten be switched off.
    big = background_mode_hint("nebula", SEESTAR_FOV_LONG_ARCMIN + 1)
    small = background_mode_hint("nebula", SEESTAR_FOV_LONG_ARCMIN - 1)
    assert big is not None and small is not None
    assert "Background box size" in big.text
    assert "Background box size" not in small.text
    # Both still recommend the same mode — the caveat is extra guidance, not a
    # different answer.
    assert big.mode == small.mode == "luminance"


def test_advice_rides_on_the_catalog_identity_for_a_real_target():
    # End-to-end through the lookup a beginner's target actually goes through:
    # M42 is the archetype the engine's own docstring names.
    info = identify_object("M_42")
    assert info is not None
    assert info.background_mode_hint is not None
    assert info.background_mode_hint.mode == "luminance"


def test_the_default_stays_right_for_most_of_the_catalog():
    # The advice must stay a rare exception, not a blanket nudge: only the
    # extended-emission types can ever carry it, and every one that does is big.
    advised = [o for o in load_catalog()
               if background_mode_hint(o.type, o.size_arcmin) is not None]
    assert advised, "the catalog should carry some large emission nebulae"
    assert all(o.type in EXTENDED_EMISSION_TYPES for o in advised)
    assert all((o.size_arcmin or 0) >= MIN_EXTENDED_ARCMIN for o in advised)
    assert len(advised) < len(load_catalog()) / 2
