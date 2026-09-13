"""An editor export keeps how long the picture was exposed for.

The sibling of ``test_editor_export_wcs.py``: that one found the export dropping
the picture's *place in the sky*, this one found it dropping the picture's
*light*. ``_apply_editor_to_run`` recorded its new ``stack_runs`` row with
``total_exposure_s``, ``calstat`` and ``transparency_ratio`` left at their
``None`` defaults, even though an export re-renders pixels a stack already
combined and collects no photons of its own. So the moment a user finished an
edit — the picture they actually share and pin as a cover — its Gallery and
History cards stopped naming any integration time, and "My best pictures" scored
it over two of the four metrics its blend has (``seestack.portfolio._score``
renormalises over the figures an entry carries, so a missing one is a quietly
lower placing).

The other half of these tests is the list the export must *not* inherit: the
figures measured on the pixels, which an edit changes. ``is_mosaic`` is the one
with teeth — it is read behaviourally by ``editor._run_is_mosaic``, which falls
back to the coverage map only while the column is NULL, so stamping it would
make re-opening an edit trim a border off a picture Auto has already trimmed.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow

H, W = 160, 240

# What the source stack recorded. Deliberately a *mosaic* run with real
# calibration and a measured noise/sharpness, because that is the shape where
# every column below differs from its default.
SRC = dict(
    total_exposure_s=5400.0,
    calstat="dark+flat",
    transparency_ratio=0.91,
    is_mosaic=True,
    noise_sigma=0.0041,
    stack_fwhm_px=2.2,
)


def _wait_job(client, job_id, timeout=120.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "error", "cancelled", "interrupted"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish in time")


def _make_source_run(data_root, safe: str) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            outdir = Path(proj.project_dir) / "output"
            outdir.mkdir(parents=True, exist_ok=True)
            fp = outdir / "deepstack.fits"
            rng = np.random.default_rng(0)
            fits.writeto(fp, (rng.random((3, H, W)) * 0.1).astype("float32"),
                         overwrite=True)
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="deepstack", fits_path=str(fp), tiff_path=None,
                preview_path=None, n_frames_used=180,
                canvas_h=H, canvas_w=W, coverage_min=1, coverage_max=180,
                options_json="{}",
                capture_start_utc="2024-11-15T22:00:00Z",
                capture_end_utc="2024-11-15T23:30:00Z",
                **SRC,
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _export(client, data_root, safe: str, run_id: int, name: str):
    r = client.post(
        f"/api/targets/{safe}/stack-runs/{run_id}/editor/export",
        json={"recipe": {"ops": [{"id": "tone.stretch", "params": {}}]},
              "output_name": name})
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    new_id = job["result"]["run_id"]
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(x for x in proj.iter_stack_runs() if x.id == new_id)
        finally:
            proj.close()
    finally:
        lib.close()


def test_an_export_keeps_the_exposure_and_calibration_of_the_light(
    client, solved_library,
):
    """The regression. Same subs, same nights, same darks and flats — so the
    edited picture has to be able to say so."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_source_run(solved_library, safe)

    edited = _export(client, solved_library, safe, rid, "light_edit")

    assert edited.total_exposure_s == SRC["total_exposure_s"]
    assert edited.calstat == SRC["calstat"]
    assert edited.transparency_ratio == SRC["transparency_ratio"]
    # The two that were already right, re-pinned here so a change to this block
    # can't quietly drop one while adding the three above.
    assert edited.n_frames_used == 180
    assert edited.capture_start_utc == "2024-11-15T22:00:00Z"


def test_an_export_claims_no_measurement_of_its_own_pixels(client, solved_library):
    """The other half of the rule: an edit moves the grain and the stars, so the
    export must not inherit a σ or an FWHM measured on the picture *before* it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_source_run(solved_library, safe)

    edited = _export(client, solved_library, safe, rid, "measure_edit")

    assert edited.noise_sigma is None
    assert edited.stack_fwhm_px is None
    # `is_mosaic` is the behavioural one — see below.
    assert edited.is_mosaic is None


def test_a_re_edit_of_an_export_is_not_treated_as_a_mosaic(client, solved_library):
    """Why ``is_mosaic`` stays NULL, stated as behaviour rather than as a column.

    ``editor._run_is_mosaic`` trusts the stamped flag when it is set and only
    then falls back to the coverage map. An export's coverage is uniform, so the
    fallback correctly answers "no" — but a flag inherited from the mosaic it
    came from would answer "yes" and hand the re-edit a border trim for a picture
    that has already been trimmed.
    """
    from webapp.routers.editor import _run_is_mosaic

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_source_run(solved_library, safe)
    edited = _export(client, solved_library, safe, rid, "remosaic_edit")

    assert _run_is_mosaic(edited, load=True) is False


def test_the_gallery_card_of_an_edited_picture_names_its_integration(
    client, solved_library,
):
    """End to end on the surface the owner reads: the listing the Gallery and
    History cards are built from used to serve `null` here, so the picture
    someone finished was the one with no integration time on it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_source_run(solved_library, safe)
    edited = _export(client, solved_library, safe, rid, "card_edit")

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    row = next(r for r in runs if r["id"] == edited.id)
    assert row["total_exposure_s"] == SRC["total_exposure_s"]
    assert row["calstat"] == SRC["calstat"]
