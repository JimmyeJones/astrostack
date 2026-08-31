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


def _mosaic_project(
    tmp_path, counts: tuple[int, ...], *, name: str = "mosaic",
    dither_px: float = 0.0,
) -> Project:
    """A mosaic of ``counts`` subs per panel, stepped by 0.8 of a field.

    ``dither_px`` offsets every sub except each panel's *first* by that many
    pixels of sky, without touching its WCS — i.e. exactly the residual
    misalignment sub-pixel refine exists to measure and remove. Each panel's subs
    share a star field (one ``seed`` per panel) so a correlation within a panel
    is meaningful, with independent noise per sub.
    """
    proj = Project.create(tmp_path / "p", name=name)
    raws = tmp_path / "raws"
    raws.mkdir()
    for panel, count in enumerate(counts):
        ra = 83.6 + panel * STEP_DEG
        for j in range(count):
            path = write_seestar_fits(
                raws / f"p{panel}_{j}.fit", add_wcs=True,
                seed=(100 + panel) if dither_px else 100 + 10 * panel + j,
                noise_seed=(900 + 10 * panel + j) if dither_px else None,
                star_shift=(dither_px, 0.0) if (dither_px and j) else (0.0, 0.0),
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


def _lopsided_mosaic_project(tmp_path) -> Project:
    return _mosaic_project(tmp_path, PANEL_COUNTS, name="lopsided-mosaic")


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


# --------------------------------------------------------------------------
# One patch per *panel*.
#
# A reference patch can only refine the frames whose window overlaps it, so a
# single patch delivered the option's sharpness to the reference panel and to
# whatever thin overlap strip its neighbours shared with it — and to nothing at
# all on a panel further away. Each substantial panel now gets its own patch,
# cut from its own central sub and aligned to the same canvas WCS.
# --------------------------------------------------------------------------

BALANCED_COUNTS = (4, 3, 3, 3)
# Sky-pixels of residual misalignment carried by every sub except each panel's
# first — what refine exists to measure. Well inside SUBPIXEL_SHIFT_CAP_PX, and
# large enough to read unambiguously off this fixture's stars.
DITHER_PX = 2.0


def _header(res) -> dict:
    from astropy.io import fits

    with fits.open(res.fits_path) as hdul:
        return dict(hdul[0].header)


def _stack_balanced(tmp_path, *, split: bool) -> dict:
    """Stack the balanced mosaic with refine on, logging every correlation.

    ``split=False`` reproduces the pre-per-panel behaviour exactly, by making the
    panel split unavailable — that is the same code path a single-field target
    and a mosaic too tightly packed to separate take today.
    """
    import skimage.registration as skreg

    import seestack.stack.stacker as st

    log: list[dict] = []
    real = skreg.phase_cross_correlation

    def spy(ref, frame, **kwargs):
        out = real(ref, frame, **kwargs)
        log.append({"shift": tuple(float(v) for v in out[0]),
                    "overlap_px": int(ref.shape[0]) * int(ref.shape[1])})
        return out

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(skreg, "phase_cross_correlation", spy)
        if not split:
            mp.setattr(st, "pointing_groups", lambda *a, **k: None)
        proj = _mosaic_project(tmp_path, BALANCED_COUNTS, dither_px=DITHER_PX)
        try:
            res = run_stack(proj, StackOptions(output_name="m", max_workers=1,
                                               sigma_clip=False,
                                               subpixel_refine=True))
        finally:
            proj.close()
    return {"header": _header(res), "correlations": log,
            "n_used": res.n_frames_used}


@pytest.fixture(scope="module")
def balanced_runs(tmp_path_factory) -> dict:
    """The same four-panel mosaic stacked with one patch and with one per panel."""
    return {
        "before": _stack_balanced(tmp_path_factory.mktemp("one_patch"), split=False),
        "after": _stack_balanced(tmp_path_factory.mktemp("per_panel"), split=True),
    }


def test_every_panel_gets_its_own_patch_and_no_sub_is_left_unreached(balanced_runs):
    before, after = balanced_runs["before"]["header"], balanced_runs["after"]["header"]
    # The whole point: one patch on a four-panel mosaic couldn't reach the panel
    # two steps from the reference (its window shares no area with the patch).
    assert before["NREFPANL"] == 1
    assert before["NREFSKIP"] == BALANCED_COUNTS[3]
    # Now one patch per panel, and every contributing sub is inside one.
    assert after["NREFPANL"] == len(BALANCED_COUNTS)
    assert after["NREFSKIP"] == 0
    assert balanced_runs["after"]["n_used"] == sum(BALANCED_COUNTS)


def test_a_neighbouring_panel_stops_correlating_on_a_sliver(balanced_runs):
    """Reach is area, not only headcount: an adjacent panel's subs *did* reach
    the single patch — through the ~1/4-width strip the two panels shared."""
    def median_overlap(run: dict) -> float:
        areas = sorted(c["overlap_px"] for c in run["correlations"])
        assert areas, "no correlation ran at all"
        return float(areas[len(areas) // 2])

    before = median_overlap(balanced_runs["before"])
    after = median_overlap(balanced_runs["after"])
    assert after > before * 3, (
        f"median correlation area {before:.0f} px → {after:.0f} px — a sub should "
        "now correlate against its own whole panel, not a seam strip"
    )


def test_every_subs_dither_is_now_measured_and_none_is_left_rough(balanced_runs):
    """The measurable payoff: each sub's known 2 px offset is read back.

    Each panel's first sub *is* its patch, so it measures zero; every other sub
    carries ``DITHER_PX`` and must now be seen to carry it.
    """
    def n_dither_measured(run: dict) -> int:
        return sum(
            1 for c in run["correlations"]
            if abs(abs(c["shift"][1]) - DITHER_PX) < 0.3 and abs(c["shift"][0]) < 0.3
        )

    dithered = sum(count - 1 for count in BALANCED_COUNTS)
    assert n_dither_measured(balanced_runs["after"]) == dithered
    assert n_dither_measured(balanced_runs["before"]) < dithered
    # …and every shift the run measured was plausible, so nothing had to be
    # thrown away as "only roughly aligned" (a sliver correlation against another
    # panel's stars produced shifts of tens of pixels, which the cap discarded).
    assert balanced_runs["after"]["header"]["NROUGHAL"] == 0
    assert balanced_runs["before"]["header"]["NROUGHAL"] > 0


def test_the_panel_seam_does_not_get_worse(balanced_runs):
    """Each panel is refined against its own reference, so the guard that matters
    is that the panels stay registered to each other: every patch is aligned to
    the same canvas WCS, and the finished mosaic's seam step must not grow."""
    before = float(balanced_runs["before"]["header"]["SEAMRES"])
    after = float(balanced_runs["after"]["header"]["SEAMRES"])
    assert after <= before + 0.01, (
        f"panel-seam step {before:.3f} → {after:.3f} sky sigma"
    )


def test_a_single_field_stack_still_builds_exactly_one_patch(tmp_path, monkeypatch):
    """The guard: no split, no change. One pointing means one patch, cut from the
    same frame at the same origin as before — and nothing to skip."""
    import seestack.stack.stacker as st

    built: list[str] = []
    real = st._build_refine_patch

    def spy(frame, **kwargs):
        built.append(kwargs.get("what", "reference"))
        return real(frame, **kwargs)

    monkeypatch.setattr(st, "_build_refine_patch", spy)
    proj = _mosaic_project(tmp_path, (5,), name="single-field", dither_px=DITHER_PX)
    try:
        res = run_stack(proj, StackOptions(output_name="single", max_workers=1,
                                           sigma_clip=False, subpixel_refine=True))
    finally:
        proj.close()
    assert built == ["reference"]
    header = _header(res)
    assert header["NREFPANL"] == 1
    assert header["NREFSKIP"] == 0


def test_one_panels_failed_patch_does_not_cost_the_others_theirs(tmp_path,
                                                                 monkeypatch):
    """A panel whose own patch can't be built falls back to the target-wide one —
    today's behaviour for that panel — and the other panels keep theirs."""
    import seestack.stack.stacker as st

    real = st._build_refine_patch

    def flaky(frame, **kwargs):
        if kwargs.get("what") == "panel 3":
            return None
        return real(frame, **kwargs)

    monkeypatch.setattr(st, "_build_refine_patch", flaky)
    proj = _mosaic_project(tmp_path, BALANCED_COUNTS, name="one-panel-failed",
                           dither_px=DITHER_PX)
    try:
        res = run_stack(proj, StackOptions(output_name="failed", max_workers=1,
                                           sigma_clip=False, subpixel_refine=True))
    finally:
        proj.close()
    header = _header(res)
    # Three patches instead of four, and only the failed panel's subs go unreached.
    assert header["NREFPANL"] == len(BALANCED_COUNTS) - 1
    assert header["NREFSKIP"] == BALANCED_COUNTS[3]
    assert res.n_frames_used == sum(BALANCED_COUNTS)
