"""The *other* way a mosaic panel shows: it is grainier, not stepped.

``measure_seam_residual`` asks whether the per-coverage levelling pass worked —
whether the sky *level* matches across the joins — and a mosaic built over
several nights routinely measures flat by that yardstick while still showing an
obvious rectangle, because the panel with fewer subs is simply noisier. Grain
falls as ``1/√depth`` and no amount of processing puts back light nobody
collected, so this is not a fault to fix; it is a fact to name, with the one
action that changes it (more subs on that panel).

Measured on the bundled mosaic sample (four panels at 6/6/6/3 subs — the uneven
depth a multi-night mosaic actually has): the finished picture shows a visibly
grainier rectangle over 23 % of the canvas, ``grain_ratio`` reads 1.43, and
``seam_residual`` reads 0.70 — "the panels matched". Both numbers are true. Only
one of them is what the owner is looking at.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.bg.coverage_leveling import (
    _GRAIN_MIN_SHARE,
    measure_coverage_grain,
    measure_seam_residual,
)
from seestack.io.project import FrameRow, StackRunRow
from seestack.stackhealth import grain_verdict, stack_health

# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

def _uneven_canvas(thin_depth=3, deep_depth=6, thin_cols=0.25, h=400, w=800,
                   base_sigma=6.0, stars=250, seed=11):
    """A canvas whose sky is perfectly level everywhere and whose *grain* is not.

    The left ``thin_cols`` of the frame is covered ``thin_depth`` times and the
    rest ``deep_depth`` times, and each region's noise is scaled by
    ``1/√depth`` — exactly what stacking that many subs produces. Every region
    shares one sky level, so a seam measurement has nothing to find and the only
    difference left is the one this module measures.
    """
    rng = np.random.default_rng(seed)
    cov = np.full((h, w), deep_depth, dtype=np.int32)
    split = int(w * thin_cols)
    cov[:, :split] = thin_depth
    rgb = np.empty((h, w, 3), dtype=np.float32)
    for depth in (thin_depth, deep_depth):
        m = cov == depth
        sigma = base_sigma / np.sqrt(depth)
        for c in range(3):
            rgb[..., c][m] = rng.normal(0.0, sigma, size=int(m.sum()))
    # Stars, so the object mask has something real to exclude on both sides.
    for _ in range(stars):
        y = int(rng.integers(6, h - 6))
        x = int(rng.integers(6, w - 6))
        rgb[y - 1:y + 2, x - 1:x + 2, :] += 400.0
    return rgb, cov.astype(np.float32)


def _run(**kw) -> StackRunRow:
    base = dict(
        id=1, timestamp_utc="2026-09-09T00:00:00+00:00", output_basename="m42",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=21,
        canvas_h=615, canvas_w=907, coverage_min=1, coverage_max=21,
        options_json="{}", is_mosaic=True, seam_residual=0.7,
        coverage_thin_frac=0.0,
    )
    base.update(kw)
    return StackRunRow(**base)


def _frames(n=12) -> list[FrameRow]:
    return [FrameRow(id=i, source_path=f"/incoming/s{i}.fit", accept=True,
                     fwhm_px=2.1, exposure_s=10.0)
            for i in range(n)]


# --------------------------------------------------------------------------
# the measurement
# --------------------------------------------------------------------------

def test_a_thinner_region_is_measured_as_grainier_and_named_by_its_depth():
    rgb, cov = _uneven_canvas()
    grain = measure_coverage_grain(rgb, cov)
    assert grain is not None
    assert grain.thin_frames == 3
    assert grain.deep_frames == 6
    assert grain.thin_share == pytest.approx(0.25, abs=0.02)
    # 3 subs against 6 is √2 more grain; the clipped σ behind the ratio is
    # inflated by leftover structure on both sides, so it may only understate.
    assert 1.2 <= grain.ratio <= np.sqrt(2.0) + 0.05


def test_the_grain_step_is_invisible_to_the_seam_measurement():
    """The reason this measurement exists, stated as a test: on this canvas the
    app's existing mosaic number says the panels matched — and they do, in the
    only way it measures."""
    rgb, cov = _uneven_canvas()
    seam = measure_seam_residual(rgb, cov)
    assert seam is not None and seam.ratio < 1.0      # "flat"
    grain = measure_coverage_grain(rgb, cov)
    assert grain is not None and grain_verdict(grain.ratio) == "uneven"


def test_an_evenly_shot_mosaic_says_nothing():
    """Every mosaic has overlap strips deeper than its panels, so a measurement
    that compared against the *deepest* level would fire on all of them. This
    one compares against the level most of the canvas is at, and an even mosaic
    has nothing below it."""
    rng = np.random.default_rng(5)
    h, w = 400, 800
    cov = np.full((h, w), 6, dtype=np.float32)
    cov[:, 350:450] = 12                              # the overlap strip
    rgb = rng.normal(0.0, 3.0, size=(h, w, 3)).astype(np.float32)
    rgb[:, 350:450, :] = rng.normal(0.0, 3.0 / np.sqrt(2), size=(h, 100, 3))
    assert measure_coverage_grain(rgb, cov) is None


def test_a_single_field_stack_says_nothing():
    rng = np.random.default_rng(7)
    rgb = rng.normal(0.0, 3.0, size=(300, 400, 3)).astype(np.float32)
    cov = np.full((300, 400), 40, dtype=np.float32)
    assert measure_coverage_grain(rgb, cov) is None


def test_a_thin_region_too_small_to_matter_says_nothing():
    """A dithered border is a few percent of the canvas and always thinner than
    the body; naming it would fire on every stack ever made."""
    rgb, cov = _uneven_canvas(thin_cols=_GRAIN_MIN_SHARE / 3.0)
    assert measure_coverage_grain(rgb, cov) is None


def test_the_ratio_survives_a_decimated_read():
    """The healing path (:func:`backfill_coverage_grain`) reads an older run's
    master strided, so the estimator has to be one striding leaves alone. This
    is why the σ is sigma-clipped rather than taken from adjacent-pixel
    differences, which measures the picture's structure once its pixels are no
    longer adjacent."""
    rgb, cov = _uneven_canvas(h=800, w=1600)
    full = measure_coverage_grain(rgb, cov)
    strided = measure_coverage_grain(rgb[::2, ::2], cov[::2, ::2], proxy_scale=2.0)
    assert full is not None and strided is not None
    assert strided.ratio == pytest.approx(full.ratio, rel=0.15)
    assert strided.thin_frames == full.thin_frames
    assert strided.deep_frames == full.deep_frames


def test_an_all_nan_canvas_declines_rather_than_raising():
    rgb = np.full((200, 200, 3), np.nan, dtype=np.float32)
    cov = np.zeros((200, 200), dtype=np.float32)
    assert measure_coverage_grain(rgb, cov) is None


# --------------------------------------------------------------------------
# a canvas that ramps instead of stepping (issue #952)
# --------------------------------------------------------------------------
# Every fixture above is a flat-plateau coverage map — `np.full` blocks at 3 / 6
# / 12 / 40 subs — and that is the shape the `_GRAIN_MIN_SHARE`-per-*integer
# level* rule was written against. A mosaic dithered across many nights does not
# have that shape: the per-pixel frame count is a near-continuous ramp, and on
# the owner's own library (2026-09-19) it spread over 79-1,392 distinct integer
# levels with **not one level clearing the bar on any of 26 mosaics**. So the
# measurement returned None on every mosaic it exists for, and the five surfaces
# that read it went quiet — including the chip that then said "Panels even" over
# a canvas 1.86x grainier across 44 % of itself.
#
# These fixtures build the coverage map the way the real one is built: one
# rectangle per sub, jittered by a dither, re-pointed night to night. Nothing is
# asserted about them that is not first asserted about their *shape* — a fixture
# that stops ramping stops exhibiting the bug, and would go green for the wrong
# reason.

def _dithered_coverage(panels=3, n_per_visit=12, panel_h=170, panel_w=240,
                       step=0.80, nights=20, night_drift=0.20, dither=0.03,
                       starve=None, starve_frac=0.15, seed=3):
    """Per-pixel frame counts for a dithered, re-pointed mosaic.

    ``panels`` x ``panels`` pointings stepping ``step`` of a frame, each visited
    on ``nights`` nights; every night carries its own pointing offset
    (``night_drift`` of a frame) and every sub its own dither. ``starve`` names a
    panel that gets ``starve_frac`` of the visits — an under-shot panel, as
    opposed to the ragged outline the drift leaves on every edge.
    """
    rng = np.random.default_rng(seed)
    dy = int(round(panel_h * step))
    dx = int(round(panel_w * step))
    pad_y = int(round(panel_h * (night_drift + dither))) + 2
    pad_x = int(round(panel_w * (night_drift + dither))) + 2
    h = panel_h + dy * (panels - 1) + 2 * pad_y
    w = panel_w + dx * (panels - 1) + 2 * pad_x
    cov = np.zeros((h, w), dtype=np.int32)
    for _night in range(nights):
        oy = int(round(rng.normal(0.0, panel_h * night_drift / 2)))
        ox = int(round(rng.normal(0.0, panel_w * night_drift / 2)))
        for py in range(panels):
            for px in range(panels):
                scale = starve_frac if (py, px) == starve else 1.0
                n = max(1, int(round(n_per_visit * scale
                                     * rng.uniform(0.85, 1.0))))
                for _ in range(n):
                    jy = int(round(rng.normal(0.0, panel_h * dither)))
                    jx = int(round(rng.normal(0.0, panel_w * dither)))
                    y0 = max(0, min(h - panel_h, pad_y + py * dy + oy + jy))
                    x0 = max(0, min(w - panel_w, pad_x + px * dx + ox + jx))
                    cov[y0:y0 + panel_h, x0:x0 + panel_w] += 1
    return cov


def _sky_for(cov, base_sigma=6.0, stars=300, seed=5):
    """Sky whose grain really does fall as 1/√depth, pixel by pixel, with NaN
    where nothing landed — so a measured ratio is a fact about the fixture and
    not about how it was drawn."""
    rng = np.random.default_rng(seed)
    h, w = cov.shape
    depth = np.maximum(cov, 1).astype(np.float32)
    scale = base_sigma / np.sqrt(depth)
    rgb = np.empty((h, w, 3), dtype=np.float32)
    for c in range(3):
        rgb[..., c] = rng.normal(0.0, 1.0, size=(h, w)).astype(np.float32) * scale
    rgb[cov == 0] = np.nan
    for _ in range(stars):                        # something real to mask
        y = int(rng.integers(6, h - 6))
        x = int(rng.integers(6, w - 6))
        if cov[y, x] > 0:
            rgb[y - 1:y + 2, x - 1:x + 2, :] += 400.0
    return rgb


def _as_map(cov):
    """The float coverage map a stack writes. Zero-filled, not NaN-filled, which
    is what the accumulators actually emit — the NaN in these fixtures is in the
    *image*, where it means "no coverage", exactly as the pipeline has it."""
    return cov.astype(np.float32)


def _levels_over_the_bar(cov) -> int:
    covered = cov > 0
    total = int(covered.sum())
    _, counts = np.unique(cov[covered], return_counts=True)
    return int((counts >= _GRAIN_MIN_SHARE * total).sum())


def test_a_dithered_mosaic_is_measured_instead_of_staying_silent():
    """The bug, and the fix, on the shape the owner's 26 mosaics have."""
    cov = _dithered_coverage()
    # The premise first: this canvas has no plateau for the per-level rule to
    # find. If a future change makes it plateau, this test stops being about the
    # bug and says so here rather than passing quietly.
    assert len(np.unique(cov[cov > 0])) > 100
    assert _levels_over_the_bar(cov) == 0

    grain = measure_coverage_grain(_sky_for(cov), _as_map(cov))
    assert grain is not None                       # None before this fix
    assert grain_verdict(grain.ratio) == "uneven"
    assert grain.thin_frames < grain.deep_frames
    # Measured over a substantial part of the picture, and conservative against
    # the 1/√depth prediction the way `CoverageGrain`'s docstring says it must
    # be. Both land inside the ranges the observer measured on the real library
    # (17.8-43.8 % of the canvas, 1.39-1.86x against a prediction of 1.90-2.31).
    assert 0.15 <= grain.thin_share <= 0.5
    assert 1.25 <= grain.ratio <= math.sqrt(grain.deep_frames / grain.thin_frames)


