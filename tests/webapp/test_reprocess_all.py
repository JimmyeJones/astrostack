"""Reprocess-everything: restack all targets serially, non-destructively.

Covers the pure helpers, the batch job body (reuse of each target's last
settings, per-target failure isolation, cancel-between-targets), the
duplicate-batch guard, and end-to-end wiring through the API — including that
old runs are preserved (additive).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job, JobManager


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root) -> Settings:
    return Settings(data_root=str(root), auto_ingest=False, auto_qc=False,
                    auto_solve=False, auto_stack=False)


# --------------------------------------------------------------------------- #
# Pure helper: which run's options to reuse
# --------------------------------------------------------------------------- #

def test_stack_options_from_run_json_genuine():
    opts = pipeline._stack_options_from_run_json(
        json.dumps({"sigma_clip": True, "sigma_kappa": 2.5, "junk": 1}))
    assert opts == {"sigma_clip": True, "sigma_kappa": 2.5}  # unknown key dropped


@pytest.mark.parametrize("bad", [
    None, "", "{}", "not json", "[1,2,3]",
    json.dumps({"editor_recipe": {"ops": []}}),   # editor-export run
    json.dumps({"channel_combine": []}),           # combine run
    json.dumps({"junk_only": 1}),                  # no real StackOptions keys
])
def test_stack_options_from_run_json_rejects(bad):
    assert pipeline._stack_options_from_run_json(bad) is None


# --------------------------------------------------------------------------- #
# Batch body
# --------------------------------------------------------------------------- #

def _patch_run_stack(monkeypatch, *, capture: list | None = None):
    """Fake run_stack that records the opts it was called with."""
    def fake(proj, opts, *, progress=None, cancel=None, memory_budget_gb=None, app_version=None):  # noqa: ANN001
        if capture is not None:
            capture.append(opts)
        # emit a little progress so the phase/detail interplay is exercised
        if progress:
            progress("combine", 1, 1)
        return SimpleNamespace(output_dir="/tmp/x", n_frames_used=3,
                               canvas_shape=(1, 1, 3), cancelled=False,
                               errors=[], excluded_frames=[])
    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake)


def test_reprocess_all_restacks_every_target_reusing_last_options(solved_library, monkeypatch):
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    lib = Library.open_or_create(solved_library / "library")
    try:
        # Seed each target with a genuine prior stack run carrying a distinctive
        # kappa, so we can assert the reprocess reused it.
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"method": "sigma", "sigma_kappa": 4.25}),
                ))
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        # Call the body directly (submit would run it on a worker thread).
        summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)
    finally:
        lib.close()

    assert summary["total"] == 2
    assert summary["stacked"] == 2
    assert summary["failed"] == []
    assert summary["cancelled"] is False
    # Every target restacked with the reused kappa.
    assert len(captured) == 2
    assert all(abs(o.sigma_kappa - 4.25) < 1e-6 for o in captured)


def test_reprocess_all_isolates_a_failing_target(solved_library, monkeypatch):
    seen: list[str] = []

    def fake(proj, opts, *, progress=None, cancel=None, memory_budget_gb=None, app_version=None):  # noqa: ANN001
        seen.append(getattr(proj, "safe_name", "?"))
        if len(seen) == 1:
            raise ValueError("boom on first target")
        return SimpleNamespace(output_dir="/tmp/x", n_frames_used=3,
                               canvas_shape=(1, 1, 3), cancelled=False,
                               errors=[], excluded_frames=[])
    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake)

    job = Job(kind="reprocess_all")
    summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)

    assert summary["total"] == 2
    assert summary["stacked"] == 1           # the second target still stacked
    assert len(summary["failed"]) == 1       # the first was isolated, not fatal
    assert "boom" in summary["failed"][0]["error"]
    assert summary["cancelled"] is False


def test_reprocess_all_stale_only_skips_current_version_targets(solved_library, monkeypatch):
    """With stale_only, a target already stacked on the current app version is
    skipped; one whose latest genuine stack is on an older version is reprocessed."""
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        assert len(targets) == 2
        # One target up to date (current version), one stale (old version).
        vers = {targets[0]: pipeline.APP_VERSION, targets[1]: "0.0.1"}
        for safe in targets:
            proj = lib.open_target(safe)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"method": "sigma", "sigma_kappa": 4.25}),
                    engine_version=vers[safe],
                ))
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library),
                            job, stale_only=True)
    finally:
        lib.close()

    assert summary["total"] == 2
    assert summary["stacked"] == 1      # only the stale target
    assert summary["skipped"] == 1      # the up-to-date one was skipped
    assert summary["failed"] == []
    assert len(captured) == 1           # run_stack called once, for the stale target


def test_reprocess_all_default_reprocesses_current_version_targets(solved_library, monkeypatch):
    """Without stale_only (the default), a target already on the current version is
    still reprocessed — the version filter is strictly opt-in."""
    captured: list = []
    _patch_run_stack(monkeypatch, capture=captured)
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"method": "sigma", "sigma_kappa": 4.25}),
                    engine_version=pipeline.APP_VERSION,
                ))
            finally:
                proj.close()
        job = Job(kind="reprocess_all")
        summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)
    finally:
        lib.close()

    assert summary["stacked"] == 2
    assert summary["skipped"] == 0
    assert len(captured) == 2


def test_reprocess_all_cancels_between_targets(solved_library, monkeypatch):
    calls: list = []

    def fake(proj, opts, *, progress=None, cancel=None, memory_budget_gb=None, app_version=None):  # noqa: ANN001
        calls.append(1)
        return SimpleNamespace(output_dir="/tmp/x", n_frames_used=3,
                               canvas_shape=(1, 1, 3), cancelled=False,
                               errors=[], excluded_frames=[])
    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake)

    job = Job(kind="reprocess_all")
    job._cancel.set()  # cancel before the first target is picked up
    summary = _run_body(pipeline.submit_reprocess_all, _settings(solved_library), job)

    assert summary["cancelled"] is True
    assert calls == []                       # never started a stack
    assert summary["stacked"] == 0


def _run_body(submit_fn, settings, job, **submit_kwargs):
    """Invoke a submit_* function's body synchronously by capturing the job fn
    it hands to a recording JobManager."""
    captured: dict = {}

    class _RecordingJM(_FakeJM):
        def submit(self, kind, fn, *, target=None):  # noqa: ANN001
            captured["fn"] = fn
            return job
    submit_fn(settings, _RecordingJM(), **submit_kwargs)
    return captured["fn"](job)


# --------------------------------------------------------------------------- #
# Duplicate-batch guard (JobManager.active_of_kind)
# --------------------------------------------------------------------------- #

def test_active_of_kind(tmp_path: Path):
    jm = JobManager(tmp_path / "jobs.sqlite")
    assert jm.active_of_kind("reprocess_all") is None
    running = Job(kind="reprocess_all", state="running")
    jm._jobs[running.id] = running
    assert jm.active_of_kind("reprocess_all") is running
    assert jm.active_of_kind("stack") is None
    # A terminal job of the same kind doesn't count as active.
    running.state = "done"
    assert jm.active_of_kind("reprocess_all") is None


# --------------------------------------------------------------------------- #
# End-to-end through the API (real stacker), additive / non-destructive
# --------------------------------------------------------------------------- #

@pytest.fixture
def solved_client(solved_library, monkeypatch):
    monkeypatch.setenv("ASTROSTACK_DATA", str(solved_library))
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    from fastapi.testclient import TestClient

    from webapp.main import create_app

    app = create_app()
    with TestClient(app) as c:
        c.put("/api/settings", json={"watcher_enabled": False})
        yield c


def _wait_job(client, job_id, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_reprocess_all_endpoint_is_additive(solved_client, solved_library):
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        # Seed one genuine prior run per target so we can prove it's preserved.
        for safe in targets:
            proj = lib.open_target(safe)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="seed", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"sigma_clip": True, "sigma_kappa": 3.0}),
                ))
            finally:
                proj.close()
    finally:
        lib.close()

    before = {s: len(solved_client.get(f"/api/targets/{s}/stack-runs").json())
              for s in targets}

    r = solved_client.post("/api/reprocess-all")
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert r.json()["already_running"] is False

    body = _wait_job(solved_client, job_id)
    assert body["state"] == "done"
    assert body["result"]["total"] == len(targets)
    assert body["result"]["stacked"] == len(targets)
    assert body["result"]["failed"] == []

    # Each target gained exactly one new run; the seeded run is still there.
    for s in targets:
        runs = solved_client.get(f"/api/targets/{s}/stack-runs").json()
        assert len(runs) == before[s] + 1
        assert any(r.get("output_basename") == "seed" for r in runs)


def test_reprocess_all_endpoint_stale_only_skips_current_version(solved_client, solved_library):
    """POST {stale_only: true} skips targets whose latest genuine stack was already
    made with the current app version — no new run is added for them."""
    from webapp import __version__ as app_version

    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = [e.safe_name for e in lib.list_targets()]
        for safe in targets:
            proj = lib.open_target(safe)
            try:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="uptodate", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=3, canvas_h=10, canvas_w=10,
                    coverage_min=1, coverage_max=3,
                    options_json=json.dumps({"sigma_clip": True, "sigma_kappa": 3.0}),
                    engine_version=app_version,
                ))
            finally:
                proj.close()
    finally:
        lib.close()

    before = {s: len(solved_client.get(f"/api/targets/{s}/stack-runs").json())
              for s in targets}

    r = solved_client.post("/api/reprocess-all", json={"stale_only": True})
    assert r.status_code == 200
    body = _wait_job(solved_client, r.json()["job_id"])
    assert body["state"] == "done"
    assert body["result"]["total"] == len(targets)
    assert body["result"]["stacked"] == 0
    assert body["result"]["skipped"] == len(targets)

    # No target gained a new run — all were up to date and skipped.
    for s in targets:
        runs = solved_client.get(f"/api/targets/{s}/stack-runs").json()
        assert len(runs) == before[s]
