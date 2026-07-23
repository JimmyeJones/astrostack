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

from seestack.calibrate import save_master  # noqa: E402
from seestack.calibrate.masters import MasterMeta  # noqa: E402
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


def test_stack_logs_a_mismatched_dark_exposure_warning(tmp_path, caplog):
    """A master dark shot at a different exposure than the lights silently
    over/under-subtracts on the default (unscaled) path. validate() checks only
    shape, so run_stack must emit the advisory calibration warning to the log."""
    import logging

    proj = _build_project(tmp_path, n=4)
    try:
        for f in proj.iter_frames():
            proj.update_frame(f.id, exposure_s=10.0, sensor_temp_c=-10.0)
        # A shape-matching master dark (raw dims 320×480) shot at 30 s → 3× the
        # 10 s lights: passes validate() but should trip the exposure warning.
        dark = np.zeros((320, 480), dtype=np.float32)
        dark_path = tmp_path / "dark30.fits"
        save_master(dark_path, dark,
                    MasterMeta("dark", 5, 480, 320, "mean", exposure_s=30.0,
                               sensor_temp_c=-10.0))
        with caplog.at_level(logging.WARNING, logger="seestack.stack.stacker"):
            run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                         dark_path=str(dark_path),
                                         output_name="mismatch"))
        msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("Master dark is 30s but your subs are 10s" in m for m in msgs), msgs
    finally:
        proj.close()


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


def test_stack_records_rejection_tally_on_sigma_clip(tmp_path):
    """A κ-σ stack persists its outlier-rejection tally (a real fraction — 0 or
    more — and the mode), so "How's my stack?" can read what the pass did without
    a FITS read. The pass ran and saw samples, so the fraction is recorded (not
    NULL) even when it happened to clip nothing on this clean synthetic set."""
    proj = _build_project(tmp_path, n=5, with_outlier=True)
    try:
        run_stack(proj, StackOptions(sigma_clip=True, max_workers=2,
                                     output_name="clip"))
        run = next(iter(proj.iter_stack_runs()))
        assert run.rejection_mode == "sigma-clip"
        assert run.rejection_fraction is not None and run.rejection_fraction >= 0
    finally:
        proj.close()


def test_stack_records_a_positive_rejection_fraction_on_min_max(tmp_path):
    """Min/max rejection structurally drops the extreme sample at each covered
    pixel, so a ≥3-frame stack always records a positive clipped fraction and the
    min-max mode — the tally the health card softens to a no-percentage cue."""
    proj = _build_project(tmp_path, n=5)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, min_max_reject=True,
                                     max_workers=2, output_name="mmr"))
        run = next(iter(proj.iter_stack_runs()))
        assert run.rejection_mode == "min-max-reject"
        assert run.rejection_fraction is not None and run.rejection_fraction > 0
    finally:
        proj.close()


def test_stack_leaves_rejection_tally_null_for_a_plain_mean(tmp_path):
    """A plain weighted-mean stack (no rejection pass) leaves the tally NULL — no
    clean-up to claim, so the health card stays quiet about it."""
    proj = _build_project(tmp_path, n=4)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, min_max_reject=False,
                                     max_workers=2, output_name="mean"))
        run = next(iter(proj.iter_stack_runs()))
        assert run.rejection_fraction is None
        assert run.rejection_mode is None
    finally:
        proj.close()


def test_stack_reports_honest_frame_accounting_all_aligned(tmp_path):
    """run_stack reports how many subs it attempted to combine and how many
    couldn't be aligned. When every sub aligns cleanly, n_offered == frames used
    and nothing failed — the happy case the History panel stays quiet about."""
    proj = _build_project(tmp_path, n=5)
    try:
        result = run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                              output_name="allok"))
        assert result.n_offered == 5
        assert result.n_align_failed == 0
        assert result.n_frames_used == 5
        # And it self-documents in the master FITS header for a later info read.
        from astropy.io import fits
        header = fits.getheader(result.fits_path)
        assert int(header["NOFFERED"]) == 5
        assert int(header["NALIGNFL"]) == 0
    finally:
        proj.close()


