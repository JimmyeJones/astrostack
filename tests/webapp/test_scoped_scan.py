"""``POST /api/scan`` with a ``root`` inside incoming scans **that folder**.

The field always read like a "re-scan just this folder" shortcut and was not
one: ``scan_and_organize`` derives each target's name from the file's path
*relative to the scan root*, so a root pointed **at** a target's folder left
nothing to derive from and every frame in it landed in ``Unsorted``.

The user-visible reason to fix it is the folder the Seestar convention skips as
"the device's own finished picture". When such a folder holds files the naming
cannot vouch for — the owner's library has one of exactly that shape — the scan
reports it, and the only recovery on offer was to *rename the folder*, inside
``incoming/``, where the owner's raws exist in one copy and nowhere else
(AGENTS.md §10). A scoped scan brings the folder in without touching a byte of
it.

Confinement itself is ``test_scan_root_confined.py``; this file is about what
the scan then does.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from tests.synth import write_seestar_fits


def _wait_job(client, job_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def _scan(client, root=None):
    payload = {"root": str(root)} if root is not None else {}
    r = client.post("/api/scan", json=payload)
    assert r.status_code == 200, r.text
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body
    return body["result"]


def test_scanning_one_folder_files_it_under_that_folder_not_unsorted(
        client, data_root):
    result = _scan(client, data_root / "incoming" / "M_42")
    assert result["folder"] == "M_42"
    names = {t["safe_name"] for t in client.get("/api/targets").json()}
    assert "M_42" in names
    assert "Unsorted" not in names


def test_the_plain_scan_button_is_unchanged(client, data_root):
    """The default path — no ``root`` — must read byte-for-byte as before: no
    ``folder`` key, and the whole incoming folder walked as a folder of
    folders."""
    result = _scan(client)
    assert "folder" not in result
    assert "device_pictures_skipped" not in result
    assert Path(result["root"]) == data_root / "incoming"
    names = {t["safe_name"] for t in client.get("/api/targets").json()}
    assert {"M_42", "NGC_7000"} <= names


def test_naming_the_incoming_folder_itself_is_still_the_whole_scan(
        client, data_root):
    """``root`` set to incoming is the same request as no ``root`` — it must not
    become a scoped scan that files everything under one target named after the
    incoming folder."""
    result = _scan(client, data_root / "incoming")
    assert "folder" not in result
    names = {t["safe_name"] for t in client.get("/api/targets").json()}
    assert {"M_42", "NGC_7000"} <= names
    assert "incoming" not in names


def test_bringing_a_skipped_folder_in_reports_its_path_and_then_ingests_it(
        client, data_root):
    """End to end, the way the Jobs page walks it: the scan names the folder it
    passed over *and where it is*, and posting that path back brings it in."""
    incoming = Path(data_root) / "incoming"
    (incoming / "NGC_6888_sub").mkdir(parents=True)
    write_seestar_fits(incoming / "NGC_6888_sub" / "Light_0001.fit",
                       width=480, height=320, n_stars=10, seed=1)
    bare = incoming / "NGC_6888"
    bare.mkdir()
    for i in range(2):
        write_seestar_fits(bare / f"Light_{i:04d}.fit",
                           width=480, height=320, n_stars=10, seed=10 + i)
    write_seestar_fits(bare / "Stacked.fit", width=480, height=320,
                       n_stars=10, seed=99)

    reported = _scan(client)["skipped_folders"]
    assert [(s["name"], s["n_files"], s["n_unrecognised"]) for s in reported] \
        == [("NGC_6888", 3, 2)]
    path = reported[0]["path"]
    assert Path(path) == bare

    result = _scan(client, path)
    assert result["folder"] == "NGC_6888"
    # The device's own picture is left out; the two real subs come in.
    assert result["device_pictures_skipped"] == 1
    assert result["scanned"] == 2
    # And they joined the target of that name rather than forking a new one.
    frames = client.get("/api/targets/NGC_6888/frames?limit=100").json()
    names = {f["name"] for f in frames}
    assert "Stacked.fit" not in names
    assert {"Light_0000.fit", "Light_0001.fit"} <= names


def test_a_scoped_scan_does_not_touch_the_folder_it_reads(client, data_root):
    """AGENTS.md §10 — read and create-new only under ``incoming/``. Nothing in
    this path renames, moves or rewrites, so the folder is byte-identical."""
    folder = Path(data_root) / "incoming" / "M_42"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(folder.iterdir())}
    _scan(client, folder)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(folder.iterdir())}
    assert after == before
