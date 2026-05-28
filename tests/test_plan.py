"""Batch plan: load/save round-trip, runner end-to-end."""

import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("scipy")

from seestack.plan import (
    IngestStep,
    Plan,
    PlanResult,
    QCStep,
    SolveStep,
    StackStep,
    run_plan,
)
from seestack.stack.stacker import StackOptions
from tests.synth import make_synth_wcs_text, write_seestar_fits


def test_plan_roundtrip(tmp_path):
    plan = Plan(
        project_dir=str(tmp_path / "proj"),
        project_name="Test",
        ingest=IngestStep(enabled=True, source_dir=str(tmp_path / "raws")),
        qc=QCStep(enabled=False),
        solve=SolveStep(enabled=True, astap_path="C:/astap/astap.exe"),
        stack=StackStep(enabled=True, options=StackOptions(
            sigma_kappa=2.8, drizzle=True, drizzle_scale=1.5, output_name="x",
        )),
    )
    path = tmp_path / "plan.seestackplan"
    plan.save(path)
    loaded = Plan.load(path)
    assert loaded.project_dir == plan.project_dir
    assert loaded.ingest.source_dir == plan.ingest.source_dir
    assert loaded.qc.enabled is False
    assert loaded.solve.astap_path == "C:/astap/astap.exe"
    assert loaded.stack.options.sigma_kappa == 2.8
    assert loaded.stack.options.drizzle is True


def test_plan_load_tolerates_unknown_keys(tmp_path):
    raw = """
{
    "project_dir": "P:/x",
    "schema_version": 99,
    "future_field": "ignore me",
    "stack": {
        "enabled": true,
        "options": {
            "sigma_kappa": 3.0,
            "future_option": "ignore me"
        }
    }
}
"""
    path = tmp_path / "future.seestackplan"
    path.write_text(raw)
    loaded = Plan.load(path)
    assert loaded.project_dir == "P:/x"
    assert loaded.stack.options.sigma_kappa == 3.0


def test_run_plan_end_to_end(tmp_path):
    """Ingest + stack only (no QC, no solve — we pre-attach WCS to frames)."""
    project_dir = tmp_path / "proj"
    raws = tmp_path / "raws"
    raws.mkdir()
    # Three FITS, each with embedded WCS (so we can skip the solve step).
    for i in range(3):
        write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, seed=10 + i, n_stars=20,
        )

    plan = Plan(
        project_dir=str(project_dir),
        project_name="autotest",
        ingest=IngestStep(enabled=True, source_dir=str(raws)),
        qc=QCStep(enabled=False),
        solve=SolveStep(enabled=False),
        stack=StackStep(enabled=True, options=StackOptions(
            sigma_clip=False, background_flatten=False, max_workers=1,
            output_name="auto",
        )),
    )

    # The stack step needs WCS in the DB. Our ingest step doesn't plate-solve,
    # so we use a custom helper: ingest, then manually attach WCS to every
    # frame from the synthetic header.
    from seestack.io.project import Project

    progress_calls: list = []
    result = run_plan(
        plan, progress=lambda p: progress_calls.append((p.step, p.sub_done, p.sub_total)),
    )
    assert "ingest" in result.steps_run

    # Now attach WCS to each frame and re-run just the stack step.
    proj = Project.open(project_dir)
    try:
        wcs_text = make_synth_wcs_text()
        for f in proj.iter_frames():
            proj.update_frame(
                f.id,
                wcs_json=wcs_text,
                ra_center_deg=83.6,
                dec_center_deg=-5.4,
            )
    finally:
        proj.close()
    # Plan: stack only.
    plan2 = Plan(
        project_dir=str(project_dir),
        ingest=IngestStep(enabled=False),
        qc=QCStep(enabled=False),
        solve=SolveStep(enabled=False),
        stack=StackStep(enabled=True, options=StackOptions(
            sigma_clip=False, background_flatten=False, max_workers=1,
            output_name="auto2",
        )),
    )
    result2 = run_plan(plan2)
    assert "stack" in result2.steps_run
    assert result2.stack_result is not None
    assert result2.stack_result.fits_path.exists()


def test_run_plan_cancels_cleanly(tmp_path):
    project_dir = tmp_path / "proj"
    plan = Plan(
        project_dir=str(project_dir),
        ingest=IngestStep(enabled=False),
        qc=QCStep(enabled=False),
        solve=SolveStep(enabled=False),
        stack=StackStep(enabled=False),
    )
    result = run_plan(plan, cancel=lambda: True)
    # No steps to run, cancelled before anything began.
    assert isinstance(result, PlanResult)
    assert not result.steps_run
