"""End-to-end pipeline via the API: scan → QC/solve, then stack.

ASTAP is not installed in CI, so solve gracefully marks frames unsolved; QC
still runs and the pipeline completes. The stack test is skipped if the
optional ``reproject`` dependency isn't present.
"""

from __future__ import annotations

import time


def _wait_job(client, job_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_scan_pipeline_populates_qc(client, data_root):
    # Fresh data_root (not the built_library fixture) so scan does the ingest.
    r = client.post("/api/scan", json={})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    body = _wait_job(client, job_id)
    assert body["state"] == "done", body

    targets = client.get("/api/targets").json()
    names = {t["safe_name"] for t in targets}
    assert {"M_42", "NGC_7000"} <= names

    frames = client.get("/api/targets/M_42/frames").json()
    assert len(frames) == 3
    # QC ran → at least one frame has FWHM / star_count populated.
    assert any(f["fwhm_px"] is not None for f in frames)
    assert any(f["star_count"] is not None for f in frames)


def test_qc_solve_single_target(client, built_library):
    r = client.post("/api/targets/M_42/qc-solve")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body
    frames = client.get("/api/targets/M_42/frames").json()
    assert any(f["fwhm_px"] is not None for f in frames)


def test_stack_end_to_end(client, solved_library):
    r = client.post(
        "/api/targets/M_42/stack",
        json={"output_name": "test_master", "sigma_clip": False,
              "background_flatten": False, "suppress_hot_pixels": False,
              "max_workers": 2},
    )
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body

    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) >= 1
    run = runs[0]
    assert run["n_frames_used"] >= 1
    # The run records the producing app version for provenance (surfaced on the
    # History card as "made with vX"). The webapp passes its own __version__.
    from webapp import __version__ as app_version
    assert run["engine_version"] == app_version
    # Download the preview PNG.
    rid = run["id"]
    if run["has_preview"]:
        pr = client.get(f"/api/targets/M_42/stack-runs/{rid}/preview")
        assert pr.status_code == 200
        assert pr.content[:8] == b"\x89PNG\r\n\x1a\n"