def test_a_ramping_canvas_says_a_spread_and_a_plateau_says_a_panel():
    """The word that decides the advice, and what it is a claim about.

    A coverage *level* holding a tenth of the canvas is a panel by construction —
    nothing but a frame's footprint makes one — so the plateau fixtures keep the
    panel wording they have always had. A ramp is not a claim either way, and
    says so: part of it is the outline the pointings leave, which no amount of
    further shooting narrows.
    """
    plateau_rgb, plateau_cov = _uneven_canvas()
    plateau = measure_coverage_grain(plateau_rgb, plateau_cov)
    assert plateau is not None and plateau.region == "panel"

    cov = _dithered_coverage()
    ramp = measure_coverage_grain(_sky_for(cov), _as_map(cov))
    assert ramp is not None and ramp.region == "spread"


def test_a_dithered_single_field_with_a_tight_dither_says_nothing():
    """A dither of a few pixels leaves a ramp a couple of percent wide, which is
    what `test_a_thin_region_too_small_to_matter_says_nothing` is about at the
    plateau end: below :data:`_GRAIN_MIN_SHARE` there is nothing to say, however
    many distinct levels the canvas happens to hold."""
    cov = _dithered_coverage(panels=1, panel_h=300, panel_w=420, nights=20,
                             night_drift=0.02, dither=0.015, n_per_visit=16,
                             seed=3)
    assert len(np.unique(cov[cov > 0])) > 100      # it really does ramp
    assert measure_coverage_grain(_sky_for(cov), _as_map(cov)) is None


