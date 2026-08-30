"""``POST /api/scan`` may only be pointed at the incoming folder, or inside it.

Every other ingest/target endpoint names its subject with a database
``safe_name`` and is traversal-safe by construction. ``root`` is the one input
that names a directory directly, and an unconfined one lets anything that can
reach the API register — and, with ``copy_to_cache``, copy — FITS out of any
server-readable directory. Auth is **off by default** on this app, so "anything
that can reach the API" is everything on the owner's network.

This is confinement, not deletion: ``incoming/`` stays read-and-create-new only
(AGENTS.md §10), and a rejected scan does nothing at all.
"""

from __future__ import annotations

import time
from pathlib import Path


def _wait_job(client, job_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_scan_refuses_a_root_outside_the_incoming_folder(client, data_root, tmp_path):
    outside = tmp_path / "somewhere_else"
    outside.mkdir()

    r = client.post("/api/scan", json={"root": str(outside)})
    assert r.status_code == 400
    # Says what the rule is and how to get on with it, in the beginner's words.
    detail = r.json()["detail"]
    assert "incoming folder" in detail
    assert "Leave the folder out" in detail
    # And nothing ran: no job was queued to look there.
    assert "job_id" not in r.json()


def test_scan_refuses_a_traversal_out_of_the_incoming_folder(client, data_root):
    escape = str(data_root / "incoming" / ".." / ".." / "etc")
    r = client.post("/api/scan", json={"root": escape})
    assert r.status_code == 400


def test_scan_still_accepts_the_incoming_folder_itself(client, data_root):
    r = client.post("/api/scan", json={"root": str(data_root / "incoming")})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body


def test_scan_still_accepts_one_folder_inside_incoming(client, data_root):
    # A sub-folder of incoming is inside the tree, so it is allowed through and
    # scanned. (What the scanner then *calls* those frames is a separate, older
    # question — a sub-folder root loses the folder-name target, which is why
    # nothing in the app passes one; filed rather than changed here.)
    inside = data_root / "incoming" / "M_42"
    r = client.post("/api/scan", json={"root": str(inside)})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body
    assert Path(body["result"]["root"]) == inside


def test_scan_with_no_root_scans_the_whole_incoming_folder(client, data_root):
    # The default path every existing caller (and the frontend) uses is untouched.
    for payload in ({}, {"root": None}):
        r = client.post("/api/scan", json=payload)
        assert r.status_code == 200
        assert _wait_job(client, r.json()["job_id"])["state"] == "done"
    names = {t["safe_name"] for t in client.get("/api/targets").json()}
    assert {"M_42", "NGC_7000"} <= names


def test_a_symlinked_incoming_folder_is_not_refused(client, data_root, tmp_path):
    """A NAS share mounted into ``incoming/`` by symlink is normal on this box.

    The confinement is lexical for exactly this reason — the scan already
    follows such links when it walks the default root, so refusing a sub-path
    through one would break a real setup to close nothing.
    """
    real = tmp_path / "nas_share" / "M_99"
    real.mkdir(parents=True)
    link = Path(data_root) / "incoming" / "M_99"
    link.symlink_to(real, target_is_directory=True)

    r = client.post("/api/scan", json={"root": str(link)})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"
