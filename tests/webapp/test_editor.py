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