def test_an_evenly_shot_dithered_mosaic_still_says_nothing():
    """`test_an_evenly_shot_mosaic_says_nothing` again, on the ramping shape:
    the new rule must keep the old one's silence, not merely add to it."""
    cov = _dithered_coverage(panels=2, panel_h=200, panel_w=280, step=0.70,
                             nights=14, night_drift=0.06, n_per_visit=20,
                             seed=4)
    assert _levels_over_the_bar(cov) == 0
    assert measure_coverage_grain(_sky_for(cov), _as_map(cov)) is None


def test_a_starved_panel_on_a_dithered_canvas_is_still_measured():
    """The band rule is not only about outlines: a pointing that got a sixth of
    the visits is thin too, and on a ramping canvas it is the only rule that can
    see it."""
    cov = _dithered_coverage(panels=2, panel_h=200, panel_w=280, step=0.70,
                             nights=14, night_drift=0.06, n_per_visit=20,
                             starve=(0, 0), starve_frac=0.15, seed=4)
    assert _levels_over_the_bar(cov) == 0
    grain = measure_coverage_grain(_sky_for(cov), _as_map(cov))
    assert grain is not None and grain_verdict(grain.ratio) == "uneven"


def test_two_levels_one_sub_apart_are_not_a_depth_step():
    """The one place the per-level rule *did* fire in the owner's 680 runs, and
    it answered about the wrong pair: levels 3,116 and 3,117 each held a tenth of
    the canvas, so it reported 1.008x over 15 % of the picture while the depth
    bands on the same canvas read 2.27x over 27 %. Grain falls as 1/√depth — one
    sub apart is 0.02 % — so comparing two adjacent levels measures their sky
    samples, not their depth."""
    rng = np.random.default_rng(3)
    h, w = 400, 800
    cov = np.full((h, w), 3117, dtype=np.int32)
    cov[:, :300] = 3116
    rgb = rng.normal(0.0, 3.0, size=(h, w, 3)).astype(np.float32)
    assert measure_coverage_grain(rgb, cov.astype(np.float32)) is None


# --------------------------------------------------------------------------
# the verdict
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ratio,expected", [
    (None, None), (1.0, None), (1.24, None), (1.25, "uneven"), (2.0, "uneven"),
    (float("nan"), None), ("oops", None),
])
def test_grain_verdict_cases(ratio, expected):
    assert grain_verdict(ratio) == expected


