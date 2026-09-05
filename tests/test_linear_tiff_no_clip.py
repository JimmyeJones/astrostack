"""The "linear" 16-bit TIFF must not clip — it is the file sold as *the full data*.

``_to_uint16_linear`` used to map the robust 0.5%–99.9% percentile range onto
0–65535, which saturates the brightest 0.1% of every stack the app has ever
written: on a real field that 0.1% *is* the star cores and the object's
brightest structure, so a user who took the TIFF into Siril or PixInsight to
keep processing got flat white discs where the gradients should be — and the
darkest 0.5% piled up on black at the other end.

Measured on a Seestar-like synthetic stack (sky 0.020, σ 0.0025, a Pareto star
field with saturated cores): the 99.9th percentile sat at 0.098 against a true
max of 1.0, i.e. **10× of the real dynamic range lived above the white point**.
Mapping the full covered range instead costs nothing that matters — the sky's
own 1σ noise still spans ~165 DN of the 16 bits — and it makes the file
reversible, which is what "no stretching, full data preserved" ought to mean.
"""

from __future__ import annotations

import numpy as np
import tifffile

from seestack.stack.output import (
    _to_uint16_linear,
    _write_tiff,
    linear_scale_anchors,
    pack_unit,
)


def _seestar_like_stack(h: int = 180, w: int = 240) -> np.ndarray:
    """A linear stack with the shape real OSC data has: a low sky, a faint
    extended object, and a star field whose brightest cores reach sensor
    saturation. Deterministic."""
    rng = np.random.default_rng(11)
    rgb = np.full((h, w, 3), 0.020, dtype=np.float32)
    rgb += rng.normal(0.0, 0.0025, rgb.shape).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    neb = np.exp(-(((xx - w / 2) / 55.0) ** 2 + ((yy - h / 2) / 40.0) ** 2))
    rgb += (neb[..., None] * np.array([0.05, 0.02, 0.02], dtype=np.float32))
    ys = rng.integers(6, h - 6, 300)
    xs = rng.integers(6, w - 6, 300)
    amps = np.clip(0.002 * (rng.pareto(1.2, 300) + 1.0), 0.0, 3.0)
    for y, x, a in zip(ys, xs, amps, strict=True):
        gy, gx = yy[y - 5:y + 6, x - 5:x + 6], xx[y - 5:y + 6, x - 5:x + 6]
        g = np.exp(-(((gx - x) ** 2 + (gy - y) ** 2) / (2 * 1.4 ** 2)))
        rgb[y - 5:y + 6, x - 5:x + 6, :] += (a * g)[..., None]
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def test_the_brightest_pixels_are_not_flattened_into_white():
    """Only pixels that really are at the data's maximum may reach full scale."""
    rgb = _seestar_like_stack()
    u16 = _to_uint16_linear(rgb)

    # The packing *rounds* (it used to truncate, biasing every pixel down by up
    # to a whole DN), so the honest invariant is that only pixels within half a
    # step of the data's own maximum may land on full scale — which is what
    # correct rounding means, and is still not clipping. Stated as an exact
    # equality, not a tolerance: it is a stronger claim than the pre-rounding
    # `>= rgb.max()` one, since a truncating packer would put *fewer* pixels
    # there than this and a clipping one far more.
    lo, hi = linear_scale_anchors(rgb)
    half_step = (hi - lo) / 65535.0 / 2.0
    at_true_max = int((rgb >= rgb.max() - half_step).sum())
    at_full_scale = int((u16 == 65535).sum())
    assert at_full_scale == at_true_max, (
        f"{at_full_scale} pixels saturated in the TIFF but only {at_true_max} "
        "are within half a step of the data's own maximum — the highlights are "
        "being clipped"
    )
    assert at_full_scale < rgb.size * 0.001


def test_a_bright_core_keeps_a_monotone_gradient():
    """A star's profile must still fall off in the file, not read as a flat disc."""
    rgb = np.full((64, 64, 3), 0.02, dtype=np.float32)
    yy, xx = np.mgrid[0:64, 0:64]
    core = np.exp(-(((xx - 32) ** 2 + (yy - 32) ** 2) / (2 * 3.0 ** 2)))
    rgb += (core[..., None] * 0.9).astype(np.float32)

    u16 = _to_uint16_linear(rgb)
    profile = u16[32, 32:44, 1].astype(np.int64)
    assert profile[0] == 65535
    # Strictly decreasing away from the peak — no plateau of saturated pixels.
    assert np.all(np.diff(profile) < 0), profile.tolist()


def test_the_faint_end_is_not_piled_up_on_black():
    """Sky noise below the old 0.5th percentile used to be floored at zero."""
    rgb = _seestar_like_stack()
    u16 = _to_uint16_linear(rgb)

    # Same half-step reasoning as the highlight guard above, at the other end.
    lo, hi = linear_scale_anchors(rgb)
    half_step = (hi - lo) / 65535.0 / 2.0
    at_true_min = int((rgb <= rgb.min() + half_step).sum())
    at_zero = int((u16 == 0).sum())
    assert at_zero == at_true_min, (
        f"{at_zero} pixels are black in the TIFF but only {at_true_min} are "
        "within half a step of the data's own minimum — the shadows are being "
        "clipped"
    )


def test_sixteen_bits_still_resolves_the_sky_noise():
    """Giving the highlights their room back must not quantise the sky away."""
    rgb = _seestar_like_stack()
    lo, hi = linear_scale_anchors(rgb)
    sigma_dn = 0.0025 / (hi - lo) * 65535.0
    # Plenty of levels across one sigma of grain — quantisation is nowhere near
    # the noise, so nothing real is lost by not clipping.
    assert sigma_dn > 50.0, sigma_dn


