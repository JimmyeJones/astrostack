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


def _clustered_project_with_outlier(tmp_path) -> Project:
    """Eight good frames on one compact pointing + one frame flung 15° away.

    The far frame is a gross plate-solve outlier the mosaic canvas sizing drops
    before it stacks — so a faithful estimate must count 8 frames, not 9.
    """
    proj = Project.create(tmp_path / "p", name="clustered")
    good_wcs = make_synth_wcs_text(
        width=480, height=320, ra_center_deg=50.0, dec_center_deg=10.0,
        pixscale_arcsec=5.0,
    )
    for i in range(8):
        proj.add_frame(FrameRow(
            source_path=f"good_{i}.fit", cached_path=f"good_{i}.fit",
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=good_wcs, ra_center_deg=50.0, dec_center_deg=10.0,
            pixscale_arcsec=5.0,
        ))
    far_wcs = make_synth_wcs_text(
        width=480, height=320, ra_center_deg=65.0, dec_center_deg=10.0,
        pixscale_arcsec=5.0,
    )
    proj.add_frame(FrameRow(
        source_path="far.fit", cached_path="far.fit",
        width_px=480, height_px=320, bayer_pattern="RGGB",
        wcs_json=far_wcs, ra_center_deg=65.0, dec_center_deg=10.0,
        pixscale_arcsec=5.0,
    ))
    return proj


def test_estimate_drops_gross_outliers_like_the_run(tmp_path):
    """Regression: ``estimate_stack`` must exclude the same gross plate-solve
    outliers ``run_stack`` drops during canvas sizing, so its ``n_frames`` matches
    what the run actually stacks.

    Before the fix the estimate never read ``canvas.excluded_frame_ids`` and so
    reported 9 frames for a target the run stacks with 8 (the 15°-away sub is
    dropped as a footprint outlier). Cosmetic — estimate-only — but the estimate
    should not disagree with the run about how many frames there are.
    """
    proj = _clustered_project_with_outlier(tmp_path)
    try:
        opts = StackOptions(drizzle=False, mosaic_canvas="auto")
        est = estimate_stack(proj, opts, memory_budget_gb=1.0)
        # The flung frame is excluded; only the 8 good subs count.
        assert est.n_frames == 8
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


def test_memory_fix_offers_reference_canvas_with_its_peak(tmp_path):
    """The structured ``memory_fix`` mirrors the coarse ``suggested_reference_canvas``
    flag but also carries the concrete lever + the memory the run lands at, so the
    Stack form can show "fits at ~X GB" pre-submit."""
    proj = _mosaic_project(tmp_path)
    try:
        opts = StackOptions(drizzle=False, mosaic_canvas="auto")
        est = estimate_stack(proj, opts, memory_budget_gb=15e-3)
        assert est.would_exceed is True
        assert est.suggested_reference_canvas is True
        assert est.memory_fix is not None
        assert est.memory_fix.kind == "reference_canvas"
        assert est.memory_fix.value is None
        # The named peak genuinely fits the budget (never offer a fix the run-time
        # guard would then refuse) and is smaller than the over-budget union peak.
        assert est.memory_fix.peak_bytes <= est.budget_bytes
        assert est.memory_fix.peak_bytes < est.peak_bytes
    finally:
        proj.close()


def test_memory_fix_prefers_dropping_extra_outlier_passes(tmp_path):
    """When a k>1 min/max reject is the *only* reason a run busts the budget, the
    pre-submit fix offers "drop to k=1" — the least-destructive lever — which the
    two coarse suggestion fields never surfaced. This closes the gap where the
    pre-submit advice was blunter than the run-time refusal message."""
    proj = _mosaic_project(tmp_path)
    try:
        opts = StackOptions(
            drizzle=False, mosaic_canvas="auto",
            min_max_reject=True, min_max_reject_count=3,
        )
        # Budget the union canvas fits at the baseline 4 planes (k=1) but not at
        # k=3's 8 planes: dropping the extra passes rescues it without cropping.
        from seestack.stack.stacker import _estimate_peak_bytes, _min_max_reject_arrays

        dst = (est_union := estimate_stack(proj, opts, memory_budget_gb=1.0)).canvas_h, \
            est_union.canvas_w
        peak_k1, _ = _estimate_peak_bytes(
            dst, drizzle=False, drizzle_scale=1.0,
            reject_arrays=_min_max_reject_arrays(1))
        peak_k3, _ = _estimate_peak_bytes(
            dst, drizzle=False, drizzle_scale=1.0,
            reject_arrays=_min_max_reject_arrays(3))
        budget_gb = (peak_k1 + peak_k3) / 2 / 1e9  # fits k=1, busts k=3
        est = estimate_stack(proj, opts, memory_budget_gb=budget_gb)
        assert est.would_exceed is True
        assert est.memory_fix is not None
        assert est.memory_fix.kind == "reduce_outlier_passes"
        assert est.memory_fix.value is None
        assert est.memory_fix.peak_bytes <= est.budget_bytes
    finally:
        proj.close()


def test_memory_fix_offers_drizzle_scale_with_its_peak(tmp_path):
    """A drizzle run over budget → the fix names the smaller scale + its peak."""
    proj = _mosaic_project(tmp_path)
    try:
        opts = StackOptions(drizzle=True, drizzle_scale=2.0, mosaic_canvas="reference")
        # A budget between the ×1.0 and ×2.0 reference-canvas peaks.
        from seestack.stack.stacker import _estimate_peak_bytes

        p1, _ = _estimate_peak_bytes((320, 480), drizzle=True, drizzle_scale=1.0)
        p2, _ = _estimate_peak_bytes((320, 480), drizzle=True, drizzle_scale=2.0)
        est = estimate_stack(proj, opts, memory_budget_gb=(p1 + p2) / 2 / 1e9)
        assert est.would_exceed is True
        assert est.memory_fix is not None
        assert est.memory_fix.kind == "drizzle_scale"
        assert 1.0 <= est.memory_fix.value < 2.0
        assert est.memory_fix.peak_bytes <= est.budget_bytes
        # The structured value agrees with the coarse suggested_drizzle_scale.
        assert est.memory_fix.value == est.suggested_drizzle_scale
    finally:
        proj.close()


def test_memory_fix_none_when_run_fits(tmp_path):
    proj = _mosaic_project(tmp_path)
    try:
        opts = StackOptions(drizzle=False, mosaic_canvas="auto")
        est = estimate_stack(proj, opts, memory_budget_gb=1.0)  # generous
        assert est.would_exceed is False
        assert est.memory_fix is None
    finally:
        proj.close()
