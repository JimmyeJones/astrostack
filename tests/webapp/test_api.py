"""API surface tests against a real library/project (no ASTAP needed)."""

from __future__ import annotations


def test_health_and_system(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    r = client.get("/api/system")
    assert r.status_code == 200
    body = r.json()
    assert "cpu_count" in body and "astap" in body
    # Memory info lets the UI warn when the stack budget exceeds available RAM.
    assert "memory" in body
    mem = body["memory"]
    assert isinstance(mem, dict)
    # On Linux both fields are present and sane; on other platforms it's {}.
    if mem:
        for k in ("total_gb", "available_gb"):
            if k in mem:
                assert mem[k] > 0
    # Watched-folder readiness lets the Dashboard warn upfront when the incoming
    # or library folder is missing/unwritable. In a healthy install (dirs created
    # at boot) both report present + writable.
    assert "folders" in body
    fol = body["folders"]
    for key in ("incoming", "library"):
        assert key in fol
        assert fol[key]["exists"] is True
        assert fol[key]["writable"] is True
        assert isinstance(fol[key]["path"], str)


def test_folder_status_reports_a_missing_and_a_present_folder(tmp_path):
    # Unit-test the helper directly: a healthy install always has its dirs (so the
    # endpoint test above can't exercise the missing case), but a vanished/unmounted
    # mount must report exists=False so the Dashboard banner can fire.
    from webapp.routers.system import _folder_status

    missing = _folder_status(tmp_path / "not_here")
    assert missing["exists"] is False and missing["writable"] is False

    present = _folder_status(tmp_path)
    assert present["exists"] is True and present["writable"] is True


def test_astap_test_no_frames_is_clean(client):
    # With no ingested frames the self-test returns a clean message, not a 500.
    r = client.post("/api/system/astap-test")
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_clear_jobs_endpoint(client):
    r = client.post("/api/jobs/clear")
    assert r.status_code == 200
    assert "removed" in r.json()


def test_list_targets(client, built_library):
    r = client.get("/api/targets")
    assert r.status_code == 200
    names = {t["safe_name"] for t in r.json()}
    assert {"M_42", "NGC_7000"} <= names
    for t in r.json():
        assert t["n_frames"] >= 1


def test_list_and_sort_frames(client, built_library):
    r = client.get("/api/targets/M_42/frames")
    assert r.status_code == 200
    frames = r.json()
    assert len(frames) == 3
    # Sorting by id desc should reverse order.
    r2 = client.get("/api/targets/M_42/frames", params={"sort": "id", "order": "desc"})
    ids = [f["id"] for f in r2.json()]
    assert ids == sorted(ids, reverse=True)


def test_accept_reject_frame(client, built_library):
    frames = client.get("/api/targets/M_42/frames").json()
    fid = frames[0]["id"]
    r = client.patch(f"/api/targets/M_42/frames/{fid}", json={"accept": False})
    assert r.status_code == 200
    body = r.json()
    assert body["accept"] is False
    assert body["user_override"] is True
    assert body["reject_reason"] == "user"
    # Re-accept.
    r = client.patch(f"/api/targets/M_42/frames/{fid}", json={"accept": True})
    assert r.json()["accept"] is True


def test_bulk_reject_worst(client, built_library):
    # Give frames distinct fwhm so "worst" is well-defined.
    lib_frames = client.get("/api/targets/M_42/frames").json()
    assert len(lib_frames) == 3
    r = client.post(
        "/api/targets/M_42/frames/bulk",
        json={"action": "reject_worst", "metric": "id", "fraction": 0.34},
    )
    # 'id' isn't an allowed metric -> validation error (422). Use a valid one:
    assert r.status_code == 422

    r = client.post(
        "/api/targets/M_42/frames/bulk",
        json={"action": "reject", "ids": [lib_frames[0]["id"]]},
    )
    assert r.status_code == 200
    assert r.json()["changed"] == 1


def test_bulk_reject_worst_by_transparency(client, built_library, data_root):
    from seestack.io.library import Library

    frames = client.get("/api/targets/M_42/frames").json()
    assert len(frames) == 3
    # Give the three frames distinct transparency scores; the lowest is the haziest.
    scores = {frames[0]["id"]: 900.0, frames[1]["id"]: 100.0, frames[2]["id"]: 500.0}
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            for fid, s in scores.items():
                proj.update_frame(fid, transparency_score=s)
        finally:
            proj.close()
    finally:
        lib.close()

    # Reject the worst ~1/3 by transparency: the single lowest-transparency frame.
    r = client.post(
        "/api/targets/M_42/frames/bulk",
        json={"action": "reject_worst", "metric": "transparency_score", "fraction": 0.34},
    )
    assert r.status_code == 200
    assert r.json()["changed"] == 1
    after = {f["id"]: f for f in client.get("/api/targets/M_42/frames").json()}
    haziest = frames[1]["id"]  # score 100.0
    assert after[haziest]["accept"] is False
    assert after[haziest]["reject_reason"] == "bulk:transparency_score"
    # The clearer frames stay accepted.
    assert after[frames[0]["id"]]["accept"] is True
    assert after[frames[2]["id"]]["accept"] is True


def test_bulk_reject_streaked(client, built_library, data_root):
    from seestack.io.library import Library

    frames = client.get("/api/targets/M_42/frames").json()
    assert len(frames) == 3
    # Flag one accepted frame as streaked via the DB (QC would normally set it).
    target_id = frames[0]["id"]
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            proj.update_frame(target_id, streak_detected=True)
        finally:
            proj.close()
    finally:
        lib.close()

    # Only the streaked, accepted frame is rejected.
    r = client.post(
        "/api/targets/M_42/frames/bulk",
        json={"action": "reject_streaked"},
    )
    assert r.status_code == 200
    assert r.json()["changed"] == 1

    after = {f["id"]: f for f in client.get("/api/targets/M_42/frames").json()}
    assert after[target_id]["accept"] is False
    assert after[target_id]["reject_reason"] == "bulk:streaked"
    assert after[target_id]["user_override"] is True

    # Idempotent: a second call rejects nothing (no accepted streaked frames left).
    r = client.post(
        "/api/targets/M_42/frames/bulk",
        json={"action": "reject_streaked"},
    )
    assert r.json()["changed"] == 0


def test_trailed_frame_ids_flags_strong_outliers():
    """The trailed-outlier helper flags only strong, above-floor eccentricity
    outliers, needs a floor of measured frames, and ignores unmeasured ones."""
    from types import SimpleNamespace

    from webapp.routers.frames import trailed_frame_ids

    def frame(fid, ecc):
        return SimpleNamespace(id=fid, eccentricity_median=ecc)

    # A tight, round set with one badly-trailed sub: only that one is flagged.
    tight = [frame(i, 0.2 + 0.01 * (i % 3)) for i in range(10)]
    tight.append(frame(99, 0.85))
    assert trailed_frame_ids(tight) == [99]

    # Below the minimum measured-frame count → never flags (stats too noisy).
    assert trailed_frame_ids([frame(1, 0.2), frame(2, 0.9)]) == []

    # A frame that is a >3·MAD outlier but still below the 0.6 absolute floor is
    # not "trailed" — its stars aren't actually elongated.
    below_floor = [frame(i, 0.10 + 0.005 * (i % 2)) for i in range(10)]
    below_floor.append(frame(50, 0.45))
    assert trailed_frame_ids(below_floor) == []

    # Frames without a measured eccentricity don't count toward the floor and
    # are never flagged.
    assert trailed_frame_ids([frame(i, None) for i in range(10)]) == []


def test_bulk_reject_trailed_needs_enough_frames(client, built_library):
    # The default fixture has 3 frames — below the robust-stats floor — so
    # reject_trailed is a safe no-op rather than nuking a tiny set.
    r = client.post(
        "/api/targets/M_42/frames/bulk",
        json={"action": "reject_trailed"},
    )
    assert r.status_code == 200
    assert r.json()["changed"] == 0


def test_bulk_returns_changed_ids_for_undo(client, built_library):
    frames = client.get("/api/targets/M_42/frames").json()
    ids = [f["id"] for f in frames[:2]]
    # A bulk reject reports exactly which frame ids it touched...
    r = client.post(
        "/api/targets/M_42/frames/bulk",
        json={"action": "reject", "ids": ids},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["changed"] == 2
    assert sorted(body["changed_ids"]) == sorted(ids)
    # ...so the client can undo by re-accepting exactly those ids.
    r = client.post(
        "/api/targets/M_42/frames/bulk",
        json={"action": "accept", "ids": body["changed_ids"]},
    )
    assert r.json()["changed"] == 2
    after = {f["id"]: f for f in client.get("/api/targets/M_42/frames").json()}
    for fid in ids:
        assert after[fid]["accept"] is True
        assert after[fid]["reject_reason"] is None


def test_reject_summary_groups_by_reason(client, built_library, data_root):
    from seestack.io.library import Library

    frames = client.get("/api/targets/M_42/frames").json()
    # Nothing rejected yet.
    r = client.get("/api/targets/M_42/frames/reject-summary")
    assert r.status_code == 200
    assert r.json() == {"counts": {}, "total": 0, "solve_setup_problem": None}

    # A manual reject (reason "user")...
    client.post("/api/targets/M_42/frames/bulk",
                json={"action": "reject", "ids": [frames[0]["id"]]})
    # ...and a QC-style reject set directly (QC would normally write this reason).
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            proj.update_frame(frames[1]["id"], accept=False, reject_reason="qc:fwhm")
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get("/api/targets/M_42/frames/reject-summary").json()
    assert body["total"] == sum(body["counts"].values()) == 2
    assert body["counts"].get("user") == 1
    assert body["counts"].get("qc:fwhm") == 1
    # Ordinary rejects are not a solve-setup problem.
    assert body["solve_setup_problem"] is None
    # 'reject-summary' is a literal path, not captured as a frame id.
    assert client.get("/api/targets/M_42/frames/reject-summary").status_code == 200


def test_reject_summary_flags_solve_setup_problem(client, built_library, data_root):
    """When ASTAP's star database is missing, every frame's solve fails the same
    way; the summary surfaces one server-side `solve_setup_problem` classification
    (reliable for the database case, not just the deterministic astap-missing one)."""
    from seestack.io.library import Library

    frames = client.get("/api/targets/M_42/frames").json()
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            # Reasons as written by apply_solve_result_to_db for a setup failure:
            # a canonical, un-truncatable "no star database" token.
            for f in frames[:2]:
                proj.update_frame(f["id"], accept=False,
                                  reject_reason="solve_failed:no star database")
            # An unrelated per-frame reject shouldn't confuse the classifier.
            proj.update_frame(frames[2]["id"], accept=False, reject_reason="qc:fwhm")
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get("/api/targets/M_42/frames/reject-summary").json()
    assert body["solve_setup_problem"] == {"kind": "database", "frames": 2}


def test_frame_preview_renders_png(client, built_library):
    frames = client.get("/api/targets/M_42/frames").json()
    fid = frames[0]["id"]
    r = client.get(f"/api/targets/M_42/frames/{fid}/preview", params={"size": 128})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    etag = r.headers.get("etag")
    assert etag
    # Conditional request → 304.
    r2 = client.get(
        f"/api/targets/M_42/frames/{fid}/preview",
        params={"size": 128}, headers={"if-none-match": etag},
    )
    assert r2.status_code == 304


def test_frame_preview_rejects_invalid_bayer_pattern(client, built_library):
    # `bayer` ends up in the cache filename, so it must be validated against
    # the fixed set of real patterns rather than accepted as free text (which
    # would let a value like "../../x" reach a filesystem path join).
    frames = client.get("/api/targets/M_42/frames").json()
    fid = frames[0]["id"]
    r = client.get(f"/api/targets/M_42/frames/{fid}/preview",
                    params={"bayer": "../../../../etc/passwd"})
    assert r.status_code == 400


def test_stack_options_schema(client):
    r = client.get("/api/stack/options/schema")
    assert r.status_code == 200
    fields = r.json()
    keys = {f["key"] for f in fields}
    assert "sigma_kappa" in keys
    groups = {f["group"] for f in fields}
    assert groups == {"simple", "advanced"}


def test_stack_defaults_roundtrip(client, built_library):
    r = client.get("/api/targets/M_42/stack-defaults")
    assert r.status_code == 200
    assert "sigma_kappa" in r.json()
    r = client.put("/api/targets/M_42/stack-defaults", json={"sigma_kappa": 2.0})
    assert r.json()["sigma_kappa"] == 2.0
    assert client.get("/api/targets/M_42/stack-defaults").json()["sigma_kappa"] == 2.0


def test_settings_roundtrip(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["auto_solve"] is True
    r = client.put("/api/settings", json={"auto_stack": True, "watch_quiet_period_s": 45})
    body = r.json()
    assert body["auto_stack"] is True
    assert body["watch_quiet_period_s"] == 45


def test_settings_put_strips_calibration_paths_from_default_stack_options(client):
    # Calibration master paths are resolved server-side from master ids and must
    # never be persisted from raw client input — a settings PUT drops them from
    # default_stack_options (keeping legitimate form fields).
    r = client.put("/api/settings", json={"default_stack_options": {
        "dark_path": "/etc/shadow", "flat_path": "/evil.fits",
        "bias_path": "/x", "flat_dark_path": "/y", "sigma_kappa": 2.5}})
    assert r.status_code == 200
    stored = client.get("/api/settings").json()["default_stack_options"]
    assert stored.get("sigma_kappa") == 2.5
    for k in ("dark_path", "flat_path", "bias_path", "flat_dark_path"):
        assert k not in stored, f"{k} should have been stripped, got {stored}"


def test_settings_rejects_out_of_bounds_values(client):
    # A zero timeout would make every ASTAP solve fail instantly; a zero
    # quiet-period would defeat the half-written-file guard.
    r = client.put("/api/settings", json={"astap_timeout_s": 0})
    assert r.status_code == 422
    r = client.put("/api/settings", json={"watch_quiet_period_s": -5})
    assert r.status_code == 422
    r = client.put("/api/settings", json={"cpu_workers": 0})
    assert r.status_code == 422
    # Rejected patches must not partially apply.
    assert client.get("/api/settings").json()["astap_timeout_s"] == 60.0


def test_job_history_limit_defaults_and_syncs_to_the_running_manager(client):
    # Defaults to the long-standing hard-coded cap, and the running JobManager
    # was created with it.
    assert client.get("/api/settings").json()["job_history_limit"] == 200
    assert client.app.state.job_manager.max_history == 200
    # Changing it takes effect live (no restart) on the running manager.
    r = client.put("/api/settings", json={"job_history_limit": 500})
    assert r.status_code == 200 and r.json()["job_history_limit"] == 500
    assert client.app.state.job_manager.max_history == 500
    # Out-of-bounds values are rejected and don't partially apply.
    assert client.put("/api/settings", json={"job_history_limit": 0}).status_code == 422
    assert client.app.state.job_manager.max_history == 500


def test_settings_export_excludes_secrets_and_host_paths(client):
    r = client.get("/api/settings/export")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    body = r.json()
    # Secrets and host-specific paths are never in a backup.
    for k in ("auth_password_hash", "auth_salt", "auth_username",
              "data_root", "incoming_dir", "library_root", "astap_path"):
        assert k not in body
    # Normal tunables are present.
    assert "auto_stack" in body
    assert "watch_quiet_period_s" in body


def test_settings_import_roundtrip(client):
    # Change a couple of values, export, mutate live, then restore the backup.
    client.put("/api/settings", json={"auto_stack": True, "watch_quiet_period_s": 45})
    backup = client.get("/api/settings/export").json()

    client.put("/api/settings", json={"auto_stack": False, "watch_quiet_period_s": 99})
    assert client.get("/api/settings").json()["watch_quiet_period_s"] == 99

    r = client.post("/api/settings/import", json=backup)
    assert r.status_code == 200
    restored = client.get("/api/settings").json()
    assert restored["auto_stack"] is True
    assert restored["watch_quiet_period_s"] == 45


def test_settings_import_ignores_secrets_host_paths_and_unknown(client):
    before = client.get("/api/settings").json()
    r = client.post("/api/settings/import", json={
        "auto_qc": False,                       # applied
        "auth_password_hash": "sneaky",         # ignored (secret)
        "data_root": "/etc",                    # ignored (host path)
        "totally_unknown_key": 1,               # ignored (unknown)
    })
    assert r.status_code == 200
    after = r.json()
    assert after["auto_qc"] is False
    assert "auth_password_hash" not in after
    # data_root is host-owned and must be untouched by an import.
    assert after["resolved_library_root"] == before["resolved_library_root"]


def test_settings_import_rejects_invalid_values(client):
    r = client.post("/api/settings/import", json={"astap_timeout_s": 0})
    assert r.status_code == 422
    # A rejected import must not partially apply.
    assert client.get("/api/settings").json()["astap_timeout_s"] == 60.0


def test_jobs_list_limit_is_clamped(client):
    # Neither an absurdly large nor a non-positive limit should error.
    assert client.get("/api/jobs", params={"limit": 10_000_000}).status_code == 200
    assert client.get("/api/jobs", params={"limit": 0}).status_code == 200
    assert client.get("/api/jobs", params={"limit": -5}).status_code == 200


def test_unknown_target_404(client):
    assert client.get("/api/targets/does_not_exist/frames").status_code == 404


def test_delete_unknown_target_404(client):
    r = client.delete("/api/targets/does_not_exist")
    assert r.status_code == 404


def test_delete_target_removes_it(client, built_library):
    assert client.get("/api/targets/M_42").status_code == 200
    r = client.delete("/api/targets/M_42")
    assert r.status_code == 200
    assert r.json() == {"deleted": "M_42", "files_removed": False}
    assert client.get("/api/targets/M_42").status_code == 404


def test_merge_unknown_destination_404(client, built_library):
    r = client.post("/api/targets/merge", json={"into": "does_not_exist", "sources": ["M_42"]})
    assert r.status_code == 404
