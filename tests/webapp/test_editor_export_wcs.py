"""An editor export keeps the picture's place in the sky.

``_apply_editor_to_run`` wrote every export with ``wcs_text=None``, so the moment
a user finished an edit the result lost its solution — and with it North-up, the
scale bar, the compass and the object labels, every one of which reads the run's
own FITS through ``celestial_wcs_from_fits``. The edited picture was the one the
owner actually shares, so those overlays were missing exactly where they matter.

These tests go through the real export job, then read the written FITS back the
way the app's own overlays do.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for synth
from synth import make_synth_wcs_text  # noqa: E402

H, W = 160, 240
DOT_X, DOT_Y = 150.0, 60.0


def _wait_job(client, job_id, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "error", "cancelled", "interrupted"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish in time")


def _make_solved_run(data_root, safe, basename="wcsmaster"):
    """A stack run whose FITS carries a real celestial WCS and one tight star."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            outdir = Path(proj.project_dir) / "output"
            outdir.mkdir(parents=True, exist_ok=True)
            yy, xx = np.mgrid[0:H, 0:W]
            plane = (0.02 + np.exp(-(((xx - DOT_X) / 2.0) ** 2
                                     + ((yy - DOT_Y) / 2.0) ** 2))).astype(np.float32)
            cube = np.repeat(plane[None, ...], 3, axis=0)
            header = fits.Header.fromstring(make_synth_wcs_text(width=W, height=H))
            fp = outdir / f"{basename}.fits"
            fits.writeto(fp, cube, header=header, overwrite=True)
            rid = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename=basename, fits_path=str(fp), tiff_path=None,
                preview_path=None, n_frames_used=5, canvas_h=H, canvas_w=W,
                coverage_min=1, coverage_max=5, options_json="{}",
            ))
            return rid, str(fp)
        finally:
            proj.close()
    finally:
        lib.close()


def _export(client, data_root, safe, rid, recipe, name):
    """Run the real export job; return ``(new_run_id, fits_path)``."""
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": name})
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    new_id = job["result"]["run_id"]
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            row = next(r for r in proj.iter_stack_runs() if r.id == new_id)
        finally:
            proj.close()
    finally:
        lib.close()
    return new_id, row.fits_path


def _centroid(path):
    data = np.asarray(fits.getdata(path), dtype=np.float64)
    m = np.nan_to_num(data[0] if data.ndim == 3 else data)
    m = np.clip(m - np.median(m), 0, None)
    h, w = m.shape
    yy, xx = np.mgrid[0:h, 0:w]
    total = m.sum()
    return float((m * xx).sum() / total), float((m * yy).sum() / total)


def _sky(path, x, y):
    from seestack.io.wcs_io import celestial_wcs_from_fits

    wcs, _w, _h = celestial_wcs_from_fits(path)
    assert wcs is not None, f"{path} carries no celestial WCS"
    ra, dec = (float(v) for v in wcs.all_pix2world([[x, y]], 0)[0])
    return ra, dec


def _sep_arcsec(a, b):
    dec = np.radians((a[1] + b[1]) / 2.0)
    return float(np.hypot((a[0] - b[0]) * np.cos(dec), a[1] - b[1]) * 3600.0)


def test_a_tone_only_export_keeps_the_sources_wcs(client, solved_library):
    """The regression. Tone ops move no pixels, so the exported picture is on the
    very same grid — and used to come out with no solution at all."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid, src = _make_solved_run(solved_library, safe)

    _new, out = _export(client, solved_library, safe, rid, {"ops": [
        {"id": "tone.stretch", "params": {}},
        {"id": "tone.saturation", "params": {"amount": 1.2}},
    ]}, "tone_edit")

    for x, y in ((0.0, 0.0), (W - 1.0, H - 1.0), (DOT_X, DOT_Y)):
        assert _sep_arcsec(_sky(out, x, y), _sky(src, x, y)) < 0.01


def test_a_cropped_export_moves_the_wcs_with_the_crop(client, solved_library):
    """A crop is where a carried-over-verbatim WCS would be *wrong* — every
    overlay would sit one crop-offset away — so pin the star, not the keywords."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid, src = _make_solved_run(solved_library, safe)

    _new, out = _export(client, solved_library, safe, rid, {"ops": [
        {"id": "tone.stretch", "params": {}},
        {"id": "geometry.crop", "params": {"x0": 0.4, "x1": 0.95,
                                           "y0": 0.1, "y1": 0.7}},
    ]}, "crop_edit")

    cx, cy = _centroid(out)
    assert _sep_arcsec(_sky(out, cx, cy), _sky(src, DOT_X, DOT_Y)) < 1.0
    # …and it really is a different reference pixel, i.e. the crop was honoured.
    assert fits.getheader(out)["CRPIX1"] != fits.getheader(src)["CRPIX1"]


def test_a_rotated_export_carries_no_wcs_rather_than_a_wrong_one(client, solved_library):
    from seestack.io.wcs_io import celestial_wcs_from_fits

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid, _src = _make_solved_run(solved_library, safe)

    _new, out = _export(client, solved_library, safe, rid, {"ops": [
        {"id": "tone.stretch", "params": {}},
        {"id": "geometry.rotate", "params": {"angle": 15.0}},
    ]}, "rot_edit")

    assert celestial_wcs_from_fits(out)[0] is None


def test_an_export_of_an_unsolved_run_is_unchanged(client, solved_library):
    """No solution in, no solution out — and no error. Upgrade-safety for every
    run stacked before plate-solving worked."""
    from seestack.io.wcs_io import celestial_wcs_from_fits

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            outdir = Path(proj.project_dir) / "output"
            outdir.mkdir(parents=True, exist_ok=True)
            fp = outdir / "nowcs.fits"
            fits.writeto(fp, (np.random.default_rng(0).random((3, H, W))
                              * 0.1).astype("float32"), overwrite=True)
            rid = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="nowcs", fits_path=str(fp), tiff_path=None,
                preview_path=None, n_frames_used=5, canvas_h=H, canvas_w=W,
                coverage_min=1, coverage_max=5, options_json="{}"))
        finally:
            proj.close()
    finally:
        lib.close()

    _new, out = _export(client, solved_library, safe, rid,
                        {"ops": [{"id": "tone.stretch", "params": {}}]}, "nowcs_edit")
    assert celestial_wcs_from_fits(out)[0] is None


def test_the_annotations_endpoint_answers_for_an_edited_run(client, solved_library):
    """The user-visible half: the overlays that read a run's WCS now have one to
    read on the edited picture, which is the picture the owner actually shares."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid, _src = _make_solved_run(solved_library, safe)
    new_id, _out = _export(client, solved_library, safe, rid,
                           {"ops": [{"id": "tone.stretch", "params": {}}]},
                           "annot_edit")

    r = client.get(f"/api/targets/{safe}/stack-runs/{new_id}/annotations")
    assert r.status_code == 200, r.text
    edited = r.json()
    # The compass, the scale bar and the North-up turn — all three used to come
    # back null on an edited run, because the export carried no solution.
    assert edited["directions"] is not None, json.dumps(edited)[:400]
    assert edited["scale_bar"] is not None
    assert edited["north_up_deg"] is not None

    # Same run, same overlays as the source it was edited from.
    src_body = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/annotations").json()
    assert edited["directions"] == src_body["directions"]
    assert edited["scale_bar"] == src_body["scale_bar"]
    assert edited["north_up_deg"] == src_body["north_up_deg"]
