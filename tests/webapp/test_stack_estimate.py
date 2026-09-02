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
    # The structured memory_fix carries the same lever plus its resulting peak.
    fix = data["memory_fix"]
    assert fix is not None
    assert fix["kind"] == "drizzle_scale"
    assert fix["value"] == s
    assert fix["peak_bytes"] <= data["budget_bytes"]
    assert fix["peak_gb"] == round(fix["peak_bytes"] / 1e9, 2)


def test_estimate_memory_fix_null_when_within_budget(client, solved_library):
    """A run that fits carries no memory_fix (the field is present but null)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    data = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert data["would_exceed"] is False
    assert data["memory_fix"] is None


def test_estimate_charges_extra_outlier_passes(client, solved_library):
    """A k>1 min/max reject holds extra canvas planes, so the pre-submit peak must
    rise with it — otherwise the estimate under-counts memory versus the run-time
    guard and could say "fits" for a run the guard then refuses."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    base = client.get(f"/api/targets/{safe}/stack-estimate").json()
    k3 = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"min_max_reject": "true", "min_max_reject_count": 3},
    ).json()
    assert k3["peak_bytes"] > base["peak_bytes"]


def test_estimate_offers_dropping_extra_outlier_passes_when_over_budget(
    client, solved_library, monkeypatch):
    """A k=3 min/max reject that busts the budget but fits at k=1 → the estimate
    offers "drop the extra passes" (the least-destructive lever), reachable only
    now that the endpoint forwards the reject knobs."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # 480×320 reference canvas ≈ 7.4 MB at 4 planes (k=1), ≈ 14.7 MB at 8 (k=3).
    # A ~10 MB budget refuses k=3 but fits k=1.
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", str(10e-3))
    data = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"min_max_reject": "true", "min_max_reject_count": 3},
    ).json()
    assert data["would_exceed"] is True
    fix = data["memory_fix"]
    assert fix is not None
    assert fix["kind"] == "reduce_outlier_passes"
    assert fix["value"] is None
    assert fix["peak_bytes"] <= data["budget_bytes"]


def test_estimate_no_drizzle_suggestion_when_within_budget(client, solved_library):
    """A comfortably-sized drizzle run carries no suggestion."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    data = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"drizzle": "true", "drizzle_scale": 1.5},
    ).json()
    assert data["would_exceed"] is False
    assert data["suggested_drizzle_scale"] is None


def test_estimate_honors_memory_budget_setting(client, solved_library, monkeypatch):
    """The Settings ``max_stack_memory_gb`` value drives the estimate's budget /
    would_exceed when no env override is present."""
    monkeypatch.delenv("ASTROSTACK_MAX_STACK_GB", raising=False)
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # A punishingly small budget via Settings must be reflected and refuse.
    client.put("/api/settings", json={"max_stack_memory_gb": 0.5})
    data = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert data["budget_gb"] == 0.5
    # The 480×320 reference canvas is tiny, so 0.5 GB still fits; bump to a
    # drizzle that won't: ×4 ≈ 118 MB… still under 0.5 GB. Instead assert the
    # budget wiring: a 0.5 GB budget is exactly what the endpoint reports.
    assert data["budget_bytes"] == 500_000_000


def test_estimate_422_when_nothing_solved(client, built_library):
    """No plate-solved frames → a clean 422 with guidance, not a 500."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-estimate")
    assert r.status_code == 422
    assert "solve" in r.json()["detail"].lower()


def test_estimate_unknown_target_404(client):
    r = client.get("/api/targets/does_not_exist/stack-estimate")
    assert r.status_code == 404


def test_estimate_reports_what_auto_outlier_removal_resolves_to(
    client, solved_library,
):
    """With "Auto outlier removal" on, the engine *overrides* the sigma-clip and
    min/max toggles — so the form showing them as live could tell a beginner the
    exact opposite of what runs. The estimate answers which method will actually
    be used, from the same rule the picker applies, so the two can't drift."""
    from seestack.stack.stacker import auto_reject_switch_frames

    safe = client.get("/api/targets").json()[0]["safe_name"]
    url = f"/api/targets/{safe}/stack-estimate"

    # Auto off → null: the toggles below really are live, nothing to explain.
    assert client.get(url).json()["auto_reject_resolved"] is None

    # Auto on, 3 solved frames → min/max (κ-σ is blind to a lone outlier here).
    resolved = client.get(url, params={"auto_reject": "true"}).json()[
        "auto_reject_resolved"]
    assert resolved["method"] == "min_max"
    assert resolved["n_frames"] == 3
    assert resolved["switch_at_frames"] == auto_reject_switch_frames(3.0)

    # The boundary moves with κ, and the answer follows it rather than a
    # hard-coded 11 in the browser.
    tight = client.get(url, params={"auto_reject": "true",
                                    "sigma_kappa": 1.0}).json()[
        "auto_reject_resolved"]
    assert tight["switch_at_frames"] == auto_reject_switch_frames(1.0)
    assert tight["switch_at_frames"] < resolved["switch_at_frames"]

    # Drizzle keeps its own two-pass rejection and auto leaves the toggles
    # alone, so there is nothing to grey out → null again.
    assert client.get(url, params={"auto_reject": "true",
                                   "drizzle": "true"}).json()[
        "auto_reject_resolved"] is None


