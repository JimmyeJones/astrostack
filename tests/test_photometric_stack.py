"""End-to-end: photometric normalization inside run_stack.

Proves the per-frame multiplicative scale actually reaches the accumulated
pixels (a dim, low-transparency frame is gain-matched *up*, brightening its
contribution), that the run self-documents via the PHOTNORM FITS provenance,
and that the feature is genuinely off by default (opt-in, upgrade-safe).
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
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def _build_project(tmp_path, n: int = 4) -> Project:
    proj = Project.create(tmp_path / "p", name="phot")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(n):
        path = write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, seed=10 + i, n_stars=30,
        )
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    return proj


def _bright_level(data: np.ndarray) -> float:
    """Mean of the brightest star pixels — a stable probe of signal amplitude
    that averages out per-frame noise (unlike a single ``nanmax``)."""
    finite = data[np.isfinite(data)]
    hi = np.percentile(finite, 99.9)
    return float(np.mean(finite[finite >= hi]))


def test_photometric_normalize_brightens_a_dim_frame_and_records_provenance(tmp_path):
    # Four frames of the same scene; three at the median transparency and one a
    # quarter as transparent (a hazy sub). Normalization scales the hazy frame's
    # signal up (clamped to 2×) toward the median, so the combined star flux is
    # measurably higher than the plain (un-normalized) mean of the same frames.
    proj = _build_project(tmp_path, n=4)
    try:
        ids = [f.id for f in proj.iter_frames()]
        for fid in ids[:3]:
            proj.update_frame(fid, transparency_score=5000.0)
        proj.update_frame(ids[3], transparency_score=1250.0)  # hazy → wants 4×, clamped to 2×

        base = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="base",
            photometric_normalize=False,
        ))
        norm = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="norm",
            photometric_normalize=True,
        ))
    finally:
        proj.close()

    with fits.open(base.fits_path) as hdul:
        base_data = np.asarray(hdul[0].data, dtype=np.float64)
        base_hdr = hdul[0].header
    with fits.open(norm.fits_path) as hdul:
        norm_data = np.asarray(hdul[0].data, dtype=np.float64)
        norm_hdr = hdul[0].header

    # The hazy frame, boosted ~2×, lifts the combined bright-star level. With one
    # of four frames doubled the mean rises ~25%; require a clear margin.
    assert _bright_level(norm_data) > _bright_level(base_data) * 1.1

    # The normalized run self-documents; the plain run carries no PHOTNORM keys.
    assert norm_hdr["PHOTNORM"] == "transparency"
    assert norm_hdr["PHOTNADJ"] == 1          # exactly the one hazy frame moved
    assert float(norm_hdr["PHOTMAX"]) == 2.0  # clamped boost
    assert "PHOTNORM" not in base_hdr


def _coverage_max(fits_path) -> float:
    """Peak per-pixel coverage (Σ of the combine weights) from the run's
    ``*_coverage.fits`` sidecar."""
    from pathlib import Path
    cov_path = Path(fits_path).with_name(Path(fits_path).stem + "_coverage.fits")
    with fits.open(cov_path) as hdul:
        return float(np.nanmax(np.asarray(hdul[0].data, dtype=np.float64)))


def test_photometric_scale_downweights_the_amplified_frame_in_the_combine(tmp_path):
    # Inverse-variance combine: a hazy frame gain-matched ×2 has its noise
    # amplified ×2, so the weighted-sum combine must down-weight it by 1/s² = 1/4.
    # The accumulator's coverage map is Σ of the per-frame combine weights, so a
    # fully-covered pixel reads 3·1 + 1·0.25 = 3.25 with normalization on vs 4.0
    # off — a direct, deterministic proof the 1/s² reaches the accumulator (not
    # just the pixels). Quality weighting stays off so every base weight is 1.0.
    proj = _build_project(tmp_path, n=4)
    try:
        ids = [f.id for f in proj.iter_frames()]
        for fid in ids[:3]:
            proj.update_frame(fid, transparency_score=5000.0)
        proj.update_frame(ids[3], transparency_score=1250.0)  # → scale clamped to 2×

        base = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="cov_base",
            photometric_normalize=False))
        norm = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="cov_norm",
            photometric_normalize=True))
    finally:
        proj.close()

    # Off: all four frames at weight 1 → peak coverage is the frame count, 4.
    assert _coverage_max(base.fits_path) == pytest.approx(4.0, abs=0.02)
    # On: the ×2 frame contributes 1/4, so peak coverage drops to 3.25 — proof
    # the amplified frame is trusted less in the combine, not at full weight.
    assert _coverage_max(norm.fits_path) == pytest.approx(3.25, abs=0.02)


def test_photometric_normalize_off_by_default(tmp_path):
    # The default StackOptions must not normalize — no PHOTNORM provenance, so an
    # existing live install's stacks are byte-for-byte unaffected until opted in.
    proj = _build_project(tmp_path, n=4)
    try:
        for f in proj.iter_frames():
            proj.update_frame(f.id, transparency_score=3000.0)
        result = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="default"))
    finally:
        proj.close()

    assert StackOptions().photometric_normalize is False
    with fits.open(result.fits_path) as hdul:
        assert "PHOTNORM" not in hdul[0].header


def test_photometric_normalize_runs_on_the_drizzle_path(tmp_path):
    # The scale is applied in the drizzle prepare() worker too; verify that path
    # runs end to end and records PHOTNORM (a separate injection point from the
    # standard reproject pass).
    proj = _build_project(tmp_path, n=4)
    try:
        ids = [f.id for f in proj.iter_frames()]
        for fid in ids[:3]:
            proj.update_frame(fid, transparency_score=5000.0)
        proj.update_frame(ids[3], transparency_score=1250.0)
        result = run_stack(proj, StackOptions(
            drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
            max_workers=2, output_name="driz", photometric_normalize=True))
    finally:
        proj.close()

    assert result.n_frames_used == 4
    with fits.open(result.fits_path) as hdul:
        assert hdul[0].header["PHOTNORM"] == "transparency"


def test_photometric_normalize_neutral_when_no_transparency(tmp_path):
    # Enabled but no frame carries a transparency score → fully neutral: the run
    # still succeeds and records no PHOTNORM keys (nothing was actually scaled).
    proj = _build_project(tmp_path, n=4)
    try:
        result = run_stack(proj, StackOptions(
            sigma_clip=False, max_workers=2, output_name="neutral",
            photometric_normalize=True))
    finally:
        proj.close()

    assert result.n_frames_used == 4
    with fits.open(result.fits_path) as hdul:
        assert "PHOTNORM" not in hdul[0].header
