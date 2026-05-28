"""Target identification (graceful failure modes — no network in tests)."""

from seestack.post.target_id import _TYPE_HINTS, identify_target


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
