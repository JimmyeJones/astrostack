"""
End-to-end stack pipeline test.

Builds a small project with synthesised plate-solved frames, runs the full
stacker (both no-clip and sigma-clipped paths), and verifies that the output
files exist and contain reasonable data.

This is the test that proves the headline feature works.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("photutils")
pytest.importorskip("PIL")
pytest.importorskip("tifffile")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def _build_project(tmp_path, n: int = 5, *, with_outlier: bool = False) -> Project:
    proj = Project.create(tmp_path / "p", name="stacktest")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(n):
        # All frames have the same WCS — they all land on the same canvas.
        path = write_seestar_fits(
            raws / f"f{i}.fit",
            add_wcs=True,
            seed=10 + i,
            n_stars=30,
            streak=(with_outlier and i == 0),
        )
        fid = proj.add_frame(FrameRow(
            source_path=str(path),
            cached_path=str(path),
            width_px=480, height_px=320,
            bayer_pattern="RGGB",
            wcs_json=wcs_text,
            ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    return proj


def test_stack_no_clip(tmp_path):
    proj = _build_project(tmp_path, n=4)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=False, max_workers=2, output_name="nostack"),
        )
    finally:
        proj.close()

    assert result.fits_path.exists()
    assert result.tiff_path.exists()
    assert result.preview_path.exists()
    assert result.n_frames_used == 4
    # Coverage map should reflect that every pixel has all 4 frames in the
    # interior of the canvas.
    assert result.coverage_max == 4


def test_stack_sigma_clipped(tmp_path):
    proj = _build_project(tmp_path, n=6, with_outlier=True)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=True, sigma_kappa=2.5, max_workers=2,
                         output_name="clipped"),
        )
    finally:
        proj.close()

    assert result.fits_path.exists()
    assert result.tiff_path.exists()
    assert result.preview_path.exists()
    assert result.n_frames_used == 6


def test_stack_fails_with_no_solved_frames(tmp_path):
    proj = Project.create(tmp_path / "p", name="empty")
    try:
        # add a frame with no WCS
        proj.add_frame(FrameRow(source_path="x.fit"))
        with pytest.raises(ValueError):
            run_stack(proj, StackOptions(sigma_clip=False))
    finally:
        proj.close()


def test_stack_sanitizes_path_traversal_output_name(tmp_path):
    # output_name reaches here as free-text from the web API (StackOptions
    # .output_name); a value containing a path separator must never be able
    # to write outside <project>/output/ — including via the quick-look
    # preview path (_save_quick_look), which builds its own filename from
    # options.output_name independently of write_stack_outputs.
    proj = _build_project(tmp_path, n=4)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=False, max_workers=2,
                         output_name="../../../../tmp/pwned"),
        )
    finally:
        proj.close()
    assert not (tmp_path / "tmp" / "pwned.fits").exists()
    assert result.fits_path.parent == proj.project_dir / "output"
    assert result.fits_path.exists()


@pytest.mark.parametrize("lucky_fraction", [0.0, -0.5, 1.5])
def test_stack_rejects_out_of_range_lucky_fraction(tmp_path, lucky_fraction):
    # 0 previously fell back to `max(1, ...)` and silently kept exactly one
    # frame instead of erroring; negative/>1 values were never rejected at
    # all. Fail fast before any work (canvas sizing, IO) happens.
    proj = Project.create(tmp_path / "p", name="empty")
    try:
        proj.add_frame(FrameRow(source_path="x.fit"))
        with pytest.raises(ValueError, match="lucky_fraction"):
            run_stack(proj, StackOptions(lucky_fraction=lucky_fraction))
    finally:
        proj.close()


def test_stack_drops_and_flags_bad_plate_solve_outlier(tmp_path):
    """A frame with a wildly-off WCS is dropped (not fatal) and flagged rejected.

    Regression for the "mosaic canvas would be N px, exceeding the limit" crash:
    instead of failing the whole stack, the outlier is excluded and marked
    rejected so the user can see which frame was bad.
    """
    proj = Project.create(tmp_path / "p", name="outlier")
    raws = tmp_path / "raws"
    raws.mkdir()
    good_wcs = make_synth_wcs_text(ra_center_deg=83.6, dec_center_deg=-5.4)
    bad_wcs = make_synth_wcs_text(ra_center_deg=120.0, dec_center_deg=-5.4)  # ~36° away
    bad_id = None
    try:
        for i in range(4):
            path = write_seestar_fits(raws / f"g{i}.fit", add_wcs=True, seed=10 + i, n_stars=30)
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=480, height_px=320, bayer_pattern="RGGB",
                wcs_json=good_wcs, ra_center_deg=83.6, dec_center_deg=-5.4,
            ))
        bad_path = write_seestar_fits(raws / "bad_solve.fit", add_wcs=True, seed=99, n_stars=30)
        bad_id = proj.add_frame(FrameRow(
            source_path=str(bad_path), cached_path=str(bad_path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=bad_wcs, ra_center_deg=120.0, dec_center_deg=-5.4,
        ))

        result = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, mosaic_canvas="union", output_name="o",
        ))

        # The outlier was dropped from the stack, the 4 good frames remain.
        assert result.n_frames_used == 4
        assert len(result.excluded_frames) == 1
        assert "bad_solve.fit" in result.excluded_frames[0]
        # ...and it was flagged rejected in the project DB.
        bad = proj.get_frame(bad_id)
        assert bad.accept is False
        assert "plate-solve" in (bad.reject_reason or "")
    finally:
        proj.close()


def test_stack_progress_callback_called(tmp_path):
    proj = _build_project(tmp_path, n=3)
    calls: list[tuple[str, int, int]] = []
    try:
        run_stack(
            proj,
            StackOptions(sigma_clip=False, max_workers=1, output_name="prog"),
            progress=lambda phase, done, total: calls.append((phase, done, total)),
        )
    finally:
        proj.close()
    assert len(calls) > 0
    # We should see "Stacking" phase emitted multiple times.
    assert any("Stack" in c[0] for c in calls)


def test_stack_fits_has_3_channels(tmp_path):
    from astropy.io import fits

    proj = _build_project(tmp_path, n=3)
    try:
        result = run_stack(
            proj,
            StackOptions(
                sigma_clip=False, max_workers=1,
                background_flatten=False, output_name="m",
            ),
        )
    finally:
        proj.close()

    with fits.open(result.fits_path) as hdul:
        data = hdul[0].data
        # Cube layout: (channels, H, W).
        assert data.shape[0] == 3
        finite = data[np.isfinite(data)]
        assert finite.size > 0
        # Even with bg flatten off, the post-stack coverage-leveling pass now
        # subtracts the per-coverage sky median, so the final stack lands at
        # roughly zero — we no longer expect the raw ~1000 ADU sky level.
        assert abs(float(np.median(finite))) < 200


def test_stack_with_bg_flatten_subtracts_sky(tmp_path):
    """With bg-flatten on, the stack median should be near zero, not ~1000."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=3)
    try:
        result = run_stack(
            proj,
            StackOptions(
                sigma_clip=False, max_workers=1,
                background_flatten=True, background_box_size=32,
                output_name="bgflat",
            ),
        )
    finally:
        proj.close()

    with fits.open(result.fits_path) as hdul:
        data = hdul[0].data
        finite = data[np.isfinite(data)]
        assert finite.size > 0
        # Sky was 1000 ADU before flattening; should be near zero after.
        assert abs(float(np.median(finite))) < 50