def test_stack_reports_a_sub_that_could_not_be_aligned(tmp_path):
    """A sub that plate-solved to a wildly different pointing (a stray frame from
    another target, or a bad solve) reprojects entirely off the reference canvas,
    so it silently drops out of the stack. run_stack now counts it: n_offered
    includes it, n_align_failed flags it, and the header records the gap so the
    History panel can honestly say "N of M subs combined; 1 couldn't be aligned".

    Regression: before this change the drop was invisible — only n_frames_used was
    kept, so nothing told the user a sub hadn't lined up.
    """
    proj = _build_project(tmp_path, n=4)
    try:
        # Add one accepted, plate-solved frame whose WCS points far across the sky.
        stray_wcs = make_synth_wcs_text(ra_center_deg=200.0, dec_center_deg=50.0)
        raws = tmp_path / "raws"
        stray = write_seestar_fits(raws / "stray.fit", add_wcs=True, seed=99,
                                   n_stars=30)
        proj.add_frame(FrameRow(
            source_path=str(stray), cached_path=str(stray),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=stray_wcs, ra_center_deg=200.0, dec_center_deg=50.0,
        ))
        # Force the reference-frame canvas so the stray isn't folded into a union
        # mosaic (which would land it on-canvas) or dropped as a mosaic outlier —
        # it must reach the stacking pass and miss the canvas there.
        result = run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                              mosaic_canvas="reference",
                                              output_name="stray"))
        assert result.n_offered == 5
        assert result.n_align_failed == 1
        assert result.n_frames_used == 4
        from astropy.io import fits
        header = fits.getheader(result.fits_path)
        assert int(header["NOFFERED"]) == 5
        assert int(header["NALIGNFL"]) == 1
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


def test_sigma_clip_raises_when_pass2_aligns_nothing(tmp_path, monkeypatch):
    """The κ-σ two-pass path must guard an empty pass-2 result exactly like its
    sibling combine paths (min/max, pass-1, single-pass) do.

    If pass 1 aligns frames but pass 2 aligns *none* — e.g. the cached/source
    frames become unreadable between the two passes on a long run — the weighted
    sum is empty and its result is all-NaN. Before the fix the κ-σ branch did
    only ``n_used = min(n_used_p1, n_used_p2)`` with no guard, so it fell through
    and wrote a silent all-NaN master recorded as a *successful* run with
    ``n_frames_used=0`` (the exact hazard the drizzle two-pass path guards
    against). run_stack must instead raise.
    """
    import seestack.stack.stacker as st

    proj = _build_project(tmp_path, n=4)
    real_pass = st._pass

    def flaky_pass(*args, **kwargs):
        # Pass 1 runs for real (aligns the frames + fills the Welford stats);
        # pass 2 simulates every frame failing to align this time.
        if str(kwargs.get("phase_label", "")).startswith("Pass 2"):
            return 0
        return real_pass(*args, **kwargs)

    monkeypatch.setattr(st, "_pass", flaky_pass)
    try:
        with pytest.raises(ValueError, match="no usable frames"):
            run_stack(proj, StackOptions(sigma_clip=True, max_workers=2,
                                         output_name="p2empty"))
        # And nothing was recorded as a run — no all-NaN master masquerading as
        # a successful stack.
        assert list(proj.iter_stack_runs()) == []
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


def test_subpixel_reference_patch_matches_frame_alignment_domain(tmp_path, monkeypatch):
    """Regression: the sub-pixel-refine reference patch must be built in the SAME
    domain (mono / calibration) as the frames it is phase-correlated against.

    The reference patch is built by calling `align_one`, then every frame is
    `align_one`'d and cross-correlated against that patch. The reference call
    omitted `mono=`/`calibration=`, so for a mono stack the reference was
    OSC-debayered (a different luminance representation) while every frame was
    mono-luminance, and for a calibrated stack the reference was uncalibrated —
    a domain mismatch that degrades the measured sub-pixel shift. Assert the
    reference-patch call shares the per-frame calls' `mono`/`calibration`."""
    import seestack.stack.stacker as st

    real_align_one = st.align_one
    ref_call: dict = {}
    frame_call: dict = {}

    def spy(**kwargs):
        # The per-frame alignment (via _align_for_stack) passes subpixel_refine=;
        # the one setup call that builds the reference patch does not.
        if "subpixel_refine" in kwargs:
            frame_call.update(kwargs)
        else:
            ref_call.update(kwargs)
        return real_align_one(**kwargs)

    monkeypatch.setattr(st, "align_one", spy)

    proj = _build_project(tmp_path, n=3)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, subpixel_refine=True,
                                     mono=True, max_workers=1, output_name="spmono"))
    finally:
        proj.close()

    assert ref_call, "reference-patch align_one call was not made"
    assert frame_call, "per-frame align_one call was not made"
    # Same colour domain and same calibration as the frames it aligns against.
    assert ref_call["mono"] is True
    assert ref_call["mono"] == frame_call["mono"]
    assert ref_call["calibration"] == frame_call["calibration"]


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


