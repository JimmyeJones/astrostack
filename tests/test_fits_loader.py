"""FITS loading and bilinear debayer."""

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.io.fits_loader import (  # noqa: E402
    _parse_timestamp,
    bilinear_debayer,
    fov_deg_from_header,
    load_header,
    load_seestar_raw,
)
from tests.synth import write_seestar_fits  # noqa: E402


def test_load_header(tmp_path):
    p = write_seestar_fits(tmp_path / "x.fit")
    h = load_header(p)
    assert h.width_px == 480
    assert h.height_px == 320
    assert h.bayer_pattern == "RGGB"
    assert h.exposure_s == 10.0
    assert h.timestamp_utc and h.timestamp_utc.startswith("2024-09-12")


def test_parse_timestamp_normalises_all_legal_forms():
    """Regression: ``DATE-OBS`` forms that the three hardcoded strptime patterns
    miss (a trailing 'Z', >6 fractional digits, an explicit offset) used to be
    stored as the *raw* string, so the same instant could land in the DB two
    different ways — silently breaking the lexicographic ``timestamp_utc``
    ordering/equality that the gallery, sky, stats and stacker all rely on. Every
    legal form must now normalise to the same tz-aware UTC ISO string."""
    canonical = "2024-09-12T03:14:55+00:00"
    # A trailing 'Z' must produce byte-for-byte the same string as no-suffix.
    assert _parse_timestamp({"DATE-OBS": "2024-09-12T03:14:55Z"}) == canonical
    assert _parse_timestamp({"DATE-OBS": "2024-09-12T03:14:55"}) == canonical
    assert _parse_timestamp({"DATE-OBS": "2024-09-12 03:14:55"}) == canonical
    # >6 fractional digits (legal FITS) are clamped, not rejected to raw.
    assert (_parse_timestamp({"DATE-OBS": "2024-09-12T03:14:55.1234567"})
            == "2024-09-12T03:14:55.123456+00:00")
    assert (_parse_timestamp({"DATE-OBS": "2024-09-12T03:14:55.123456789Z"})
            == "2024-09-12T03:14:55.123456+00:00")
    # An explicit non-UTC offset is converted to UTC, not stored verbatim.
    assert (_parse_timestamp({"DATE-OBS": "2024-09-12T03:14:55+02:00"})
            == "2024-09-12T01:14:55+00:00")
    # The common Seestar 3-digit-ms form is unchanged (tz-aware ISO).
    assert (_parse_timestamp({"DATE-OBS": "2024-09-12T03:14:55.123"})
            == "2024-09-12T03:14:55.123000+00:00")
    # Genuinely unparseable → None (never the raw garbage string).
    assert _parse_timestamp({"DATE-OBS": "not a date"}) is None
    assert _parse_timestamp({}) is None


def test_load_raw_no_debayer(tmp_path):
    p = write_seestar_fits(tmp_path / "x.fit")
    img, h = load_seestar_raw(p, debayer=False)
    assert img.ndim == 2
    assert img.shape == (320, 480)
    assert img.dtype == np.float32


def test_load_raw_debayer(tmp_path):
    p = write_seestar_fits(tmp_path / "x.fit")
    img, h = load_seestar_raw(p, debayer=True)
    assert img.ndim == 3
    assert img.shape == (320, 480, 3)


def test_load_raw_reads_image_from_a_data_less_primary_hdu(tmp_path):
    """A multi-extension FITS with an empty primary HDU and the image in ext 1
    must load, not raise an opaque IndexError.

    Regression: ``load_seestar_raw`` read ``hdul[0]`` unconditionally, so an
    empty primary made ``np.asarray(None).shape[-1]`` raise ``IndexError: tuple
    index out of range`` *before* the intended "expected 2D" guard could fire.
    We now fall through to the first data-bearing HDU."""
    from astropy.io import fits

    data = (np.arange(320 * 480, dtype=np.uint16) % 1000).reshape(320, 480)
    ext = fits.ImageHDU(data=data)
    ext.header["BAYERPAT"] = "RGGB"
    hdul = fits.HDUList([fits.PrimaryHDU(), ext])  # primary carries no data
    p = tmp_path / "multiext.fits"
    hdul.writeto(p)

    img, info = load_seestar_raw(p, debayer=False)
    assert img.shape == (320, 480)
    assert info.width_px == 480 and info.height_px == 320
    # load_header reports the same geometry, from the same data-bearing HDU.
    h = load_header(p)
    assert h.width_px == 480 and h.height_px == 320


