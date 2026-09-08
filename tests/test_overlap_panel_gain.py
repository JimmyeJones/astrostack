"""A mosaic panel shot through haze is lifted back to match its neighbours,
using the only honest evidence there is: the sky the panels share.

``photometric_normalize`` (auto-on for a mosaic since v0.271.0) gain-matches each
sub against **its own panel's** median transparency, so a panel whose subs were
*all* shot through haze is its own reference and comes out unchanged — a
uniformly darker tile with a step along the join. That restraint is deliberate:
``transparency_score`` is the median flux of a frame's brightest stars, so
comparing panels by it reads "aimed at an emptier patch of sky" as "hazy" and
gain-matched real panels apart by a measured 2.23×
(``photometric._pointing_references``).

The overlaps are the way out. Adjacent panels image the *same* stars there, so
the ratio of their sky-subtracted signal is a pointing-independent gain ratio.
These fixtures therefore render every panel as a window onto **one** star catalog
(``synth.star_catalog`` / ``synth.make_shared_sky_field``) — without that an
overlap holds two unrelated star fields and there is nothing to measure. The
older ``tests/test_photometric_mosaic_auto.py`` fixture draws a fresh field per
frame, which is why it can pin per-panel behaviour but not this.

**What is measured is signal continuity across the join, never ``SEAMRES``** —
that measures a *sky* step between coverage levels, and multiplicative dimming
doesn't move the sky, so it reads ~0 either way.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("photutils")

from astropy.io import fits  # noqa: E402

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack import overlapgain  # noqa: E402
from seestack.stack.overlapgain import compute_overlap_gain_scales  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import (  # noqa: E402
    make_shared_sky_field,
    make_synth_wcs_text,
    star_catalog,
    write_seestar_fits,
)

W, H = 480, 320
PIXSCALE = 5.0
# Panels step 80 % of a field, so ~20 % of each panel is shared with its
# neighbour — the geometry a Seestar mosaic actually produces, and the strip the
# whole measurement lives in.
STEP_PX = int(W * 0.8)
RA0, DEC0 = 83.6, -5.4
# How much of the hazy panel's signal the haze ate. 0.6 needs a 1.67× correction:
# a real amount of haze, comfortably inside the 2× clamp.
HAZE = 0.6


def _catalog(width: int, height: int, n_stars: int = 260, seed: int = 7):
    return star_catalog(seed=seed, width=width, height=height, n_stars=n_stars)


def _panel_center_deg(cat_w: int, cat_h: int, origin: tuple[int, int]):
    """Where a panel whose top-left sits at ``origin`` is pointed."""
    from astropy.io.fits import Header
    from astropy.wcs import WCS

    wcs = WCS(Header.fromstring(make_synth_wcs_text(
        width=cat_w, height=cat_h, ra_center_deg=RA0, dec_center_deg=DEC0,
        pixscale_arcsec=PIXSCALE)))
    ra, dec = wcs.all_pix2world(
        [[origin[0] + W / 2, origin[1] + H / 2]], 0)[0]
    return float(ra), float(dec)


def shared_sky_mosaic(
    tmp_path,
    *,
    origins: list[tuple[int, int]],
    signal_scales: list[float],
    n_per_panel: int = 4,
    score: bool = True,
    separate_skies: bool = False,
) -> Project:
    """A mosaic of overlapping panels cut from one sky, one gain each.

    ``signal_scales[i]`` dims panel ``i``'s signal (1.0 = as shot). Every sub
    carries a ``transparency_score`` proportional to its own signal, exactly as
    QC would measure it — which is what makes the "left alone by the per-panel
    pass" behaviour real here rather than assumed.

    ``separate_skies`` draws a **different** catalog per panel while keeping the
    same pointings: the footprints still overlap on the canvas, but the strip
    they share holds unrelated stars. That is what a mis-solved panel produces —
    a WCS claiming a patch of sky the pixels were never pointed at — and the one
    input from which a measured gain ratio would be meaningless.
    """
    cat_w = max(ox for ox, _ in origins) + W
    cat_h = max(oy for _, oy in origins) + H
    stars = _catalog(cat_w, cat_h)
    proj = Project.create(tmp_path / "p", name="shared-sky-mosaic")
    raws = tmp_path / "raws"
    raws.mkdir(exist_ok=True)
    for panel, (origin, scale) in enumerate(zip(origins, signal_scales, strict=True)):
        ra, dec = _panel_center_deg(cat_w, cat_h, origin)
        for j in range(n_per_panel):
            # A small dither, described in both the pixels and the WCS, so the
            # subs of a panel are a genuinely dithered set rather than copies.
            shift = (0.4 * j, -0.3 * j)
            panel_stars = (_catalog(cat_w, cat_h, seed=7 + 31 * panel)
                           if separate_skies else stars)
            data = make_shared_sky_field(
                panel_stars, width=W, height=H, origin=origin, star_shift=shift,
                signal_scale=scale, noise_seed=1000 + panel * 10 + j)
            path = write_seestar_fits(
                raws / f"p{panel}_{j}.fit", data=data, add_wcs=True,
                ra_center_deg=ra, dec_center_deg=dec, pixscale_arcsec=PIXSCALE)
            fid = proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(
                    width=cat_w, height=cat_h, ra_center_deg=RA0,
                    dec_center_deg=DEC0, pixscale_arcsec=PIXSCALE,
                    crpix_shift=(-origin[0] + shift[0], -origin[1] + shift[1])),
                ra_center_deg=ra, dec_center_deg=dec,
            ))
            if score:
                proj.update_frame(fid, transparency_score=5000.0 * scale)
    return proj


def _panel_signal(fits_path, origins: list[tuple[int, int]], which: int) -> float:
    """Mean star-core brightness above sky inside one panel's *exclusive* half.

    Sampled from the canvas by column, using the panel's own footprint minus the
    overlap strip — the overlap is a blend of both panels and would dilute the
    very step being measured.
    """
    data = np.asarray(fits.getdata(fits_path), dtype=np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN canvas rows
        lum = np.nanmean(data, axis=0) if data.ndim == 3 else data
    _height, width = lum.shape
    # The canvas spans the union; panel k's exclusive strip is its own width
    # minus the overlap it shares, scaled onto the canvas by column fraction.
    cat_w = max(ox for ox, _ in origins) + W
    exclusive_start = origins[which][0] if which == 0 else origins[which][0] + (W - STEP_PX)
    exclusive_end = origins[which][0] + (STEP_PX if which == 0 else W)
    lo = int(width * exclusive_start / cat_w)
    hi = int(width * exclusive_end / cat_w)
    region = lum[:, lo:hi]
    vals = region[np.isfinite(region)]
    assert vals.size > 5000, "region too small to measure"
    sky = float(np.median(vals))
    cores = vals[vals >= np.percentile(vals, 99.5)]
    return float(np.mean(cores) - sky)


def _panel_step(fits_path, origins) -> float:
    a = _panel_signal(fits_path, origins, 0)
    b = _panel_signal(fits_path, origins, 1)
    return abs(a - b) / max(abs(a), abs(b))


TWO_PANELS = [(0, 0), (STEP_PX, 0)]


def test_a_wholly_hazy_panel_is_lifted_to_match_its_neighbour(tmp_path):
    """The measurement this whole module exists for, and the one that fails on
    ``main``: a panel whose subs were *all* shot through haze comes out matching
    the panel next to it, because the strip they share says by how much.

    Before this pass the step was the haze itself (~40 % of the brighter panel's
    star flux). It is measured on signal, not on ``SEAMRES``.
    """
    proj = shared_sky_mosaic(
        tmp_path, origins=TWO_PANELS, signal_scales=[1.0, HAZE])
    try:
        after = run_stack(proj, StackOptions(
            output_name="after", max_workers=1, sigma_clip=False))
        before = run_stack(proj, StackOptions(
            output_name="before", max_workers=1, sigma_clip=False,
            panel_gain_match=False))
    finally:
        proj.close()

    step_before = _panel_step(before.fits_path, TWO_PANELS)
    step_after = _panel_step(after.fits_path, TWO_PANELS)
    assert step_before > 0.25, (
        f"the fixture must actually have a hazy panel (step {step_before:.1%})")
    assert step_after < 0.10, (
        f"the hazy panel should be lifted to match (step {step_after:.1%}, "
        f"was {step_before:.1%})")


def test_the_run_records_that_it_matched_the_panels(tmp_path):
    """Provenance: the user never ticked a box, so the finished FITS has to be
    able to say what was done to it and on what evidence."""
    proj = shared_sky_mosaic(
        tmp_path, origins=TWO_PANELS, signal_scales=[1.0, HAZE])
    try:
        res = run_stack(proj, StackOptions(
            output_name="prov", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    hdr = fits.getheader(res.fits_path)
    assert hdr["PANGAIN"] == "overlap"
    assert int(hdr["PANGNPAN"]) == 2
    assert int(hdr["PANGNPAR"]) == 1
    assert float(hdr["PANGMAX"]) > 1.2


def test_equal_panels_are_left_where_they_are(tmp_path):
    """The neutral case must not drift. Two panels shot in the same air get no
    correction at all — and the run says nothing rather than claiming a no-op
    one."""
    proj = shared_sky_mosaic(
        tmp_path, origins=TWO_PANELS, signal_scales=[1.0, 1.0])
    try:
        after = run_stack(proj, StackOptions(
            output_name="after", max_workers=1, sigma_clip=False))
        before = run_stack(proj, StackOptions(
            output_name="before", max_workers=1, sigma_clip=False,
            panel_gain_match=False))
    finally:
        proj.close()

    a = np.asarray(fits.getdata(after.fits_path), dtype=np.float64)
    b = np.asarray(fits.getdata(before.fits_path), dtype=np.float64)
    finite = np.isfinite(a) & np.isfinite(b)
    # Within a fraction of a percent everywhere: nothing meaningful moved.
    assert float(np.nanmax(np.abs(a[finite] - b[finite]))
                 / max(1.0, float(np.nanmax(np.abs(b[finite]))))) < 0.01


def test_panels_that_do_not_overlap_are_never_guessed_at(tmp_path):
    """No shared sky, no evidence, no correction — and the stack is exactly the
    stack it would have been. This is the failure mode that matters: inventing a
    cross-panel gain from a pair that never saw the same stars is how a panel
    grid gets manufactured."""
    apart = [(0, 0), (W + 60, 0)]  # a genuine gap between the panels
    proj = shared_sky_mosaic(
        tmp_path, origins=apart, signal_scales=[1.0, HAZE])
    try:
        after = run_stack(proj, StackOptions(
            output_name="after", max_workers=1, sigma_clip=False))
        before = run_stack(proj, StackOptions(
            output_name="before", max_workers=1, sigma_clip=False,
            panel_gain_match=False))
    finally:
        proj.close()

    assert "PANGAIN" not in fits.getheader(after.fits_path)
    a = np.asarray(fits.getdata(after.fits_path), dtype=np.float64)
    b = np.asarray(fits.getdata(before.fits_path), dtype=np.float64)
    assert np.array_equal(np.nan_to_num(a, nan=-1.0), np.nan_to_num(b, nan=-1.0))


def test_a_single_field_target_never_enters_the_pass(tmp_path):
    """One pointing is not a mosaic: there are no panels to match, so the pass
    is not reached at all and a hazy *night* stays the per-frame pass's job."""
    proj = shared_sky_mosaic(
        tmp_path, origins=[(0, 0), (0, 0)], signal_scales=[1.0, HAZE])
    try:
        res = run_stack(proj, StackOptions(
            output_name="single", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    assert "PANGAIN" not in fits.getheader(res.fits_path)


def test_an_implausible_panel_ratio_is_dropped_rather_than_clamped(tmp_path):
    """A panel measuring 5× its neighbour is a broken measurement, not a hazy
    night. The pair is dropped and nothing is applied — clamping it to 2× would
    apply a gain the evidence never supported."""
    proj = shared_sky_mosaic(
        tmp_path, origins=TWO_PANELS, signal_scales=[1.0, 0.15])
    try:
        res = run_stack(proj, StackOptions(
            output_name="wild", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    assert "PANGAIN" not in fits.getheader(res.fits_path)


def test_the_pass_never_raises_out_of_a_stack(tmp_path):
    """Whatever goes wrong inside a *diagnostic* pre-pass, the stack still runs.
    An aligner that throws must cost the run its correction, not its picture."""
    def boom(*_a, **_kw):
        raise RuntimeError("no")

    frames = {0: [FrameRow(id=1, source_path="a", wcs_json="x")],
              1: [FrameRow(id=2, source_path="b", wcs_json="y")]}
    assert compute_overlap_gain_scales(
        frames, "not-a-wcs", (100, 100), align_frame=boom) is None


def test_a_panel_with_no_measurable_pair_keeps_its_own_gain(tmp_path):
    """Three panels in a row where the far one shares nothing: the two that do
    overlap are matched to each other and the third is left at 1.0, rather than
    being dragged along by a gain nobody measured for it."""
    origins = [(0, 0), (STEP_PX, 0), (2 * W + 120, 0)]
    proj = shared_sky_mosaic(
        tmp_path, origins=origins, signal_scales=[1.0, HAZE, HAZE])
    try:
        res = run_stack(proj, StackOptions(
            output_name="three", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    hdr = fits.getheader(res.fits_path)
    assert hdr["PANGAIN"] == "overlap"
    # Only the overlapping pair could be measured.
    assert int(hdr["PANGNPAR"]) == 1
    assert int(hdr["PANGNPAN"]) == 3


def test_an_overlap_holding_unrelated_stars_is_refused(tmp_path):
    """The guard that makes the whole pass safe to leave on: overlapping
    *footprints* only mean two WCS solutions claim the same patch of sky. A
    mis-solved panel claims a patch it never pointed at, and the ratio measured
    across that strip is a number with nothing behind it — on this fixture it
    reads 2.6× between two panels that were equally exposed.

    Correlation catches it, and cannot be fooled by the thing being measured: a
    gain difference leaves the correlation alone, which is exactly why a real
    hazy panel still passes this test while unrelated sky does not.
    """
    proj = shared_sky_mosaic(
        tmp_path, origins=TWO_PANELS, signal_scales=[1.0, 1.0],
        separate_skies=True)
    try:
        res = run_stack(proj, StackOptions(
            output_name="mis-solved", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    assert "PANGAIN" not in fits.getheader(res.fits_path)


def test_the_block_fold_lands_a_window_where_the_canvas_put_it():
    """The coarse maps are only comparable if a window folds to the cells its
    canvas position says it should — an off-by-one here would shift one panel
    against the other and quietly compare a star to the sky beside it.

    Folded directly, at a block size and an offset that are both awkward: a
    window whose corner sits mid-block, over a canvas whose height is not a
    multiple of the block.
    """
    ds = 3
    sums = np.zeros((4, 4), dtype=np.float64)
    counts = np.zeros((4, 4), dtype=np.int32)
    # A 3×3 window of 2.0 whose top-left is canvas (4, 4) — so it straddles the
    # four coarse cells (1,1), (1,2), (2,1) and (2,2).
    window = np.full((3, 3), 2.0, dtype=np.float32)
    overlapgain._block_reduce_into(sums, counts, window, 4, 4, ds)

    assert counts.sum() == 9, "every covered pixel counted exactly once"
    # Cell (1,1) spans canvas rows/cols 3–5, so it takes the 2×2 of the window
    # that lands there; cell (2,2) spans 6–8 and takes the single far pixel.
    assert counts[1, 1] == 4
    assert counts[1, 2] == 2 and counts[2, 1] == 2
    assert counts[2, 2] == 1
    assert counts[0, 0] == 0 and counts[3, 3] == 0
    covered = counts > 0
    assert np.allclose(sums[covered] / counts[covered], 2.0)


def test_a_window_of_nothing_but_gaps_contributes_nothing():
    """NaN is "no coverage", not a value: it must move neither the sum nor the
    count, or an uncovered corner of one panel would read as dark sky and drag
    that panel's measured gain."""
    sums = np.zeros((3, 3), dtype=np.float64)
    counts = np.zeros((3, 3), dtype=np.int32)
    window = np.full((4, 4), np.nan, dtype=np.float32)
    window[0, 0] = 5.0
    overlapgain._block_reduce_into(sums, counts, window, 0, 0, 2)

    assert counts.sum() == 1
    assert counts[0, 0] == 1
    assert sums[0, 0] == 5.0


def test_one_noisy_pair_is_dropped_rather_than_losing_the_whole_mosaic():
    """A mosaic's diagonal neighbours share only a small corner, so one pair
    disagreeing with five sound ones is the ordinary case — dropping it and
    re-fitting keeps the correction the other five paid for."""
    # Four panels; three are equal and the fourth was shot 1.5× *dimmer*, so
    # every pair reads 1.5 against it — except one, which says the opposite.
    pairs = {
        (0, 1): 1.0, (0, 2): 1.0, (1, 2): 1.0,
        (0, 3): 1.5, (1, 3): 1.5,
        (2, 3): 0.5,  # the noisy corner, contradicting the other five
    }
    solution = overlapgain._solve_log_scales([0, 1, 2, 3], pairs)
    assert solution is not None
    scales = np.exp(solution)
    # Panels 0–2 stay together and panel 3 is lifted by exactly the 1.5× the
    # five sound pairs give — not a compromise with the sixth.
    assert np.allclose(scales[:3], scales[0], rtol=0.02)
    assert scales[3] / scales[0] == pytest.approx(1.5, rel=0.02)


def test_a_mildly_disagreeing_pair_is_averaged_in_rather_than_thrown_away():
    """Not every disagreement is an outlier. Pairs that differ by less than the
    tolerance are what noise looks like, and least squares splitting the
    difference between them beats discarding a real measurement."""
    pairs = {
        (0, 1): 1.0, (0, 2): 1.0, (1, 2): 1.0,
        (0, 3): 1.5, (1, 3): 1.5,
        (2, 3): 1.0,  # off by 1.5×, but no single residual reaches the bound
    }
    solution = overlapgain._solve_log_scales([0, 1, 2, 3], pairs)
    assert solution is not None
    scales = np.exp(solution)
    # Panel 3 still moves most of the way toward its neighbours, and no panel is
    # thrown far off by the sixth pair's dissent.
    assert 1.2 < scales[3] / scales[0] < 1.5
    assert np.allclose(scales[:3], scales[0], rtol=0.15)


def test_ratios_that_never_settle_stand_the_whole_pass_down():
    """Three panels whose pairs contradict each other around the loop describe
    no single per-panel gain. Agreeing only once there is nothing left to
    disagree with is not agreement — nothing is applied."""
    pairs = {(0, 1): 1.9, (1, 2): 1.9, (0, 2): 1.0}
    assert overlapgain._solve_log_scales([0, 1, 2], pairs) is None


def test_a_lone_panel_is_left_at_one_rather_than_dragged_along():
    """A panel sharing no overlap with anybody gets scale 1.0 — the minimum-norm
    solution gives each connected component its own gauge, so the measured pair
    can't reach across a gap it never measured."""
    solution = overlapgain._solve_log_scales([0, 1, 2], {(0, 1): 1.6})
    assert solution is not None
    scales = np.exp(solution)
    assert scales[2] == pytest.approx(1.0, abs=1e-9)
    assert scales[0] / scales[1] == pytest.approx(1 / 1.6, rel=1e-6)
