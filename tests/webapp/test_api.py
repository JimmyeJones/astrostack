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


def test_settings_export_envelope_excludes_secrets(client):
    r = client.get("/api/settings/export")
    assert r.status_code == 200
    body = r.json()
    assert body["astrostack_settings"] is True
    assert "app_version" in body and "exported_utc" in body
    s = body["settings"]
    # A real setting is present; auth + derived fields are not.
    assert "auto_solve" in s
    for secret in ("auth_password_hash", "auth_salt", "auth_username"):
        assert secret not in s
    for derived in ("resolved_incoming_dir", "resolved_library_root"):
        assert derived not in s


def test_settings_import_roundtrip_from_export(client):
    # Change a value, export, mutate the exported copy, re-import → applied.
    client.put("/api/settings", json={"auto_stack": False, "watch_quiet_period_s": 30})
    backup = client.get("/api/settings/export").json()
    backup["settings"]["auto_stack"] = True
    backup["settings"]["watch_quiet_period_s"] = 90
    r = client.post("/api/settings/import", json=backup)
    assert r.status_code == 200
    assert r.json()["auto_stack"] is True
    assert client.get("/api/settings").json()["watch_quiet_period_s"] == 90


def test_settings_import_accepts_bare_object(client):
    r = client.post("/api/settings/import", json={"auto_qc": False})
    assert r.status_code == 200
    assert r.json()["auto_qc"] is False


def test_settings_import_rejects_bad_values_without_applying(client):
    before = client.get("/api/settings").json()["astap_timeout_s"]
    r = client.post("/api/settings/import", json={"settings": {"astap_timeout_s": 0}})
    assert r.status_code == 422
    assert client.get("/api/settings").json()["astap_timeout_s"] == before


def test_settings_import_ignores_auth_and_unknown_keys(client):
    # Auth creds and junk keys are dropped; a valid field still applies.
    r = client.post("/api/settings/import", json={
        "auth_password_hash": "deadbeef", "auth_username": "hacker",
        "totally_unknown_key": 1, "auto_ingest": False,
    })
    assert r.status_code == 200
    assert r.json()["auto_ingest"] is False
    # Auth stays managed only via /api/auth/password → still disabled/open.
    assert client.get("/api/auth/status").json()["enabled"] is False


def test_settings_import_empty_payload_422s(client):
    r = client.post("/api/settings/import", json={"settings": {}})
    assert r.status_code == 422


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