# --------------------------------------------------------------------------
# what the app says
# --------------------------------------------------------------------------

def test_the_health_panel_explains_the_grainier_panel():
    """The measurement half, on the bundled sample's own figures. What the note
    *prescribes* about them is the two tests below — those numbers are 3 subs
    against 6 at a 10 s sub, i.e. half a minute behind."""
    notes = stack_health(_run(grain_ratio=1.43, grain_thin_frames=3,
                              grain_deep_frames=6, grain_thin_share=0.2257),
                         _frames())
    note = next(n for n in notes if n.kind == "grain_uneven")
    assert "23%" in note.message
    assert "3 subs" in note.message and "has 6" in note.message
    assert "1.4×" in note.message
    # The only thing that changes it is more light — so the note must not offer
    # an in-app fix, which is the untruth it exists to remove.
    assert note.action is None
    # …and it says so, in both endings.
    assert "grain only comes down with more light" in note.message


def test_a_ramping_canvas_is_not_sent_out_for_another_night_on_that_panel():
    """The second half of the 2026-09-19 observer report, and the reason the
    measurement could not simply be switched on: the note's own wording — "that
    corner has 3 subs where the rest has 6, another night on that panel evens it
    out" — is a panel's advice, and on a ramping canvas part of the thin region
    is the outline the pointings leave, whose width is the pointing spread. It is
    the same shape after another ten nights."""
    notes = stack_health(
        _run(grain_ratio=1.59, grain_thin_frames=26, grain_deep_frames=224,
             grain_thin_share=0.25, grain_region="spread",
             coverage_thin_frac=0.0),
        _frames())
    note = next(n for n in notes if n.kind == "grain_uneven")
    assert "25%" in note.message and "1.6×" in note.message
    assert "26 subs" in note.message and "224" in note.message
    assert "another night on that panel" not in note.message
    assert "ragged outer edge" in note.message
    assert "grain only comes down with more light" in note.message
    assert note.action is None


def test_a_plateau_keeps_the_panel_sentence_it_has_always_had():
    """The same run with a *level* behind it, not a ramp — and with no word at
    all, which is every run recorded before the column existed. Both keep the
    sentence byte for byte."""
    for region in ("panel", None):
        notes = stack_health(
            _run(grain_ratio=1.43, grain_thin_frames=3, grain_deep_frames=6,
                 grain_thin_share=0.2257, grain_region=region), _frames())
        note = next(n for n in notes if n.kind == "grain_uneven")
        assert "Part of this mosaic is thinner than the rest" in note.message
        assert "ragged outer edge" not in note.message


def test_the_border_trim_stops_promising_a_clean_rectangle_it_cannot_cut():
    """The third finding of the same report, measured on the owner's own library:
    `largest_covered_rect` keeps 37 % of one of his mosaics and 19.5 % of what it
    keeps is *still* below half the median depth, at 1.58x the grain of the rest.
    A ramp has no edge for a rectangle to stop at. So a run that carries a
    measured depth spread trades the promise for what the trim really does — and
    the grain note stands down rather than quoting a second percentage about the
    same thin part two notes apart."""
    run = _run(coverage_thin_frac=0.55, coverage_max=12, grain_ratio=1.58,
               grain_thin_frames=26, grain_deep_frames=224,
               grain_thin_share=0.25, grain_region="spread")
    notes = stack_health(run, _frames())
    coverage = next(n for n in notes if n.kind == "coverage")
    assert "clean, even rectangle" not in coverage.message
    assert "crops to the well-covered part" in coverage.message
    assert "1.6×" in coverage.message
    assert coverage.action == "trim_border"          # the button is untouched
    assert not [n for n in notes if n.kind == "grain_uneven"]


def test_a_thin_panel_keeps_the_border_trims_own_promise():
    """The same offer on every run that carries no depth-spread measurement — a
    single field, an evenly covered mosaic, a thin *panel*, or anything recorded
    before the word existed. Byte for byte what it was."""
    run = _run(coverage_thin_frac=0.55, coverage_max=12, grain_ratio=1.43,
               grain_thin_frames=3, grain_deep_frames=6, grain_thin_share=0.2257)
    coverage = next(n for n in stack_health(run, _frames())
                    if n.kind == "coverage")
    assert coverage.message.endswith(
        "Trim border gives a clean, even rectangle.")


def test_a_panel_only_minutes_behind_is_not_sent_out_for_another_night():
    """The bug, reproduced on the running app by the `--mosaic` dogfood pass and
    on the sample's own figures here.

    The panel map and this note were printed one under the other, about the same
    panel of the same run, giving **opposite** instructions: the map's *"it's
    only a few minutes' difference at this stage, so it evens out on its own as
    you keep shooting"*, and this note's *"another night on that panel is what
    evens it out"*. The map asks whether the shortfall clears
    ``THIN_MIN_SHORTFALL_S``; this note asked nothing at all, because a *depth*
    cannot answer it — 3 subs against 6 reads 1.4× grainier whether that is
    half a minute or three hours behind.

    *(The map no longer says the words quoted above: that same fixed phrase was
    then found describing a 30-second gap as "a few minutes", and it now names
    the shortfall in this note's exact closing clause — see
    ``tests/test_mosaic_map.py::test_the_gap_the_card_names_is_the_one_it_just_printed``.
    So the two sentences agree about the size of the gap as well as about what to
    do; grep ``_verdict_text`` rather than the old string.)*

    Nothing is removed: the picture really is 1.4× grainier over a quarter of
    itself and the note still says so. Only the prescription follows the same
    threshold the map uses — the shape v0.406.2 gave the map's own ``behind``
    branch, which kept the fact and dropped the nag."""
    notes = stack_health(_run(grain_ratio=1.43, grain_thin_frames=3,
                              grain_deep_frames=6, grain_thin_share=0.2257),
                         _frames())          # 10 s subs → 3 × 10 s = 30 s behind
    note = next(n for n in notes if n.kind == "grain_uneven")
    assert "another night" not in note.message.lower()
    assert "30 s behind" in note.message
    assert "evens out on its own as you keep shooting" in note.message
    # The measurement is untouched.
    assert "23%" in note.message and "1.4×" in note.message


