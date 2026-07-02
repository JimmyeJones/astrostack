"""Calibration path NaN/coverage audit — the mosaic-edge (partial-overlap) case.

The last piece of the NaN/coverage audit series (channel combine done v0.16.1,
mono single-frame v0.22.1, mono mosaic-edge v0.28.1). Here two dark/flat-
*calibrated* frames whose sky footprints only partially overlap are stacked onto
a union canvas. Applying a dark subtraction + flat division must not turn the
uncovered margin into finite zeros: the "no coverage" pixels have to stay NaN,
never be zero-filled (a black wedge that would drag downstream reductions toward
zero), while the covered interior stays finite.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("scipy")

from astropy.io import fits

from seestack.io.project import FrameRow, Project
from seestack.stack.stacker import StackOptions, run_stack
from tests.synth import make_synth_wcs_text, write_seestar_fits


def _write_master(path, shape, level, *, kind="dark"):
    """A tiny constant master FITS matching the raw frame shape (h, w)."""
    hdu = fits.PrimaryHDU(data=np.full(shape, level, dtype=np.float32))
    hdu.header["EXPTIME"] = 30.0
    hdu.header["GAIN"] = 80.0
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.header["FRAME"] = kind
    hdu.writeto(path, overwrite=True)
    return str(path)


def test_calibration_mosaic_edge_partial_overlap_stays_nan(tmp_path):
    proj = Project.create(tmp_path / "proj", name="CalMosaic")
    # Same partial-overlap geometry as the mono mosaic-edge audit: offset the two
    # frames' WCS in RA by ~0.35° (about half the ~0.67° field) so their
    # footprints overlap in the middle but each leaves a margin the other never
    # covers → a union canvas with genuinely uncovered corners.
    for ra, tag in ((83.60, "a"), (83.95, "b")):
        wcs_text = make_synth_wcs_text(ra_center_deg=ra)
        fp = write_seestar_fits(tmp_path / f"{tag}.fit", add_wcs=True, n_stars=25,
                                seed=20, ra_center_deg=ra)
        proj.add_frame(FrameRow(
            id=None, source_path=str(fp), cached_path=str(fp),
            wcs_json=wcs_text, width_px=480, height_px=320,
            bayer_pattern="RGGB", accept=True,
            ra_center_deg=ra, dec_center_deg=-5.4,
        ))

    # Raw Bayer frames are 320×480 (h×w). A gentle dark pedestal + a constant
    # flat (normalises to 1.0) exercises the (raw − dark) / flat path.
    dark_path = _write_master(tmp_path / "dark.fit", (320, 480), 5.0, kind="dark")
    flat_path = _write_master(tmp_path / "flat.fit", (320, 480), 1000.0, kind="flat")

    result = run_stack(proj, StackOptions(
        sigma_clip=False, background_flatten=False, mosaic_canvas="union",
        dark_path=dark_path, flat_path=flat_path))
    proj.close()

    # A real partial-coverage canvas: some pixels seen by neither frame (0),
    # some by both (2).
    assert result.coverage_min == 0
    assert result.coverage_max == 2

    with fits.open(result.fits_path) as hdul:
        data = np.asarray(hdul[0].data, dtype=np.float32)
    ch0 = data[0] if data.ndim == 3 else data
    # Uncovered margin stays NaN through calibration; interior is real signal.
    assert np.isnan(ch0).any(), "expected uncovered mosaic-edge pixels to be NaN"
    assert np.isfinite(ch0).any()
    assert np.nanmax(ch0) > 0
    # The no-coverage pixels must be NaN, never 0 — calibration (dark subtract +
    # flat divide) must not fabricate a zero wedge where there is no coverage.
    assert not np.any(ch0 == 0.0)
