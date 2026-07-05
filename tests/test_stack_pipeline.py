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


def test_stack_records_is_mosaic_false_for_single_field(tmp_path):
    """run_stack persists its authoritative mosaic verdict. A single-field stack
    (all frames the same pointing) is recorded is_mosaic=False, so the editor no
    longer misclassifies it as a mosaic from the uncovered reprojection border."""
    proj = _build_project(tmp_path, n=4)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     output_name="single"))
        run = next(iter(proj.iter_stack_runs()))
        assert run.is_mosaic is False
    finally:
        proj.close()


def test_restack_same_basename_keeps_old_run_pointing_at_its_own_image(tmp_path):
    """Re-stacking a target under the same basename (the Stack form's default
    ``master``) must not make the *previous* run's history row serve the new
    image. run_stack archives the old outputs and repoints the old run's row at
    them, so both runs resolve to distinct, existing files.

    Regression: before the fix, the second write archived ``master.fits`` to an
    orphan and the old run's row (still ``master.fits``) silently served the new
    pixels — History showed two runs but both resolved to the newest image.
    """
    from pathlib import Path

    proj = _build_project(tmp_path, n=4)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     output_name="master"))
        old = next(iter(proj.iter_stack_runs()))
        # Capture the original image's bytes before the re-stack moves it aside.
        old_bytes = Path(old.fits_path).read_bytes()

        # A second stack of the same target under the same default basename.
        run_stack(proj, StackOptions(sigma_clip=True, max_workers=2,
                                     output_name="master"))

        runs = list(proj.iter_stack_runs())
        assert len(runs) == 2
        new = runs[0]  # newest first
        old_after = next(r for r in runs if r.id == old.id)

        # The new run keeps the canonical master.fits; the old run's row was
        # repointed to a *different* path (this is what fails before the fix —
        # the old row would still be master.fits, i.e. == new.fits_path).
        assert new.fits_path.endswith("master.fits")
        assert old_after.fits_path != new.fits_path
        assert Path(old_after.fits_path).exists()
        assert Path(new.fits_path).exists()
        # The old run still resolves to *its own* original image, byte-for-byte —
        # not the new pixels written to master.fits.
        assert Path(old_after.fits_path).read_bytes() == old_bytes
    finally:
        proj.close()


def test_stack_records_engine_version(tmp_path):
    """run_stack stamps the run record with the app version passed by the caller,
    for provenance ("made with vX") and stale-target reprocessing. Unset
    (app_version=None) leaves it None, so direct engine callers aren't forced to
    supply one."""
    proj = _build_project(tmp_path, n=4)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     output_name="ver"), app_version="9.9.9")
        run = next(iter(proj.iter_stack_runs()))
        assert run.engine_version == "9.9.9"
    finally:
        proj.close()

    subdir = tmp_path / "b"
    subdir.mkdir()
    proj2 = _build_project(subdir, n=4)
    try:
        run_stack(proj2, StackOptions(sigma_clip=False, max_workers=2,
                                      output_name="nover"))
        run = next(iter(proj2.iter_stack_runs()))
        assert run.engine_version is None
    finally:
        proj2.close()


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
    # The finished stack's normalized background-noise σ is self-documented in
    # the header (and matches the run record), so Siril/PixInsight and the Info
    # panel can show how clean the result is.
    assert "BKGSIGMA" in hdr
    assert float(hdr["BKGSIGMA"]) >= 0.0


def test_stack_records_calibration_provenance(tmp_path):
    """A calibrated stack self-documents which masters were applied via CALSTAT.
    Bias-only (no dark) → (light − bias) / flat, recorded as 'bias+flat'."""
    from astropy.io import fits

    from seestack.calibrate.masters import MasterMeta, save_master

    # Masters must match the raw (un-debayered) frame dimensions: 480×320.
    bias = np.full((320, 480), 5.0, dtype=np.float32)
    flat = np.full((320, 480), 100.0, dtype=np.float32)  # uniform → flat_norm == 1
    save_master(tmp_path / "bias.fits", bias, MasterMeta("bias", 0, 480, 320, "median"))
    save_master(tmp_path / "flat.fits", flat, MasterMeta("flat", 5, 480, 320, "median"))

    proj = _build_project(tmp_path, n=4)
    try:
        result = run_stack(
            proj,
            StackOptions(
                sigma_clip=False, max_workers=2, output_name="calib",
                bias_path=str(tmp_path / "bias.fits"),
                flat_path=str(tmp_path / "flat.fits"),
            ),
        )
    finally:
        proj.close()

    with fits.open(result.fits_path) as hdul:
        assert hdul[0].header["CALSTAT"] == "bias+flat"

    # The same verdict is recorded in the run history (additive `calstat` column)
    # so a History/Gallery card can show a "bias+flat" chip without re-reading the
    # FITS.
    from seestack.io.project import Project

    proj2 = Project.open(tmp_path / "p")
    try:
        runs = list(proj2.iter_stack_runs())
        assert runs and runs[0].calstat == "bias+flat"
    finally:
        proj2.close()