def test_a_panel_genuinely_behind_still_says_to_go_and_shoot_it():
    """The other side, byte for byte: a mosaic whose thin panel is 15 minutes
    down really does need a night on that panel, and the sentence for that case
    is exactly the one the note has always said."""
    notes = stack_health(_run(grain_ratio=1.43, grain_thin_frames=30,
                              grain_deep_frames=120, grain_thin_share=0.2257),
                         _frames())          # 90 × 10 s = 15 min behind
    note = next(n for n in notes if n.kind == "grain_uneven")
    assert note.message == (
        "Part of this mosaic is thinner than the rest — about 23% of the "
        "picture has 30 subs on it where most of it has 120, so that part "
        "looks about 1.4× grainier. That isn't something processing can fix — "
        "grain only comes down with more light — so another night on that "
        "panel is what evens it out.")


def test_a_sub_exposure_nobody_recorded_keeps_the_sentence_it_had():
    """The shortfall is a claim about minutes, so a run whose subs never
    recorded an exposure cannot make it. Silence in the safe direction: keep
    today's wording rather than assert a smallness we can't measure."""
    bare = [FrameRow(id=i, source_path=f"/incoming/s{i}.fit", accept=True,
                     fwhm_px=2.1, exposure_s=None) for i in range(12)]
    notes = stack_health(_run(grain_ratio=1.43, grain_thin_frames=3,
                              grain_deep_frames=6, grain_thin_share=0.2257),
                         bare)
    note = next(n for n in notes if n.kind == "grain_uneven")
    assert "another night on that panel" in note.message


@pytest.mark.parametrize("thin_subs,deep_subs,expect_a_night", [
    (3, 6, False),        # the bundled sample: 30 s behind
    (6, 24, False),       # 3 min behind — the map's "young mosaic" case
    (30, 120, True),      # 15 min behind
    (90, 360, True),      # 45 min behind
])
def test_the_grain_note_and_the_panel_map_never_give_opposite_instructions(
        thin_subs, deep_subs, expect_a_night):
    """The agreement pin, asserted against the map itself rather than against a
    copy of its answer: for one mosaic, at one sub exposure, "go and shoot that
    panel" must be said by both surfaces or by neither.

    The two measure different things on purpose — the map clusters *pointings*,
    the note reads the finished canvas's *coverage* — so this cannot be one
    function. What it can be, and now is, is one threshold applied to one
    quantity: how far behind, in seconds."""
    from seestack.mosaicmap import mosaic_depth_map

    sub_s = 10.0
    # A 2×2 mosaic whose bottom-right panel holds `thin_subs` where the rest
    # hold `deep_subs`, at the same sub exposure the run's frames report.
    frames = []
    for r in range(2):
        for c in range(2):
            n = thin_subs if (r, c) == (1, 1) else deep_subs
            dec = 30.0 + (1 - r) * 0.5
            ra = 200.0 + (1 - c) * 0.5 / math.cos(math.radians(dec))
            frames.extend([(ra, dec, sub_s)] * n)

    m = mosaic_depth_map(frames)
    assert m is not None
    map_says_go = m.thin is not None
    assert map_says_go is expect_a_night

    notes = stack_health(
        _run(grain_ratio=1.43, grain_thin_frames=thin_subs,
             grain_deep_frames=deep_subs, grain_thin_share=0.2257),
        [FrameRow(id=i, source_path=f"/incoming/s{i}.fit", accept=True,
                  fwhm_px=2.1, exposure_s=sub_s) for i in range(12)])
    note = next(n for n in notes if n.kind == "grain_uneven")
    note_says_go = "another night on that panel" in note.message
    assert note_says_go is map_says_go


