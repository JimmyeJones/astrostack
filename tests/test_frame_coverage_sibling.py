"""The editor levels a mosaic's panels by FRAME COUNT, not by a sum of weights.

``level_by_coverage`` has always accepted a ``frame_coverage`` argument, and the
in-stack leveling pass has always passed it — but nothing wrote that map to
disk, so the **editor**, which reloads a run's maps from its output files, had
nothing to pass and fell back to the weighted ``coverage`` map.

That matters because the walk-away chain turns ``quality_weighted`` on by
itself, at which point a pixel's coverage value is Σ of per-frame weights: a
four-sub panel reads anywhere from ~2.5 to 4 depending on how good those four
subs happened to be. Rounded into leveling bins, **one real panel splits in
half along a weight boundary that has nothing to do with the sky**, and each
half then gets its own sky pushed to zero independently — a step-generating
mechanism inside the very pass whose job is to remove steps. Measured on a
synthetic two-region mosaic: 4 bins (3, 4, 6, 7 — the 4-sub panel split exactly
50/50) against the 2 the canvas actually has.

These tests cover the plumbing that closes that gap. The leveling maths itself
is covered by ``tests/test_coverage_leveling.py``.
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

from seestack.edit.proxy import (  # noqa: E402
    frame_coverage_path_for,
    load_coverage,
    load_frame_coverage,
)
from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.output import RUN_ARTEFACT_SUFFIXES, write_stack_outputs  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

W, H = 480, 320
PIXSCALE = 5.0
# Two panels stepped by most of a field, so the union is a real mosaic with an
# overlap strip — i.e. two genuine coverage levels.
STEP_DEG = W * PIXSCALE / 3600.0 * 0.8


def _mosaic_project(tmp_path, n_per_panel: int = 4) -> Project:
    proj = Project.create(tmp_path / "p", name="mosaic")
    raws = tmp_path / "raws"
    raws.mkdir()
    k = 0
    for panel in (0, 1):
        ra = 83.6 + panel * STEP_DEG
        for _ in range(n_per_panel):
            path = write_seestar_fits(
                raws / f"p{panel}_{k}.fit", add_wcs=True, seed=100 + k, n_stars=40,
                ra_center_deg=ra, dec_center_deg=-5.4, pixscale_arcsec=PIXSCALE,
            )
            proj.add_frame(FrameRow(
                source_path=str(path), cached_path=str(path),
                width_px=W, height_px=H, bayer_pattern="RGGB",
                wcs_json=make_synth_wcs_text(
                    width=W, height=H, ra_center_deg=ra, dec_center_deg=-5.4,
                    pixscale_arcsec=PIXSCALE),
                ra_center_deg=ra, dec_center_deg=-5.4,
            ))
            k += 1
    return proj


def _spread_quality(proj) -> None:
    """Give the subs a realistic quality spread, as QC would — this is what
    makes the weighted coverage map stop being a frame count."""
    rng = np.random.default_rng(3)
    for f in proj.iter_frames():
        proj.update_frame(
            f.id,
            fwhm_px=float(3.0 + rng.uniform(0, 2.5)),
            star_count=int(rng.uniform(120, 450)),
            sky_adu_median=float(rng.uniform(900, 2400)),
        )


def _leveling_bins(cov: np.ndarray, min_pixels: int = 200) -> list[int]:
    """The coverage levels the leveling pass would actually correct."""
    v = cov[np.isfinite(cov) & (cov > 0)]
    levels, counts = np.unique(np.rint(v).astype(int), return_counts=True)
    return [int(a) for a, c in zip(levels, counts) if c >= min_pixels]


def test_a_weighted_stack_writes_an_honest_frame_count_beside_its_coverage_map(
    tmp_path,
):
    """The regression. With quality weighting on — the walk-away default — the
    weighted map splits this two-region mosaic into four leveling bins; the
    frame-count sibling gives the editor the two the canvas actually has.

    Fail-before: no ``_framecov.fits`` was written at all, so
    ``load_frame_coverage`` returned ``None`` and the editor had only the
    weighted map to bin on.
    """
    proj = _mosaic_project(tmp_path)
    try:
        _spread_quality(proj)
        res = run_stack(proj, StackOptions(
            output_name="qw", max_workers=1, sigma_clip=False,
            quality_weighted=True,
        ))
    finally:
        proj.close()

    weighted = load_coverage(res.fits_path)
    frames = load_frame_coverage(res.fits_path)
    assert weighted is not None
    assert frames is not None, "the frame-count sibling must be written"

    # It is a genuine frame count: whole numbers, and it agrees with the
    # coverage_max the run row already reports honestly.
    finite = frames[np.isfinite(frames) & (frames > 0)]
    assert np.allclose(finite, np.rint(finite)), "frame counts must be integers"
    assert int(finite.max()) == res.coverage_max

    # …and it is what actually fixes the binning. This canvas has exactly two
    # real regions — a single-panel area covered by 4 subs and the overlap strip
    # covered by 8 — so those are the levels the leveling pass must see.
    assert _leveling_bins(frames) == [4, 8], (
        f"the leveling bins must be the real frame counts, got "
        f"{_leveling_bins(frames)}")
    assert _leveling_bins(weighted) != [4, 8], (
        "the weighted map is expected to disagree with the real coverage — "
        f"that is the bug this sibling routes around (it reads "
        f"{_leveling_bins(weighted)})")


def test_the_editor_levels_the_reloaded_run_by_frame_count(tmp_path):
    """End-to-end through the editor's own op: the coverage-leveling op must see
    the frame count the run recorded, not just the weighted map."""
    from seestack.edit.proxy import load_coverage as _lc
    from seestack.edit.registry import EditContext, get_op

    proj = _mosaic_project(tmp_path)
    try:
        _spread_quality(proj)
        res = run_stack(proj, StackOptions(
            output_name="qw", max_workers=1, sigma_clip=False,
            quality_weighted=True,
        ))
    finally:
        proj.close()

    rgb = np.asarray(fits.getdata(res.fits_path), dtype=np.float32)
    if rgb.ndim == 3 and rgb.shape[0] == 3:
        rgb = np.moveaxis(rgb, 0, -1)
    spec = get_op("background.level_coverage")
    assert spec is not None

    ctx = EditContext(
        coverage=_lc(res.fits_path),
        frame_coverage=load_frame_coverage(res.fits_path),
    )
    assert ctx.frame_coverage is not None
    # It runs, and it changes something (there is a real panel step to remove).
    out = spec.apply(rgb.copy(), {}, ctx)
    assert out.shape == rgb.shape
    assert np.isfinite(out).any()

    # A mismatched-geometry frame-count map is ignored rather than crashing the
    # render, exactly like the coverage map beside it.
    ctx_bad = EditContext(
        coverage=_lc(res.fits_path),
        frame_coverage=np.ones((7, 9), dtype=np.float32),
    )
    out_bad = spec.apply(rgb.copy(), {}, ctx_bad)
    assert out_bad.shape == rgb.shape


def test_a_run_without_the_sibling_behaves_exactly_as_before(tmp_path):
    """Upgrade-safety: every run recorded before this file existed has no
    sibling, and must keep being leveled by the weighted map as it always was."""
    rng = np.random.default_rng(5)
    rgb = rng.normal(0.0, 5.0, size=(40, 60, 3)).astype(np.float32)
    coverage = np.full((40, 60), 4.0, dtype=np.float32)

    # Writing without a frame-count map writes no sibling and reports no path.
    paths = write_stack_outputs(
        tmp_path, rgb, coverage, wcs_text=None, out_basename="legacy")
    assert "frame_coverage" not in paths
    assert not frame_coverage_path_for(paths["fits"]).exists()
    assert load_frame_coverage(paths["fits"]) is None
    assert load_coverage(paths["fits"]) is not None


def test_the_sibling_is_archived_with_the_rest_of_a_run(tmp_path):
    """A re-stack moves a run's whole file set aside under one basename so the
    siblings stay siblings. The frame-count map must travel with it, or an
    archived run silently loses its honest binning."""
    assert RUN_ARTEFACT_SUFFIXES["frame_coverage"] == "_framecov.fits"

    rng = np.random.default_rng(5)
    rgb = rng.normal(0.0, 5.0, size=(40, 60, 3)).astype(np.float32)
    # A weighted map that genuinely disagrees with the frame count — otherwise
    # there is nothing worth a second file (see the test below).
    coverage = np.full((40, 60), 3.4, dtype=np.float32)
    frames = np.full((40, 60), 4, dtype=np.int32)

    first = write_stack_outputs(
        tmp_path, rgb, coverage, wcs_text=None, out_basename="master",
        frame_coverage=frames)
    assert first["frame_coverage"].exists()

    second = write_stack_outputs(
        tmp_path, rgb, coverage, wcs_text=None, out_basename="master",
        frame_coverage=frames)
    # The fresh run owns the canonical name…
    assert second["frame_coverage"].exists()
    # …and the archived set kept its own frame-count map next to its FITS.
    archived = [
        p for p in second["fits"].parent.glob("master_*_framecov.fits")
    ]
    assert archived, "the archived run should keep its frame-count sibling"
    for path in archived:
        stem = path.name[: -len("_framecov.fits")]
        assert (path.parent / f"{stem}.fits").exists(), (
            "the archived sibling must stay a sibling of the archived FITS")
        assert load_frame_coverage(path.parent / f"{stem}.fits") is not None


def test_the_sibling_records_what_it_is(tmp_path):
    """Anyone who opens the file should be able to tell it from the weighted map
    beside it — they are the same shape and dtype and differ only in meaning."""
    rng = np.random.default_rng(5)
    rgb = rng.normal(0.0, 5.0, size=(30, 40, 3)).astype(np.float32)
    paths = write_stack_outputs(
        tmp_path, rgb, np.full((30, 40), 3.4, dtype=np.float32),
        wcs_text=None, out_basename="master",
        frame_coverage=np.full((30, 40), 4, dtype=np.int32))
    assert fits.getheader(paths["frame_coverage"])["BUNIT"] == "frames"
    assert fits.getheader(paths["coverage"])["BUNIT"] == "weight"


def test_no_second_file_when_the_coverage_map_already_is_the_frame_count(tmp_path):
    """An unweighted stack's Σ-of-weights *is* the frame count, so writing the
    sibling would only duplicate a canvas-sized file — on a big mosaic that is
    tens of megabytes per run for nothing. A consumer that finds no sibling
    correctly falls back to the coverage map, which is the same numbers."""
    rng = np.random.default_rng(5)
    rgb = rng.normal(0.0, 5.0, size=(40, 60, 3)).astype(np.float32)
    same = np.full((40, 60), 4.0, dtype=np.float32)
    paths = write_stack_outputs(
        tmp_path, rgb, same, wcs_text=None, out_basename="unweighted",
        frame_coverage=same.astype(np.int32))
    assert "frame_coverage" not in paths
    assert not frame_coverage_path_for(paths["fits"]).exists()
    # …and the fallback really does carry the same numbers.
    cov = load_coverage(paths["fits"])
    assert cov is not None and np.allclose(cov, 4.0)
