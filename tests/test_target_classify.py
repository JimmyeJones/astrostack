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


# ---------------------------------------------------------------------------
# The classifier must not read a stack's *grain* as colour.
#
# ``chroma`` used to be the median of the per-pixel ``(max−min)/mean`` over the
# extended region. R, G and B carry independent noise, so on a grey pixel that
# is ~1.7σ of pure grain — a statistic that means something different depending
# on how many subs went in, which is the bug class the QA lead in
# docs/IMPROVEMENTS.md exists to sweep for. Measured on one unchanging,
# completely colourless synthetic field, the old number ran 0.118 at 4 subs down
# to 0.010 at 800, so a thin stack of a *grey* object cleared the ``>= 0.06``
# nebula bar on grain alone and got the nebula preset suggested — and, for an
# owner with a stored per-object-type taste profile, the nebula taste applied to
# their picture. It is now measured on a locally averaged copy of the region,
# which is depth-invariant because colour is a property of the region and noise
# is not.


def _neutral_object_field(noise: float, seed: int = 2) -> np.ndarray:
    """A big, bright, extended object with **no colour at all** — every channel
    identical — under per-channel noise of the given σ."""
    rng = np.random.default_rng(seed)
    h = w = 220
    lum = (np.full((h, w), 0.02, np.float32)
           + 0.58 * _blob((h, w), 110, 110, 70)
           + _stars((h, w), 8, rng, sigma=1.0))
    rgb = np.repeat(lum[..., None], 3, axis=2).astype("float32")
    return rgb + rng.normal(0, noise, rgb.shape).astype("float32")


def _coloured_nebula_field(noise: float, seed: int = 2) -> np.ndarray:
    """The same geometry, genuinely red-dominant — a real emission nebula."""
    rng = np.random.default_rng(seed)
    h = w = 220
    base = np.full((h, w), 0.02, np.float32) + 0.5 * _blob((h, w), 110, 110, 70)
    stars = _stars((h, w), 8, rng, sigma=1.0)
    rgb = np.stack([base * 1.6 + stars, base + stars, base * 0.9 + stars],
                   axis=-1).astype("float32")
    return rgb + rng.normal(0, noise, rgb.shape).astype("float32")


def test_a_grainy_colourless_object_is_never_called_a_nebula():
    """The regression. Before the fix this field read chroma 0.064 at σ=0.02 and
    0.151 at σ=0.05 — over the nebula bar — on a picture with no colour in it."""
    for noise in (0.004, 0.02, 0.05):
        out = classify_target(_neutral_object_field(noise))
        assert out["cues"]["chroma"] < 0.06, f"grain read as colour at σ={noise}"
        assert out["cls"] != "nebula", f"colourless field called a nebula at σ={noise}"


def test_the_colour_cue_does_not_move_with_how_deep_the_stack_is():
    """The property the whole fix is for: one unchanging sky must give one
    answer whether it is four subs deep or eight hundred. Noise falls as 1/√N,
    so sweeping σ *is* sweeping the sub count."""
    coloured = [classify_target(_coloured_nebula_field(n))["cues"]["chroma"]
                for n in (0.004, 0.02, 0.05)]
    # A real colour reads the same at every depth (within a few percent) …
    assert max(coloured) - min(coloured) < 0.05 * max(coloured)
    # … and stays far above the bar, so the fix didn't buy invariance by
    # flattening the signal too.
    assert min(coloured) >= 0.2
    neutral = [classify_target(_neutral_object_field(n))["cues"]["chroma"]
               for n in (0.004, 0.02, 0.05)]
    # The colourless twin stays near zero at every depth, and — the direction
    # that matters — never crosses the bar as the stack gets thinner.
    assert max(neutral) < 0.06


def test_a_real_coloured_nebula_survives_a_noisy_stack():
    """The other half: the fix must not make the classifier deaf. A genuinely
    red nebula is still called one on a thin, grainy stack."""
    for noise in (0.004, 0.02, 0.05):
        out = classify_target(_coloured_nebula_field(noise))
        assert out["cls"] == "nebula", f"missed a real nebula at σ={noise}"
        assert out["preset_id"] == "nebula_broadband"


def test_extended_chroma_reads_the_region_not_its_pixels():
    """Unit-level: the estimator itself. A uniformly grey patch under heavy
    per-channel noise has no colour; a uniformly red one has the same colour
    however noisy it is."""
    from seestack.edit.presets import _extended_chroma

    rng = np.random.default_rng(9)
    mask = np.zeros((80, 80), dtype=bool)
    mask[10:70, 10:70] = True
    grey = np.full((80, 80, 3), 0.4, np.float32)
    grey += rng.normal(0, 0.05, grey.shape).astype("float32")
    assert _extended_chroma(grey, mask) < 0.03

    red = np.stack([np.full((80, 80), 0.6, np.float32),
                    np.full((80, 80), 0.3, np.float32),
                    np.full((80, 80), 0.3, np.float32)], axis=-1)
    clean = _extended_chroma(red, mask)
    noisy = _extended_chroma(
        red + rng.normal(0, 0.05, red.shape).astype("float32"), mask)
    assert clean > 0.5
    assert abs(noisy - clean) < 0.05 * clean

    # Too small a region says nothing rather than guessing off a handful of px.
    tiny = np.zeros((80, 80), dtype=bool)
    tiny[0:4, 0:4] = True
    assert _extended_chroma(red, tiny) == 0.0
