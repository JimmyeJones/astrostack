"""Storage accounting + housekeeping: usage report, cache clear, run prune."""

from __future__ import annotations

import json

from seestack.core.cache import CacheManager
from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _target_dir(data_root, safe):
    return data_root / "library" / "targets" / safe


def test_storage_reports_cache_usage_and_clears(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    tdir = _target_dir(solved_library, safe)
    cm = CacheManager(tdir)
    cm.ensure_dirs()
    (cm.stage1 / "frame_000001.fit").write_bytes(b"x" * 2048)
    (cm.stage2 / "frame_000001.f16.mmap").write_bytes(b"y" * 1024)

    r = client.get("/api/storage")
    assert r.status_code == 200
    row = next(t for t in r.json()["targets"] if t["safe"] == safe)
    assert row["stage1_bytes"] == 2048
    assert row["stage2_bytes"] == 1024
    assert row["cache_bytes"] >= 3072
    assert r.json()["cache_bytes"] >= 3072

    # Clear just stage1.
    c = client.post(f"/api/targets/{safe}/cache/clear", params={"stage": "stage1"})
    assert c.status_code == 200
    assert "stage1" in c.json()["cleared"]
    assert not (cm.stage1 / "frame_000001.fit").exists()
    # stage2 untouched.
    assert (cm.stage2 / "frame_000001.f16.mmap").exists()

    # Clear all wipes the rest.
    client.post(f"/api/targets/{safe}/cache/clear", params={"stage": "all"})
    assert not (cm.stage2 / "frame_000001.f16.mmap").exists()


def test_cache_clear_bad_stage_400(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.post(f"/api/targets/{safe}/cache/clear", params={"stage": "bogus"})
    assert r.status_code == 400


def _add_run(data_root, safe, ts, basename):
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename=basename,
                fits_path=None, tiff_path=None, preview_path=None,
                n_frames_used=1, canvas_h=10, canvas_w=10,
                coverage_min=1, coverage_max=1, options_json=json.dumps({}),
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def test_prune_keeps_newest(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_run(solved_library, safe, "2026-01-01T00:00:00Z", "old1")
    _add_run(solved_library, safe, "2026-02-01T00:00:00Z", "old2")
    _add_run(solved_library, safe, "2026-03-01T00:00:00Z", "newest")

    r = client.post(f"/api/targets/{safe}/stack-runs/prune", json={"keep": 1})
    assert r.status_code == 200
    assert len(r.json()["deleted"]) == 2

    remaining = client.get(f"/api/targets/{safe}/stack-runs").json()
    assert len(remaining) == 1
    assert remaining[0]["output_basename"] == "newest"


def test_prune_requires_argument(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.post(f"/api/targets/{safe}/stack-runs/prune", json={})
    assert r.status_code == 400
