"""A typed *Output name* never becomes a path outside the run's own folder.

An editor export stores what the user typed in *Output name* as the run's
``output_basename`` verbatim (only the files it writes are sanitised, by
``safe_basename``). The zoom-clip and the deepening-reel caches then named their
files ``out_dir / f"{run.output_basename}…"`` — so "M42/final" made the zoom
clip 500 (no such directory) and "../x" wrote, and on a rebuild unlinked, files
one folder *above* the target's ``output/``. Every artefact path is now built
from ``safe_basename`` of the column, the same stem the export's own files use.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "_export_wcs_helpers", Path(__file__).with_name("test_editor_export_wcs.py"))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
_make_solved_run, _wait_job = _helpers._make_solved_run, _helpers._wait_job


def _export(client, solved_library, typed: str) -> tuple[str, int, Path]:
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid, src_fits = _make_solved_run(solved_library, safe)
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": {"ops": [{"id": "stretch.stf", "params": {}}]},
                          "output_name": typed})
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    new_id = job["result"]["run_id"]
    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    row = next(x for x in runs if x["id"] == new_id)
    assert row["output_basename"] == typed  # the column keeps what was typed
    out_dir = Path(src_fits).parent  # the target's output/, where the export wrote
    return safe, new_id, out_dir


def _files_under(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("typed", ["M42/final", "../escape", "Orion – final"])
def test_zoom_clip_of_an_export_with_a_typed_name_stays_in_its_folder(
        client, solved_library, typed):
    safe, new_id, out_dir = _export(client, solved_library, typed)
    above = out_dir.parent
    before = _files_under(above)

    resp = client.get(f"/api/targets/{safe}/stack-runs/{new_id}/zoom-clip")
    assert resp.status_code == 200, resp.text[:300]

    made = _files_under(above) - before
    assert made, "the clip was not cached anywhere"
    assert all(p.parent == out_dir for p in made), sorted(map(str, made))
    # Named on the export's own (sanitised) stem, beside its FITS.
    from seestack.stack.output import safe_basename
    assert all(p.name.startswith(safe_basename(typed) + "_zoom") for p in made)


def test_the_zoom_clip_of_a_typed_name_export_goes_with_its_run(client, solved_library):
    """Delete resolves a run's cached siblings from its FITS stem; a clip named on
    the raw column ("Orion – final_zoom.webp" beside "Orion_final.fits") was a
    file no delete ever reclaimed."""
    safe, new_id, out_dir = _export(client, solved_library, "Orion – final")
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{new_id}/zoom-clip").status_code == 200
    assert list(out_dir.glob("*_zoom.*"))

    assert client.delete(
        f"/api/targets/{safe}/stack-runs/{new_id}").status_code in (200, 204)
    assert list(out_dir.glob("*_zoom.*")) == []


class _Row:
    def __init__(self, fits_path=None, preview_path=None, output_basename=""):
        self.fits_path, self.preview_path = fits_path, preview_path
        self.output_basename = output_basename


@pytest.mark.parametrize("row, stem", [
    # The recorded master names the set — including an archived older run's.
    (_Row("/o/M_42_20261101T010203.fits", "/o/M_42_20261101T010203_preview.png",
          "M_42"), "M_42_20261101T010203"),
    (_Row(None, "/o/Orion_final_preview.png", "Orion – final"), "Orion_final"),
    (_Row(None, None, "../../escape"), "escape"),
    (_Row(None, None, ""), "master"),
])
def test_run_artefact_stem_never_comes_from_the_raw_column(row, stem):
    from webapp.routers.stack import _run_artefact_stem

    assert _run_artefact_stem(row) == stem
    assert "/" not in stem and ".." not in stem