def test_quality_weighted_coverage_reports_frame_count_not_weight_sum(tmp_path):
    """Regression: under quality weighting the accumulator's coverage map is
    Σ-of-weights, not a frame count, so the coverage_min/max diagnostics — shown
    to the user as "N frames per pixel" — used to *understate* coverage (e.g. a
    fully-covered 4-frame stack reporting max 2). They now read the unweighted
    frame count, so a pixel covered by all N frames reports N regardless of the
    weights applied."""
    proj = _build_project(tmp_path, n=4)
    try:
        # Give the frames sharply different FWHM so quality weighting pulls the
        # softer frames well below weight 1.0 (Σweights at a full-coverage pixel
        # then rounds to < 4).
        for i, f in enumerate(proj.iter_frames()):
            proj.update_frame(f.id, fwhm_px=2.0 if i == 0 else 5.0)
        result = run_stack(
            proj,
            StackOptions(quality_weighted=True, sigma_clip=True, max_workers=2,
                         output_name="qw"),
        )
        run = next(iter(proj.iter_stack_runs()))
    finally:
        proj.close()

    assert result.n_frames_used == 4
    # Every interior pixel is covered by all 4 frames → honest frame count is 4,
    # even though Σweights there is < 4. Before the fix this was < 4.
    assert result.coverage_max == 4
    assert run.coverage_max == 4


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


def test_weighting_provenance_omitted_when_min_max_reject_ignores_weights(tmp_path):
    """Regression: min/max reject combines by rank and ignores per-frame weights,
    so a stack run with both quality_weighted and min_max_reject on must NOT stamp
    WGT* provenance (which the History Info card turns into a false "N frames
    down-weighted" trust line). The κ-σ path, which DOES apply the weights in its
    weighted-sum second pass, still records it — proving the gate is specific."""
    from astropy.io import fits

    def _weighted_project(name: str):
        # Spread the frames' FWHM so quality weighting genuinely demotes some
        # subs (n_downweighted > 0) — otherwise there'd be nothing to (falsely)
        # advertise and the test couldn't tell the paths apart.
        proj = _build_project(tmp_path / name, n=5)
        for i, f in enumerate(proj.iter_frames()):
            proj.update_frame(f.id, fwhm_px=2.5 + 0.6 * i, star_count=40 - 3 * i)
        return proj

    # Both flags on → min/max path wins and ignores the weights → no WGT* cards.
    proj = _weighted_project("mmr")
    try:
        res = run_stack(proj, StackOptions(
            quality_weighted=True, min_max_reject=True, sigma_clip=False,
            max_workers=2, output_name="mmr"))
    finally:
        proj.close()
    with fits.open(res.fits_path) as hdul:
        hdr = hdul[0].header
    assert hdr["STACKER"] == "min-max-reject"
    assert "WGTMODE" not in hdr, "min/max reject ignores weights — must not claim weighting"
    assert "WGTNDOWN" not in hdr

    # Control: quality weighting on the κ-σ path DOES influence the result (pass-2
    # weighted sum), so its provenance is still honestly recorded.
    proj2 = _weighted_project("kappa")
    try:
        res2 = run_stack(proj2, StackOptions(
            quality_weighted=True, sigma_clip=True,
            max_workers=2, output_name="kappa"))
    finally:
        proj2.close()
    with fits.open(res2.fits_path) as hdul:
        hdr2 = hdul[0].header
    assert hdr2["WGTMODE"] == "quality"
    assert int(hdr2["WGTNDOWN"]) > 0


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
        hdr = hdul[0].header
        assert hdr["STACKER"] == "min-max-reject"
        # Rejection trust provenance is stamped for the min/max path too, tagged
        # with its own mode so the History line can word it as a by-design drop
        # (not a κ-σ over-clipping caution). Every covered pixel with ≥3 samples
        # drops 2, so the fraction is positive and consistent with the counts.
        assert hdr["REJMODE"] == "min-max-reject"
        assert hdr["REJNTOT"] > 0
        assert hdr["REJNREJ"] > 0
        assert 0.0 < hdr["REJFRAC"] <= 1.0
        assert abs(hdr["REJFRAC"] - hdr["REJNREJ"] / hdr["REJNTOT"]) < 1e-4
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


