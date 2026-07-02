"""Editor API: op schema, recipe round-trip, proxy preview, histogram,
auto-process, presets, full-res export + batch (non-destructive)."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _make_run(data_root, safe, basename="master", h=80, w=100):
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            outdir = Path(proj.project_dir) / "output"
            outdir.mkdir(parents=True, exist_ok=True)
            rng = np.random.default_rng(0)
            cube = (rng.random((3, h, w)) * 0.1).astype("float32")
            # a bright blob so the stretch has something to reveal
            yy, xx = np.mgrid[0:h, 0:w]
            cube += 0.4 * np.exp(-(((xx - w / 2) / 8) ** 2 + ((yy - h / 2) / 8) ** 2))
            fp = outdir / f"{basename}.fits"
            fits.writeto(fp, cube, overwrite=True)
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z", output_basename=basename,
                fits_path=str(fp), tiff_path=None, preview_path=None, n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5, options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _enc(recipe: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(recipe).encode()).decode()


def _wait_job(client, job_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "error", "cancelled", "interrupted"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish in time")


def _set_fwhm(data_root, safe, values):
    """Set fwhm_px on the target's frames (in id order) and mark them accepted."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            frames = list(proj.iter_frames())
            for f, v in zip(frames, values):
                proj.update_frame(f.id, fwhm_px=v, accept=True)
        finally:
            proj.close()
    finally:
        lib.close()


def test_psf_suggestion_from_median_fwhm(client, built_library, data_root):
    import math

    _set_fwhm(data_root, "M_42", [2.0, 3.0, 4.0])
    r = client.get("/api/targets/M_42/editor/psf-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["fwhm_px"] == 3.0  # median of 2, 3, 4
    expected_sigma = 3.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    assert abs(body["psf_sigma"] - round(expected_sigma, 2)) < 0.01


def test_psf_suggestion_none_without_fwhm(client, built_library):
    # No frame carries an FWHM → both fields null (button won't be offered).
    r = client.get("/api/targets/M_42/editor/psf-suggestion")
    assert r.status_code == 200
    assert r.json() == {"fwhm_px": None, "psf_sigma": None}


def test_psf_suggestion_clamps_to_op_range(client, built_library, data_root):
    # A huge FWHM would map to σ well above the op's 5.0 ceiling; it's clamped.
    _set_fwhm(data_root, "M_42", [30.0, 30.0, 30.0])
    body = client.get("/api/targets/M_42/editor/psf-suggestion").json()
    assert body["psf_sigma"] == 5.0


def test_denoise_suggestion_from_image_noise(client, solved_library):
    # The run's proxy has a bright blob on a noisy sky (see _make_run), so the
    # endpoint returns a measurable noise σ and a usable in-range strength.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="denoise_src")
    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/denoise-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["noise_sigma"] is not None and body["noise_sigma"] > 0
    assert 0.1 <= body["strength"] <= 1.0


def test_ops_schema(client):
    r = client.get("/api/editor/ops/schema")
    assert r.status_code == 200
    ops = r.json()
    ids = {o["id"] for o in ops}
    assert {"tone.stretch", "tone.curves", "detail.denoise", "stars.reduce",
            "geometry.crop", "background.final_gradient"} <= ids
    stretch = next(o for o in ops if o["id"] == "tone.stretch")
    assert stretch["is_stretch"] is True
    assert any(p["key"] == "stretch" for p in stretch["params"])
    # the curve param surfaces with the new "curve" type
    curves = next(o for o in ops if o["id"] == "tone.curves")
    assert curves["params"][0]["type"] == "curve"


def test_recipe_round_trip_and_validation(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    assert client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe").json()["ops"] == []

    recipe = {"ops": [
        {"id": "tone.stretch", "params": {"stretch": 0.6, "black": 0.4}},
        {"id": "bogus.op", "params": {}},            # dropped by validation
        {"id": "tone.saturation", "params": {"amount": 1.4}},
    ]}
    put = client.put(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe", json=recipe)
    assert put.status_code == 200
    saved = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe").json()
    assert [o["id"] for o in saved["ops"]] == ["tone.stretch", "tone.saturation"]
    assert saved["base_run_id"] == rid


def test_edit_preview_and_histogram(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6, "black": 0.35}},
                      {"id": "tone.curves", "params": {"points": [[0, 0], [0.5, 0.6], [1, 1]]}}]}
    q = _enc(recipe)

    img = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/preview?recipe={q}")
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/png")
    assert len(img.content) > 100

    hist = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={q}").json()
    assert len(hist["r"]) == hist["bins"] and len(hist["g"]) == hist["bins"]
    assert sum(hist["r"]) > 0