def test_load_raw_reads_a_compressed_fits(tmp_path):
    """An fpack'd (CompImageHDU) FITS keeps an empty primary and the pixels in a
    compressed extension. Falling through to the first data-bearing HDU lets us
    read those too instead of crashing on the empty primary."""
    from astropy.io import fits

    data = (np.arange(320 * 480, dtype=np.uint16) % 1000).reshape(320, 480)
    comp = fits.CompImageHDU(data=data)
    comp.header["BAYERPAT"] = "RGGB"
    hdul = fits.HDUList([fits.PrimaryHDU(), comp])
    p = tmp_path / "compressed.fits"
    hdul.writeto(p)

    img, info = load_seestar_raw(p, debayer=False)
    assert img.shape == (320, 480)
    assert info.bayer_pattern == "RGGB"


def test_load_raw_raises_clear_error_when_no_image_data(tmp_path):
    """A FITS with no image extension at all raises a clear ValueError, not an
    opaque IndexError."""
    from astropy.io import fits

    hdul = fits.HDUList([fits.PrimaryHDU()])  # no data anywhere
    p = tmp_path / "empty.fits"
    hdul.writeto(p)

    with pytest.raises(ValueError, match="no image data|expected 2D"):
        load_seestar_raw(p, debayer=False)


def test_bilinear_debayer_constant_image():
    """A constant mosaic must debayer to that exact constant in every channel —
    borders included. A missing-sample interpolation that reached off the frame
    used to average a real edge sample against the sparse plane's zeros, darkening
    the outermost ring (~50% on edges, ~75% at the corners); the drizzle stack path
    feeds the full frame (no border inset), so that seam reached the final image."""
    for pattern in ("RGGB", "BGGR", "GRBG", "GBRG"):
        mosaic = np.full((40, 60), 1000.0, dtype=np.float32)
        rgb = bilinear_debayer(mosaic, pattern=pattern)
        assert rgb.shape == (40, 60, 3)
        # Regression: no darkened border. Every pixel of every channel is exactly
        # the input constant (the interior already was; this now holds on the ring).
        assert np.allclose(rgb, 1000.0), (
            pattern, float(rgb.min()), float(rgb.max()))


def test_bilinear_debayer_border_not_darkened():
    """The outermost ring of a bright-but-noisy field must not be systematically
    darker than the interior (the sparse-plane zero-averaging border artefact)."""
    rng = np.random.default_rng(1)
    mosaic = rng.uniform(800.0, 1200.0, size=(64, 96)).astype(np.float32)
    rgb = bilinear_debayer(mosaic, pattern="RGGB")
    interior_mean = float(np.mean(rgb[3:-3, 3:-3, :]))
    # Each border strip's mean tracks the interior mean (no ~2-4× dilution).
    for strip in (rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :]):
        assert abs(float(np.mean(strip)) - interior_mean) < 60.0, float(np.mean(strip))


def test_bilinear_debayer_unsupported_pattern():
    with pytest.raises(ValueError):
        bilinear_debayer(np.zeros((10, 10), dtype=np.float32), pattern="XYZ")


def test_bilinear_debayer_non_2d():
    with pytest.raises(ValueError):
        bilinear_debayer(np.zeros((10, 10, 3), dtype=np.float32))