def _two_night_mosaic(thin_subs: int, deep_subs: int, short_s=10.0, long_s=30.0):
    """A 2x2 mosaic shot over two nights at two sub lengths — the shape the pin
    above deliberately does not have.

    Three quarters of *every* panel's subs are ``short_s`` and the rest
    ``long_s``, so the mix is the same everywhere and a panel's integration is
    exactly its depth times the set's mean. Returns the map's
    ``(ra, dec, exposure_s)`` triples and the flat list of exposures the run's
    frames report, which is the same population read two ways.
    """
    def panel(n: int) -> list[float]:
        return [short_s] * (n * 3 // 4) + [long_s] * (n - n * 3 // 4)

    triples: list[tuple[float, float, float]] = []
    exposures: list[float] = []
    for r in range(2):
        for c in range(2):
            n = thin_subs if (r, c) == (1, 1) else deep_subs
            dec = 30.0 + (1 - r) * 0.5
            ra = 200.0 + (1 - c) * 0.5 / math.cos(math.radians(dec))
            for e in panel(n):
                triples.append((ra, dec, e))
                exposures.append(e)
    return triples, exposures


def _grain_note(thin_subs: int, deep_subs: int, exposures: list[float]):
    return next(
        n for n in stack_health(
            _run(grain_ratio=1.43, grain_thin_frames=thin_subs,
                 grain_deep_frames=deep_subs, grain_thin_share=0.2257),
            [FrameRow(id=i, source_path=f"/incoming/s{i}.fit", accept=True,
                      fwhm_px=2.1, exposure_s=e)
             for i, e in enumerate(exposures)])
        if n.kind == "grain_uneven")


def test_a_two_night_mosaic_is_not_told_its_thin_panel_evens_out_on_its_own():
    """The bug, reproduced before it was fixed. A target is one folder, never one
    exposure, and this note multiplies a per-sub length by a *count* — so it used
    a plain median, which on a set of two lengths is one member of it chosen by
    position rather than a summary.

    Three quarters of every panel's subs at 10 s and the rest at 30 s makes the
    median 10 s where the set's own mean is 15 s, and the shortfall the note
    quotes lands on the wrong side of ``THIN_MIN_SHORTFALL_S``: 24 missing subs
    read as 4 min ("it evens out on its own as you keep shooting") where the
    light really missing is 6 min. The panel map directly above it, which sums
    each panel's *actual* exposures, said to go and shoot that panel."""
    from seestack.mosaicmap import THIN_MIN_SHORTFALL_S

    triples, exposures = _two_night_mosaic(thin_subs=8, deep_subs=32)
    note = _grain_note(8, 32, exposures)
    # The honest shortfall — the mean times the missing count, which is exactly
    # the light the thin panel is behind — clears the threshold the map uses.
    assert (32 - 8) * (sum(exposures) / len(exposures)) > THIN_MIN_SHORTFALL_S
    assert "another night on that panel" in note.message
    assert "evens out on its own" not in note.message
    # The measurement itself is untouched.
    assert "23%" in note.message and "1.4×" in note.message


def test_the_shortfall_the_note_names_is_the_gap_the_panel_map_measured():
    """And the agreement is exact, not approximate: the map sums the thin panel's
    own exposures against a typical panel's, and the note multiplies the missing
    depth by the set's mean — which *is* that sum when the mix is the same on
    every panel. Pinned as the same number rather than as the same verdict, so a
    future basis change shows up here before it shows up as two sentences giving
    opposite advice."""
    from seestack.mosaicmap import mosaic_depth_map
    from seestack.sharecard import format_duration

    triples, exposures = _two_night_mosaic(thin_subs=8, deep_subs=32)
    m = mosaic_depth_map(triples)
    assert m is not None and m.thin is not None      # the map says: go and shoot
    map_gap_s = m.median_exposure_s - m.thin.exposure_s

    note_gap_s = (32 - 8) * (sum(exposures) / len(exposures))
    assert note_gap_s == pytest.approx(map_gap_s)

    # …and when the gap is small enough for the reassuring branch, the number the
    # note prints is that same gap in the map's own words.
    triples, exposures = _two_night_mosaic(thin_subs=8, deep_subs=20)
    note = _grain_note(8, 20, exposures)
    small_gap_s = (20 - 8) * (sum(exposures) / len(exposures))
    assert f"about {format_duration(small_gap_s)} behind" in note.message


@pytest.mark.parametrize("thin_subs,deep_subs,expect_a_night", [
    (8, 20, False),       # 3 min behind at a 15 s mean
    (8, 32, True),        # 6 min behind — the reproduction above
])
def test_the_two_surfaces_agree_on_a_mosaic_shot_at_two_sub_lengths(
        thin_subs, deep_subs, expect_a_night):
    """The pin above, re-run on the shape it excludes: "go and shoot that panel"
    must still be said by both surfaces or by neither once the target holds more
    than one sub length."""
    from seestack.mosaicmap import mosaic_depth_map

    triples, exposures = _two_night_mosaic(thin_subs, deep_subs)
    m = mosaic_depth_map(triples)
    assert m is not None
    map_says_go = m.thin is not None
    assert map_says_go is expect_a_night

    note = _grain_note(thin_subs, deep_subs, exposures)
    assert ("another night on that panel" in note.message) is map_says_go


def test_the_panel_flatness_praise_stops_claiming_there_is_nothing_to_see():
    """The bug half. ``seam_residual`` 0.7 is "flat", and on an unevenly deep
    canvas the app used to answer someone looking straight at a grainier
    rectangle with *"you shouldn't see seams between them"*."""
    notes = stack_health(_run(grain_ratio=1.43, grain_thin_frames=3,
                              grain_deep_frames=6, grain_thin_share=0.2257),
                         _frames())
    flat = next(n for n in notes if n.kind == "seams_flat")
    assert "you shouldn't see seams" not in flat.message
    assert "not a step in the sky" in flat.message
    # It has to stand on its own: the card renders the top two notes, and at 42
    # against 62 the grain note and this one are rarely both on screen.
    assert "above" not in flat.message
    # Nothing removed: it still says the panels evened out.
    assert "evened out" in flat.message
    # ...and it must not be praised for "even coverage" in the same breath.
    solid = next((n for n in notes if n.kind == "solid"), None)
    assert solid is None or "even coverage" not in solid.message


def test_a_mosaic_that_is_only_flat_keeps_exactly_the_wording_it_had():
    """No measurement (an older run, a single-field stack, an even mosaic) and
    the panel says what it has always said."""
    notes = stack_health(_run(), _frames())
    flat = next(n for n in notes if n.kind == "seams_flat")
    assert flat.message == ("The panels of this mosaic evened out — the sky "
                            "matches across the joins, so you shouldn't see "
                            "seams between them.")
    assert not any(n.kind == "grain_uneven" for n in notes)


def test_a_measured_but_even_canvas_says_nothing():
    notes = stack_health(_run(grain_ratio=1.05, grain_thin_frames=5,
                              grain_deep_frames=6, grain_thin_share=0.3),
                         _frames())
    assert not any(n.kind == "grain_uneven" for n in notes)
    flat = next(n for n in notes if n.kind == "seams_flat")
    assert "you shouldn't see seams" in flat.message


def test_a_ratio_with_no_depths_behind_it_is_never_spoken():
    """The four figures are one measurement; a half-written row must not produce
    a sentence with a blank in it."""
    notes = stack_health(_run(grain_ratio=1.6), _frames())
    assert not any(n.kind == "grain_uneven" for n in notes)


# --------------------------------------------------------------------------
# healing a run stacked before the columns existed
# --------------------------------------------------------------------------

def _write_outputs(fits_path, rgb, cov) -> None:
    """The master and coverage siblings a mosaic run leaves on disk — the master
    as the ``(C, H, W)`` cube ``write_stack_outputs`` writes."""
    from astropy.io import fits

    fits_path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(
        data=np.transpose(np.asarray(rgb, dtype=np.float32), (2, 0, 1))
    ).writeto(fits_path, overwrite=True)
    for suffix in ("_coverage", "_framecov"):
        fits.PrimaryHDU(data=np.asarray(cov, dtype=np.float32)).writeto(
            fits_path.with_name(f"{fits_path.stem}{suffix}.fits"), overwrite=True)


def test_an_existing_mosaic_explains_its_grainy_panel_without_being_restacked(tmp_path):
    from seestack.coverage_backfill import backfill_coverage_grain
    from seestack.io.project import Project

    rgb, cov = _uneven_canvas(h=600, w=1000)
    fits_path = tmp_path / "out" / "m42.fits"
    _write_outputs(fits_path, rgb, cov)

    proj = Project.create(tmp_path / "t", name="T")
    try:
        run_id = proj.add_stack_run(_run(
            id=None, fits_path=str(fits_path), canvas_h=600, canvas_w=1000,
            grain_ratio=None, grain_thin_frames=None, grain_deep_frames=None,
            grain_thin_share=None))
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert row.grain_ratio is None      # what the owner's library looks like

        assert backfill_coverage_grain(proj, row) is True
        assert grain_verdict(row.grain_ratio) == "uneven"
        assert (row.grain_thin_frames, row.grain_deep_frames) == (3, 6)
        # …and it stays healed, without opening the master again.
        again = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert again.grain_ratio == pytest.approx(row.grain_ratio)
        assert again.grain_thin_frames == 3
        # The healed row grades exactly like a freshly-stacked one.
        note = next(n for n in stack_health(again, _frames())
                    if n.kind == "grain_uneven")
        assert "3 subs" in note.message
    finally:
        proj.close()


def test_an_older_project_gains_the_grain_columns_on_open_without_a_version_bump(
        tmp_path):
    """Upgrade safety (§9), and specifically **rollback** safety: the four
    columns are additive through ``_reconcile_table_columns``, not through a
    ``SCHEMA_VERSION`` bump — an older build refuses to open a project stamped
    newer than itself, so bumping would mean this could not be rolled back. A
    project missing them must gain them on open and keep every row."""
    import sqlite3

    from seestack.io.project import Project

    proj_dir = tmp_path / "t"
    proj = Project.create(proj_dir, name="T")
    try:
        proj.add_stack_run(_run(id=None, output_basename="old", grain_ratio=None,
                                grain_thin_frames=None, grain_deep_frames=None,
                                grain_thin_share=None))
    finally:
        proj.close()

    conn = sqlite3.connect(proj_dir / "project.sqlite")
    try:
        for column in ("grain_ratio", "grain_thin_frames", "grain_deep_frames",
                       "grain_thin_share"):
            conn.execute(f"ALTER TABLE stack_runs DROP COLUMN {column}")
        conn.commit()
        version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    proj = Project.open(proj_dir)
    try:
        assert proj._conn.execute(
            "PRAGMA user_version").fetchone()[0] == version_before
        runs = list(proj.iter_stack_runs())
        assert [r.output_basename for r in runs] == ["old"]
        # NULL reads as "never measured", so an upgraded library is silent about
        # its old runs rather than claiming their panels are even.
        assert runs[0].grain_ratio is None
        assert not any(n.kind == "grain_uneven"
                       for n in stack_health(runs[0], _frames()))
        # …and a fresh row round-trips all four figures.
        new_id = proj.add_stack_run(_run(
            id=None, output_basename="new", grain_ratio=1.43,
            grain_thin_frames=3, grain_deep_frames=6, grain_thin_share=0.2257))
        fresh = next(r for r in proj.iter_stack_runs() if r.id == new_id)
        assert (fresh.grain_ratio, fresh.grain_thin_frames,
                fresh.grain_deep_frames, fresh.grain_thin_share) == (
                    1.43, 3, 6, 0.2257)
    finally:
        proj.close()


# --------------------------------------------------------------------------
# a real stack, end to end
# --------------------------------------------------------------------------

def _uneven_mosaic_project(tmp_path, depths=(8, 2)):
    """Two panels of one sky shot to different depths — a mosaic caught
    mid-build, which is what a multi-night mosaic is for most of its life."""
    from seestack.io.project import Project
    from tests.synth import make_synth_wcs_text, write_seestar_fits

    w, h, pixscale = 480, 320, 5.0
    step_deg = w * pixscale / 3600.0 * 0.8
    proj = Project.create(tmp_path / "p", name="uneven-mosaic")
    raws = tmp_path / "raws"
    raws.mkdir()
    for panel, n in enumerate(depths):
        ra = 83.6 + panel * step_deg
        for j in range(n):
            path = write_seestar_fits(
                raws / f"p{panel}_{j}.fit", add_wcs=True, seed=100 + j,
                n_stars=40, ra_center_deg=ra, dec_center_deg=-5.4,
                pixscale_arcsec=pixscale)
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=w, height_px=h, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(
                    width=w, height=h, ra_center_deg=ra, dec_center_deg=-5.4,
                    pixscale_arcsec=pixscale),
                ra_center_deg=ra, dec_center_deg=-5.4))
    return proj


