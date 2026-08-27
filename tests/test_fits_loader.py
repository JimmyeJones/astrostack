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


def _reference_debayer(mosaic: np.ndarray, pattern: str) -> np.ndarray:
    """An independent, deliberately slow reference bilinear debayer.

    Written per-pixel from the definition — for each missing colour site, average
    the values of the *nearest same-channel sample sites that exist on the frame* —
    with sample sites identified purely by their Bayer position. It knows nothing
    about sparse planes or shifted masks, so it can't share a bug with the
    production vectorised path.
    """
    layouts = {
        "RGGB": (("r", "g"), ("g", "b")),
        "BGGR": (("b", "g"), ("g", "r")),
        "GRBG": (("g", "r"), ("b", "g")),
        "GBRG": (("g", "b"), ("r", "g")),
    }
    (tl, tr), (bl, br) = layouts[pattern]
    site = {(0, 0): tl, (0, 1): tr, (1, 0): bl, (1, 1): br}
    h, w = mosaic.shape
    out = np.zeros((h, w, 3), dtype=np.float64)
    for ci, ch in enumerate("rgb"):
        # Every position that is a genuine sample site of this channel.
        samples = {(y, x) for y in range(h) for x in range(w)
                   if site[(y % 2, x % 2)] == ch}
        for y in range(h):
            for x in range(w):
                if (y, x) in samples:
                    out[y, x, ci] = mosaic[y, x]
                    continue
                # Nearest same-channel neighbours: cross for G, and for R/B the
                # horizontal / vertical / diagonal pair depending on which axis is
                # off the sample grid.
                if ch == "g":
                    offsets = ((1, 0), (-1, 0), (0, 1), (0, -1))
                else:
                    sy, sx = next(iter(
                        p for p, c in site.items() if c == ch))
                    on_row, on_col = (y % 2) == sy, (x % 2) == sx
                    if on_row and not on_col:
                        offsets = ((0, 1), (0, -1))
                    elif on_col and not on_row:
                        offsets = ((1, 0), (-1, 0))
                    else:
                        offsets = ((1, 1), (1, -1), (-1, 1), (-1, -1))
                vals = [mosaic[y + dy, x + dx] for dy, dx in offsets
                        if (y + dy, x + dx) in samples]
                out[y, x, ci] = float(np.mean(vals)) if vals else 0.0
    return out


@pytest.mark.parametrize("pattern", ("RGGB", "BGGR", "GRBG", "GBRG"))
def test_debayer_counts_a_genuine_zero_sample(pattern):
    """A real sample whose value is exactly 0.0 is still a sample, and must be
    counted in the neighbour average of every adjacent missing site.

    The interpolators used to identify sample sites with a ``!= 0`` *value* test,
    which conflated "not this channel's site" (correctly excluded) with "a genuine
    datum that reads 0.0". Dropping those real zeros divided a smaller neighbour
    sum by a smaller count, biasing the interpolated chroma of their neighbours
    upward — reachable on the on-by-default hot path whenever dark subtraction with
    an integer-valued master lands pixels exactly on zero. Checked against an
    independent reference for every Bayer layout.
    """
    rng = np.random.default_rng(3)
    mosaic = rng.uniform(0.0, 200.0, size=(12, 14)).astype(np.float32)
    # Scatter genuine exact-zero samples the way an integer master dark does.
    zeros = rng.random(mosaic.shape) < 0.15
    mosaic[zeros] = 0.0
    assert zeros.any()

    got = bilinear_debayer(mosaic, pattern=pattern)
    want = _reference_debayer(mosaic, pattern)
    assert np.allclose(got, want, atol=1e-4), (
        pattern, float(np.max(np.abs(got - want))))


def test_debayer_unchanged_when_no_sample_is_exactly_zero():
    """The positional sample mask must be *byte-for-byte* identical to the old
    value test on any frame with no exact-0 sample — i.e. every ordinary frame,
    including the float-averaged-master install. These hashes were taken from the
    pre-fix implementation, so a drift here means the fix changed the common path.
    """
    import hashlib

    rng = np.random.default_rng(7)
    mosaic = rng.uniform(800.0, 1200.0, size=(34, 46)).astype(np.float32)
    assert (mosaic != 0).all()
    golden = {
        "RGGB": "a0052065d576bd5a183b7de0c03fe8125246ff19040f901c62e74a13105dbc04",
        "BGGR": "f9546824af89f43cf1d40b0de37b432bcb894d57f68724575560872cda7c27f3",
        "GRBG": "6285901d1b7616d3d498eae6a5d7fb580a7f8092b99b78c1d715d98bc0ca5a59",
        "GBRG": "601aa61145ae09d963ce06351297b9a23669fbab567e739ab1b6e55f204f3448",
    }
    for pattern, want in golden.items():
        out = bilinear_debayer(mosaic, pattern=pattern)
        assert hashlib.sha256(out.tobytes()).hexdigest() == want, pattern


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
