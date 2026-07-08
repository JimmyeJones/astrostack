"""Coarse target classifier → starting-preset *suggestion* (presets.classify_target).

The classifier is a hint only (the editor shows it as a one-click "try this preset?"
chip and never changes the Auto recipe), so its contract is: confidently pick the
matching preset on a *clear* archetype, and stay quiet (``preset_id=None``) when the
content is ambiguous or blank. These tests pin that behaviour on unambiguous
synthetic fields so a future change can't silently start mis-suggesting.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.presets import BUILTIN_PRESETS, classify_target


def _stars(shape, n, rng, *, amp=0.8, sigma=1.0):
    """Add ``n`` compact Gaussian point sources (stars) to a fresh dark field."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    field = np.zeros((h, w), np.float32)
    for _ in range(n):
        cy, cx = rng.uniform(3, h - 3), rng.uniform(3, w - 3)
        a = amp * rng.uniform(0.5, 1.0)
        field += a * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sigma ** 2))
    return field


def _blob(shape, cy, cx, radius):
    """A smooth extended (non-star) elliptical blob — galaxy/nebula structure."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((yy - cy) ** 2 + (xx - cx) ** 2) / float(radius ** 2)
    return np.exp(-r2).astype(np.float32)


def test_star_dominated_field_is_a_cluster():
    """A dark field of many compact stars with no diffuse structure → cluster."""
    rng = np.random.default_rng(1)
    h, w = 200, 200
    lum = np.full((h, w), 0.02, np.float32) + _stars((h, w), 180, rng, sigma=1.0)
    lum += rng.normal(0, 0.004, (h, w)).astype("float32")
    rgb = np.repeat(lum[..., None], 3, axis=2)

    out = classify_target(rgb)
    assert out["cls"] == "cluster"
    assert out["preset_id"] == "globular_cluster"
    assert out["label"] == BUILTIN_PRESETS["globular_cluster"]["label"]
    assert out["reason"]
    assert out["confidence"] > 0.5


def test_large_coloured_diffuse_field_is_a_nebula():
    """A large diffuse *coloured* emission region (few stars) → nebula."""
    rng = np.random.default_rng(2)
    h, w = 200, 200
    diffuse = 0.5 * _blob((h, w), 100, 100, 70)      # covers a big share of the frame
    base = np.full((h, w), 0.02, np.float32) + diffuse
    stars = _stars((h, w), 8, rng, sigma=1.0)
    r = base * 1.6 + stars                            # red-dominant emission
    g = base + stars
    b = base * 0.9 + stars
    rgb = np.stack([r, g, b], axis=-1).astype("float32")
    rgb += rng.normal(0, 0.004, rgb.shape).astype("float32")

    out = classify_target(rgb)
    assert out["cls"] == "nebula"
    assert out["preset_id"] == "nebula_broadband"
    assert out["cues"]["ext_frac"] >= 0.06


def test_small_concentrated_neutral_object_is_a_galaxy():
    """A small, concentrated, neutral extended object on a dark sky → galaxy."""
    rng = np.random.default_rng(3)
    h, w = 240, 240
    obj = 0.6 * _blob((h, w), 120, 120, 16)          # a compact ~galaxy-sized blob
    lum = np.full((h, w), 0.02, np.float32) + obj + _stars((h, w), 20, rng, sigma=1.0)
    lum += rng.normal(0, 0.004, (h, w)).astype("float32")
    rgb = np.repeat(lum[..., None], 3, axis=2)        # neutral colour

    out = classify_target(rgb)
    assert out["cls"] == "galaxy"
    assert out["preset_id"] == "galaxy_broadband"
    assert 0.004 <= out["cues"]["ext_frac"] <= 0.05


def test_blank_field_declines_to_suggest():
    """A near-uniform, structureless field → no confident suggestion (no chip)."""
    rng = np.random.default_rng(4)
    lum = np.full((200, 200), 0.1, np.float32) + rng.normal(0, 0.01, (200, 200)).astype("float32")
    rgb = np.repeat(lum[..., None], 3, axis=2)

    out = classify_target(rgb)
    assert out["cls"] is None
    assert out["preset_id"] is None


def test_neutral_large_object_is_not_confidently_a_nebula():
    """A big *neutral* extended object (galaxy-like, e.g. M31) must not be
    confidently mis-labelled a coloured nebula — the colour floor makes the
    classifier decline rather than mis-suggest."""
    rng = np.random.default_rng(5)
    h, w = 200, 200
    diffuse = 0.5 * _blob((h, w), 100, 100, 45)      # moderately large but neutral
    lum = np.full((h, w), 0.02, np.float32) + diffuse + _stars((h, w), 8, rng, sigma=1.0)
    lum += rng.normal(0, 0.004, (h, w)).astype("float32")
    rgb = np.repeat(lum[..., None], 3, axis=2)

    out = classify_target(rgb)
    assert out["cls"] != "nebula"          # never a confident coloured-nebula call


def test_none_and_mono_inputs_decline_cleanly():
    """Defensive: no proxy, or a non-RGB array, yields a clean no-suggestion."""
    assert classify_target(None)["preset_id"] is None
    assert classify_target(np.zeros((50, 50), np.float32))["preset_id"] is None
    assert classify_target(np.zeros((10, 10, 3), np.float32))["preset_id"] is None
