"""Calibration master store + endpoints."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from astropy.io import fits

from webapp import calibration


def _wait_job(client, job_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def _write_darks(folder: Path, n=4, shape=(8, 8), level=100.0):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        hdu = fits.PrimaryHDU(data=np.full(shape, level, dtype=np.float32))
        hdu.header["EXPTIME"] = 30.0
        hdu.header["GAIN"] = 80.0
        hdu.header["BAYERPAT"] = "RGGB"
        hdu.writeto(folder / f"dark_{i}.fit", overwrite=True)


def test_store_register_list_resolve_delete(tmp_path):
    from seestack.calibrate.masters import MasterMeta

    root = tmp_path / "lib"
    arr = np.full((4, 4), 42.0, dtype=np.float32)
    meta = MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0)
    entry = calibration.register_master(root, name="My Dark", array=arr, meta=meta)
    assert entry["id"] == 1
    assert (calibration.calibration_dir(root) / entry["filename"]).exists()

    listed = calibration.list_masters(root)
    assert len(listed) == 1 and listed[0]["exists"] is True

    dark_path, flat_path = calibration.resolve_master_paths(root, 1, None)
    assert dark_path and Path(dark_path).exists()
    assert flat_path is None

    assert calibration.delete_master(root, 1) is True
    assert calibration.list_masters(root) == []


def test_resolve_unknown_raises(tmp_path):
    import pytest

    with pytest.raises(KeyError):
        calibration.resolve_master_paths(tmp_path / "lib", 999, None)


def test_build_master_endpoint(client, data_root, tmp_path):
    darks = tmp_path / "darks"
    _write_darks(darks)

    r = client.post("/api/calibration/masters", json={
        "kind": "dark", "source_dir": str(darks), "name": "Session A",
        "method": "median",
    })
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert job["result"]["kind"] == "dark"
    assert job["result"]["n_frames"] == 4

    listed = client.get("/api/calibration/masters").json()
    assert len(listed) == 1
    mid = listed[0]["id"]
    assert listed[0]["name"] == "Session A"

    # Delete it.
    d = client.delete(f"/api/calibration/masters/{mid}")
    assert d.status_code == 200
    assert client.get("/api/calibration/masters").json() == []


def test_build_master_bad_kind(client, tmp_path):
    darks = tmp_path / "d"
    _write_darks(darks, n=1)
    r = client.post("/api/calibration/masters",
                    json={"kind": "nope", "source_dir": str(darks)})
    assert r.status_code == 400


def test_build_master_missing_dir(client):
    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": "/no/such/folder"})
    assert r.status_code == 400


def test_stack_rejects_unknown_master(client, solved_library):
    # Triggering a stack with a non-existent dark master id → 404.
    r = client.post("/api/targets/M_42/stack", json={"dark_master_id": 4242})
    assert r.status_code == 404


def test_stack_with_calibration_master_runs(client, solved_library, tmp_path):
    # Build a master dark matching the solved frames' raw size (320×480) and
    # stack with it — the full resolve → engine path must complete.
    darks = tmp_path / "cdarks"
    _write_darks(darks, n=3, shape=(320, 480), level=5.0)
    r = client.post("/api/calibration/masters",
                    json={"kind": "dark", "source_dir": str(darks), "method": "median"})
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done"
    mid = client.get("/api/calibration/masters").json()[0]["id"]

    s = client.post("/api/targets/M_42/stack", json={"dark_master_id": mid})
    assert s.status_code == 200
    sjob = _wait_job(client, s.json()["job_id"], timeout=120)
    assert sjob["state"] == "done", sjob
    # The run record should remember which dark was applied.
    runs = client.get("/api/targets/M_42/stack-runs").json()
    assert len(runs) >= 1
