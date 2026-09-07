"""``estimate_stack`` split into a shared canvas basis + a cheap per-option sizing.

Sizing a stack is two jobs of very different cost: building the union canvas
(one WCS read per sub — ~1 s on the owner's 5,477-sub mosaic) and then doing
arithmetic on it. Only ``mosaic_canvas`` reaches the first, so one
:class:`StackCanvasBasis` can price as many option sets as a caller likes.

These tests pin the two properties that make that safe: the split answers
*exactly* what the one-shot ``estimate_stack`` answers for every option set, and
the expensive canvas computation really does happen once per basis rather than
once per sizing.
"""

import pytest

pytest.importorskip("astropy")

from dataclasses import asdict

from seestack.io.project import FrameRow, Project
from seestack.stack import mosaic as mosaic_mod
from seestack.stack.stacker import (
    StackOptions,
    estimate_stack,
    estimate_stack_basis,
    estimate_stack_from_basis,
)
from tests.synth import make_synth_wcs_text


def _mosaic_project(tmp_path) -> Project:
    """A 2×2 mosaic: four pointings, three frames each, on 480×320 panels."""
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


#: Option sets spanning every lever the sizing consults, so "the split agrees"
#: is a claim about the whole surface and not about the default alone.
_OPTION_SETS = [
    StackOptions(),
    StackOptions(drizzle=True, drizzle_scale=2.0),
    StackOptions(drizzle=True, drizzle_scale=1.5, drizzle_reject=True),
    StackOptions(min_max_reject=True, min_max_reject_count=3),
    StackOptions(auto_reject=True),
    StackOptions(auto_reject=True, sigma_kappa=1.5),
    StackOptions(sigma_clip=False),
    StackOptions(mosaic_canvas="reference"),
    StackOptions(mosaic_canvas="union"),
]


@pytest.mark.parametrize("budget_gb", [1.0, 15e-3])
def test_split_sizing_matches_the_one_shot_estimate(tmp_path, budget_gb):
    """Every field, for every option set, at a comfortable and a punishing budget.

    Both budgets are explicit: with ``memory_budget_gb=None`` the budget is read
    from the box's *available* memory, which moves by a few kilobytes between two
    calls, so the two answers would differ for a reason that has nothing to do
    with the split."""
    proj = _mosaic_project(tmp_path)
    try:
        for opts in _OPTION_SETS:
            whole = estimate_stack(proj, opts, memory_budget_gb=budget_gb)
            basis = estimate_stack_basis(proj, opts.mosaic_canvas)
            split = estimate_stack_from_basis(basis, opts,
                                              memory_budget_gb=budget_gb)
            assert asdict(split) == asdict(whole), opts
    finally:
        proj.close()


def test_one_basis_prices_many_option_sets_with_one_canvas_computation(
        tmp_path, monkeypatch):
    """The point of the split: the expensive half runs once, not once per sizing.

    Fails before the split — ``estimate_stack`` rebuilt the canvas on every call,
    so N sizings cost N canvas computations."""
    proj = _mosaic_project(tmp_path)
    calls = {"n": 0}
    real = mosaic_mod.compute_mosaic_canvas

    def counted(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(mosaic_mod, "compute_mosaic_canvas", counted)
    try:
        basis = estimate_stack_basis(proj, "auto")
        assert calls["n"] == 1
        sizings = [
            estimate_stack_from_basis(basis, o)
            for o in _OPTION_SETS if o.mosaic_canvas == "auto"
        ]
        assert len(sizings) >= 5
        # Still one — the sizings never touched a frame.
        assert calls["n"] == 1
        # And they are genuinely different answers, not one cached blob.
        assert len({s.peak_bytes for s in sizings}) > 1
    finally:
        proj.close()


def test_basis_reports_the_canvas_facts_the_sizings_share(tmp_path):
    proj = _mosaic_project(tmp_path)
    try:
        basis = estimate_stack_basis(proj, "auto")
        assert basis.is_mosaic is True
        assert basis.n_frames == 12
        assert basis.ref_shape == (320, 480)
        # A union canvas of four overlapping 480×320 panels is bigger than one.
        assert basis.dst_shape[0] > 320 and basis.dst_shape[1] > 480
        # Three subs land on a pixel of every panel.
        assert basis.panel_depth == 3
        assert basis.mosaic_canvas == "auto"

        ref_basis = estimate_stack_basis(proj, "reference")
        assert ref_basis.is_mosaic is False
        assert ref_basis.dst_shape == (320, 480)
    finally:
        proj.close()


def test_a_basis_refuses_options_from_a_different_canvas_mode(tmp_path):
    """``mosaic_canvas`` is the one option the canvas depends on, so mixing a
    basis with options that disagree would silently size the wrong canvas."""
    proj = _mosaic_project(tmp_path)
    try:
        basis = estimate_stack_basis(proj, "reference")
        with pytest.raises(ValueError, match="mosaic_canvas"):
            estimate_stack_from_basis(basis, StackOptions(mosaic_canvas="union"))
    finally:
        proj.close()


def test_basis_raises_the_same_guidance_when_nothing_is_solved(tmp_path):
    proj = Project.create(tmp_path / "empty", name="empty")
    try:
        with pytest.raises(ValueError, match="Plate Solve"):
            estimate_stack_basis(proj, "auto")
    finally:
        proj.close()