@pytest.mark.parametrize("depths,expect_uneven", [((8, 2), True), ((5, 5), False)])
def test_a_stack_stamps_the_grain_step_on_the_header_and_the_run(
        tmp_path, depths, expect_uneven):
    """The wiring, on a real ``run_stack``: an unevenly deep mosaic records the
    measurement in its own FITS provenance and its history row, and an evenly
    shot one records nothing rather than a reassuring number."""
    pytest.importorskip("scipy")
    pytest.importorskip("photutils")
    pytest.importorskip("tifffile")
    from astropy.io import fits as _fits

    from seestack.stack.stacker import StackOptions, run_stack

    proj = _uneven_mosaic_project(tmp_path, depths=depths)
    try:
        result = run_stack(proj, StackOptions(
            output_name="uneven", max_workers=1, sigma_clip=False))
        header = _fits.getheader(str(result.fits_path))
        run = next(r for r in proj.iter_stack_runs()
                   if r.output_basename == "uneven")
    finally:
        proj.close()

    # Both cases must really be mosaics, or the negative one would pass because
    # the measurement never ran rather than because it declined.
    assert run.is_mosaic
    if not expect_uneven:
        assert "GRAINRAT" not in header
        assert run.grain_ratio is None
        return
    assert header["GRAINTHN"] < header["GRAINDEP"]
    assert 0.1 <= header["GRAINSHR"] <= 0.9
    # The row and the header are one measurement, not two.
    assert run.grain_ratio == pytest.approx(float(header["GRAINRAT"]))
    assert run.grain_thin_frames == int(header["GRAINTHN"])
    assert run.grain_deep_frames == int(header["GRAINDEP"])
    assert run.grain_thin_share == pytest.approx(float(header["GRAINSHR"]))
    assert grain_verdict(run.grain_ratio) == "uneven"
    # ...and *what* was found travels with the four figures, on both, so nothing
    # downstream has to guess which advice the numbers license.
    assert run.grain_region == header["GRAINREG"] == "panel"


