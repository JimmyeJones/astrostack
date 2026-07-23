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


def test_storage_survives_one_unreadable_target_dir(client, solved_library, monkeypatch):
    """A target whose cache dir is unreadable (a NAS mount gone permission-denied,
    a dataset unmounted mid-scan) must not 500 the whole storage page — the other
    targets must still list, matching gallery/sky/stats per-target resilience.

    Simulated by making the cache scan raise ``OSError`` (chmod can't be used —
    the test suite runs as root, which bypasses file permissions)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]

    def _boom(self, stage):
        raise OSError("[Errno 13] Permission denied")

    monkeypatch.setattr(CacheManager, "stats", _boom)

    r = client.get("/api/storage")
    assert r.status_code == 200
    body = r.json()
    row = next(t for t in body["targets"] if t["safe"] == safe)
    # Unreadable cache parts report 0 rather than crashing the listing.
    assert row["stage1_bytes"] == 0
    assert row["stage2_bytes"] == 0
    # The target is still listed (not dropped), and totals are still returned.
    assert "disk" in body


def test_storage_reports_nightly_growth_estimate(client, solved_library):
    """The disk payload carries the additive fields the 'nights left' headroom
    line needs: free_bytes plus a nightly_bytes growth estimate once there are
    ≥2 capture nights of frames on disk."""
    # Spread the fixture's frames across two capture nights so the estimate has
    # enough history (a single night reports null by design).
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                for i, f in enumerate(proj.iter_frames()):
                    night = "2026-07-20" if i % 2 == 0 else "2026-07-21"
                    proj.update_frame(f.id, timestamp_utc=f"{night}T22:0{i % 6}:00Z")
            finally:
                proj.close()
    finally:
        lib.close()

    disk = client.get("/api/storage").json()["disk"]
    assert "free_bytes" in disk
    assert "nightly_bytes" in disk
    # Two nights of frames on a non-empty library → a positive estimate.
    assert disk["nightly_bytes"] is not None
    assert disk["nightly_bytes"] > 0


def test_cache_clear_bad_stage_400(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.post(f"/api/targets/{safe}/cache/clear", params={"stage": "bogus"})
    assert r.status_code == 400


def _add_run(data_root, safe, ts, basename, options=None):
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename=basename,
                fits_path=None, tiff_path=None, preview_path=None,
                n_frames_used=1, canvas_h=10, canvas_w=10,
                coverage_min=1, coverage_max=1,
                options_json=json.dumps(options or {}),
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


def test_stack_runs_expose_options_for_combine_badge(client, solved_library):
    """The stack-runs list carries each run's stored options so the History card
    can badge how it was combined (σ-clip / min-max / drizzle)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_run(solved_library, safe, "2026-04-01T00:00:00Z", "sigma",
             options={"sigma_clip": True, "sigma_kappa": 3.0})
    _add_run(solved_library, safe, "2026-04-02T00:00:00Z", "minmax",
             options={"min_max_reject": True})

    runs = {r["output_basename"]: r
            for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs["sigma"]["options"]["sigma_clip"] is True
    assert runs["sigma"]["options"]["sigma_kappa"] == 3.0
    assert runs["minmax"]["options"]["min_max_reject"] is True


def test_stack_runs_options_defaults_empty_when_unrecorded(client, solved_library):
    """A run with no stored options (malformed / legacy) reports an empty dict,
    so the badge simply renders nothing rather than erroring."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_run(solved_library, safe, "2026-05-01T00:00:00Z", "plain", options={})
    runs = {r["output_basename"]: r
            for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs["plain"]["options"] == {}
