"""Reference-canvas suggestion when a non-drizzle mosaic is over the budget.

The drizzle-off mirror of the ``suggested_drizzle_scale`` path: when a union
mosaic canvas alone blows the memory budget but the smaller reference-frame
canvas would fit, the estimate offers a one-click "use the reference canvas".
"""

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.stack.stacker import StackOptions, estimate_stack
from tests.synth import make_synth_wcs_text


def _mosaic_project(tmp_path) -> Project:
    """A 2×2 mosaic: four pointings, a few frames each, on 480×320 panels."""
    proj = Project.create(tmp_path / "p", name="mosaic")
    fov_w_deg = 480 * 5.0 / 3600.0
    fov_h_deg = 320 * 5.0 / 3600.0
    dx, dy = fov_w_deg * 0.75, fov_h_deg * 0.75  # 25% overlap
    centers = [
        (100.0, 20.0), (100.0 + dx, 20.0),
        (100.0, 20.0 + dy), (100.0 + dx, 20.0 + dy),
    ]
    for ra, dec in centers:
        wcs_text = make_synth_wcs_text(
            width=480, height=320, ra_center_deg=ra, dec_center_deg=dec,
            pixscale_arcsec=5.0,
        )
        for i in range(3):
            proj.add_frame(FrameRow(
                source_path=f"{ra}_{dec}_{i}.fit",
                cached_path=f"{ra}_{dec}_{i}.fit",  # truthy; need not exist for sizing
                width_px=480, height_px=320, bayer_pattern="RGGB",
                wcs_json=wcs_text, ra_center_deg=ra, dec_center_deg=dec,
                pixscale_arcsec=5.0,
            ))
    return proj


def test_suggests_reference_canvas_when_union_over_budget(tmp_path):
    proj = _mosaic_project(tmp_path)
    try:
        opts = StackOptions(drizzle=False, mosaic_canvas="auto")
        # Reference 480×320 ≈ 7.4 MB peak; the 2×2 union ≈ 4× that. A ~15 MB
        # budget refuses the union but the reference canvas still fits.
        est = estimate_stack(proj, opts, memory_budget_gb=15e-3)
        assert est.is_mosaic is True
        assert est.would_exceed is True
        assert est.suggested_reference_canvas is True
        # Drizzle-off path never offers a drizzle scale.
        assert est.suggested_drizzle_scale is None
    finally:
        proj.close()


def test_no_reference_suggestion_when_union_fits(tmp_path):
    proj = _mosaic_project(tmp_path)
    try:
        opts = StackOptions(drizzle=False, mosaic_canvas="auto")
        est = estimate_stack(proj, opts, memory_budget_gb=1.0)  # generous
        assert est.is_mosaic is True
        assert est.would_exceed is False
        assert est.suggested_reference_canvas is False
    finally:
        proj.close()


def test_no_reference_suggestion_when_even_reference_exceeds(tmp_path):
    proj = _mosaic_project(tmp_path)
    try:
        opts = StackOptions(drizzle=False, mosaic_canvas="auto")
        # A punishing 1 MB budget: even the reference canvas (~7.4 MB) can't fit,
        # so there's nothing to suggest — dropping the canvas won't rescue it.
        est = estimate_stack(proj, opts, memory_budget_gb=1e-3)
        assert est.would_exceed is True
        assert est.suggested_reference_canvas is False
    finally:
        proj.close()


def test_no_reference_suggestion_when_reference_only_fits_without_reject_planes(tmp_path):
    """A k>1 min/max reject makes the reference canvas need more planes than the
    baseline estimate, and the suggestion must charge them too — otherwise the UI
    offers a reference canvas the run-time OOM guard would then refuse.

    Reference 480×320 ≈ 7.4 MB at the baseline 4 canvas planes, but ≈ 14.7 MB at
    the ``2+2k`` = 8 planes a k=3 min/max reject holds. A ~10 MB budget fits the
    former but not the latter — so the reference canvas does *not* actually fit,
    and no suggestion should be offered (a run on it would raise ``MemoryError``).
    """
    proj = _mosaic_project(tmp_path)
    try:
        opts = StackOptions(
            drizzle=False, mosaic_canvas="auto",
            min_max_reject=True, min_max_reject_count=3,
        )
        est = estimate_stack(proj, opts, memory_budget_gb=10e-3)
        assert est.is_mosaic is True
        assert est.would_exceed is True
        # Before the fix the ref-canvas estimate omitted the reject planes, so it
        # wrongly reported the reference canvas as fitting (True).
        assert est.suggested_reference_canvas is False
    finally:
        proj.close()


def test_reference_canvas_mode_never_suggests(tmp_path):
    proj = _mosaic_project(tmp_path)
    try:
        # Already on the reference canvas → not a mosaic sizing, no suggestion.
        opts = StackOptions(drizzle=False, mosaic_canvas="reference")
        est = estimate_stack(proj, opts, memory_budget_gb=1e-3)
        assert est.is_mosaic is False
        assert est.suggested_reference_canvas is False
    finally:
        proj.close()