def test_star_mask_preview(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)

    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/star-mask")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # A custom star size is accepted and still renders.
    r2 = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/star-mask", params={"size_px": 6}
    )
    assert r2.status_code == 200
    assert r2.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_auto_process(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/auto")
    assert r.status_code == 200
    ops = [o["id"] for o in r.json()["ops"]]
    assert "tone.stretch" in ops


def test_export_creates_new_run_non_destructive(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}},
                      {"id": "tone.saturation", "params": {"amount": 1.2}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "edited1"})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    names = {x["output_basename"] for x in runs}
    assert "edited1" in names               # new edited run exists
    assert any(x["id"] == rid for x in runs)  # original run untouched
    edited = next(x for x in runs if x["output_basename"] == "edited1")
    assert edited["has_fits"] and edited["notes"] == "edited"


def test_export_carries_provenance_headers(client, solved_library):
    """The derived master.fits keeps the source integration provenance
    (OBJECT/NFRAMES/EXPTOTAL) and records how it was produced (STACKMTD/EDITFROM)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="prov_src")
    # Stamp provenance cards onto the source FITS, as a real stack would.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == rid)
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["OBJECT"] = "M42"
                hdul[0].header["NFRAMES"] = 840
                hdul[0].header["EXPTOTAL"] = 2520.0
                hdul[0].header["STACKER"] = "sigma-clip"
        finally:
            proj.close()
    finally:
        lib.close()

    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "prov_edit"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "prov_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            hdr = fits.getheader(new_run.fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    # Integration provenance carried forward…
    assert hdr["OBJECT"] == "M42"
    assert int(hdr["NFRAMES"]) == 840
    assert float(hdr["EXPTOTAL"]) == 2520.0
    # …and the derivation is recorded.
    assert "editor recipe" in str(hdr["STACKMTD"])
    assert int(hdr["EDITFROM"]) == rid


def test_export_records_deconvolution_psf_header(client, solved_library):
    """An editor recipe with a deconvolution op stamps the PSF sigma actually
    used into the derived master.fits (DECONPSF), self-documenting the sharpen."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="deconv_src")
    recipe = {"ops": [
        {"id": "tone.stretch", "params": {"stretch": 0.6}},
        {"id": "detail.deconvolve", "params": {"psf_sigma": 2.3}},
    ]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "deconv_edit"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "deconv_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            hdr = fits.getheader(new_run.fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    assert float(hdr["DECONPSF"]) == 2.3
    # …and the Info endpoint surfaces it as a provenance card.
    info = client.get(f"/api/targets/{safe}/stack-runs/{edited['id']}/info").json()
    assert any(c["key"] == "DECONPSF" for c in info["cards"])


def test_export_no_deconvolution_omits_psf_header(client, solved_library):
    """A recipe without a deconvolution op leaves no DECONPSF card."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="nodeconv_src")
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "nodeconv_edit"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "nodeconv_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            hdr = fits.getheader(new_run.fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    assert "DECONPSF" not in hdr


def test_export_records_recipe_history(client, solved_library):
    """The derived master.fits records each enabled editor op as a FITS HISTORY
    card, so an edited export self-documents its full processing chain."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="hist_src")
    recipe = {"ops": [
        {"id": "tone.stretch", "params": {"stretch": 0.6}},
        {"id": "detail.denoise", "params": {"method": "tv", "strength": 0.4},
         "enabled": False},  # disabled ops are not recorded
        {"id": "detail.sharpen", "params": {"amount": 1.2}},
    ]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "hist_edit"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "hist_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            hdr = fits.getheader(new_run.fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    history = "\n".join(str(c) for c in hdr["HISTORY"])
    assert "tone.stretch" in history
    assert "detail.sharpen" in history
    assert "detail.denoise" not in history  # disabled op omitted


def test_export_sanitizes_path_traversal_output_name(client, solved_library, tmp_path):
    # output_name is free text from the client and is spliced into a
    # filename under <project>/output/; a path-separator payload must not
    # be able to write outside the project (write_stack_outputs sanitizes
    # it rather than failing the job outright).
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "../../../../tmp/pwned"})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert not (Path("/tmp") / "pwned.fits").exists()


