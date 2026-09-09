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
