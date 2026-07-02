"""Mono (non-Bayer) stacking: load as luminance, no debayer."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")

from seestack.stack.align import align_one
from tests.synth import make_synth_wcs_text, write_seestar_fits


def test_mono_align_is_grayscale(tmp_path):
    p = write_seestar_fits(tmp_path / "m.fit", add_wcs=True, n_stars=20, seed=4)
    wcs_text = make_synth_wcs_text()
    common = dict(bayer_pattern="RGGB", src_wcs_text=wcs_text, dst_wcs_text=wcs_text,
                  dst_shape=(320, 480), suppress_hot_pixels=False)
    res = align_one(str(p), mono=True, **common)
    assert res is not None
    rgb = res[0]
    finite = np.isfinite(rgb).all(axis=2)
    # In mono mode the three channels are identical (pure luminance).
    np.testing.assert_allclose(rgb[..., 0][finite], rgb[..., 1][finite])
    np.testing.assert_allclose(rgb[..., 1][finite], rgb[..., 2][finite])


def test_color_align_is_not_grayscale(tmp_path):
    # Sanity: with debayering on, channels differ (it's a colour mosaic).
    p = write_seestar_fits(tmp_path / "c.fit", add_wcs=True, n_stars=20, seed=4)
    wcs_text = make_synth_wcs_text()
    res = align_one(str(p), bayer_pattern="RGGB", src_wcs_text=wcs_text,
                    dst_wcs_text=wcs_text, dst_shape=(320, 480),
                    suppress_hot_pixels=False, mono=False)
    assert res is not None
    rgb = res[0]
    finite = np.isfinite(rgb).all(axis=2)
    assert not np.allclose(rgb[..., 0][finite], rgb[..., 2][finite])


def test_mono_full_stack(tmp_path):
    # A small end-to-end mono stack via run_stack using the synth project helper.
    pytest.importorskip("photutils")
    from seestack.io.project import Project
    from seestack.stack.stacker import StackOptions, run_stack
    from tests.synth import write_seestar_fits as _w

    proj_dir = tmp_path / "proj"
    proj = Project.create(proj_dir, name="MonoTarget")
    wcs_text = make_synth_wcs_text()
    from seestack.io.project import FrameRow
    for i in range(4):
        fp = _w(tmp_path / f"f{i}.fit", add_wcs=True, n_stars=25, seed=10 + i)
        proj.add_frame(FrameRow(
            id=None, source_path=str(fp), cached_path=str(fp),
            wcs_json=wcs_text, width_px=480, height_px=320,
            bayer_pattern="RGGB", accept=True,
            ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    result = run_stack(proj, StackOptions(mono=True, sigma_clip=False,
                                          background_flatten=False))
    proj.close()
    assert result.n_frames_used >= 1
    import numpy as _np
    from astropy.io import fits
    with fits.open(result.fits_path) as hdul:
        data = _np.asarray(hdul[0].data, dtype=_np.float32)
    # Output channels identical → grayscale stack.
    if data.ndim == 3:
        ch = [data[c] for c in range(min(3, data.shape[0]))]
        m = _np.isfinite(ch[0]) & _np.isfinite(ch[-1])
        _np.testing.assert_allclose(ch[0][m], ch[-1][m], rtol=1e-4)


def test_mono_single_frame_sigma_clip_is_finite_and_gray(tmp_path):
    """Edge case: a one-frame mono stack with sigma-clip on. Coverage tops out
    at 1, the covered pixels stay finite (a single-coverage pixel has no spread
    to clip against, so the frame must not be rejected into NaN), and the three
    output channels remain identical (pure luminance)."""
    pytest.importorskip("photutils")
    import numpy as _np
    from astropy.io import fits

    from seestack.io.project import FrameRow, Project
    from seestack.stack.stacker import StackOptions, run_stack
    from tests.synth import write_seestar_fits as _w

    proj = Project.create(tmp_path / "proj", name="MonoSingle")
    wcs_text = make_synth_wcs_text()
    fp = _w(tmp_path / "one.fit", add_wcs=True, n_stars=25, seed=7)
    proj.add_frame(FrameRow(
        id=None, source_path=str(fp), cached_path=str(fp),
        wcs_json=wcs_text, width_px=480, height_px=320,
        bayer_pattern="RGGB", accept=True,
        ra_center_deg=83.6, dec_center_deg=-5.4,
    ))
    result = run_stack(proj, StackOptions(mono=True, sigma_clip=True,
                                          sigma_kappa=2.5, background_flatten=False))
    proj.close()

    assert result.n_frames_used == 1
    assert result.coverage_max == 1
    with fits.open(result.fits_path) as hdul:
        data = _np.asarray(hdul[0].data, dtype=_np.float32)
    # Real signal survived the (degenerate) clip rather than becoming NaN/zero.
    assert _np.isfinite(data).any()
    assert _np.nanmax(data) > 0
    if data.ndim == 3:
        ch = [data[c] for c in range(min(3, data.shape[0]))]
        m = _np.isfinite(ch[0]) & _np.isfinite(ch[-1])
        _np.testing.assert_allclose(ch[0][m], ch[-1][m], rtol=1e-4)
