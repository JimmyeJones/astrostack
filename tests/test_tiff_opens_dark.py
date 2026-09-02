"""The TIFF download's copy, pinned to the file rather than to a string.

History's artifact menu now says a plain stack's TIFF "opens dark until you
stretch it in another app", and says the opposite for an editor export. Both
claims are properties of the bytes ``write_stack_outputs`` writes, so this
measures them there — the same shape as the full-res-PNG cap guard, and for the
same reason: a download's copy is written once and the writer underneath it
evolves.

Note the claim is deliberately about *how it looks*, not about scaling. A linear
TIFF is rescaled to fill sixteen bits (``_to_uint16_linear`` maps the robust
0.5–99.9 percentile range onto 0–65535), so "dark" is not "empty" — it is that
no *curve* was applied, which on real astro data leaves the faint object sitting
just above black while a star reaches white. That is exactly what a beginner
sees when they open it, so that is what is measured.
"""

from __future__ import annotations

import numpy as np
import tifffile

from seestack.stack.output import write_stack_outputs


def _sky_with_a_faint_object(h: int = 128, w: int = 128) -> np.ndarray:
    """A realistic linear stack: a low sky, a faint extended object just above
    it, and a *field* of stars spanning a wide dynamic range. Deterministic.

    The star field is what makes this realistic rather than a toy — the linear
    packer maps the robust 0.5–99.9 percentile range onto 0–65535, so it is the
    bright end of the star distribution that decides where the sky and the object
    land. A scene with one lone star has its 99.9th percentile down in the
    nebulosity, and the linear file comes out looking mid-grey, which no real
    stack ever does."""
    rng = np.random.default_rng(7)
    rgb = np.full((h, w, 3), 0.010, dtype=np.float32)      # sky
    rgb += rng.normal(0.0, 0.0006, rgb.shape).astype(np.float32)
    rgb[40:88, 40:88, :] += 0.004                          # the faint object
    ys = rng.integers(0, h, 400)
    xs = rng.integers(0, w, 400)
    amps = (rng.pareto(1.2, 400) + 1.0) * 0.05             # a few very bright
    for y, x, a in zip(ys, xs, amps, strict=True):
        rgb[y, x, :] += a
    return rgb


def _median_level(path) -> float:
    """The TIFF's median level as a 0–1 fraction of full scale — "how bright does
    this look when it opens?"."""
    arr = tifffile.imread(path)
    return float(np.median(arr)) / 65535.0


def test_a_plain_stacks_tiff_really_does_open_dark(tmp_path):
    rgb = _sky_with_a_faint_object()
    cov = np.ones(rgb.shape[:2], dtype=np.float32)
    paths = write_stack_outputs(
        project_dir=tmp_path, rgb=rgb, coverage=cov, wcs_text=None,
        out_basename="linear",
    )
    # The default mode is linear — the case the warning is written for. The sky
    # and the object land within a couple of percent of black, which is what
    # "opens dark" means to the person who double-clicks it.
    assert _median_level(paths["tiff"]) < 0.02


def test_an_editor_exports_tiff_opens_as_the_finished_picture(tmp_path):
    """`already_display=True` writes the tone-mapped result verbatim, so the file
    opens looking like the picture on screen — which is why the menu must not
    warn about it. Written by the same call that records `display_space: true` on
    the run, which is the fact the frontend reads."""
    # A finished display-space picture: mid-grey, as a stretched image is.
    disp = np.full((64, 64, 3), 0.45, dtype=np.float32)
    cov = np.ones(disp.shape[:2], dtype=np.float32)
    paths = write_stack_outputs(
        project_dir=tmp_path, rgb=disp, coverage=cov, wcs_text=None,
        out_basename="edited", already_display=True,
    )
    assert _median_level(paths["tiff"]) > 0.35


def test_an_editor_exports_tiff_is_the_same_file_whichever_mode_is_asked_for(tmp_path):
    """The editor's export panel used to offer a "TIFF: Linear / Auto-stretched"
    choice; it now *states* what the export writes instead, because the choice
    could not change it — `_write_tiff` returns in its `already_display` branch
    before `mode` is read, and `webapp/pipeline.py` passes `already_display=True`
    on every editor export.

    Pinned here, on the bytes, rather than on the removed control: the copy in the
    panel ("saves the picture exactly as shown") and in `tiffDownload.ts` ("the
    finished picture, at full depth") are both claims about this file. If a future
    change ever makes `mode` mean something for a display-space export, this fails
    and that copy has to be rewritten in the same commit."""
    disp = np.full((48, 48, 3), 0.45, dtype=np.float32)
    disp[8:24, 8:24, :] = 0.9                              # something to differ over
    cov = np.ones(disp.shape[:2], dtype=np.float32)
    both = {
        mode: write_stack_outputs(
            project_dir=tmp_path / mode, rgb=disp, coverage=cov, wcs_text=None,
            out_basename="edited", tiff_mode=mode, already_display=True,
        )["tiff"]
        for mode in ("linear", "autostretch")
    }
    assert np.array_equal(tifffile.imread(both["linear"]),
                          tifffile.imread(both["autostretch"]))
    # And the mode is not inert in general — the stacker's own control still works,
    # so this is a property of a display-space export, not a dead parameter.
    rgb = _sky_with_a_faint_object()
    plain_cov = np.ones(rgb.shape[:2], dtype=np.float32)
    plain = {
        mode: write_stack_outputs(
            project_dir=tmp_path / f"plain_{mode}", rgb=rgb, coverage=plain_cov,
            wcs_text=None, out_basename="m", tiff_mode=mode,
        )["tiff"]
        for mode in ("linear", "autostretch")
    }
    assert not np.array_equal(tifffile.imread(plain["linear"]),
                              tifffile.imread(plain["autostretch"]))


def test_the_autostretch_mode_is_the_other_non_dark_case(tmp_path):
    """The stacker's other TIFF mode bakes the export stretch in, so it opens
    bright too — the second case `tiffOpensAsShown` treats as "as shown"."""
    rgb = _sky_with_a_faint_object()
    cov = np.ones(rgb.shape[:2], dtype=np.float32)
    linear = write_stack_outputs(
        project_dir=tmp_path / "a", rgb=rgb, coverage=cov, wcs_text=None,
        out_basename="m", tiff_mode="linear",
    )
    stretched = write_stack_outputs(
        project_dir=tmp_path / "b", rgb=rgb, coverage=cov, wcs_text=None,
        out_basename="m", tiff_mode="autostretch",
    )
    assert _median_level(stretched["tiff"]) > 3 * _median_level(linear["tiff"])
