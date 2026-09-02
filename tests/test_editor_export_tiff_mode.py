"""An editor export's TIFF mode changes nothing — pin the fact the UI now states.

The editor's "Export full resolution" panel used to carry a **TIFF: Linear /
Auto-stretched** select whose own hint said *"both options produce that same
result"*. That was accurate, and it made the control a decision a beginner had
to stop and make, on the priority-1 surface, that changed nothing: an editor
export writes the recipe's already tone-mapped image, so
:func:`seestack.stack.output._write_tiff` short-circuits on ``already_display``
**before** ``mode`` is read.

The hint's other half — *"for the underlying unstretched data, use the separate
FITS output"* — was simply wrong: an export's FITS is display-space too, stamped
``SSDISPLY`` precisely so nothing re-stretches it. The unstretched data lives in
the *source stack's* own files, which is what the panel says now.

These tests pin both facts, so the copy stays true. If a future change ever
makes ``tiff_mode`` mean something on this path, the first test fails and the
panel has to start asking again.
"""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from seestack.stack.output import DISPLAY_SPACE_CARD, write_stack_outputs


def _edited_picture(h: int = 40, w: int = 60) -> np.ndarray:
    """What the editor hands the exporter: a display-space [0, 1] result, i.e.
    a recipe's tone-mapped image rather than a linear stack."""
    yy, xx = np.mgrid[0:h, 0:w]
    ramp = (xx / (w - 1)).astype(np.float32)
    glow = np.exp(-(((xx - w / 2) / 12.0) ** 2 + ((yy - h / 2) / 9.0) ** 2)).astype(np.float32)
    rgb = np.stack([0.15 + 0.7 * glow, 0.12 + 0.5 * ramp, 0.10 + 0.4 * glow], axis=-1)
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def _export(tmp_path, mode: str):
    """Write an editor export exactly as ``webapp.pipeline._export_edit_body``
    does — the one call site, which always passes ``already_display=True``."""
    rgb = _edited_picture()
    project_dir = tmp_path / mode
    project_dir.mkdir()
    return write_stack_outputs(
        project_dir=project_dir, rgb=rgb,
        coverage=np.ones(rgb.shape[:2], dtype=np.float32),
        wcs_text=None, out_basename="master_edit", tiff_mode=mode,
        already_display=True,
    )


def test_editor_export_tiff_is_identical_for_both_modes(tmp_path):
    """The choice the panel used to ask about produces byte-identical files."""
    linear = _export(tmp_path, "linear")["tiff"].read_bytes()
    stretched = _export(tmp_path, "autostretch")["tiff"].read_bytes()
    assert linear == stretched


def test_editor_export_tiff_is_the_picture_as_shown(tmp_path):
    """...and what both write is the edit itself, not a rescale of it — so the
    panel can promise "exactly as shown here"."""
    import tifffile

    rgb = _edited_picture()
    paths = _export(tmp_path, "linear")
    u16 = tifffile.imread(paths["tiff"])
    expected = (np.clip(rgb, 0.0, 1.0) * 65535.0).astype(np.uint16)
    assert np.array_equal(u16, expected)


def test_editor_export_fits_is_display_space_not_unstretched(tmp_path):
    """The removed hint pointed at this file for "the underlying unstretched
    data". It is display-space, and says so — which is why the panel now points
    at the source stack's files instead."""
    paths = _export(tmp_path, "linear")
    header = fits.getheader(paths["fits"])
    assert bool(header.get(DISPLAY_SPACE_CARD, False)) is True
    assert header["BUNIT"] == "display"


def test_plain_stack_tiff_modes_still_differ(tmp_path):
    """The guard on the fix: ``tiff_mode`` is *not* dead in general. On the
    stacker's own path — where the data really is linear — the two modes still
    write different files, and that control keeps its meaning in Stack settings."""
    rng = np.random.default_rng(7)
    rgb = np.clip(
        0.02 + rng.normal(0.0, 0.003, (40, 60, 3)).astype(np.float32), 0.0, 1.0)
    rgb[20, 30, :] = 0.9  # a star core, so the two mappings can't coincide

    def write(mode: str):
        d = tmp_path / f"plain_{mode}"
        d.mkdir()
        return write_stack_outputs(
            project_dir=d, rgb=rgb,
            coverage=np.ones(rgb.shape[:2], dtype=np.float32),
            wcs_text=None, out_basename="master", tiff_mode=mode,
        )["tiff"].read_bytes()

    assert write("linear") != write("autostretch")