def test_sigma_clip_frees_pass1_accumulator_before_pass2(tmp_path, monkeypatch):
    """The κ-σ path must release its pass-1 Welford accumulator (n/mean/M2 — 3
    full-canvas arrays) *before* pass 2 allocates its weighted-sum buffers.

    If it doesn't, the live set through all of pass 2 is ~7 canvas arrays
    (wel 3 + mean 1 + std 1 + wsum ~2) instead of the 4 the pre-allocation OOM
    guard (``_PEAK_CANVAS_ARRAYS``) charges — so a large mosaic canvas the guard
    certified as safe could OOM-kill mid-stack, the exact failure the guard
    exists to prevent. We can't measure RAM directly, so we assert the
    observable consequence: when pass 2 constructs its ``WeightedSumAccumulator``,
    no ``WelfordAccumulator`` is still alive. Fails before the ``del wel`` fix
    (one Welford still live), passes after.
    """
    import gc

    from seestack.stack import accumulator as acc

    proj = _build_project(tmp_path, n=5)
    live_welfords_at_wsum_build: list[int] = []
    orig_init = acc.WeightedSumAccumulator.__init__

    def counting_init(self, *a, **k):
        orig_init(self, *a, **k)
        gc.collect()
        live_welfords_at_wsum_build.append(
            sum(1 for o in gc.get_objects()
                if isinstance(o, acc.WelfordAccumulator)))

    monkeypatch.setattr(acc.WeightedSumAccumulator, "__init__", counting_init)
    gc.collect()
    try:
        run_stack(proj, StackOptions(sigma_clip=True, max_workers=1,
                                     output_name="sigfree"))
    finally:
        proj.close()

    # The κ-σ path builds exactly one WeightedSumAccumulator — pass 2's — and it
    # must be built only after the pass-1 Welford has been freed.
    assert live_welfords_at_wsum_build, "pass 2 never built its weighted sum"
    assert live_welfords_at_wsum_build[-1] == 0


# ---- auto_reject: pick the rejection method from the frame count -----------

def test_auto_kappa_min_frames_matches_the_z_score_crossover():
    """The κ-effective threshold is the smallest n where a lone point's z-score
    against stats that include it, (n−1)/√n, first reaches κ. At κ=3 that's 11
    (10/√10 ≈ 3.16 ≥ 3, but 9/√9 = 3.0 at n=9 is <3 after the −1 term: 8/3 <3),
    and a looser κ crosses over sooner."""
    from seestack.stack.stacker import _auto_kappa_min_frames

    assert _auto_kappa_min_frames(3.0) == 11
    # Verify it's genuinely the crossover: κ-σ can catch a lone outlier at the
    # returned n but not at n-1.
    for kappa in (2.0, 2.5, 3.0, 3.5):
        n = _auto_kappa_min_frames(kappa)
        assert (n - 1) / (n ** 0.5) >= kappa
        assert (n - 2) / ((n - 1) ** 0.5) < kappa
    # Looser κ ⇒ crosses over at fewer frames; never below the min/max floor of 3.
    assert _auto_kappa_min_frames(2.0) < _auto_kappa_min_frames(3.0)
    assert _auto_kappa_min_frames(1.0) >= 3


def test_resolve_auto_reject_picks_by_frame_count():
    """auto_reject resolves to min/max on small stacks and κ-σ on large ones, and
    is a no-op when off or on the drizzle path."""
    from seestack.stack.stacker import _resolve_auto_reject

    base = StackOptions(auto_reject=True, sigma_clip=False, min_max_reject=False)
    small = _resolve_auto_reject(base, n=6)
    assert small.min_max_reject and not small.sigma_clip
    large = _resolve_auto_reject(base, n=50)
    assert large.sigma_clip and not large.min_max_reject
    # Off → returned unchanged (same object, byte-for-byte back-compat).
    off = StackOptions(auto_reject=False, sigma_clip=True, min_max_reject=False)
    assert _resolve_auto_reject(off, n=6) is off
    # Drizzle has its own rejection → auto is a no-op even when on.
    driz = StackOptions(auto_reject=True, drizzle=True)
    assert _resolve_auto_reject(driz, n=6) is driz


