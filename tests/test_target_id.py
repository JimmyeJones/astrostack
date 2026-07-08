"""Target identification (graceful failure modes — no network in tests)."""

from seestack.post.target_id import (
    _TYPE_HINTS,
    friendly_object_type,
    identify_target,
)


def test_lookup_returns_error_when_offline_or_no_match():
    """The function must not raise — it returns a result with an ``error`` field."""
    # We don't know the network state, but the function is contract-bound to
    # return a TargetIdResult either way.
    result = identify_target(83.6, -5.4)
    # Either it succeeded (network available + match found), or it returned an
    # error string. In both cases attributes exist.
    assert hasattr(result, "identifier")
    assert hasattr(result, "object_type")
    assert hasattr(result, "bg_mode_hint")
    assert hasattr(result, "error")


def test_type_hints_cover_major_categories():
    """Spot-check the hint table includes the categories we care about."""
    assert _TYPE_HINTS["G"] == "per_channel"          # galaxy
    assert _TYPE_HINTS["GlC"] == "per_channel"        # globular cluster
    assert _TYPE_HINTS["HII"] == "off"                # HII region (e.g. M42)
    assert _TYPE_HINTS["RNe"] == "luminance"          # reflection nebula


def test_friendly_object_type_maps_known_codes_to_plain_words():
    """A known SIMBAD OTYPE code reads as plain language, not the bare code."""
    assert friendly_object_type("G") == "Galaxy"
    assert friendly_object_type("GlC") == "Globular cluster"
    assert friendly_object_type("HII") == "HII region"
    assert friendly_object_type("PN") == "Planetary nebula"
    # Every code we give a bg-flatten hint for must also have a plain name,
    # so the identify surface never shows a raw code for a mapped target.
    for code in _TYPE_HINTS:
        assert friendly_object_type(code) != code


def test_friendly_object_type_falls_back_to_the_raw_code():
    """An unrecognised code still shows something rather than nothing."""
    assert friendly_object_type("ZzZ") == "ZzZ"
    assert friendly_object_type(None) is None
    assert friendly_object_type("") is None
