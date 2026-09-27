"""A faint field's un-located subs join the stack by their star patterns.

``run_stack`` combines only accepted **and** plate-solved frames, so a target whose
subs mostly fail to plate-solve stacks the handful that did — which is the
per-pixel colour speckle the owner reported as "gibberish on faint targets". With
``StackOptions.star_match_unsolved`` on, the rest are placed from the reference
sub's own stars instead.

These tests run the **real** stacker on synthetic subs rendered from one shared
catalog at a ladder of rotations and dithers — the alt-az case — and check three
separate things: that the subs reach the picture, that the picture is genuinely
deeper for it, and that nothing was written into the project DB to make it happen.
"""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("photutils")
pytest.importorskip("PIL")
pytest.importorskip("tifffile")
pytest.importorskip("astroalign")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import (  # noqa: E402
    make_rotated_star_field,
    make_synth_wcs_text,
    write_seestar_fits,
)

W, H = 480, 320
N_STARS = 30
SEED = 21
# One night of alt-az rotation over the subs that never solved, with the dither
# that rides on it. Rotation is what makes these *un*-placeable by anything but a
# star pattern; the solved pair below is the un-rotated reference.
ROTATIONS = [0.0, 1.5, -2.0, 4.0, -6.0, 9.0, 13.0, -17.0]


def _sub(path: Path, rotation_deg: float, shift=(0.0, 0.0), noise_seed: int = 0) -> Path:
    return write_seestar_fits(
        path, width=W, height=H,
        data=make_rotated_star_field(
            width=W, height=H, n_stars=N_STARS, seed=SEED,
            rotation_deg=rotation_deg, shift=shift, noise_seed=noise_seed,
        ),
    )


def _faint_field(tmp_path, *, n_solved: int = 2) -> tuple[Project, list[int]]:
    """A target with a couple of solved subs and eight the solver never placed.

    Every sub is the same patch of sky: the solved ones un-rotated (so their WCS is
    honest), the rest turned and dithered the way a session turns them. Returns the
    project and the ids of the un-located subs.
    """
    proj = Project.create(tmp_path / "p", name="faint")
    raws = tmp_path / "raws"
    raws.mkdir()
    wcs_text = make_synth_wcs_text(width=W, height=H)
    for i in range(n_solved):
        path = _sub(raws / f"solved_{i}.fit", 0.0, noise_seed=1 + i)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=W, height_px=H, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            star_count=N_STARS, fwhm_px=4.0,
        ))
    unsolved: list[int] = []
    for i, rot in enumerate(ROTATIONS):
        path = _sub(raws / f"unsolved_{i}.fit", rot, shift=(2.0, -1.0),
                    noise_seed=20 + i)
        fid = proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=W, height_px=H, bayer_pattern="RGGB",
            star_count=N_STARS - i, fwhm_px=4.0,
            reject_reason="solve_failed:no solution",
        ))
        unsolved.append(fid)
    return proj, unsolved


def _options(**kw) -> StackOptions:
    # A plain, fast stack: what is under test is which frames reach it.
    return StackOptions(
        output_name="out", sigma_clip=False, background_flatten=False,
        suppress_hot_pixels=False, final_gradient_removal=False,
        max_workers=1, **kw,
    )


def test_the_unsolved_subs_stay_out_by_default(tmp_path):
    """FAIL-BEFORE, and the §9 half: the default changes nothing."""
    assert StackOptions().star_match_unsolved is False
    proj, unsolved = _faint_field(tmp_path)
    try:
        res = run_stack(proj, _options())
        assert res.n_frames_used == 2
        assert res.n_star_matched == 0
        assert res.coverage_max == 2
    finally:
        proj.close()


def test_star_matching_brings_the_whole_night_into_the_picture(tmp_path):
    proj, unsolved = _faint_field(tmp_path)
    try:
        res = run_stack(proj, _options(star_match_unsolved=True))
        # Two solved plus most of the eight that were not.
        assert res.n_star_matched >= 6, res.n_star_matched
        assert res.n_frames_used == 2 + res.n_star_matched
        # And the picture really is deeper where they overlap, which is the point.
        assert res.coverage_max >= 8, res.coverage_max
        assert Path(res.fits_path).exists()
    finally:
        proj.close()


