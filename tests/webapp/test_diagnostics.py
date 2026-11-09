"""webapp.diagnostics — the shipped library diagnostics run once per version,
store a numbers-only result, and are served on the read-only token's path.

Owner, 2026-11-09: "I can't keep running these random tests … have the AI on
the NAS run them." A diagnostic now ships with the app, runs after the update
by itself, and the observer collects the result from ``GET /api/diagnostics``.
"""
from __future__ import annotations

import json

import pytest

from seestack.diag import Diagnostic, DiagnosticStopped
from webapp import diagnostics as wd
from webapp.config import Settings


@pytest.fixture
def settings(tmp_path):
    s = Settings(data_root=str(tmp_path / "data"))
    s.ensure_dirs()
    return s


def _diag(run, *, name="probe", version=1, ready=None):
    return Diagnostic(name=name, version=version, question="Is it?", run=run, ready=ready)


def test_a_result_is_stored_once_per_version(settings, monkeypatch):
    calls = []

    def run(lib, *, progress=None, should_stop=None):
        calls.append(1)
        return {"targets": 3, "label": "below 0 C"}

    d1 = _diag(run)
    monkeypatch.setattr(wd, "registry", lambda: [d1])
    assert [d.name for d in wd.pending(settings)] == ["probe"]
    out = wd.run_one(settings, d1)
    assert out["status"] == "done" and out["result"]["targets"] == 3
    assert wd.pending(settings) == []
    # A new version is a new question: it runs again, and the old answer stays.
    d2 = _diag(run, version=2)
    monkeypatch.setattr(wd, "registry", lambda: [d2])
    assert [d.version for d in wd.pending(settings)] == [2]
    wd.run_one(settings, d2)
    got = wd.all_results(settings)
    assert [(r["name"], r["version"]) for r in got["results"]] == [("probe", 2), ("probe", 1)]
    assert got["pending"] == []


def test_a_failure_is_recorded_by_class_only(settings, monkeypatch):
    def run(lib, *, progress=None, should_stop=None):
        raise OSError("could not open /mnt/tank/astro/incoming/M 31_sub/a.fit")

    d = _diag(run)
    out = wd.run_one(settings, d)
    assert out["status"] == "error" and out["error"] == "OSError"
    stored = (wd.results_dir(settings) / "probe-v1.json").read_text()
    assert "/mnt" not in stored and "incoming" not in stored


def test_a_result_carrying_a_path_is_refused_not_published(settings):
    d = _diag(lambda lib, **_: {"file": "/data/incoming/M 31_sub/a.fit"})
    out = wd.run_one(settings, d)
    assert out["status"] == "error" and out["error"] == "ValueError"
    assert "incoming" not in json.dumps(wd.all_results(settings))


def test_a_stopped_run_stores_nothing_and_stays_pending(settings, monkeypatch):
    def run(lib, *, progress=None, should_stop=None):
        raise DiagnosticStopped("stopped")

    d = _diag(run)
    monkeypatch.setattr(wd, "registry", lambda: [d])
    with pytest.raises(DiagnosticStopped):
        wd.run_one(settings, d)
    assert [x.name for x in wd.pending(settings)] == ["probe"]


def test_only_ready_diagnostics_are_queued(settings, monkeypatch):
    queued = []

    class FakeJM:
        def active_of_kind(self, kind):
            return None

        def submit(self, kind, fn):
            queued.append(kind)
            return kind

    not_ready = _diag(lambda lib, **_: {}, ready=lambda lib: False)
    monkeypatch.setattr(wd, "registry", lambda: [not_ready])
    assert wd.submit_pending_diagnostics(settings, FakeJM()) is None
    ready = _diag(lambda lib, **_: {}, name="other", ready=lambda lib: True)
    monkeypatch.setattr(wd, "registry", lambda: [not_ready, ready])
    assert wd.submit_pending_diagnostics(settings, FakeJM()) == wd.JOB_KIND
    assert queued == [wd.JOB_KIND]


def test_the_endpoint_serves_results(client):
    r = client.get("/api/diagnostics")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"results", "pending"}
    names = [p["name"] for p in body["pending"]] + [x["name"] for x in body["results"]]
    assert "sensor_pattern_by_temperature" in names


def _run_through_job_manager(settings, monkeypatch, tmp_path, diags, *, cancel_after=None):
    """Queue the real boot-time job on a real JobManager and wait for it."""
    import threading
    import time

    from webapp.jobs import JobManager

    monkeypatch.setattr(wd, "registry", lambda: diags)
    jm = JobManager(tmp_path / "jobs.sqlite")
    jm.start()
    started = threading.Event()
    if cancel_after is not None:
        cancel_after.started = started  # the diagnostic signals when it is running
    job = wd.submit_pending_diagnostics(settings, jm)
    assert job is not None
    if cancel_after is not None:
        assert started.wait(10)
        jm.cancel(job.id)
    deadline = time.time() + 20
    while jm.get(job.id).state in ("queued", "running") and time.time() < deadline:
        time.sleep(0.02)
    out = jm.get(job.id)
    jm.stop()
    return out


def test_a_cancelled_diagnostics_job_reads_cancelled_not_done(settings, monkeypatch, tmp_path):
    """Cancel on the Jobs page stops the run, and the job must *say* cancelled.

    v0.506.0's body returned ``{"ran": []}`` on a stop — a truthy dict with no
    cancellation sentinel — so JobManager marked the cancelled run 'done'."""
    import time

    def first(lib, **_):
        return {"n": 1}

    class Waits:
        started = None

        def __call__(self, lib, *, progress=None, should_stop=None):
            self.started.set()
            for _ in range(500):
                if should_stop():
                    raise DiagnosticStopped("stopped")
                time.sleep(0.01)
            return {"n": 2}

    waits = Waits()
    job = _run_through_job_manager(
        settings, monkeypatch, tmp_path,
        [_diag(first, name="first"), _diag(waits, name="slow")], cancel_after=waits)
    assert job.state == "cancelled"
    assert job.result["cancelled"] is True
    # What finished is kept and listed; the stopped one stays pending.
    assert [r["name"] for r in job.result["ran"]] == ["first"]
    assert [d.name for d in wd.pending(settings)] == ["slow"]


def test_a_finished_diagnostics_job_reads_done(settings, monkeypatch, tmp_path):
    job = _run_through_job_manager(
        settings, monkeypatch, tmp_path,
        [_diag(lambda lib, **_: {"n": 1}, name="a"),
         _diag(lambda lib, **_: {"file": "/data/x.fit"}, name="b")])
    assert job.state == "done"
    assert job.result == {"ran": [{"name": "a", "version": 1, "status": "done"},
                                  {"name": "b", "version": 1, "status": "error"}]}
