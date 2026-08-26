"""A mosaic gain-matches its panels by itself.

A mosaic's panels are shot at different times through different air, so one
panel can easily be recorded through haze while its neighbour was clear. The
corrections that already run automatically on the mosaic path only touch the
**sky**: the per-frame background flatten removes each frame's additive sky
offset, and the coverage-leveling pass removes the panel-to-panel sky step.
Haze dims the *signal* multiplicatively, which leaves the sky alone and
survives both — so the finished picture has one panel's stars and nebulosity
visibly fainter than the next panel's, with a step along the join.

``photometric_normalize`` is exactly the correction for that, but it was
off-by-default and nothing on the walk-away chain ever turned it on. It is now
auto-enabled for a mosaic canvas, the same way (and for the same reason) the
final-stack gradient pass already is.

**The measurement that matters is signal continuity across the join, NOT the
seam residual** — ``SEAMRES`` measures a *sky* step between coverage levels, and
multiplicative dimming doesn't move the sky, so it reads ~0 either way. These
tests measure the star flux of one panel against the other.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("photutils")
pytest.importorskip("PIL")
pytest.importorskip("tifffile")

from astropy.io import fits  # noqa: E402

from seestack.edit.proxy import load_frame_coverage  # noqa: E402
from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.photometric import PhotometricStats  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

W, H = 480, 320
PIXSCALE = 5.0
# Two panels stepped by most of a field, so the union is a real mosaic with an
# overlap strip — the same geometry tests/test_frame_coverage_sibling.py uses.
STEP_DEG = W * PIXSCALE / 3600.0 * 0.8
SKY = 1000.0
# How much of the second panel's signal the haze ate. With four clear and four
# hazy subs the run's median transparency sits half way between, so the clear
# frames scale to 0.75× and the hazy ones to 1.5× — both well inside the 2×
# clamp, i.e. a correction the op can actually finish.
HAZE = 0.5


def _dim_signal(path, factor: float) -> None:
    """Dim a written sub's *signal* multiplicatively, leaving its sky where it
    is — what thin haze/cloud actually does to a recorded frame (and what the
    additive per-frame background flatten therefore cannot undo)."""
    with fits.open(path, mode="update") as hdul:
        data = np.asarray(hdul[0].data, dtype=np.float64)
        hdul[0].data = np.clip(
            SKY + (data - SKY) * factor, 0, 65535).astype(np.uint16)


def _hazy_mosaic_project(tmp_path, n_per_panel: int = 4, *, haze: float = HAZE,
                         score: bool = True) -> Project:
    """Two panels of identical synthetic sky — the second one shot through haze.

    Both panels use the *same* per-sub star seeds, so the two halves of the
    canvas carry the same star field and their brightness can be compared
    directly: any step between them is photometric mismatch, not a different
    patch of sky.
    """
    proj = Project.create(tmp_path / "p", name="hazy-mosaic")
    raws = tmp_path / "raws"
    raws.mkdir()
    for panel in (0, 1):
        ra = 83.6 + panel * STEP_DEG
        for j in range(n_per_panel):
            path = write_seestar_fits(
                raws / f"p{panel}_{j}.fit", add_wcs=True, seed=100 + j,
                n_stars=40, ra_center_deg=ra, dec_center_deg=-5.4,
                pixscale_arcsec=PIXSCALE,
            )
            if panel == 1:
                _dim_signal(path, haze)
            fid = proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(
                    width=W, height=H, ra_center_deg=ra, dec_center_deg=-5.4,
                    pixscale_arcsec=PIXSCALE),
                ra_center_deg=ra, dec_center_deg=-5.4,
            ))
            if score:
                # What QC measures: the median flux of the frame's brightest
                # stars, so the hazy panel's subs score proportionally lower.
                proj.update_frame(
                    fid, transparency_score=5000.0 * (haze if panel == 1 else 1.0))
    return proj


def _panel_masks(fits_path) -> tuple[np.ndarray, np.ndarray]:
    """Left-panel-only and right-panel-only pixel masks of a two-panel canvas.

    Single-coverage pixels belong to exactly one panel; the overlap strip (twice
    the coverage) is excluded, since it is a blend of both and would dilute the
    very step being measured.
    """
    cov = load_frame_coverage(fits_path)
    if cov is None:
        cov = np.asarray(fits.getdata(
            str(fits_path).replace(".fits", "_coverage.fits")), dtype=np.float32)
    if cov.ndim == 3:
        cov = np.nanmax(cov, axis=0 if cov.shape[0] <= 4 else -1)
    single = np.isfinite(cov) & (np.rint(cov) == np.rint(np.nanmin(
        cov[np.isfinite(cov) & (cov > 0)])))
    xs = np.where(single.any(axis=0))[0]
    mid = int((xs.min() + xs.max()) / 2)
    cols = np.zeros_like(single)
    cols[:, :mid] = True
    return single & cols, single & ~cols


def _star_flux(data: np.ndarray, mask: np.ndarray) -> float:
    """Mean star-core brightness inside a region, above its own sky."""
    lum = np.nanmean(data, axis=0) if data.ndim == 3 else data
    vals = lum[mask & np.isfinite(lum)]
    assert vals.size > 1000, "region too small to measure"
    sky = float(np.median(vals))
    cores = vals[vals >= np.percentile(vals, 99.8)]
    return float(np.mean(cores) - sky)


def _panel_step(fits_path) -> float:
    """Fractional star-flux mismatch between the two panels (0 = seamless)."""
    left_mask, right_mask = _panel_masks(fits_path)
    data = np.asarray(fits.getdata(fits_path), dtype=np.float64)
    a, b = _star_flux(data, left_mask), _star_flux(data, right_mask)
    return abs(a - b) / max(abs(a), abs(b))


def _neutral_scales(monkeypatch) -> None:
    """Pin the *old* behaviour — no gain-matching at all — so a before/after can
    be measured on one build without weakening anything in the shipped path."""
    def _none(frames, **_kw):
        return ({f.id: 1.0 for f in frames if f.id is not None},
                PhotometricStats(0, len(frames), 0, 1.0, 1.0, 1.0))
    monkeypatch.setattr(
        "seestack.stack.stacker.compute_photometric_scales", _none)


def test_a_hazy_mosaic_panel_is_gain_matched_to_its_neighbour(tmp_path, monkeypatch):
    """The measurement. One panel shot at half transparency comes out roughly as
    bright as the clear one — where before it stayed visibly fainter.

    Fail-before: ``photometric_normalize`` defaulted off and nothing turned it on
    for a mosaic, so the hazy panel kept its ~50% deficit.
    """
    proj = _hazy_mosaic_project(tmp_path)
    try:
        after = run_stack(proj, StackOptions(
            output_name="after", max_workers=1, sigma_clip=False))
        _neutral_scales(monkeypatch)
        before = run_stack(proj, StackOptions(
            output_name="before", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    step_before = _panel_step(before.fits_path)
    step_after = _panel_step(after.fits_path)
    assert step_before > 0.25, (
        f"the fixture must actually have a hazy panel (step {step_before:.1%})")
    assert step_after < 0.10, (
        f"the hazy panel should be gain-matched to within a few percent, "
        f"got {step_after:.1%} (was {step_before:.1%})")
    assert step_after < step_before / 3


def test_a_mosaic_records_that_it_normalized_itself(tmp_path):
    """Provenance: the run says it gain-matched, and that *it* chose to — the
    user never ticked a box, so the History panel must be able to say why."""
    proj = _hazy_mosaic_project(tmp_path)
    try:
        res = run_stack(proj, StackOptions(
            output_name="auto", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    hdr = fits.getheader(res.fits_path)
    assert hdr["PHOTNORM"] == "transparency"
    assert bool(hdr["PHOTAUTO"]) is True
    assert int(hdr["PHOTNADJ"]) == 8


def test_an_explicit_normalize_is_still_recorded_as_the_users_choice(tmp_path):
    """…and when the user *did* ask for it, the run doesn't claim otherwise."""
    proj = _hazy_mosaic_project(tmp_path)
    try:
        res = run_stack(proj, StackOptions(
            output_name="explicit", max_workers=1, sigma_clip=False,
            photometric_normalize=True))
    finally:
        proj.close()

    hdr = fits.getheader(res.fits_path)
    assert hdr["PHOTNORM"] == "transparency"
    assert bool(hdr["PHOTAUTO"]) is False