def test_auto_reject_small_stack_removes_a_lone_streak_via_min_max(tmp_path):
    """A 6-frame stack with a planted satellite streak: with only auto_reject on,
    the stacker picks min/max (κ-σ is mathematically blind to a lone outlier this
    small), so the streak is actually clipped — the beginner gets the right
    rejection with zero knobs. The run record keeps the user's *auto* choice."""
    import json

    from astropy.io import fits

    proj = _build_project(tmp_path, n=6, with_outlier=True)
    try:
        result = run_stack(
            proj, StackOptions(auto_reject=True, max_workers=2,
                               output_name="autosmall"),
        )
        run = next(iter(proj.iter_stack_runs()))
    finally:
        proj.close()

    hdr = fits.getheader(result.fits_path)
    assert hdr["STACKER"] == "min-max-reject"   # resolved to the order statistic
    assert hdr["REJMODE"] == "min-max-reject"
    assert hdr["REJNREJ"] > 0                    # the planted streak was clipped
    # The persisted options record the *resolved* method (so the History
    # rejection badge and any re-run match what actually ran) while keeping
    # auto_reject=True to show it was auto-picked.
    opts = json.loads(run.options_json)
    assert opts["auto_reject"] is True
    assert opts["min_max_reject"] is True and opts["sigma_clip"] is False


def test_auto_reject_large_stack_uses_sigma_clip(tmp_path):
    """A 12-frame stack: auto_reject resolves to κ-σ (large enough for it to bite,
    and it respects quality weights, unlike min/max)."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n=12, with_outlier=True)
    try:
        result = run_stack(
            proj, StackOptions(auto_reject=True, sigma_kappa=2.5, max_workers=2,
                               output_name="autolarge"),
        )
    finally:
        proj.close()

    hdr = fits.getheader(result.fits_path)
    assert hdr["STACKER"] == "sigma-clip"
    assert hdr["REJMODE"] == "sigma-clip"
    assert hdr["REJNREJ"] > 0                    # the planted streak was clipped


def test_kappa_sigma_keeps_pixel_with_no_pass1_reference():
    """Regression: the κ-σ pass-2 clip must not turn real pass-2 data into a NaN
    coverage gap at a pixel that had *no* pass-1 coverage (mean = NaN).

    Coverage can diverge between the two passes when a frame fails to align in
    pass 1 (e.g. a transient I/O error on a NAS over a thousands-of-frame run)
    but succeeds in pass 2. At a pixel only that frame covers, pass 1 leaves
    mean = std = NaN. The old inline test ``|aligned − NaN| ≤ tol`` is False, so
    the frame's genuine pass-2 value was dropped to NaN — a silent black hole in
    the final image, violating "NaN = no coverage; never turn real data into a
    gap". The mean-unknown widening keeps it; a normally-covered pixel is
    unchanged.
    """
    from seestack.stack.stacker import _kappa_sigma_keep_mask

    # pixel 0: no pass-1 coverage (mean/std NaN) but real finite pass-2 data.
    # pixel 1: normal — finite mean/σ, in-tolerance.
    # pixel 2: normal — finite mean/σ, a genuine outlier that must still clip.
    # pixel 3: pass-2 gap (aligned NaN) — stays dropped.
    aligned = np.array([7.0, 5.2, 99.0, np.nan], dtype=np.float32)
    mean_win = np.array([np.nan, 5.0, 5.0, 5.0], dtype=np.float32)
    std_win = np.array([np.nan, 1.0, 1.0, 1.0], dtype=np.float32)
    keep = _kappa_sigma_keep_mask(aligned, mean_win, std_win, kappa=3.0)
    assert bool(keep[0]) is True    # real data kept despite no pass-1 reference
    assert bool(keep[1]) is True    # in-tolerance pixel kept
    assert bool(keep[2]) is False   # real outlier still clipped
    assert bool(keep[3]) is False   # uncovered pass-2 pixel stays out


def test_kappa_sigma_keep_mask_matches_plain_clip_when_fully_covered():
    """The mean-unknown / σ-unknown widenings are no-ops on an all-finite,
    fully-covered stack: the mask is byte-for-byte the plain mean ± κ·σ test, so
    ordinary stacks are unaffected by the coverage-gap fix."""
    from seestack.stack.stacker import _kappa_sigma_keep_mask

    rng = np.random.default_rng(0)
    aligned = rng.normal(5.0, 1.0, size=(8, 8, 3)).astype(np.float32)
    mean_win = np.full((8, 8, 3), 5.0, dtype=np.float32)
    std_win = np.full((8, 8, 3), 1.0, dtype=np.float32)
    keep = _kappa_sigma_keep_mask(aligned, mean_win, std_win, kappa=3.0)
    plain = np.isfinite(aligned) & (np.abs(aligned - mean_win) <= 3.0 * std_win)
    assert np.array_equal(keep, plain)
