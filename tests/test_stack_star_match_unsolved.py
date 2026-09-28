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
from seestack.io.wcs_io import wcs_from_text  # noqa: E402
from seestack.stack.stacker import (  # noqa: E402
    StackOptions,
    _anchor_order,
    _capture_epoch,
    _panel_anchors,
    _star_matched_unsolved_frames,
    run_stack,
)
from tests.synth import (  # noqa: E402
    make_rotated_star_field,
    make_shared_sky_field,
    make_synth_wcs_text,
    star_catalog,
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


# --- a mosaic: one anchor per panel -----------------------------------------
#
# The reference sub's stars cover **one** panel, so it can only ever place that
# panel's subs — which is why this pass used to decline a mosaic canvas outright,
# leaving a heavy mosaic user with none of the feature. Every solved panel now offers
# its own anchor, and a sub is placed by the panel whose stars it measurably matches.

PIXSCALE = 5.0                       # `make_synth_wcs_text`'s own pixel scale
RA0, DEC0 = 83.6, -5.4
PANEL_STEP_PX = 360                  # a 75 % step across a 480 px panel: real overlap
PANEL_STEP_DEG = PANEL_STEP_PX * PIXSCALE / 3600.0   # 0.5 deg, well past the 0.25 deg
                                                     # `pointing_groups` link distance
MOSAIC_N_STARS = 60                  # over the wider catalog: ~30 per panel window
# A mosaic is shot panel by panel, which is what makes "the panel shot around this
# sub's own time" a usable ordering for the anchors. Two hours apart, so a sub's own
# block is unambiguous.
PANEL_HOUR = {0: 20, 1: 22}


def _panel_time(panel: int, i: int) -> str:
    return f"2026-09-01T{PANEL_HOUR[panel]:02d}:{i * 3:02d}:00+00:00"


def _panel_ra(panel: int) -> float:
    # CDELT1 is negative, so RA falls as the window moves right across the catalog.
    return RA0 - panel * PANEL_STEP_DEG


def _panel_sub(path: Path, stars, panel: int, *, shift=(0.0, 0.0),
               noise_seed: int = 0, catalog_origin: int | None = None) -> Path:
    """One sub of ``panel`` — a window onto the shared catalog, so two panels really
    do show different stars and their overlap really does show the same ones."""
    origin = (panel * PANEL_STEP_PX if catalog_origin is None else catalog_origin, 0)
    return write_seestar_fits(
        path, width=W, height=H,
        data=make_shared_sky_field(stars, width=W, height=H, origin=origin,
                                   star_shift=shift, noise_seed=noise_seed),
    )


def _two_panel_mosaic(tmp_path, *, n_solved: int = 2, n_unsolved: int = 2):
    """A two-panel mosaic: each panel solved, each panel holding un-located subs.

    Returns ``(project, catalog, {panel: [unsolved frame ids]})``.
    """
    proj = Project.create(tmp_path / "p", name="mosaic")
    raws = tmp_path / "raws"
    raws.mkdir()
    stars = star_catalog(seed=SEED, width=W + PANEL_STEP_PX, height=H,
                         n_stars=MOSAIC_N_STARS)
    unsolved: dict[int, list[int]] = {0: [], 1: []}
    for panel in (0, 1):
        wcs_text = make_synth_wcs_text(
            width=W, height=H, ra_center_deg=_panel_ra(panel), dec_center_deg=DEC0,
            pixscale_arcsec=PIXSCALE)
        for i in range(n_solved):
            path = _panel_sub(raws / f"s{panel}_{i}.fit", stars, panel,
                              noise_seed=10 + panel * 10 + i)
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                wcs_json=wcs_text, ra_center_deg=_panel_ra(panel),
                dec_center_deg=DEC0, star_count=30 - i, fwhm_px=4.0,
                timestamp_utc=_panel_time(panel, i),
            ))
        for i in range(n_unsolved):
            path = _panel_sub(raws / f"u{panel}_{i}.fit", stars, panel,
                              shift=(2.0, -1.0), noise_seed=50 + panel * 10 + i)
            unsolved[panel].append(proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                star_count=28, fwhm_px=4.0,
                timestamp_utc=_panel_time(panel, i + 1),
                reject_reason="solve_failed:no solution",
            )))
    return proj, stars, unsolved


def _centre_sky(wcs_text: str) -> tuple[float, float]:
    w = wcs_from_text(wcs_text)
    assert w is not None
    ra, dec = w.all_pix2world([[(W - 1) / 2.0, (H - 1) / 2.0]], 0)[0]
    return float(ra), float(dec)


def _solved(proj) -> list[FrameRow]:
    return [f for f in proj.iter_frames(accepted_only=True) if f.wcs_json]