def test_debayer_edge_does_not_wrap_opposite_side():
    """A bright pixel on the last column must not leak into column 0 via the
    debayer neighbour average (the old np.roll-based _shift wrapped edges)."""
    mosaic = np.full((8, 8), 100.0, dtype=np.float32)
    mosaic[:, -1] = 60000.0            # bright last column
    rgb = bilinear_debayer(mosaic, pattern="RGGB")
    # Column 0 should stay near the background, not pick up the far-edge spike.
    assert float(rgb[:, 0].max()) < 1000.0


def test_bilinear_debayer_uint16_does_not_overflow():
    """An integer (raw 16-bit Bayer) mosaic must not wrap modulo 2**16 in the
    neighbour-sum interpolation. Before the float-upcast fix, interpolated sites on
    a bright constant uint16 mosaic wrapped (60000+60000 → 54464 → /2 = 27232),
    silently corrupting the result; the identical float32 mosaic was correct."""
    mosaic_u16 = np.full((6, 6), 60000, dtype=np.uint16)
    rgb_u16 = bilinear_debayer(mosaic_u16, pattern="RGGB")
    # Contract: dtype preserved, and a constant field debayers to that constant
    # everywhere (no wrapped-down interpolated pixels).
    assert rgb_u16.dtype == np.uint16
    assert int(rgb_u16.min()) == 60000 and int(rgb_u16.max()) == 60000, (
        int(rgb_u16.min()), int(rgb_u16.max()))
    # The float path is unchanged and agrees with the (now-correct) integer path.
    rgb_f32 = bilinear_debayer(mosaic_u16.astype(np.float32), pattern="RGGB")
    assert rgb_f32.dtype == np.float32
    assert np.allclose(rgb_f32, 60000.0)


def test_fov_deg_from_header_s30(tmp_path):
    """An S30-shaped header (150 mm f.l., 2.9 µm pixels, 1920 px long edge) yields
    the true ~2.1° field — not the hardcoded 1.3° that silently fails an S30's
    plate-solves. Regression for the owner-confirmed wrong-FOV bug."""
    p = write_seestar_fits(
        tmp_path / "s30.fit", width=1920, height=1080,
        focal_len_mm=150.0, pixel_size_um=2.9,
    )
    fov = fov_deg_from_header(load_header(p))
    assert fov is not None
    # 206.265 * 2.9 / 150 * 1920 / 3600 ≈ 2.126°
    assert fov == pytest.approx(2.13, abs=0.05)


def test_fov_deg_from_header_s50(tmp_path):
    """An S50-shaped header (250 mm f.l., 2.9 µm pixels) yields ~1.27° — close to
    the old 1.3° default (which is why only the S30 was badly broken)."""
    p = write_seestar_fits(
        tmp_path / "s50.fit", width=1920, height=1080,
        focal_len_mm=250.0, pixel_size_um=2.9,
    )
    fov = fov_deg_from_header(load_header(p))
    assert fov is not None
    assert fov == pytest.approx(1.28, abs=0.05)


def test_fov_deg_from_header_missing_optics_returns_none(tmp_path):
    """Without FOCALLEN/XPIXSZ (older/non-Seestar headers) the derivation declines
    so the caller falls back to the configured/default FOV."""
    p = write_seestar_fits(tmp_path / "plain.fit", width=1920, height=1080)
    assert fov_deg_from_header(load_header(p)) is None


def test_fov_deg_from_header_rejects_nonphysical(tmp_path):
    """A garbage/zero focal length can't produce an absurd FOV — decline instead."""
    p = write_seestar_fits(
        tmp_path / "bad.fit", width=1920, height=1080,
        focal_len_mm=0.0, pixel_size_um=2.9,
    )
    assert fov_deg_from_header(load_header(p)) is None


