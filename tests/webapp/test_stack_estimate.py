"""Tests for the pre-run stack sizing endpoint (GET .../stack-estimate)."""

from __future__ import annotations


def test_estimate_basic_reference_canvas(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-estimate")
    assert r.status_code == 200
    data = r.json()
    # The synthetic frames are 480×320 and share a footprint → reference canvas.
    assert data["canvas_w"] == 480
    assert data["canvas_h"] == 320
    assert data["output_w"] == 480
    assert data["output_h"] == 320
    assert data["is_mosaic"] is False
    assert data["n_frames"] == 3
    assert data["peak_bytes"] > 0
    assert data["budget_bytes"] > 0
    # A tiny canvas never blows the budget.
    assert data["would_exceed"] is False
    assert data["peak_gb"] == round(data["peak_bytes"] / 1e9, 2)


def test_estimate_drizzle_scales_output_and_memory(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    base = client.get(f"/api/targets/{safe}/stack-estimate").json()
    driz = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"drizzle": "true", "drizzle_scale": 2.0},
    ).json()
    # ×2 drizzle roughly doubles each output axis and multiplies memory ~4×.
    assert driz["output_w"] > base["output_w"]
    assert driz["output_h"] > base["output_h"]
    assert abs(driz["output_w"] - (480 * 2 + 1)) <= 1
    assert driz["peak_bytes"] > base["peak_bytes"] * 3


def test_estimate_matches_guard_would_exceed(client, solved_library, monkeypatch):
    """With a punishingly small budget the estimate must flag would_exceed —
    the same threshold the in-run memory guard uses."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # 480×320×3×4×4 ≈ 7.4 MB peak for the reference canvas; force a 1 MB budget.
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", str(1e-3))
    data = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert data["would_exceed"] is True


def test_estimate_suggests_smaller_drizzle_scale_when_over_budget(
    client, solved_library, monkeypatch):
    """When a drizzle run would blow the budget, the estimate offers the largest
    scale that still fits as a one-click alternative."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # ×1.0 drizzle on the 480×320 canvas ≈ 7.4 MB peak, ×2.0 ≈ 30 MB. A ~15 MB
    # budget refuses ×2.0 but leaves room for a smaller scale.
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", str(15e-3))
    data = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"drizzle": "true", "drizzle_scale": 2.0},
    ).json()
    assert data["would_exceed"] is True
    s = data["suggested_drizzle_scale"]
    assert s is not None
    assert 1.0 <= s < 2.0


def test_estimate_no_drizzle_suggestion_when_within_budget(client, solved_library):
    """A comfortably-sized drizzle run carries no suggestion."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    data = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"drizzle": "true", "drizzle_scale": 1.5},
    ).json()
    assert data["would_exceed"] is False
    assert data["suggested_drizzle_scale"] is None


def test_estimate_422_when_nothing_solved(client, built_library):
    """No plate-solved frames → a clean 422 with guidance, not a 500."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-estimate")
    assert r.status_code == 422
    assert "solve" in r.json()["detail"].lower()


def test_estimate_unknown_target_404(client):
    r = client.get("/api/targets/does_not_exist/stack-estimate")
    assert r.status_code == 404