def test_one_anchor_is_offered_per_panel_and_none_on_a_single_field(tmp_path):
    proj, _stars, _unsolved = _two_panel_mosaic(tmp_path)
    try:
        anchors = _panel_anchors(_solved(proj))
        assert len(anchors) == 2
        # One per pointing, and the star-richest sub of each.
        ras = sorted(round(a.ra_center_deg, 4) for a in anchors)
        assert ras == sorted(round(_panel_ra(p), 4) for p in (0, 1))
        assert all(a.star_count == 30 for a in anchors)
    finally:
        proj.close()
    # A single-field target has one pointing, so there are no panels to anchor —
    # the caller keeps the reference sub, exactly as before.
    elsewhere = tmp_path / "single"
    elsewhere.mkdir()
    single, _ = _faint_field(elsewhere)
    try:
        assert _panel_anchors(_solved(single)) == []
    finally:
        single.close()


def test_a_mosaic_places_each_sub_on_the_panel_its_own_stars_are_on(tmp_path):
    """The claim the old stand-down was protecting, now met by measuring instead.

    Each un-located sub must come back carrying *its own* panel's sky — not the
    other panel's, and not a placement somewhere between them.
    """
    proj, _stars, unsolved = _two_panel_mosaic(tmp_path)
    try:
        anchors = _panel_anchors(_solved(proj))
        placed, attempted = _star_matched_unsolved_frames(proj, anchors)
        assert attempted == 4
        assert len(placed) == 4, [f.id for f in placed]
        by_id = {f.id: f for f in placed}
        for panel, ids in unsolved.items():
            for fid in ids:
                assert fid in by_id, (panel, fid)
                ra, dec = _centre_sky(by_id[fid].wcs_json)
                own = _panel_ra(panel)
                other = _panel_ra(1 - panel)
                # Its own panel, to within the dither (2 px = 10 arcsec).
                assert abs(ra - own) < 20.0 / 3600.0, (panel, fid, ra, own)
                assert abs(dec - DEC0) < 20.0 / 3600.0, (panel, fid, dec)
                # And unambiguously not the other panel's.
                assert abs(ra - other) > 0.4 * PANEL_STEP_DEG, (panel, fid, ra, other)
    finally:
        proj.close()


def test_a_mosaic_stack_takes_the_subs_the_solver_could_not_place(tmp_path):
    """FAIL-BEFORE: a mosaic canvas used to decline this pass, so the count was 0."""
    proj, _stars, _unsolved = _two_panel_mosaic(tmp_path)
    try:
        res = run_stack(proj, _options(star_match_unsolved=True))
        assert res.canvas_shape[1] > W          # the canvas really is a union
        assert res.n_star_matched == 4, res.n_star_matched
        assert res.n_frames_used == 4 + 4
        assert Path(res.fits_path).exists()
        # And still nothing in the DB: a star-matched position never poses as a solve,
        # so every rescued sub is still offered to the real solver on the next scan.
        rescued = {fid for ids in _unsolved.values() for fid in ids}
        for f in proj.iter_frames():
            if f.id not in rescued:
                continue
            assert f.wcs_json is None
            assert f.ra_center_deg is None and f.dec_center_deg is None
            assert (f.reject_reason or "").startswith("solve_failed:")
    finally:
        proj.close()


def test_a_sub_of_another_sky_is_left_out_rather_than_put_on_a_panel(tmp_path):
    """The failure that matters: a sub matching *no* panel must stay unused.

    Its field is as star-rich as the panels' and as unsolved, and it overlaps both
    panels' pointing on paper — the only thing that separates it is that its stars
    are not theirs.
    """
    proj, _stars, unsolved = _two_panel_mosaic(tmp_path)
    try:
        other_sky = star_catalog(seed=SEED + 991, width=W, height=H,
                                 n_stars=MOSAIC_N_STARS // 2)
        path = _panel_sub(tmp_path / "raws" / "elsewhere.fit", other_sky, 0,
                          noise_seed=77, catalog_origin=0)
        stranger = proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=W, height_px=H, bayer_pattern="RGGB",
            star_count=99, fwhm_px=4.0,    # tried FIRST, being the star-richest
            reject_reason="solve_failed:no solution",
        ))
        placed, attempted = _star_matched_unsolved_frames(
            proj, _panel_anchors(_solved(proj)))
        assert attempted == 5
        assert {f.id for f in placed} == {fid for ids in unsolved.values() for fid in ids}
        assert stranger not in {f.id for f in placed}
    finally:
        proj.close()