def test_the_region_word_round_trips_and_an_older_db_simply_has_none(tmp_path):
    """The column is additive and un-versioned, like the four figures beside it:
    a DB written before it existed opens, gains it, and reads NULL — which
    :func:`grain_region_of` answers as the panel wording those rows have always
    carried."""
    import sqlite3

    from seestack.io.project import Project
    from seestack.stackhealth import grain_region_of

    proj = Project.create(tmp_path / "t", name="region")
    try:
        run_id = proj.add_stack_run(_run(id=None, grain_region="spread"))
        back = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert back.grain_region == "spread"
        assert grain_region_of(back) == "spread"
        # The update path writes it beside the ratio it belongs to.
        assert proj.set_stack_coverage_grain(run_id, 1.6, 26, 224, 0.25, "panel")
        assert next(r for r in proj.iter_stack_runs()
                    if r.id == run_id).grain_region == "panel"
        db = proj.db_path
    finally:
        proj.close()

    # An older build's DB: drop the column and re-open.
    with sqlite3.connect(db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(stack_runs)")
                if r[1] != "grain_region"]
        conn.execute("CREATE TABLE old AS SELECT "
                     + ", ".join(cols) + " FROM stack_runs")
        conn.execute("DROP TABLE stack_runs")
        conn.execute("ALTER TABLE old RENAME TO stack_runs")
    proj = Project.open(tmp_path / "t")
    try:
        rows = list(proj.iter_stack_runs())
        assert rows and rows[0].grain_region is None
        assert grain_region_of(rows[0]) == "panel"
    finally:
        proj.close()


def test_a_single_field_run_is_healed_for_free_without_opening_a_file(tmp_path):
    from seestack.coverage_backfill import backfill_coverage_grain
    from seestack.io.project import Project

    proj = Project.create(tmp_path / "t", name="T")
    try:
        run_id = proj.add_stack_run(_run(
            id=None, is_mosaic=False, fits_path=str(tmp_path / "nope.fits")))
        row = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        assert backfill_coverage_grain(proj, row) is False
        assert row.grain_ratio is None
    finally:
        proj.close()
