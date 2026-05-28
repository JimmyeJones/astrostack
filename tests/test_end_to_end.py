"""
End-to-end: create a project, ingest synthetic frames, run the QC entry point
serially (not via Qt — we test the same function the JobRunner submits), and
confirm everything lands in the DB and the table model.

This is the most integration-y test we have and it's worth its weight: it
exercises the full ingest → cache → metrics → DB → model path on real FITS.
"""

import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("PIL")
pytest.importorskip("PySide6")

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from seestack.core.cache import CacheManager  # noqa: E402
from seestack.core.jobs import run_serial  # noqa: E402
from seestack.gui.frame_table import FrameTableModel  # noqa: E402
from seestack.io.ingest import ingest_files  # noqa: E402
from seestack.io.project import Project  # noqa: E402
from seestack.qc.runner import (  # noqa: E402
    apply_qc_result_to_db,
    build_qc_arglist,
    compute_for_db_row,
)
from tests.synth import write_seestar_fits  # noqa: E402

# QApplication needs to exist before any Qt model is constructed.
_app = QApplication.instance() or QApplication([])


def test_end_to_end(tmp_path):
    raws = tmp_path / "raws"
    raws.mkdir()
    paths = [
        write_seestar_fits(raws / "f0.fit", seed=1, n_stars=50),
        write_seestar_fits(raws / "f1.fit", seed=2, n_stars=50),
        write_seestar_fits(raws / "f2.fit", seed=3, n_stars=50, streak=True),
    ]

    proj = Project.create(tmp_path / "proj", name="e2e")
    cache = CacheManager(proj.project_dir)

    # Ingest
    results = list(ingest_files(proj, cache, paths))
    assert len(results) == 3
    assert all(r.frame_id is not None for r in results)
    assert all(r.cached_path and r.cached_path.exists() for r in results)

    # Frame table model picks up everything from the project
    model = FrameTableModel(proj)
    assert model.rowCount() == 3

    # Run QC serially — same function the JobRunner submits, just on this thread
    args = build_qc_arglist(proj)
    assert len(args) == 3
    qc_results = run_serial(compute_for_db_row, args)
    assert all(r.error is None for r in qc_results)

    # Apply results to the project DB and the model
    for jr in qc_results:
        result = jr.value
        apply_qc_result_to_db(proj, result)
        if result.metrics is not None:
            m = result.metrics
            model.update_frame(
                result.frame_id,
                fwhm_px=m.fwhm_px,
                star_count=m.star_count,
                sky_adu_median=m.sky_adu_median,
                eccentricity_median=m.eccentricity_median,
                streak_detected=m.streak_detected,
                streak_count=m.streak_count,
            )

    # Verify metrics actually populated
    rows = list(proj.iter_frames())
    for r in rows:
        assert r.star_count is not None and r.star_count > 0
        assert r.sky_adu_median is not None
        assert r.fwhm_px is not None

    # The streak frame should be auto-rejected
    streak_row = next(r for r in rows if r.source_path.endswith("f2.fit"))
    assert streak_row.streak_detected is True
    assert streak_row.accept is False
    assert streak_row.reject_reason == "auto:streak"

    # The clean frames should still be accepted
    clean_rows = [r for r in rows if not r.source_path.endswith("f2.fit")]
    for r in clean_rows:
        assert r.accept is True

    proj.close()