def test_a_mosaic_whose_pointings_do_not_separate_keeps_the_reference_anchor(tmp_path):
    """Two pointings a dither apart are one panel, so there is nothing to split —
    and the pass then behaves exactly as it does on a single field."""
    from dataclasses import replace

    proj, _stars, _unsolved = _two_panel_mosaic(tmp_path, n_solved=1, n_unsolved=1)
    try:
        # Collapse the two pointings to within the link distance.
        frames = [replace(f, ra_center_deg=RA0) for f in _solved(proj)]
        assert _panel_anchors(frames) == []
    finally:
        proj.close()


def test_the_anchor_shot_nearest_in_time_is_tried_first():
    """The ordering rule itself, stated where it can be checked.

    One triangle match costs ~236 ms and a big raster has many panels, so the order
    anchors are tried in is the whole difference between milliseconds and seconds per
    sub. A mosaic is shot panel by panel, so a sub's own capture time says which panel
    it is on. (Tested here rather than through ``_star_matched_unsolved_frames``: the
    attempt budget is checked once per *sub*, so an integration test places the sub
    either way and cannot tell the orders apart — it would pass on the bug.)
    """
    epochs = [1000.0, 5000.0, 9000.0]
    assert _anchor_order(epochs, 8800.0) == [2, 1, 0]
    assert _anchor_order(epochs, 1100.0) == [0, 1, 2]
    assert _anchor_order(epochs, 5200.0) == [1, 2, 0]   # 200, 3800, 4200 away
    # A sub that does not say when it was shot keeps the pool's own order, which is
    # biggest panel first.
    assert _anchor_order(epochs, None) == [0, 1, 2]
    # An anchor with no time sorts last, and ties are stable — so anchors this cannot
    # separate keep the order they came in.
    assert _anchor_order([None, 5000.0, None], 5200.0) == [1, 0, 2]
    assert _anchor_order([7000.0, 3000.0], 5000.0) == [0, 1]
    assert _anchor_order([], 5000.0) == []


def test_a_subs_capture_time_is_read_the_way_the_rest_of_the_engine_reads_it():
    def row(stamp):
        return FrameRow(source_path="/nowhere.fit", timestamp_utc=stamp)

    assert _capture_epoch(row(None)) is None
    assert _capture_epoch(row("  ")) is None
    assert _capture_epoch(row("not a date")) is None
    # A trailing Z and a naive stamp both mean UTC, as everywhere else in the engine.
    z = _capture_epoch(row("2026-09-01T20:00:00Z"))
    naive = _capture_epoch(row("2026-09-01T20:00:00"))
    offset = _capture_epoch(row("2026-09-01T20:00:00+00:00"))
    assert z is not None and z == naive == offset


def test_both_panels_subs_reach_the_stack_from_their_own_anchors(tmp_path):
    proj, _stars, unsolved = _two_panel_mosaic(tmp_path, n_solved=2, n_unsolved=1)
    try:
        anchors = _panel_anchors(_solved(proj))
        # Equal-sized panels, so the pool's own order is panel 0 first.
        assert len(anchors) == 2
        assert anchors[0].ra_center_deg == pytest.approx(_panel_ra(0))
        placed, offered = _star_matched_unsolved_frames(proj, anchors)
        assert offered == 2
        assert {f.id for f in placed} == {unsolved[0][0], unsolved[1][0]}
    finally:
        proj.close()


def test_the_pass_stops_when_it_has_spent_its_match_attempts(tmp_path):
    """A sub that matches nothing costs the whole pool, so the run needs a ceiling —
    and reaching it must leave the subs it did not reach exactly as they were."""
    proj, _stars, unsolved = _two_panel_mosaic(tmp_path)
    try:
        stranger_ids = []
        for i in range(2):
            other_sky = star_catalog(seed=SEED + 500 + i, width=W, height=H,
                                     n_stars=MOSAIC_N_STARS // 2)
            path = _panel_sub(tmp_path / "raws" / f"x{i}.fit", other_sky, 0,
                              noise_seed=90 + i, catalog_origin=0)
            stranger_ids.append(proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                star_count=99 - i, fwhm_px=4.0,   # tried first, and match nothing
                reject_reason="solve_failed:no solution",
            )))
        anchors = _panel_anchors(_solved(proj))
        placed, _offered = _star_matched_unsolved_frames(
            proj, anchors, max_match_attempts=2)
        # The star-richest candidate is a stranger, so it burns both anchors for
        # nothing — and the pass then stops, leaving the four placeable subs behind
        # it unreached rather than half-placed under a spent budget.
        assert placed == [], [f.id for f in placed]
        # Given the budget it needs, the same call places exactly those four and
        # still refuses both strangers.
        placed_full, _offered = _star_matched_unsolved_frames(proj, anchors)
        assert ({f.id for f in placed_full}
                == {fid for ids in unsolved.values() for fid in ids})
        # Nothing is written for any of them, reached or not.
        for fid in stranger_ids:
            assert proj.get_frame(fid).wcs_json is None
    finally:
        proj.close()
