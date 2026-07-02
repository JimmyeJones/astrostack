"""Provenance metadata written into the output ``master.fits`` header.

The stack writer records how a stack was made (target, frame count, integration
time, per-sub exposure, method) so the saved FITS self-documents for downstream
tools. These are purely additive header cards — they must never break the write,
even for hostile or non-FITS-safe values.
"""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from seestack.stack.output import _merge_header_meta, write_stack_outputs


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