def test_uncalibrated_stack_records_no_calstat(tmp_path):
    """A stack with no masters leaves `calstat` NULL (no calibration chip)."""
    from seestack.io.project import Project

    proj = _build_project(tmp_path, n=4)
    try:
        run_stack(
            proj,
            StackOptions(sigma_clip=False, max_workers=2, output_name="plain"),
        )
    finally:
        proj.close()

    proj2 = Project.open(tmp_path / "p")
    try:
        runs = list(proj2.iter_stack_runs())
        assert runs and runs[0].calstat is None
    finally:
        proj2.close()


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


def test_sigma_clip_stamps_rejection_fraction_provenance(tmp_path):
    """A κ-σ stack with a planted outlier (a satellite streak in one frame)
    records how much rejection actually clipped — REJMODE + a positive REJFRAC —
    so the History Info panel can show the "rejection removed ~X% of samples"
    trust line. The counter is memory-free (two scalars, no extra canvas).

    Uses ≥11 frames: κ-σ mathematically can't reject a lone outlier in a tiny
    stack (its own deviation inflates σ enough to survive — the reason min/max
    reject exists), so a 6-frame stack would legitimately clip nothing here."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=12, with_outlier=True)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=True, sigma_kappa=2.5, max_workers=2,
                         output_name="rejprov"),
        )
    finally:
        proj.close()

    hdr = fits.getheader(result.fits_path)
    assert hdr["REJMODE"] == "sigma-clip"
    assert hdr["REJNTOT"] > 0                 # samples were contributed
    assert hdr["REJNREJ"] > 0                 # the planted streak was clipped
    # Fraction is a share in [0, 1] consistent with the raw counts.
    assert 0.0 < hdr["REJFRAC"] <= 1.0
    assert abs(hdr["REJFRAC"] - hdr["REJNREJ"] / hdr["REJNTOT"]) < 1e-4


def test_non_clipped_stack_records_no_rejection_provenance(tmp_path):
    """A plain-mean stack (sigma_clip off) runs no κ-σ pass, so it must not stamp
    the rejection cards — the History line is omitted, mirroring PHOTNORM/DARKSCAL
    only appearing when the relevant pass actually ran."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=5)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=False, max_workers=2, output_name="norej"),
        )
    finally:
        proj.close()

    hdr = fits.getheader(result.fits_path)
    assert "REJMODE" not in hdr
    assert "REJFRAC" not in hdr


def test_stack_min_max_reject(tmp_path):
    """The min/max-reject path runs end to end, stamps its method into the FITS
    provenance, and produces a finite, positive result where covered."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=6, with_outlier=True)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=False, min_max_reject=True, max_workers=2,
                         output_name="minmax"),
        )
    finally:
        proj.close()

    assert result.n_frames_used == 6
    assert result.fits_path.exists()
    with fits.open(result.fits_path) as hdul:
        data = np.asarray(hdul[0].data)
        assert hdul[0].header["STACKER"] == "min-max-reject"
    assert np.isfinite(data).any()
    assert np.nanmax(data) > 0


def test_stack_min_max_reject_k3(tmp_path):
    """A top/bottom-k reject (count=3) runs end to end on a small stack and
    produces a finite, positive result — the k>1 generalisation of min/max."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=9, with_outlier=True)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=False, min_max_reject=True,
                         min_max_reject_count=3, max_workers=2, output_name="minmax3"),
        )
    finally:
        proj.close()

    assert result.n_frames_used == 9
    with fits.open(result.fits_path) as hdul:
        data = np.asarray(hdul[0].data)
        assert hdul[0].header["STACKER"] == "min-max-reject"
    assert np.isfinite(data).any()
    assert np.nanmax(data) > 0


def test_min_max_reject_takes_precedence_over_sigma_clip(tmp_path):
    """With both enabled on the standard path, min/max reject wins (it's the
    stronger order-statistic rejection), reflected in the provenance card."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=5)
    try:
        result = run_stack(
            proj,
            StackOptions(sigma_clip=True, min_max_reject=True, max_workers=1,
                         output_name="precedence"),
        )
    finally:
        proj.close()

    with fits.open(result.fits_path) as hdul:
        assert hdul[0].header["STACKER"] == "min-max-reject"


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