def test_presets_crud(client):
    base = client.get("/api/editor/presets").json()
    assert any(p["id"] == "nebula_broadband" for p in base["builtin"])
    assert base["user"] == []

    created = client.post("/api/editor/presets", json={
        "label": "My Look", "ops": [{"id": "tone.stretch", "params": {"stretch": 0.7}}],
    }).json()
    assert created["label"] == "My Look"
    after = client.get("/api/editor/presets").json()
    assert any(p["id"] == created["id"] for p in after["user"])

    client.delete(f"/api/editor/presets/{created['id']}")
    assert client.get("/api/editor/presets").json()["user"] == []


def test_batch_apply(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r1 = _make_run(solved_library, safe, basename="a")
    r2 = _make_run(solved_library, safe, basename="b")
    body = {
        "items": [{"safe": safe, "run_id": r1}, {"safe": safe, "run_id": r2}],
        "preset_id": "galaxy_broadband",
        "output_name": "batchout",
    }
    r = client.post("/api/editor/batch", json=body)
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert len(job["result"]["exported"]) == 2


def test_export_png_full_res_download(client, solved_library):
    import io

    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export-png",
                    json={"recipe": recipe})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job

    dl = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/png/{r.json()['job_id']}")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("image/png")
    assert "attachment" in dl.headers.get("content-disposition", "")
    # Full resolution: PNG matches the native canvas (w=100, h=80).
    img = Image.open(io.BytesIO(dl.content))
    assert img.size == (100, 80)


def test_histogram_reports_op_errors(client, solved_library, monkeypatch):
    from seestack.edit.registry import get_op

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)

    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(get_op("tone.saturation"), "apply", boom)
    recipe = {"ops": [{"id": "tone.stretch", "params": {}},
                      {"id": "tone.saturation", "params": {"amount": 1.2}}]}
    h = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={_enc(recipe)}").json()
    assert any("kaboom" in e for e in h["errors"])


def test_stf_stretch_renders_non_black(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"mode": "stf", "target_bg": 0.2}}]}
    h = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={_enc(recipe)}").json()
    assert h["empty"] is False
    assert sum(h["r"]) > 0 and h["errors"] == []


def test_histogram_flags_empty_stack(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]

    # A normal stack is not empty.
    rid = _make_run(solved_library, safe)
    h = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram").json()
    assert h["empty"] is False

    # An all-NaN stack (failed solve/stack) is flagged empty, not a 500.
    nan_id = _make_run(solved_library, safe, basename="blank")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == nan_id)
            cube = np.full((3, 80, 100), np.nan, dtype="float32")
            fits.writeto(run.fits_path, cube, overwrite=True)
        finally:
            proj.close()
    finally:
        lib.close()
    hb = client.get(f"/api/targets/{safe}/stack-runs/{nan_id}/editor/histogram")
    assert hb.status_code == 200
    assert hb.json()["empty"] is True
