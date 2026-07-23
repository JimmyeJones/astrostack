"""Target identification (graceful failure modes — no network in tests)."""

from astropy.table import Table

from seestack.post.target_id import (
    _TYPE_HINTS,
    _pick_nearest_row,
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


# --- nearest-row selection (query_region rows aren't sorted by separation) ---

# M 42 field centre.
_M42_RA, _M42_DEC = 83.82, -5.39


def test_pick_nearest_row_modern_numeric_columns():
    """With decimal-degree ra/dec columns, pick the object at the centre, not
    the first row (a nearby Trapezium star SIMBAD happens to list first)."""
    table = Table({
        "MAIN_ID": ["* tet01 Ori C", "M 42", "NGC 1976 far"],
        "ra": [83.86, 83.82, 84.5],
        "dec": [-5.39, -5.39, -5.9],
        "otype": ["*", "HII", "HII"],
    })
    row = _pick_nearest_row(table, _M42_RA, _M42_DEC)
    assert str(row["MAIN_ID"]) == "M 42"


def test_pick_nearest_row_legacy_sexagesimal_columns():
    """Older astroquery hands back sexagesimal RA (hours) / DEC (deg) strings —
    still resolve the nearest object correctly."""
    table = Table({
        "MAIN_ID": ["far star", "M 42"],
        "RA": ["05 40 00.0", "05 35 16.8"],   # 05h35m16.8s ≈ 83.82 deg
        "DEC": ["-05 23 00", "-05 23 24"],
        "OTYPE": ["*", "HII"],
    })
    row = _pick_nearest_row(table, _M42_RA, _M42_DEC)
    assert str(row["MAIN_ID"]) == "M 42"


def test_pick_nearest_row_falls_back_to_first_when_coords_unreadable():
    """No readable coordinates on any row → preserve the prior table[0] pick
    rather than raising."""
    table = Table({
        "MAIN_ID": ["first", "second"],
        "ra": ["--", "--"],
        "dec": ["--", "--"],
    })
    row = _pick_nearest_row(table, _M42_RA, _M42_DEC)
    assert str(row["MAIN_ID"]) == "first"