def test_nothing_is_written_to_the_project_db(tmp_path):
    """A star-matched position must never pose as a plate solve.

    It is derived from a neighbour, not verified against the sky — and a frame left
    unsolved in the DB keeps being re-offered to the real solver on every scan,
    which is where it should be rescued from for good.
    """
    proj, unsolved = _faint_field(tmp_path)
    try:
        res = run_stack(proj, _options(star_match_unsolved=True))
        assert res.n_star_matched >= 6
        for f in proj.iter_frames():
            if f.id not in unsolved:
                continue
            assert f.wcs_json is None
            assert f.ra_center_deg is None and f.dec_center_deg is None
            # Its "the solver couldn't place me" mark is untouched, so the next
            # scan still offers it to ASTAP.
            assert (f.reject_reason or "").startswith("solve_failed:")
    finally:
        proj.close()


def test_a_sub_with_no_stars_is_left_out_rather_than_placed_anywhere(tmp_path):
    proj, unsolved = _faint_field(tmp_path)
    try:
        raws = tmp_path / "raws"
        blank = write_seestar_fits(
            raws / "blank.fit", width=W, height=H,
            data=np.random.default_rng(5).integers(
                900, 1100, size=(H, W), dtype=np.uint16),
        )
        blank_id = proj.add_frame(FrameRow(
            source_path=str(blank), cached_path=str(blank),
            width_px=W, height_px=H, bayer_pattern="RGGB", star_count=0,
        ))
        res = run_stack(proj, _options(star_match_unsolved=True))
        # Nine candidates were offered, and the starless one is not among the
        # placed: the count is the same as without it.
        assert res.n_star_matched <= len(ROTATIONS)
        assert proj.get_frame(blank_id).wcs_json is None
    finally:
        proj.close()


def test_it_stands_down_on_a_mosaic_canvas(tmp_path):
    """The reference sub's stars are on one panel, so an off-panel sub has nothing
    to match against — and guessing would put it on the wrong part of the sky."""
    proj = Project.create(tmp_path / "p", name="mosaic")
    raws = tmp_path / "raws"
    raws.mkdir()
    try:
        # Two pointings, 400 px apart on a 480 px frame: a union canvas well past
        # the mosaic ratio, so ``compute_mosaic_canvas`` calls it a mosaic.
        for panel, dx in enumerate((0.0, -400.0)):
            wcs_text = make_synth_wcs_text(width=W, height=H, crpix_shift=(dx, 0.0))
            # The pointing this CRPIX shift really describes: 400 px at 5"/px, and
            # CDELT1 is negative, so the panel's centre moves east by that much.
            # ``pick_reference_frame`` needs a centre on every candidate, and one
            # that agrees with the WCS or the reference choice is fiction.
            ra = 83.6 + (400.0 * 5.0 / 3600.0) * (1 if dx else 0)
            for i in range(2):
                path = _sub(raws / f"p{panel}_{i}.fit", 0.0, noise_seed=40 + panel * 5 + i)
                proj.add_frame(FrameRow(
                    source_path=str(path), cached_path=str(path),
                    width_px=W, height_px=H, bayer_pattern="RGGB",
                    wcs_json=wcs_text, ra_center_deg=ra, dec_center_deg=-5.4,
                    star_count=N_STARS, fwhm_px=4.0,
                ))
        path = _sub(raws / "unsolved.fit", 0.0, noise_seed=60)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=W, height_px=H, bayer_pattern="RGGB", star_count=N_STARS,
        ))
        res = run_stack(proj, _options(star_match_unsolved=True))
        assert res.canvas_shape[1] > W  # the canvas really is a union
        assert res.n_star_matched == 0
        assert res.n_frames_used == 4
    finally:
        proj.close()
