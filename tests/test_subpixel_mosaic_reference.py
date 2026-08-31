"""Sub-pixel refinement survives a mosaic whose reference tile is off-centre.

``run_stack`` builds the sub-pixel-refine reference patch by aligning the
reference frame to the output canvas, embedding *just that window* into an
otherwise-NaN full canvas, and taking a patch out of it. The patch used to come
from the geometric centre of the whole canvas — fine for a single-field target,
where the frame is the canvas, but wrong for a **mosaic**, whose union canvas is
larger than any one panel.

``pick_reference_frame`` picks the frame nearest the *median* pointing, which on
a lopsided mosaic (most subs on one end) is an end panel — and an end panel need
not touch the middle of the union canvas at all. The patch was then entirely NaN,
so every frame's ``phase_cross_correlation`` raised ``ValueError: NaN values
found``, the broad ``except`` swallowed it, and the finished mosaic quietly
stacked at whole-pixel alignment: softer than it should be, with nothing in the
result saying why.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("skimage")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

W, H = 480, 320
PIXSCALE = 5.0
# Panels stepped by most of a field, so the union is a real mosaic with overlap
# strips (the geometry tests/test_photometric_mosaic_auto.py uses).
STEP_DEG = W * PIXSCALE / 3600.0 * 0.8
DEC = -5.4
# Subs per panel, most of them on panel 0. The median pointing therefore lands
# on panel 0, so that end panel becomes the reference — and with four panels the
# union canvas is wide enough that panel 0 misses its centre entirely.
PANEL_COUNTS = (4, 1, 1, 1)


def _lopsided_mosaic_project(tmp_path) -> Project:
    proj = Project.create(tmp_path / "p", name="lopsided-mosaic")
    raws = tmp_path / "raws"
    raws.mkdir()
    for panel, count in enumerate(PANEL_COUNTS):
        ra = 83.6 + panel * STEP_DEG
        for j in range(count):
            path = write_seestar_fits(
                raws / f"p{panel}_{j}.fit", add_wcs=True, seed=100 + 10 * panel + j,
                n_stars=40, ra_center_deg=ra, dec_center_deg=DEC,
                pixscale_arcsec=PIXSCALE,
            )
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(
                    width=W, height=H, ra_center_deg=ra, dec_center_deg=DEC,
                    pixscale_arcsec=PIXSCALE),
                ra_center_deg=ra, dec_center_deg=DEC,
            ))
    return proj


def _run_and_capture_patch(tmp_path, monkeypatch, name: str) -> dict:
    """Stack the lopsided mosaic with refine on, capturing the reference patch
    ``run_stack`` built and the canvas it was cut from."""
    import seestack.stack.stacker as st

    seen: dict = {}
    real = st.extract_reference_patch

    def spy(rgb, *args, **kwargs):
        patch, origin = real(rgb, *args, **kwargs)
        y0, x0 = origin
        ph, pw = patch.shape
        seen["patch"] = patch
        seen["origin"] = origin
        seen["canvas_shape"] = rgb.shape
        # How much of the patch the reference frame actually covers — the whole
        # question this test is about.
        seen["covered"] = float(
            np.isfinite(rgb[y0:y0 + ph, x0:x0 + pw, 1]).mean())
        return patch, origin

    monkeypatch.setattr(st, "extract_reference_patch", spy)

    proj = _lopsided_mosaic_project(tmp_path)
    try:
        run_stack(proj, StackOptions(output_name=name, max_workers=1,
                                     sigma_clip=False, subpixel_refine=True))
    finally:
        proj.close()
    assert "patch" in seen, "the reference patch was never built"
    return seen


def test_mosaic_reference_patch_lands_on_the_reference_panel(tmp_path, monkeypatch):
    """The patch must be cut from data the reference frame actually covers."""
    seen = _run_and_capture_patch(tmp_path, monkeypatch, "refpatch")

    # The canvas really is a mosaic — wider than one panel, so the blind
    # centre-of-canvas patch had somewhere to go wrong.
    assert seen["canvas_shape"][1] > W * 2, seen["canvas_shape"]
    # Not 100 %: the patch is a fixed 512² window centred on the panel, and the
    # panel is 480 px wide with a few pixels of edge inset — so its own edges
    # trim a little off. What matters is that it is overwhelmingly real data
    # (it was 0 % before) and comfortably clear of the stand-down threshold.
    assert seen["covered"] > 0.8, (
        f"reference patch only {seen['covered']:.0%} covered at "
        f"{seen['origin']} on a {seen['canvas_shape']} canvas — refinement "
        "would be correlating against fill, not stars"
    )
    assert np.all(np.isfinite(seen["patch"]))
    # Real structure, not a flat fill: a NaN patch replaced by its own median is
    # constant, and constant is exactly what phase correlation cannot use.
    assert float(np.std(seen["patch"])) > 0.0


def test_mosaic_stack_actually_refines_its_frames(tmp_path, monkeypatch):
    """…and the refinement step then runs for real, rather than every frame
    raising on a NaN reference and being swallowed."""
    import skimage.registration as skreg

    real_pcc = skreg.phase_cross_correlation
    calls = {"ok": 0, "raised": 0}

    def counting_pcc(ref, frame, **kwargs):
        try:
            out = real_pcc(ref, frame, **kwargs)
        except Exception:
            calls["raised"] += 1
            raise
        calls["ok"] += 1
        return out

    # ``align.py`` imports the symbol lazily inside the refine helpers, so
    # patching it on its home module is what the workers actually pick up.
    monkeypatch.setattr(skreg, "phase_cross_correlation", counting_pcc)

    _run_and_capture_patch(tmp_path, monkeypatch, "refined")

    assert calls["ok"] > 0, (
        "no frame's phase correlation succeeded — refinement was silently off"
    )
    assert calls["raised"] == 0, (
        f"{calls['raised']} correlations raised and were swallowed"
    )
