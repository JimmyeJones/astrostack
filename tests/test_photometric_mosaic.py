"""Photometric normalization on a **mosaic**: panels match themselves, not each other.

``transparency_score`` is the median flux of a frame's brightest stars, so it is
a property of *where the scope pointed* as much as of the sky — a mosaic panel
aimed at an emptier patch genuinely has fainter "brightest" stars. Normalising a
mosaic against one target-wide median therefore reads that intrinsic difference
as haze and gain-matches whole panels apart, manufacturing the panel-grid the
pass exists to prevent. (Same class of bug as the target-wide QC grading fixed
in v0.270.2.)

These tests pin the fix — each panel is normalised against its own subs — and
the mosaic auto-enable that rides on it.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("photutils")
pytest.importorskip("PIL")
pytest.importorskip("tifffile")

from astropy.io import fits  # noqa: E402

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.photometric import compute_photometric_scales  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

# Two panels half a degree apart in RA. A 480 px frame at 5"/px spans 0.667°, so
# the union is ~1.75× the reference area — comfortably past the 1.3× ratio that
# makes the stacker call it a mosaic — and the panels still overlap in the middle.
PANEL_A_RA = 83.6
PANEL_B_RA = 84.1
PANEL_DEC = -5.4


def _row(fid: int, ra: float, *, transparency: float | None) -> FrameRow:
    """A minimal solved FrameRow for the unit-level scale tests."""
    return FrameRow(id=fid, source_path=f"f{fid}", ra_center_deg=ra,
                    dec_center_deg=PANEL_DEC, transparency_score=transparency)


def _mean_scale(scales: dict[int, float], rows: list[FrameRow]) -> float:
    return float(np.mean([scales[r.id] for r in rows]))


# ---------------------------------------------------------------- unit level


def test_a_mosaics_panels_are_not_gain_matched_against_each_other():
    # Two panels, identical conditions, no haze at all — panel B's patch of sky
    # simply has fainter brightest stars. Nothing here should be rescaled.
    a = [_row(i, PANEL_A_RA, transparency=5000.0 + i * 20) for i in range(1, 9)]
    b = [_row(i + 8, PANEL_B_RA, transparency=2200.0 + i * 20) for i in range(1, 9)]
    frames = a + b

    # Target-wide (the pre-fix behaviour, still what a single-field run does):
    # the two panels are pulled apart by more than a factor of two.
    wide, _ = compute_photometric_scales(frames)
    assert _mean_scale(wide, b) / _mean_scale(wide, a) == pytest.approx(2.23, abs=0.05)

    # Per-panel: each panel is its own reference, so the panels keep the relative
    # brightness the sky gave them.
    per_panel, stats = compute_photometric_scales(frames, group_by_pointing=True)
    assert _mean_scale(per_panel, b) / _mean_scale(per_panel, a) == pytest.approx(1.0, abs=0.01)
    assert stats.n_pointing_groups == 2


def test_within_panel_haze_is_still_corrected_per_panel():
    # The point of the pass survives the split: one sub of panel B shot through
    # haze is still gain-matched up, against *its own* panel's median.
    a = [_row(i, PANEL_A_RA, transparency=5000.0) for i in range(1, 6)]
    b = [_row(i, PANEL_B_RA, transparency=2000.0) for i in range(6, 10)]
    hazy = _row(10, PANEL_B_RA, transparency=1000.0)  # half its panel's median
    scales, stats = compute_photometric_scales(a + b + [hazy], group_by_pointing=True)

    assert scales[10] == pytest.approx(2.0, abs=0.01)   # 2000/1000, at the clamp
    assert all(scales[r.id] == pytest.approx(1.0, abs=0.01) for r in a + b)
    assert stats.n_adjusted == 1


def test_a_single_pointing_target_is_unaffected_by_the_grouping():
    # A dithered single-field target clusters into one group, so there is no
    # sound split and it falls through to the target-wide reference — byte-for-
    # byte the behaviour it has always had.
    rows = [_row(i, PANEL_A_RA + i * 0.002, transparency=4000.0 + i * 500)
            for i in range(1, 8)]
    wide, wide_stats = compute_photometric_scales(rows)
    grouped, grouped_stats = compute_photometric_scales(rows, group_by_pointing=True)

    assert grouped == wide
    assert grouped_stats == wide_stats
    assert grouped_stats.n_pointing_groups == 0


def test_a_panel_too_thin_to_grade_stays_neutral_rather_than_borrowing():
    # A two-sub panel can't establish its own median, and comparing it against
    # another patch of sky is exactly the mistake this fix removes — so it is
    # left alone rather than scaled against a yardstick that doesn't apply.
    a = [_row(i, PANEL_A_RA, transparency=5000.0) for i in range(1, 6)]
    b = [_row(i, PANEL_B_RA, transparency=4800.0) for i in range(6, 11)]
    thin = [_row(i, PANEL_B_RA + 2.0, transparency=1500.0) for i in range(11, 13)]
    scales, stats = compute_photometric_scales(a + b + thin, group_by_pointing=True)

    assert all(scales[r.id] == pytest.approx(1.0, abs=0.001) for r in thin)
    assert stats.n_pointing_groups == 2
    assert stats.n_neutral == 2


def test_an_unsolved_sub_in_a_mosaic_stays_neutral():
    # No pointing → no panel → no reference. Neutral, never scaled by a median
    # measured somewhere else on the sky.
    a = [_row(i, PANEL_A_RA, transparency=5000.0) for i in range(1, 6)]
    b = [_row(i, PANEL_B_RA, transparency=2000.0) for i in range(6, 11)]
    unsolved = FrameRow(id=99, source_path="u", transparency_score=1000.0)
    scales, _ = compute_photometric_scales(a + b + [unsolved], group_by_pointing=True)

    assert scales[99] == pytest.approx(1.0, abs=0.001)


# ------------------------------------------------------------- end to end


def _mosaic_project(tmp_path, *, per_panel: int = 4) -> Project:
    """A two-panel mosaic whose panels carry the *identical* star field.

    Identical pixels is the point: any brightness difference between the two
    panel regions of the finished canvas is then purely an artefact of the
    photometric pass, not of the sky.
    """
    proj = Project.create(tmp_path / "p", name="mosaic")
    raws = tmp_path / "raws"
    raws.mkdir()
    for panel, ra in enumerate((PANEL_A_RA, PANEL_B_RA)):
        for i in range(per_panel):
            path = write_seestar_fits(
                raws / f"p{panel}_{i}.fit", add_wcs=True, seed=7, n_stars=40,
                ra_center_deg=ra, dec_center_deg=PANEL_DEC,
            )
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=480, height_px=320, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(
                    ra_center_deg=ra, dec_center_deg=PANEL_DEC),
                ra_center_deg=ra, dec_center_deg=PANEL_DEC,
            ))
    return proj


def _star_level(region: np.ndarray) -> float:
    """Mean star flux above the local sky in one region of the canvas.

    Sky-relative so it is blind to the additive leveling/gradient passes that
    run after the combine, and averaged over the brightest pixels so it doesn't
    ride on a single hot pixel.
    """
    finite = region[np.isfinite(region)]
    assert finite.size > 0
    sky = float(np.median(finite))
    bright = finite[finite >= np.percentile(finite, 99.9)]
    return float(np.mean(bright)) - sky


def _panel_levels(fits_path) -> tuple[float, float]:
    """Star level in the left and right quarters — one pure panel each."""
    with fits.open(fits_path) as hdul:
        data = np.asarray(hdul[0].data, dtype=np.float64)
    # (3, h, w) colour cube → work on the green plane, where the synth stars live.
    plane = data[1] if data.ndim == 3 else data
    q = plane.shape[1] // 4
    return _star_level(plane[:, :q]), _star_level(plane[:, -q:])


def test_a_mosaic_stack_does_not_gain_match_its_panels_apart(tmp_path):
    """The regression: two panels with identical pixels but different star-field
    brightness must come out of the mosaic stack at the same relative level they
    went in at. Pre-fix the target-wide median pushed them ~2× apart."""
    proj = _mosaic_project(tmp_path)
    try:
        rows = list(proj.iter_frames())
        # Reference run: every sub at the same transparency, so the pass is
        # exactly neutral and this is the picture the sky alone produced.
        for f in rows:
            proj.update_frame(f.id, transparency_score=5000.0)
        base = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="base"))
        # Now as QC would really measure them: panel B's patch of sky simply has
        # fainter bright stars. Nothing about the *conditions* changed.
        for f in rows:
            score = 5000.0 if f.ra_center_deg == PANEL_A_RA else 2200.0
            proj.update_frame(f.id, transparency_score=score)
        # Ticked explicitly: this is the *opt-in* path a mosaic owner could
        # already take before the mosaic auto-enable existed, and the path where
        # the target-wide comparison did its damage.
        norm = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="norm",
            photometric_normalize=True))
    finally:
        proj.close()

    base_l, base_r = _panel_levels(base.fits_path)
    norm_l, norm_r = _panel_levels(norm.fits_path)
    # Each panel compared against *itself* in the neutral run, so the crop
    # asymmetry between the two quarters cancels exactly.
    left_gain = norm_l / base_l
    right_gain = norm_r / base_r
    # Pre-fix: one quarter ~0.73×, the other ~1.67× — a 2.2× step across the
    # join. Post-fix both panels keep the level the sky gave them.
    assert left_gain == pytest.approx(1.0, abs=0.1)
    assert right_gain == pytest.approx(1.0, abs=0.1)
    assert max(left_gain, right_gain) / min(left_gain, right_gain) < 1.2


def test_a_mosaic_auto_enables_normalization_and_says_why(tmp_path):
    """Nobody ticks a box on the walk-away path, so a mosaic turns the pass on
    for itself — and records that it did, plus how many panels it matched."""
    proj = _mosaic_project(tmp_path)
    try:
        for i, f in enumerate(proj.iter_frames()):
            # Vary within each panel so there is something to gain-match.
            proj.update_frame(f.id, transparency_score=5000.0 - (i % 4) * 400.0)
        result = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="auto"))
    finally:
        proj.close()

    with fits.open(result.fits_path) as hdul:
        hdr = hdul[0].header
    assert hdr["PHOTNORM"] == "transparency"
    assert bool(hdr["PHOTAUTO"]) is True
    assert int(hdr["PHOTPANL"]) == 2


def test_a_mosaic_with_no_transparency_scores_is_untouched(tmp_path):
    """The auto-enable self-neutralises: an un-QC'd mosaic records no
    normalization at all, so it stacks exactly as it always has."""
    proj = _mosaic_project(tmp_path)
    try:
        result = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="noqc"))
    finally:
        proj.close()

    with fits.open(result.fits_path) as hdul:
        assert "PHOTNORM" not in hdul[0].header
        assert "PHOTAUTO" not in hdul[0].header


def test_a_single_field_stack_still_never_auto_normalizes(tmp_path):
    """The auto-enable is mosaic-only: an ordinary single-target stack with a
    full QC spread must stay exactly as it is today (opt-in)."""
    proj = Project.create(tmp_path / "single", name="single")
    raws = tmp_path / "raws_single"
    raws.mkdir()
    try:
        for i in range(4):
            path = write_seestar_fits(
                raws / f"s{i}.fit", add_wcs=True, seed=10 + i, n_stars=30)
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=480, height_px=320, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(),
                ra_center_deg=PANEL_A_RA, dec_center_deg=PANEL_DEC,
            ))
        for i, f in enumerate(proj.iter_frames()):
            proj.update_frame(f.id, transparency_score=5000.0 - i * 900.0)
        result = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="single"))
    finally:
        proj.close()

    with fits.open(result.fits_path) as hdul:
        assert "PHOTNORM" not in hdul[0].header
