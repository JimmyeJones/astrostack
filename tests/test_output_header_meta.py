"""Provenance metadata written into the output ``master.fits`` header.

The stack writer records how a stack was made (target, frame count, integration
time, per-sub exposure, method) so the saved FITS self-documents for downstream
tools. These are purely additive header cards — they must never break the write,
even for hostile or non-FITS-safe values.
"""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from seestack.stack.output import (
    DISPLAY_SPACE_CARD, _merge_header_meta, fits_is_display_space,
    write_stack_outputs,
)


def _read_header(fits_path):
    with fits.open(fits_path) as hdul:
        return dict(hdul[0].header)


def test_header_meta_is_written_into_output_fits(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    coverage = np.ones((8, 8), dtype=np.float32)

    paths = write_stack_outputs(
        project_dir=project_dir,
        rgb=rgb,
        coverage=coverage,
        wcs_text=None,
        out_basename="master",
        header_meta={
            "OBJECT": ("M42", "target name"),
            "NFRAMES": (120, "frames combined"),
            "EXPTOTAL": (1200.0, "integration time (s)"),
            "STACKER": "sigma-clip",
        },
    )

    hdr = _read_header(paths["fits"])
    assert hdr["OBJECT"] == "M42"
    assert hdr["NFRAMES"] == 120
    assert hdr["EXPTOTAL"] == 1200.0
    assert hdr["STACKER"] == "sigma-clip"
    # The base cards must still be present.
    assert hdr["CREATOR"] == "Seestack"


def test_omitting_header_meta_reproduces_base_header(tmp_path):
    """No header_meta → output identical to before (backward compatible)."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    rgb = np.zeros((4, 4, 3), dtype=np.float32)
    coverage = np.ones((4, 4), dtype=np.float32)

    paths = write_stack_outputs(
        project_dir=project_dir, rgb=rgb, coverage=coverage, wcs_text=None,
    )
    hdr = _read_header(paths["fits"])
    assert "OBJECT" not in hdr
    assert "NFRAMES" not in hdr
    assert hdr["CREATOR"] == "Seestack"


def test_merge_header_meta_skips_none_and_bad_keys():
    hdr = fits.Header()
    _merge_header_meta(hdr, {
        "OBJECT": "M31",
        "MISSING": None,          # None → skipped
        "": "no key",             # empty after sanitising → skipped
        "!!!": "also skipped",    # sanitises to empty → skipped
        "toolongkeyword": 5,      # truncated to 8 chars, still written
    })
    assert hdr["OBJECT"] == "M31"
    assert "MISSING" not in hdr
    assert hdr["TOOLONGK"] == 5


def test_merge_header_meta_appends_history_lines():
    hdr = fits.Header()
    _merge_header_meta(hdr, {
        "OBJECT": "M31",
        "HISTORY": ["step one", "step two", "x" * 200],  # list → one card each
    })
    hist = [str(c) for c in hdr["HISTORY"]]
    assert "step one" in hist
    assert "step two" in hist
    # each card stays within the FITS commentary limit
    assert all(len(line) <= 72 for line in hist)
    # HISTORY is not written as a normal keyword
    assert hdr["OBJECT"] == "M31"


def test_merge_header_meta_coerces_and_truncates_values():
    hdr = fits.Header()
    long_str = "x" * 200
    _merge_header_meta(hdr, {
        "NOTES": long_str,        # long string → truncated, no crash
        "OBJ": [1, 2, 3],         # non-scalar → str()'d
        "FLAG": True,             # bool → FITS logical
    })
    assert len(str(hdr["NOTES"])) <= 68
    assert hdr["FLAG"] is True
    assert isinstance(hdr["OBJ"], str)


def test_editor_export_writes_display_data_verbatim(tmp_path):
    """An editor export is already display-space [0,1]; the preview PNG and TIFF
    must be written as-is (not re-stretched / linear-rescaled), so the History
    thumbnail matches what the editor showed. Regression for the 'exports stored
    as linear' bug."""
    from PIL import Image
    import tifffile

    # A 0->1 display-space gradient: a faithful write reproduces it (mean ~0.5).
    ramp = np.linspace(0.0, 1.0, 64, dtype=np.float32)
    rgb = np.repeat(np.tile(ramp, (16, 1))[..., None], 3, axis=2)
    cov = np.ones(rgb.shape[:2], dtype=np.float32)

    disp = write_stack_outputs(tmp_path, rgb, cov, wcs_text=None,
                               out_basename="edit", already_display=True)
    png = np.asarray(Image.open(disp["preview"]).convert("RGB"))
    assert abs(int(png.mean()) - 127) <= 3               # ~0.5 mean, not re-stretched
    tif = tifffile.imread(disp["tiff"])
    assert abs(int(tif.mean()) - 32768) <= 400           # verbatim to 16-bit

    # The same data written as a *linear stack* is autostretched (STF darkens the
    # sky), so it looks materially different — proving the flag changes behaviour.
    lin = write_stack_outputs(tmp_path, rgb, cov, wcs_text=None,
                              out_basename="lin", already_display=False)
    png_lin = np.asarray(Image.open(lin["preview"]).convert("RGB"))
    assert abs(int(png_lin.mean()) - int(png.mean())) > 30


def test_editor_export_fits_marked_display_space(tmp_path):
    """An editor export (already_display) stamps the FITS as display-space so
    renderers (and Siril/PixInsight) don't stretch it again; a linear stack keeps
    the historical linear ADU header with no marker."""
    rgb = np.clip(np.linspace(0, 1, 48, dtype=np.float32), 0, 1)
    rgb = np.repeat(np.tile(rgb, (12, 1))[..., None], 3, axis=2)
    cov = np.ones(rgb.shape[:2], dtype=np.float32)

    disp = write_stack_outputs(tmp_path, rgb, cov, wcs_text=None,
                               out_basename="edit", already_display=True)
    hdr = _read_header(disp["fits"])
    assert hdr[DISPLAY_SPACE_CARD] is True
    assert "display" in str(hdr["BUNIT"]).lower()
    assert fits_is_display_space(disp["fits"]) is True

    lin = write_stack_outputs(tmp_path, rgb, cov, wcs_text=None,
                              out_basename="lin", already_display=False)
    hlin = _read_header(lin["fits"])
    assert DISPLAY_SPACE_CARD not in hlin           # old/linear stacks carry no marker
    assert str(hlin["BUNIT"]) == "ADU"
    assert fits_is_display_space(lin["fits"]) is False


def test_fits_is_display_space_tolerates_missing_file(tmp_path):
    """A bad/missing path is 'not display space' (renderers fall back to linear),
    never an exception on the hot render path."""
    assert fits_is_display_space(tmp_path / "does-not-exist.fits") is False


# --- Dark exposure-scaling provenance (companion to the v0.82.0 feature) --------
# When scale_dark_to_light actually scaled a master dark to the subs' exposure,
# _build_output_header_meta must stamp DARKSCAL/DARKDEXP/DARKLEXP so the run Info /
# History can show "Dark scaled to sub exposure · 30s → 10s". Mirrors the PHOTNORM
# provenance: present only when scaling really happened, omitted otherwise.
from types import SimpleNamespace  # noqa: E402

from seestack.stack.stacker import StackOptions, _build_output_header_meta  # noqa: E402


def _meta_for(*, scale, dark_exp, light_exp, has_bias=True, has_dark=True):
    proj = SimpleNamespace(get_meta=lambda k: "M42" if k == "name" else None)
    frames = [SimpleNamespace(exposure_s=light_exp) for _ in range(5)]
    cal = SimpleNamespace(
        scale_dark_to_light=scale,
        dark_exposure_s=dark_exp,
        bias=np.zeros((4, 4), dtype=np.float32) if has_bias else None,
        dark=np.zeros((4, 4), dtype=np.float32) if has_dark else None,
        describe=lambda: "dark+bias",
    )
    return _build_output_header_meta(proj, frames, StackOptions(), 5, calibration=cal)


def test_dark_scaling_provenance_stamped_when_scaled():
    meta = _meta_for(scale=True, dark_exp=30.0, light_exp=10.0)
    assert meta["DARKSCAL"][0] == "exposure"
    assert meta["DARKDEXP"][0] == 30.0
    assert meta["DARKLEXP"][0] == 10.0


def test_dark_scaling_provenance_absent_when_option_off():
    meta = _meta_for(scale=False, dark_exp=30.0, light_exp=10.0)
    assert "DARKSCAL" not in meta


def test_dark_scaling_provenance_absent_for_matched_exposure():
    # A matched exposure leaves the dark unscaled (see _effective_dark), so no
    # scaling actually happened → nothing to advertise.
    meta = _meta_for(scale=True, dark_exp=30.0, light_exp=30.0)
    assert "DARKSCAL" not in meta


def test_dark_scaling_provenance_absent_without_bias_or_exposure():
    # No bias to hold the pedestal, or an unknown dark exposure → the dark was
    # used unscaled, so the stamp is omitted.
    assert "DARKSCAL" not in _meta_for(scale=True, dark_exp=30.0, light_exp=10.0,
                                       has_bias=False)
    assert "DARKSCAL" not in _meta_for(scale=True, dark_exp=None, light_exp=10.0)