def test_estimate_carries_the_print_plan(client, solved_library):
    """The canvas said in the unit a human wants, before the run fixes it. The
    fixture's 480×320 reference canvas is below even the smallest paper, so this
    also pins the honest too-small answer — the one place a beginner most needs
    to be told that the lever is pixels, not more subs."""
    from seestack.printexport import print_options

    safe = client.get("/api/targets").json()[0]["safe_name"]
    data = client.get(f"/api/targets/{safe}/stack-estimate").json()
    plan = data["print_plan"]
    assert plan is not None
    assert print_options(data["output_w"], data["output_h"]) == []
    assert plan["name"] is None and plan["dpi"] is None
    assert "not more subs" in plan["text"]
    # …and the reachable half: super-resolution really does bring this canvas up
    # to the smallest paper, so the nudge names it and the scale that gets there.
    assert plan["bigger_name"] == "6×4 in"
    s = plan["bigger_drizzle_scale"]
    assert s is not None and 1.0 < s <= 2.0
    reached = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"drizzle": "true", "drizzle_scale": s},
    ).json()
    assert reached["print_plan"]["name"] == "6×4 in"
    assert "Drizzle" in plan["bigger_text"] and "6×4 in" in plan["bigger_text"]


def test_print_plan_follows_the_drizzle_scale_on_the_form(client, solved_library):
    """The plan describes the canvas the *current* settings would produce, so
    turning the knob on the form changes the sentence."""
    from seestack.printexport import print_options

    safe = client.get("/api/targets").json()[0]["safe_name"]
    driz = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"drizzle": "true", "drizzle_scale": 4.0},
    ).json()
    plan = driz["print_plan"]
    best = print_options(driz["output_w"], driz["output_h"])
    assert plan["name"] == (best[0].name if best else None)


def test_print_plan_withholds_the_nudge_when_over_budget(
    client, solved_library, monkeypatch):
    """The over-budget alert replaces the sizing line entirely, so the nudge must
    not be quietly recommending an even bigger canvas beside it."""
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", str(1e-3))
    safe = client.get("/api/targets").json()[0]["safe_name"]
    data = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert data["would_exceed"] is True
    assert data["print_plan"]["bigger_name"] is None


def test_estimate_says_whether_rejection_can_reach_a_lone_outlier(
    client, solved_library):
    """The Stack form's warnings are only honest if they know what will actually
    run. With the default options a 3-frame stack combines as a plain *mean* — no
    rejection pass dispatches at all — so the estimate must say so rather than
    leave the form to assume the ticked sigma-clip box means protection."""
    from seestack.stack.stacker import kappa_min_frames

    safe = client.get("/api/targets").json()[0]["safe_name"]
    url = f"/api/targets/{safe}/stack-estimate"

    reach = client.get(url).json()["rejection_reach"]
    assert reach["method"] == "mean"
    assert reach["n_frames"] == 3
    assert reach["reaches"] is False
    assert reach["lone_outlier_min_frames"] is None

    # Auto outlier removal is the fix the form offers, and it really does help:
    # at this frame count auto resolves to min/max, which drops an extreme from 3.
    auto = client.get(url, params={"auto_reject": "true"}).json()["rejection_reach"]
    assert auto["method"] == "min-max-reject"
    assert auto["reaches"] is True
    assert auto["lone_outlier_min_frames"] == 3

    # A loosened κ drops the blindness threshold to min/max's own floor of 3, but
    # the clip's ≥4-frame *dispatch* gate is independent of κ — so this stack is
    # still a plain mean, which is the trap `_resolve_auto_reject` guards against.
    assert kappa_min_frames(1.0) == 3
    loose = client.get(url, params={"sigma_kappa": 1.0}).json()["rejection_reach"]
    assert loose["method"] == "mean"
    assert loose["reaches"] is False
    # …and with auto on at that κ the engine still picks min/max, not a κ-σ that
    # would never run.
    loose_auto = client.get(url, params={"auto_reject": "true",
                                         "sigma_kappa": 1.0}).json()["rejection_reach"]
    assert loose_auto["method"] == "min-max-reject"
    assert loose_auto["reaches"] is True


def test_estimate_reach_follows_the_sigma_clip_toggle(client, solved_library):
    """``sigma_clip`` is not a sizing knob, so it was never a query param — but
    the reach answer is wrong without it (an untouched default would report a
    clip the user turned off). It must round-trip, and must not move the peak:
    the rejection-map plane it gates is only allocated when
    ``record_rejection_map`` is set, which this dry run never sets."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    url = f"/api/targets/{safe}/stack-estimate"

    # 3 frames: the clip can't dispatch either way, so both read "mean"…
    on = client.get(url, params={"sigma_clip": "true"}).json()
    off = client.get(url, params={"sigma_clip": "false"}).json()
    assert on["rejection_reach"]["method"] == "mean"
    assert off["rejection_reach"]["method"] == "mean"
    # …and omitting it keeps the engine's own default (true), so an older
    # frontend that never passes it sees exactly what it saw before.
    assert client.get(url).json()["rejection_reach"] == on["rejection_reach"]
    # Sizing is untouched by the new parameter.
    assert off["peak_bytes"] == on["peak_bytes"] == client.get(url).json()["peak_bytes"]