# ---------------------------------------------------------------------------
# Genuine 0.0 samples must be counted as samples (v0.285.2 regression).
#
# The sparse colour planes are zero-filled at every non-sample site, and the two
# interpolators used to recover the sample sites with `plane != 0` — conflating
# "structurally not this channel's site" with "a real datum that reads 0.0". A
# true 0.0 sample was therefore dropped from the neighbour average of every
# adjacent missing site of the same channel, biasing it upward on a positive sky
# background. Exact zeros can't occur in the raw sensor domain (bias pedestal),
# but the debayer runs *after* dark subtraction, so an integer-valued master dark
# lands ~10% of pixels exactly on 0.
# ---------------------------------------------------------------------------

_LAYOUTS = {
    "RGGB": (("r", "g"), ("g", "b")),
    "BGGR": (("b", "g"), ("g", "r")),
    "GRBG": (("g", "r"), ("b", "g")),
    "GBRG": (("g", "b"), ("r", "g")),
}
# (dy, dx) offsets each channel interpolates a missing site from, by how the site
# sits relative to that channel's 2x2 grid. Written out longhand so the reference
# below owes nothing to the implementation it checks.
_RB_NEIGHBOURS = {
    (True, False): ((0, -1), (0, 1)),                    # same row, missing col
    (False, True): ((-1, 0), (1, 0)),                    # same col, missing row
    (False, False): ((-1, -1), (-1, 1), (1, -1), (1, 1)),  # both missing
}


def _reference_debayer(mosaic, pattern):
    """A slow, obviously-correct bilinear debayer, written per-pixel.

    Same contract as the vectorised one: a missing site is the mean of its
    same-channel neighbours that are *on the frame* — every one of them, whatever
    its value. Deliberately naive so it can't share a bug with the real thing.
    """
    h, w = mosaic.shape
    (tl, tr), (bl, br) = _LAYOUTS[pattern]
    site = {(0, 0): tl, (0, 1): tr, (1, 0): bl, (1, 1): br}
    out = np.zeros((h, w, 3), dtype=np.float64)
    for ci, ch in enumerate("rgb"):
        # Every (y, x) this channel is actually sampled at.
        samples = {(y, x) for y in range(h) for x in range(w)
                   if site[(y % 2, x % 2)] == ch}
        for y in range(h):
            for x in range(w):
                if (y, x) in samples:
                    out[y, x, ci] = mosaic[y, x]
                    continue
                if ch == "g":
                    offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
                else:
                    py, px = next(p for p, c in site.items() if c == ch)
                    offsets = _RB_NEIGHBOURS[(y % 2 == py, x % 2 == px)]
                vals = [mosaic[y + dy, x + dx] for dy, dx in offsets
                        if 0 <= y + dy < h and 0 <= x + dx < w]
                out[y, x, ci] = float(np.mean(vals)) if vals else 0.0
    return out


def _legacy_debayer(mosaic, pattern):
    """The pre-v0.285.2 rule: sample sites recovered with a `!= 0` value test.

    Kept in the test rather than the module so the "unchanged for an ordinary
    frame" claim below is a *measured* byte-for-byte comparison against the old
    behaviour, not an assertion about it.
    """
    from seestack.io.fits_loader import _shift

    h, w = mosaic.shape
    (tl, tr), (bl, br) = _LAYOUTS[pattern]
    site = {(0, 0): tl, (0, 1): tr, (1, 0): bl, (1, 1): br}
    yy, xx = np.indices((h, w))
    out = np.zeros((h, w, 3), dtype=np.float32)
    for ci, ch in enumerate("rgb"):
        plane = np.zeros((h, w), dtype=np.float32)
        for (py, px), c in site.items():
            if c == ch:
                plane[py::2, px::2] = mosaic[py::2, px::2]
        has = plane != 0                      # <- the bug being pinned
        m = has.astype(np.float32)
        if ch == "g":
            num = (_shift(plane, 1, 0) + _shift(plane, -1, 0)
                   + _shift(plane, 0, 1) + _shift(plane, 0, -1))
            den = (_shift(m, 1, 0) + _shift(m, -1, 0)
                   + _shift(m, 0, 1) + _shift(m, 0, -1))
            out[:, :, ci] = np.where(has, plane, num / np.maximum(den, 1.0))
            continue
        py, px = next(p for p, c in site.items() if c == ch)
        h_avg = ((_shift(plane, 0, 1) + _shift(plane, 0, -1))
                 / np.maximum(_shift(m, 0, 1) + _shift(m, 0, -1), 1.0))
        v_avg = ((_shift(plane, 1, 0) + _shift(plane, -1, 0))
                 / np.maximum(_shift(m, 1, 0) + _shift(m, -1, 0), 1.0))
        d_num = (_shift(plane, 1, 1) + _shift(plane, 1, -1)
                 + _shift(plane, -1, 1) + _shift(plane, -1, -1))
        d_den = (_shift(m, 1, 1) + _shift(m, 1, -1)
                 + _shift(m, -1, 1) + _shift(m, -1, -1))
        row, col = (yy % 2) == py, (xx % 2) == px
        chan = plane.copy()
        chan = np.where(~has & row & ~col, h_avg, chan)
        chan = np.where(~has & ~row & col, v_avg, chan)
        chan = np.where(~has & ~row & ~col, d_num / np.maximum(d_den, 1.0), chan)
        out[:, :, ci] = chan
    return out


