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


def test_process_target_stacks_end_to_end(client, solved_library):
    # One-click "process this target": QC + solve, then stack — in a single job.
    # solved_library already carries a synthetic WCS, so the chained stack runs
    # even without ASTAP.
    r = client.post("/api/targets/M_42/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    # QC ran as part of the chain.
    frames = client.get("/api/targets/M_42/frames").json()
    assert any(f["fwhm_px"] is not None for f in frames)
    # And the stack step produced a real run.
    result = body["result"]
    assert result["stacked"] is True
    assert result["solved_accepted"] >= 1
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) >= 1
    assert runs[0]["n_frames_used"] >= 1
    # The stack summary carries the new run's id so the finished-job UI can
    # deep-link straight to that run's editor, not just the target's History.
    assert result["stack"]["run_id"] == runs[0]["id"]


def test_process_target_chains_auto_edit(client, solved_library):
    # The one-click "process this target" chains an auto-edit onto the fresh
    # master so the result is a finished *picture*: the Auto recipe is persisted
    # as the run's editor recipe (so the editor opens edited) and the run's
    # preview thumbnail is re-rendered through it.
    r = client.post("/api/targets/M_42/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    result = body["result"]
    assert result["stacked"] is True
    # The auto-edit ran and applied a non-empty recipe.
    assert result.get("auto_edited", 0) >= 1

    rid = result["stack"]["run_id"]
    # The Auto recipe is saved as this run's editor recipe (the editor opens on
    # the edited image, not a flat linear master).
    recipe = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/editor/recipe").json()
    saved_ops = [o for o in recipe["ops"] if o.get("enabled", True)]
    assert len(saved_ops) == result["auto_edited"]
    # The Auto recipe always includes a tone stretch — a genuine difference from
    # a plain manual stack, which opens with an empty recipe.
    assert any(o["id"] == "tone.stretch" for o in saved_ops)

    # The run's preview thumbnail was re-rendered through the recipe and is a
    # valid PNG.
    run = next(x for x in client.get("/api/targets/M_42/stack-runs").json()
               if x["id"] == rid)
    if run["has_preview"]:
        pr = client.get(f"/api/targets/M_42/stack-runs/{rid}/preview")
        assert pr.status_code == 200
        assert pr.content[:8] == b"\x89PNG\r\n\x1a\n"

    # The History Info panel gets a plain-language "what the auto-edit did" note
    # for this silently-auto-edited run — the trust layer for a result the user
    # didn't drive. It names the ops it applied and starts with "Auto-edited:".
    info = client.get(f"/api/targets/M_42/stack-runs/{rid}/info").json()
    assert isinstance(info.get("auto_edit"), str)
    assert info["auto_edit"].startswith("Auto-edited:")
    assert "natural stretch" in info["auto_edit"]


def test_manual_stack_has_no_auto_edit_note(client, solved_library):
    # A plain manual stack (no auto-edit chain) leaves no auto-edit note, so the
    # Info panel only annotates runs an unattended job actually auto-edited.
    r = client.post("/api/targets/M_42/stack", json={})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    rid = client.get("/api/targets/M_42/stack-runs").json()[0]["id"]
    info = client.get(f"/api/targets/M_42/stack-runs/{rid}/info").json()
    assert info.get("auto_edit") is None


def _run_scan(client):
    r = client.post("/api/scan", json={})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"], timeout=120)
    assert body["state"] == "done", body
    return body


def test_auto_stack_without_auto_edit_leaves_linear_master(client, solved_library):
    # Auto-stack on, auto-edit-on-autostack OFF (the default): the unattended
    # background stack produces a flat linear master with no saved editor recipe
    # — the pre-existing behaviour is unchanged by the new opt-in.
    client.put("/api/settings",
               json={"auto_stack": True, "auto_edit_on_autostack": False})
    body = _run_scan(client)
    assert "auto_edited" not in body["result"]
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert runs, "auto-stack should have produced a run"
    rid = runs[0]["id"]
    recipe = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/editor/recipe").json()
    assert [o for o in recipe["ops"] if o.get("enabled", True)] == []


def test_auto_edit_on_autostack_finishes_the_picture(client, solved_library):
    # With the opt-in on, the fully-unattended watcher path finishes the master
    # into a picture: the Auto recipe is saved as the run's editor recipe, just
    # like the one-click Process / Reprocess chains.
    client.put("/api/settings",
               json={"auto_stack": True, "auto_edit_on_autostack": True})
    body = _run_scan(client)
    assert body["result"].get("auto_edited", 0) >= 1
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert runs
    rid = runs[0]["id"]
    recipe = client.get(
        f"/api/targets/M_42/stack-runs/{rid}/editor/recipe").json()
    saved_ops = [o for o in recipe["ops"] if o.get("enabled", True)]
    # The Auto recipe always includes a tone stretch — a genuine finished-picture
    # recipe, not the empty recipe a plain auto-stack leaves.
    assert any(o["id"] == "tone.stretch" for o in saved_ops)


def test_process_target_skips_stack_when_nothing_solved(client, built_library):
    # No ASTAP in CI and no injected WCS → nothing is plate-solved, so the chained
    # stack is skipped with a clear reason rather than failing the whole job.
    r = client.post("/api/targets/M_42/process")
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body
    result = body["result"]
    assert result["stacked"] is False
    assert result["stack_skipped_reason"] == "no_solved_frames"
    # QC still ran even though the stack was skipped.
    frames = client.get("/api/targets/M_42/frames").json()
    assert any(f["fwhm_px"] is not None for f in frames)
    # No stack run was created.
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) == 0
