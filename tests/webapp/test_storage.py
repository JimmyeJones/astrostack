"""Storage accounting + housekeeping: usage report, cache clear, run prune."""

from __future__ import annotations

import json

import pytest

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


def test_disk_figures_are_served_as_raw_bytes_too(client, solved_library):
    """Every endpoint that reports free disk serves the byte count beside its
    rounded ``*_gb``.

    The ``*_gb`` fields are decimal (1e9) while every size the UI prints is
    binary (1024**3), so rendering one figure from each had the Storage page
    saying "23 GB free on disk" directly above "21 GB free — not enough imaging
    history yet". The client now formats the bytes; the old fields stay for
    anything already reading them.
    """
    for path in ("/api/storage", "/api/stats", "/api/system"):
        disk = client.get(path).json()["disk"]
        assert "free_gb" in disk, path          # not removed — upgrade-safe
        assert isinstance(disk["free_bytes"], int), path
        assert disk["free_bytes"] > 0, path
        # The two must describe the same disk: decimal GB of the byte count.
        assert abs(disk["free_bytes"] / 1e9 - disk["free_gb"]) < 0.2, path


def test_stats_and_system_agree_with_storage_on_free_disk(client, solved_library):
    """Three endpoints, one disk — a beginner sees these figures on three
    different screens and must not have to reconcile them."""
    seen = {p: client.get(p).json()["disk"]["free_bytes"]
            for p in ("/api/storage", "/api/stats", "/api/system")}
    lo, hi = min(seen.values()), max(seen.values())
    assert hi - lo < 50_000_000, seen   # same filesystem, moments apart


# ---- "your subs in incoming/ are the only copy" ---------------------------


def test_storage_counts_the_raw_subs_in_incoming(client, solved_library):
    """The page's honesty line needs the owner's own numbers: how many subs sit
    in ``incoming/`` and how much they weigh."""
    body = client.get("/api/storage").json()
    # The conftest library is two targets of three frames, all ingested from
    # incoming/ (copy_to_cache off), so every frame's source is under there.
    assert body["incoming_frames"] == 6
    assert body["incoming_bytes"] > 0
    assert body["incoming_unsized_frames"] == 0
    assert body["incoming_copied"] is False

    # …and the bytes are the real sizes of the files on disk, not a guess.
    on_disk = sum(p.stat().st_size
                  for p in (solved_library / "incoming").rglob("*.fit"))
    assert body["incoming_bytes"] == on_disk


def test_storage_counts_frames_whose_size_predates_the_column(client, solved_library):
    """Rows ingested before ``source_size_bytes`` existed carry no size, so the
    byte total is a floor — reported separately so the page can say "at least"."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        entry = lib.list_targets()[0]
        proj = lib.open_target(entry.safe_name)
        try:
            first = next(iter(proj.iter_frames()))
            proj.update_frame(first.id, source_size_bytes=None)
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get("/api/storage").json()
    assert body["incoming_frames"] == 6          # still counted…
    assert body["incoming_unsized_frames"] == 1  # …but its bytes are unknown


def test_storage_never_touches_the_incoming_folder_to_count_it(
        client, solved_library, monkeypatch):
    """AGENTS.md §10: the owner's only copy of every sub lives in ``incoming/``.
    The count comes from the frame rows the app already wrote, so answering must
    not walk, open or even ``stat`` anything under there."""
    import os

    incoming = str((solved_library / "incoming").resolve())
    one = next((solved_library / "incoming").rglob("*.fit"))   # before arming

    def _forbid(name):
        def guard(path, *a, **kw):
            if str(path).startswith(incoming):
                raise AssertionError(f"{name} touched incoming/: {path}")
            return guard.real(path, *a, **kw)
        guard.real = getattr(os, name)
        return guard

    for name in ("stat", "listdir", "scandir"):
        monkeypatch.setattr(os, name, _forbid(name))
    monkeypatch.setattr("builtins.open", (lambda real: (
        lambda path, *a, **kw: (
            _ for _ in ()).throw(AssertionError(f"opened incoming/: {path}"))
        if str(path).startswith(incoming) else real(path, *a, **kw)))(open))

    # Prove the trap is armed before trusting it (a guard that never fires would
    # make this test pass for the wrong reason).
    with pytest.raises(AssertionError):
        one.stat()
    with pytest.raises(AssertionError):
        open(one, "rb")  # noqa: SIM115 — the guard raises; no handle is ever made

    body = client.get("/api/storage").json()
    assert body["incoming_frames"] == 6


def test_storage_reports_the_cache_copy_setting(client, solved_library, monkeypatch):
    """With ``copy_to_cache`` on the app *does* hold copies — working files that
    "Clear caches" deletes. The page draws that distinction, so the flag ships."""
    from webapp import deps

    real = deps.get_settings

    def with_copy(request):
        s = real(request)
        s.copy_to_cache = True
        return s

    monkeypatch.setattr(deps, "get_settings", with_copy)
    assert client.get("/api/storage").json()["incoming_copied"] is True


def test_storage_says_nothing_about_incoming_on_a_fresh_install(client, data_root):
    """No ingested frames → zero, and the page's sentence self-hides."""
    body = client.get("/api/storage").json()
    assert body["incoming_frames"] == 0
    assert body["incoming_bytes"] == 0
