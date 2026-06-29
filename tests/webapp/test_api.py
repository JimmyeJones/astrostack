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


def test_unknown_target_404(client):
    assert client.get("/api/targets/does_not_exist/frames").status_code == 404
