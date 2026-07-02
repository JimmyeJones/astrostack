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

    dark_path, flat_path, flat_dark_path = calibration.resolve_master_paths(root, 1, None)
    assert dark_path and Path(dark_path).exists()
    assert flat_path is None
    assert flat_dark_path is None

    assert calibration.delete_master(root, 1) is True
    assert calibration.list_masters(root) == []


def test_resolve_unknown_raises(tmp_path):
    import pytest

    with pytest.raises(KeyError):
        calibration.resolve_master_paths(tmp_path / "lib", 999, None)


def test_resolve_flat_dark_master(tmp_path):
    from seestack.calibrate.masters import MasterMeta

    root = tmp_path / "lib"
    arr = np.full((4, 4), 5.0, dtype=np.float32)
    flat = calibration.register_master(
        root, name="Flat", array=np.full((4, 4), 100.0, dtype=np.float32),
        meta=MasterMeta("flat", 5, 4, 4, "median"))
    fd = calibration.register_master(
        root, name="FlatDark", array=arr, meta=MasterMeta("dark", 5, 4, 4, "median"))

    dark_path, flat_path, flat_dark_path = calibration.resolve_master_paths(
        root, None, flat["id"], fd["id"])
    assert dark_path is None
    assert flat_path and Path(flat_path).exists()
    assert flat_dark_path and Path(flat_dark_path).exists()


def test_recommend_masters_picks_best_match():
    # Two darks at different exposures; the target shot 30 s subs → the 30 s
    # dark must win. Flats are exposure-independent → matched by gain instead.
    masters = [
        {"id": 1, "kind": "dark", "exposure_s": 30.0, "gain": 80.0, "exists": True},
        {"id": 2, "kind": "dark", "exposure_s": 120.0, "gain": 80.0, "exists": True},
        {"id": 3, "kind": "flat", "exposure_s": 2.0, "gain": 80.0, "exists": True},
        {"id": 4, "kind": "flat", "exposure_s": 2.0, "gain": 200.0, "exists": True},
    ]
    rec = calibration.recommend_masters(masters, exposure_s=30.0, gain=80.0)
    assert rec["dark_master_id"] == 1          # exposure-matched dark
    assert rec["flat_master_id"] == 3          # gain-matched flat
    # the well-matched dark scores higher than the exposure-mismatched one
    assert rec["scores"][1] > rec["scores"][2]
    assert rec["scores"][3] > rec["scores"][4]


def test_recommend_masters_skips_missing_and_handles_empty():
    # A master whose file is gone must never be recommended.
    masters = [{"id": 1, "kind": "dark", "exposure_s": 30.0, "exists": False}]
    rec = calibration.recommend_masters(masters, exposure_s=30.0)
    assert rec["dark_master_id"] is None
    assert rec["flat_master_id"] is None
    # No masters at all → clean empty result, no crash.
    empty = calibration.recommend_masters([], exposure_s=30.0)
    assert empty["dark_master_id"] is None and empty["scores"] == {}


def test_calibration_suggestions_endpoint(client, solved_library):
    from seestack.calibrate.masters import MasterMeta
    from seestack.io.library import Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    # Give this target's frames a known exposure/gain.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, exposure_s=30.0, gain=80.0)
        finally:
            proj.close()
    finally:
        lib.close()

    root = solved_library / "library"
    good = calibration.register_master(
        root, name="Dark 30s", array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0, gain=80.0))
    calibration.register_master(
        root, name="Dark 120s", array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=120.0, gain=80.0))

    r = client.get(f"/api/targets/{safe}/calibration-suggestions")
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["exposure_s"] == 30.0
    assert body["dark_master_id"] == good["id"]
    assert body["n_frames"] >= 1


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