def test_a_mosaic_whose_subs_have_no_transparency_score_is_unchanged(tmp_path):
    """The no-data path stays byte-for-byte what it was: with nothing to measure
    the op self-neutralises, and the run must not claim it normalized anything."""
    proj = _hazy_mosaic_project(tmp_path, score=False)
    try:
        res = run_stack(proj, StackOptions(
            output_name="noscore", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    hdr = fits.getheader(res.fits_path)
    assert "PHOTNORM" not in hdr
    assert "PHOTAUTO" not in hdr


def test_a_single_field_stack_is_left_alone(tmp_path):
    """Not a mosaic → not automatic. A one-pointing target with a hazy night in
    it keeps today's exact behaviour (the user can still opt in per stack)."""
    proj = Project.create(tmp_path / "p", name="single")
    raws = tmp_path / "raws"
    raws.mkdir()
    try:
        for j in range(4):
            path = write_seestar_fits(
                raws / f"f{j}.fit", add_wcs=True, seed=100 + j, n_stars=40,
                pixscale_arcsec=PIXSCALE)
            if j == 3:
                _dim_signal(path, HAZE)
            fid = proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(
                    width=W, height=H, pixscale_arcsec=PIXSCALE),
                ra_center_deg=83.6, dec_center_deg=-5.4,
            ))
            proj.update_frame(
                fid, transparency_score=5000.0 * (HAZE if j == 3 else 1.0))
        res = run_stack(proj, StackOptions(
            output_name="single", max_workers=1, sigma_clip=False))
    finally:
        proj.close()

    assert "PHOTNORM" not in fits.getheader(res.fits_path)


def test_the_panel_bins_do_not_move_when_the_scaling_is_on(tmp_path, monkeypatch):
    """The prerequisite this change waited on (v0.270.4). Gain-matching makes a
    pixel's *weighted* coverage Σ(w/s²), which would scramble the sky-leveling
    pass's panel bins if it still binned on that map. It bins on the honest
    frame count instead, so the bins must be identical either way."""
    proj = _hazy_mosaic_project(tmp_path)
    try:
        after = run_stack(proj, StackOptions(
            output_name="after", max_workers=1, sigma_clip=False,
            quality_weighted=True))
        _neutral_scales(monkeypatch)
        before = run_stack(proj, StackOptions(
            output_name="before", max_workers=1, sigma_clip=False,
            quality_weighted=True))
    finally:
        proj.close()

    def bins(path) -> list[int]:
        cov = load_frame_coverage(path)
        assert cov is not None
        v = cov[np.isfinite(cov) & (cov > 0)]
        levels, counts = np.unique(np.rint(v).astype(int), return_counts=True)
        return [int(a) for a, c in zip(levels, counts) if c >= 200]

    assert bins(after.fits_path) == [4, 8]
    assert bins(before.fits_path) == bins(after.fits_path)
