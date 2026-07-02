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


def test_stack_records_integration_time(tmp_path):
    """run_stack stamps the run record with the effective integration time
    (median sub exposure × frames combined), so the gallery/history can show it
    without a FITS read."""
    proj = _build_project(tmp_path, n=4)
    try:
        for f in proj.iter_frames():
            proj.update_frame(f.id, exposure_s=30.0)
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     output_name="integ"))
        run = next(iter(proj.iter_stack_runs()))
        assert run.total_exposure_s == 120.0  # 30 s × 4 frames
    finally:
        proj.close()


def test_stack_records_noise_sigma(tmp_path):
    """run_stack stamps the run record with the stacked image's normalized
    background-noise σ, so the history/gallery can flag the cleanest stack."""
    proj = _build_project(tmp_path, n=4)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     output_name="noise"))
        run = next(iter(proj.iter_stack_runs()))
        # A real stack yields a finite, non-negative normalized σ.
        assert run.noise_sigma is not None
        assert run.noise_sigma >= 0.0
    finally:
        proj.close()


def test_subpixel_refine_actually_runs(tmp_path, monkeypatch):
    """Regression: sub-pixel refine used `canvas_3` before it was defined, so it
    raised NameError that the surrounding except swallowed — silently disabling
    the feature. Verify the refinement path now executes."""
    import seestack.stack.stacker as st

    calls = {"n": 0}
    orig = st.extract_reference_patch
    monkeypatch.setattr(st, "extract_reference_patch",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), orig(*a, **k))[1])

    proj = _build_project(tmp_path, n=3)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, subpixel_refine=True,
                                     max_workers=1, output_name="sp"))
    finally:
        proj.close()
    assert calls["n"] >= 1  # was 0 before the fix


def test_output_name_is_sanitized_against_path_traversal(tmp_path):
    from seestack.stack.output import safe_basename

    assert "/" not in safe_basename("../../etc/passwd")
    assert ".." not in safe_basename("../../etc/passwd")

    proj = _build_project(tmp_path, n=2)
    try:
        out_dir = (tmp_path / "p" / "output").resolve()
        result = run_stack(proj, StackOptions(sigma_clip=False, max_workers=1,
                                              output_name="../../escape"))
        # Everything must stay inside the project's output/ dir.
        assert result.fits_path.resolve().parent == out_dir
    finally:
        proj.close()


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


def test_stack_writes_provenance_header(tmp_path):
    """The output FITS records how the stack was made (target, count, method)."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=4)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=True, max_workers=2, output_name="prov"),
        )
    finally:
        proj.close()

    with fits.open(result.fits_path) as hdul:
        hdr = hdul[0].header
    assert hdr["OBJECT"] == "stacktest"
    assert hdr["NFRAMES"] == 4
    assert hdr["STACKER"] == "sigma-clip"
    assert hdr["COLORTYP"] == "OSC"


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


def test_stack_single_frame(tmp_path):
    """One accepted frame is a valid (degenerate) stack: sigma-clip has nothing
    to clip, coverage tops out at 1, and the output is finite where covered."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=1)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=True, sigma_kappa=2.5, max_workers=1,
                         output_name="single"),
        )
    finally:
        proj.close()

    assert result.n_frames_used == 1
    assert result.coverage_max == 1
    assert result.fits_path.exists()
    with fits.open(result.fits_path) as hdul:
        data = np.asarray(hdul[0].data)
    # The covered interior must be real signal, not NaN/zero everywhere.
    assert np.isfinite(data).any()
    assert np.nanmax(data) > 0


def test_stack_all_rejected_raises(tmp_path):
    """If the user rejects every frame, stacking fails cleanly rather than
    producing an empty/garbage result."""
    proj = _build_project(tmp_path, n=4)
    try:
        for f in proj.iter_frames():
            proj.update_frame(f.id, accept=False)
        with pytest.raises(ValueError):
            run_stack(proj, StackOptions(sigma_clip=False, output_name="none"))
    finally:
        proj.close()


def test_stack_drizzle_vs_sigma_clip_parity(tmp_path):
    """Drizzle and sigma-clip are two paths to the same scene: both must produce
    a finite, positive, non-degenerate result. At ``scale=1, pixfrac=1`` drizzle
    conserves surface brightness, so the two paths' median levels must agree
    closely (not merely to an order of magnitude).

    Regression guard for the drizzle flux-scale bug: ``result()`` used to divide
    the already-averaged ``out_img`` by ``out_wht`` again, deflating drizzle's
    brightness by ~N (the frame count). Here N=5, so the old code produced a
    ~5× mismatch; the tight bound below would catch any such re-normalisation.
    """
    from astropy.io import fits

    proj = _build_project(tmp_path, n=5)
    try:
        clip = run_stack(
            proj,
            StackOptions(sigma_clip=True, background_flatten=False,
                         max_workers=2, output_name="parity_clip"),
        )
        driz = run_stack(
            proj,
            StackOptions(drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
                         background_flatten=False, max_workers=2,
                         output_name="parity_driz"),
        )
    finally:
        proj.close()

    with fits.open(clip.fits_path) as hdul:
        a = np.asarray(hdul[0].data, dtype=np.float64)
    with fits.open(driz.fits_path) as hdul:
        b = np.asarray(hdul[0].data, dtype=np.float64)

    # Both paths must yield real, positive signal (not all-zero / all-NaN).
    assert np.isfinite(a).any() and np.isfinite(b).any()
    med_a = float(np.nanmedian(a[np.isfinite(a) & (a > 0)]))
    med_b = float(np.nanmedian(b[np.isfinite(b) & (b > 0)]))
    assert med_a > 0 and med_b > 0
    # Surface brightness is conserved: the two medians must agree to well within
    # a factor of 2 (they differ only by drizzle's kernel/interpolation vs the
    # weighted mean, not by any N-frame scale factor).
    ratio = med_a / med_b
    assert 0.5 < ratio < 2.0, f"brightness mismatch: clip={med_a} driz={med_b}"


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