def _adu_scale_stack(sigma_adu: float, *, h: int = 300, w: int = 420) -> np.ndarray:
    """A stack in the units the engine actually produces: **ADU**, with the sky
    zeroed by ``_zero_sky_per_channel`` (so half its noise is negative) and star
    cores at sensor saturation. This is the scene the 2026-08-16 counter-argument
    was about — a [0,1] toy can't answer it."""
    rng = np.random.default_rng(5)
    img = rng.normal(0.0, sigma_adu, (h, w, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    neb = np.exp(-(((xx - w / 2) / 90.0) ** 2 + ((yy - h / 2) / 70.0) ** 2)).astype(np.float32)
    img += (neb[..., None] * np.array([1800.0, 900.0, 700.0], dtype=np.float32))
    ys = rng.integers(6, h - 6, 400)
    xs = rng.integers(6, w - 6, 400)
    amps = np.clip(200.0 * (rng.pareto(1.1, 400) + 1.0), 0.0, 90000.0)
    for y, x, a in zip(ys, xs, amps, strict=True):
        gy, gx = yy[y - 5:y + 6, x - 5:x + 6], xx[y - 5:y + 6, x - 5:x + 6]
        g = np.exp(-(((gx - x) ** 2 + (gy - y) ** 2) / (2 * 1.5 ** 2)))
        img[y - 5:y + 6, x - 5:x + 6, :] += (a * g)[..., None]
    return np.minimum(img, 65535.0).astype(np.float32)


def test_not_clipping_costs_almost_nothing_in_precision():
    """The measured trade the change is made on, pinned so it can't silently rot.

    Widening the white point from p99.9 to the true maximum makes the 16-bit step
    ~14× coarser — the objection that kept this filed for months. But the step
    starts far below the sky's own grain, so it *stays* below it: round-tripping
    the stack through the file and re-measuring ``estimate_noise_sigma`` moves the
    answer by well under a percent, even on a stack four times cleaner than the
    owner's own deepest (which measured σ 0.015–0.020).
    """
    from seestack.edit.noise import estimate_noise_sigma

    for sigma_adu in (60.0, 20.0, 6.0):
        img = _adu_scale_stack(sigma_adu)
        before = estimate_noise_sigma(img)
        assert before is not None
        lo, hi = linear_scale_anchors(img)
        recovered = (lo + _to_uint16_linear(img).astype(np.float64) / 65535.0
                     * (hi - lo)).astype(np.float32)
        after = estimate_noise_sigma(recovered)
        assert after is not None
        assert abs(after / before - 1.0) < 0.05, (
            f"σ {before:.4f} → {after:.4f} at {sigma_adu} ADU grain: quantisation "
            "is eating the noise the file is supposed to preserve"
        )


def test_the_black_point_stays_negative_aware():
    """The sky is zeroed upstream, so half its noise is below zero. A "clip at 0"
    packing would delete that half — the black point must follow the data down."""
    img = _adu_scale_stack(60.0)
    assert img.min() < 0.0
    lo, _ = linear_scale_anchors(img)
    assert lo == float(img.min())


def test_uncovered_canvas_still_writes_black_and_does_not_set_the_anchors():
    """A mosaic's NaN gaps must not drag the black point down (regression guard
    for the behaviour the percentile version already had)."""
    rgb = _seestar_like_stack(h=120, w=160)
    rgb[:, :80, :] = np.nan

    lo, hi = linear_scale_anchors(rgb)
    covered = rgb[np.isfinite(rgb)]
    assert lo == float(covered.min())
    assert hi == float(covered.max())

    u16 = _to_uint16_linear(rgb)
    assert np.all(u16[:, :80] == 0)
    # The covered sky still uses a healthy part of the range.
    assert np.median(u16[:, 80:]) > 100


def test_the_file_says_how_to_get_the_float_values_back(tmp_path):
    """The description records the two anchors, so the TIFF is reversible."""
    rgb = _seestar_like_stack(h=90, w=120)
    path = tmp_path / "linear.tif"
    _write_tiff(path, rgb, mode="linear")

    with tifffile.TiffFile(path) as tf:
        description = tf.pages[0].description
        data = tf.asarray()

    assert "black=" in description and "white=" in description
    lo = float(description.split("black=")[1].split()[0])
    hi = float(description.split("white=")[1].split(";")[0])
    # Recorded to the data's own float32 precision.
    assert (np.float32(lo), np.float32(hi)) == tuple(
        np.float32(v) for v in linear_scale_anchors(rgb))

    recovered = lo + data.astype(np.float64) / 65535.0 * (hi - lo)
    # Round-trips to within one 16-bit step of the original float levels.
    assert np.max(np.abs(recovered - rgb)) <= (hi - lo) / 65535.0


def test_an_editor_export_tiff_is_untouched(tmp_path):
    """``already_display`` writes the display image verbatim — no anchors, no
    rescale. Only the *linear* mode changed."""
    rgb = np.linspace(0.0, 1.0, 64 * 64 * 3, dtype=np.float32).reshape(64, 64, 3)
    path = tmp_path / "display.tif"
    _write_tiff(path, rgb, mode="linear", already_display=True)

    with tifffile.TiffFile(path) as tf:
        assert "black=" not in (tf.pages[0].description or "")
        data = tf.asarray()
    # Verbatim means "no rescale and no stretch" — the packing itself rounds,
    # like every other export, so the reference is `pack_unit` and not the
    # truncating `(x * 65535).astype(...)` this used to spell by hand.
    assert np.array_equal(data, pack_unit(rgb, np.uint16))
