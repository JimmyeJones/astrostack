"""Re-stacking a target must not silently overwrite the previous run's image.

When a stack is written under a basename that already has outputs (a re-stack of
an already-stacked target, whose form sends ``output_name="master"``), the writer
moves the previous set aside and the caller repoints the *previous* history row at
the archived files. This keeps ``master.*`` as the newest image while the old run
still resolves to *its own* image — instead of the old row silently serving the new
pixels and the true old image being orphaned (no history row references it).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits

from seestack.edit.proxy import coverage_path_for
from seestack.io.project import Project, StackRunRow
from seestack.stack.output import write_stack_outputs


def _mean(path) -> float:
    with fits.open(path) as hdul:
        return float(np.nanmean(hdul[0].data))


def _run(**over) -> StackRunRow:
    base = dict(
        id=None, timestamp_utc="2026-07-05T00:00:00Z", output_basename="master",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=1,
        canvas_h=8, canvas_w=8, coverage_min=0, coverage_max=1, options_json="{}",
    )
    base.update(over)
    return StackRunRow(**base)


def test_write_archives_existing_set_to_one_basename(tmp_path):
    """A pre-existing output set is moved aside under a single new basename, and
    the archived coverage sibling stays resolvable from the archived FITS path."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cov = np.ones((8, 8), dtype=np.float32)

    first = write_stack_outputs(project_dir=project_dir,
                                rgb=np.full((8, 8, 3), 0.1, dtype=np.float32),
                                coverage=cov, wcs_text=None)
    assert first["archived"] == {}  # nothing to archive on the first write

    second = write_stack_outputs(project_dir=project_dir,
                                 rgb=np.full((8, 8, 3), 0.9, dtype=np.float32),
                                 coverage=cov, wcs_text=None)
    archived = second["archived"]
    # The three history-recorded artefacts were archived (coverage is renamed too
    # but not returned — it's resolved from the FITS basename).
    assert set(archived) == {str(first["fits"]), str(first["tiff"]),
                             str(first["preview"])}
    for arch in archived.values():
        assert Path(arch).exists()  # the moved-aside copy is on disk
    # The original paths are reoccupied by the *new* write (that's the point).
    assert Path(str(first["fits"])).exists()
    # Canonical names hold the NEW image; the archived FITS holds the OLD one.
    assert _mean(second["fits"]) > 0.8
    assert _mean(archived[str(first["fits"])]) < 0.2
    # The archived coverage sibling matches coverage_path_for(archived fits), so a
    # repointed run can still load its coverage map.
    arch_fits = archived[str(first["fits"])]
    assert coverage_path_for(arch_fits).exists()
    # The new run's coverage stays at the canonical sibling.
    assert coverage_path_for(second["fits"]).exists()


def test_repoint_stack_runs_moves_old_row_to_archived_files(tmp_path):
    """The previous run's row is repointed at the archived files; the new run keeps
    the canonical paths. Regression: before the fix the old row kept pointing at
    ``master.fits`` and so served the new image, and the old image was orphaned."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    proj = Project.create(project_dir, name="M42")
    try:
        cov = np.ones((8, 8), dtype=np.float32)
        first = write_stack_outputs(project_dir=project_dir,
                                    rgb=np.full((8, 8, 3), 0.1, dtype=np.float32),
                                    coverage=cov, wcs_text=None)
        old_id = proj.add_stack_run(_run(
            fits_path=str(first["fits"]), tiff_path=str(first["tiff"]),
            preview_path=str(first["preview"])))

        second = write_stack_outputs(project_dir=project_dir,
                                     rgb=np.full((8, 8, 3), 0.9, dtype=np.float32),
                                     coverage=cov, wcs_text=None)
        # Repoint BEFORE recording the new run, exactly as run_stack does.
        n = proj.repoint_stack_runs(second["archived"])
        assert n == 3  # fits + tiff + preview columns of the one old row
        new_id = proj.add_stack_run(_run(
            timestamp_utc="2026-07-05T01:00:00Z",
            fits_path=str(second["fits"]), tiff_path=str(second["tiff"]),
            preview_path=str(second["preview"])))

        runs = {r.id: r for r in proj.iter_stack_runs()}
        old, new = runs[old_id], runs[new_id]
        # The two runs now point at *different, existing* FITS files.
        assert old.fits_path != new.fits_path
        assert Path(old.fits_path).exists() and Path(new.fits_path).exists()
        # And each resolves to its own image: old dark, new bright.
        assert _mean(old.fits_path) < 0.2
        assert _mean(new.fits_path) > 0.8
        # The new run keeps the canonical master.fits.
        assert new.fits_path == str(second["fits"])
        # The old run's coverage sibling is resolvable (didn't get orphaned).
        assert coverage_path_for(old.fits_path).exists()
    finally:
        proj.close()


def test_repoint_is_a_noop_when_nothing_archived(tmp_path):
    """First-ever stack archives nothing → empty map → no rows touched."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    proj = Project.create(project_dir, name="M42")
    try:
        assert proj.repoint_stack_runs({}) == 0
    finally:
        proj.close()
