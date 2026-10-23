"""Combining folders never deletes a folder a job is still working on.

``POST /api/targets/merge`` ends in an ``rmtree`` of every source target's
folder. A stack still running on a source then finished into a folder that no
longer belonged to any target: the job said "done" with a run id, its picture
was written into an orphaned ``output/`` and its run row into a deleted
``project.sqlite`` — the destination never saw it, and nothing on screen said
it was gone. The merge now refuses (409) while a source has a queued or running
job, and works as before once the job has finished.
"""

from __future__ import annotations

import threading

from seestack.io.library import Library
from seestack.io.project import Project
from tests.webapp.jobwait import wait_job


def _second_target(data_root) -> str:
    lib = Library.open_or_create(data_root / "library")
    try:
        entry, proj = lib.create_target("Other night")
        proj.close()
        return entry.safe_name
    finally:
        lib.close()


def _hold_the_stack(monkeypatch):
    """Make the next stack job wait inside ``run_stack`` until released."""
    import seestack.stack.stacker as stacker

    real = stacker.run_stack
    started, release = threading.Event(), threading.Event()

    def held(*a, **k):
        started.set()
        assert release.wait(60), "the test never released the stack"
        return real(*a, **k)

    monkeypatch.setattr(stacker, "run_stack", held)
    return started, release


def test_merge_refuses_a_source_that_is_still_stacking(client, solved_library, monkeypatch):
    src = client.get("/api/targets").json()[0]["safe_name"]
    dest = _second_target(solved_library)
    started, release = _hold_the_stack(monkeypatch)

    r = client.post(f"/api/targets/{src}/stack", json={})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    try:
        assert started.wait(60)
        refused = client.post("/api/targets/merge",
                              json={"into": dest, "sources": [src]})
        assert refused.status_code == 409, refused.text
        assert "still being worked on" in refused.json()["detail"]
    finally:
        release.set()
    job = wait_job(client, job_id)
    assert job["state"] == "done", job

    # Nothing was merged away: the source is still a target with its picture.
    assert src in {t["safe_name"] for t in client.get("/api/targets").json()}

    # Once the job is done the same press works, and the new picture travels.
    ok = client.post("/api/targets/merge", json={"into": dest, "sources": [src]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["pictures_kept"] == 1
    proj = Project.open(solved_library / "library" / "targets" / dest)
    try:
        assert len(list(proj.iter_stack_runs())) == 1
    finally:
        proj.close()


def test_a_job_on_the_destination_does_not_block_the_merge(client, solved_library, monkeypatch):
    dest = client.get("/api/targets").json()[0]["safe_name"]
    src = _second_target(solved_library)
    started, release = _hold_the_stack(monkeypatch)

    r = client.post(f"/api/targets/{dest}/stack", json={})
    assert r.status_code == 200, r.text
    try:
        assert started.wait(60)
        ok = client.post("/api/targets/merge", json={"into": dest, "sources": [src]})
        assert ok.status_code == 200, ok.text
    finally:
        release.set()
    assert wait_job(client, r.json()["job_id"])["state"] == "done"