def _dark_subtracted_frame(seed=11):
    """A small sky-ish frame that has been dark-subtracted by an *integer* master
    — the reachable trigger, where ~10% of pixels land exactly on 0."""
    rng = np.random.default_rng(seed)
    light = rng.integers(100, 140, size=(12, 16)).astype(np.float32)
    dark = rng.integers(100, 130, size=(12, 16)).astype(np.float32)
    return np.maximum(light - dark, 0.0).astype(np.float32)


@pytest.mark.parametrize("pattern", ["RGGB", "BGGR", "GRBG", "GBRG"])
def test_debayer_counts_a_genuine_zero_sample(pattern):
    """A sample that reads exactly 0.0 is a datum, not an absent site: it must be
    averaged into its neighbours' interpolation like any other value.

    Fails before the fix on every one of the four Bayer layouts — a wrong parity
    would corrupt every frame, so all four are pinned.
    """
    mosaic = _dark_subtracted_frame()
    assert float((mosaic == 0).mean()) > 0.05, "the trigger must actually be present"
    got = bilinear_debayer(mosaic, pattern=pattern)
    want = _reference_debayer(mosaic, pattern)
    assert np.allclose(got, want, atol=1e-4), (
        pattern, float(np.abs(got - want).max()))
    # And the old value-mask rule really did differ here — otherwise the test
    # above would be pinning nothing.
    assert not np.allclose(_legacy_debayer(mosaic, pattern), want, atol=1e-4)


@pytest.mark.parametrize("pattern", ["RGGB", "BGGR", "GRBG", "GBRG"])
def test_debayer_unchanged_on_an_ordinary_frame(pattern):
    """The guardrail: this is the on-by-default hot path, so a frame with no
    exact-0 samples — which is every frame a float-averaged master dark produces
    — must come out **byte-for-byte** as it did before."""
    rng = np.random.default_rng(3)
    mosaic = rng.uniform(50.0, 4000.0, size=(12, 16)).astype(np.float32)
    assert not (mosaic == 0).any()
    got = bilinear_debayer(mosaic, pattern=pattern)
    assert np.array_equal(got, _legacy_debayer(mosaic, pattern))
    assert np.allclose(got, _reference_debayer(mosaic, pattern), atol=1e-3)


def test_debayer_all_zero_frame_stays_zero():
    """The degenerate end of the same change: a frame of genuine zeros (a fully
    dark-subtracted flat patch) interpolates to zeros, not to a division-by-count
    surprise."""
    for pattern in ("RGGB", "BGGR", "GRBG", "GBRG"):
        rgb = bilinear_debayer(np.zeros((8, 10), dtype=np.float32), pattern=pattern)
        assert np.array_equal(rgb, np.zeros((8, 10, 3), dtype=np.float32))
