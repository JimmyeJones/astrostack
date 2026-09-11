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


def _reject_one_frame(client, safe: str) -> None:
    """Drop a single accepted frame through the API, so the estimate sees one
    fewer accepted+solved sub."""
    fid = client.get(f"/api/targets/{safe}/frames").json()[0]["id"]
    r = client.patch(f"/api/targets/{safe}/frames/{fid}", json={"accept": False})
    assert r.status_code == 200, r.text


def test_estimate_says_whether_ANY_rejection_setting_could_reach(
    client, solved_library):
    """``best_available`` answers the question a form has to answer for someone
    who turned rejection *off*: is there a setting here that would take a lone
    satellite trail out at all?

    Without it the form has to re-derive the dispatcher's gates by hand, and the
    predicate it used to carry named sigma clipping on a stack too thin for any
    method to run — advice that could not be followed."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    url = f"/api/targets/{safe}/stack-estimate"

    # 3 subs, rejection off: nothing runs *as configured*…
    off = client.get(url, params={"sigma_clip": "false"}).json()["rejection_reach"]
    assert off["method"] == "mean"
    assert off["reaches"] is False
    # …but letting the app choose lands on min/max, which drops an extreme from
    # 3 subs up — so there is something honest to offer here.
    assert off["best_available"] == {
        "method": "min-max-reject",
        "lone_outlier_min_frames": 3,
        "reaches": True,
    }
    # It is the engine's own answer, not a second copy of it: turning auto on
    # explicitly gives exactly the same verdict.
    auto = client.get(url, params={"auto_reject": "true"}).json()["rejection_reach"]
    assert auto["method"] == off["best_available"]["method"]
    assert auto["reaches"] == off["best_available"]["reaches"]
    assert auto["lone_outlier_min_frames"] == off["best_available"]["lone_outlier_min_frames"]

    # Two subs is under every method's floor, and that is the case the old
    # hand-written predicate got wrong: no setting can help, so the answer must
    # say so rather than name one.
    _reject_one_frame(client, safe)
    thin = client.get(url, params={"sigma_clip": "false"}).json()["rejection_reach"]
    assert thin["n_frames"] == 2
    assert thin["best_available"]["reaches"] is False
    assert thin["best_available"]["lone_outlier_min_frames"] is None


def test_estimate_best_available_answers_for_the_drizzle_path_too(
    client, solved_library):
    """With drizzle on, the three toggles below it are overridden and only
    drizzle's own two-pass rejection can run — so ``best_available`` must be
    drizzle's answer, not the min/max one the normal path would give."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    from seestack.stack.stacker import kappa_min_frames

    best = client.get(
        f"/api/targets/{safe}/stack-estimate",
        params={"drizzle": "true", "drizzle_reject": "false"},
    ).json()["rejection_reach"]["best_available"]
    assert best["method"] == "drizzle"
    # Drizzle clips with the same κ against statistics that still hold the
    # outlier, so its floor is κ-σ's, not min/max's 3.
    assert best["lone_outlier_min_frames"] == kappa_min_frames(3.0)
    assert best["reaches"] is False


def test_estimate_best_available_costs_no_extra_sizing_work(
    client, solved_library):
    """The second reach question is asked of the same already-computed estimate,
    so it can never move the peak the memory guard is checked against."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    url = f"/api/targets/{safe}/stack-estimate"
    data = client.get(url).json()
    assert data["rejection_reach"]["best_available"] is not None
    assert data["peak_bytes"] == client.get(
        url, params={"auto_reject": "true"}).json()["peak_bytes"]


def test_estimate_carries_the_drizzle_feasibility_probe(client, solved_library):
    """The Stack form's proactive drizzle nudge needs one number — "would a
    drizzled run fit?" — and used to spend a *second* request on it, which re-read
    every sub's WCS to rebuild the identical canvas. It now rides along."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    data = client.get(f"/api/targets/{safe}/stack-estimate").json()
    probe = data["drizzle_probe"]
    assert probe["drizzle_scale"] == 1.5
    assert probe["would_exceed"] is False
    # Drizzle is off in this request, so the probe must not be echoing the main
    # sizing: a ×1.5 drizzled canvas costs more than the plain one.
    assert probe["peak_bytes"] > data["peak_bytes"]
    assert probe["peak_gb"] == round(probe["peak_bytes"] / 1e9, 2)


def test_drizzle_probe_agrees_with_a_real_drizzle_request(client, solved_library):
    """Agreement by construction: the folded-in answer must be exactly what the
    second request it replaces would have returned."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    url = f"/api/targets/{safe}/stack-estimate"
    probe = client.get(url).json()["drizzle_probe"]
    separate = client.get(url, params={
        "drizzle": "true", "drizzle_scale": 1.5, "drizzle_reject": "false",
    }).json()
    assert probe["peak_bytes"] == separate["peak_bytes"]
    assert probe["would_exceed"] == separate["would_exceed"]


def test_drizzle_probe_is_unmoved_by_the_rejection_knobs(client, solved_library):
    """It answers "does drizzle fit?", not "does drizzle plus whatever the form
    currently holds fit?" — the old second request sent no rejection knobs, and
    the nudge would flicker with the κ slider if this one did."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    url = f"/api/targets/{safe}/stack-estimate"
    base = client.get(url).json()["drizzle_probe"]
    loaded = client.get(url, params={
        "min_max_reject": "true", "min_max_reject_count": "3",
        "auto_reject": "true", "sigma_kappa": "1.5", "sigma_clip": "false",
    }).json()["drizzle_probe"]
    assert loaded == base


def test_drizzle_probe_flags_a_drizzled_run_that_busts_the_budget(
    client, solved_library, monkeypatch):
    """The gate the nudge exists for: never suggest a run that would be refused."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # ~7.4 MB for the plain 480×320 canvas, ~17 MB at ×1.5 drizzle. A 10 MB
    # budget fits the first and refuses the second.
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", str(10e-3))
    data = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert data["would_exceed"] is False
    assert data["drizzle_probe"]["would_exceed"] is True


def test_estimate_builds_the_canvas_once_per_request(
    client, solved_library, monkeypatch):
    """Both sizings in the response come off one canvas computation — the whole
    point of folding the probe in. Fails before: two requests, two canvases."""
    from seestack.stack import mosaic as mosaic_mod

    calls = {"n": 0}
    real = mosaic_mod.compute_mosaic_canvas

    def counted(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(mosaic_mod, "compute_mosaic_canvas", counted)
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-estimate")
    assert r.status_code == 200
    assert r.json()["drizzle_probe"] is not None
    assert calls["n"] == 1


# --- "about how long will this take?" ----------------------------------------


def _record_timed_run(data_root, safe: str, *, n_frames: int, duration_s: float,
                      options: dict, canvas: tuple[int, int] = (320, 480)) -> None:
    """Put one finished, timed run in a target's History — what the estimate
    below measures from. The real writer is ``run_stack``; this is the same row."""
    import json

    from seestack.io.library import Library
    from seestack.io.project import StackRunRow

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=n_frames,
                canvas_h=canvas[0], canvas_w=canvas[1],
                coverage_min=1, coverage_max=n_frames,
                options_json=json.dumps(options), duration_s=duration_s,
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def test_estimate_says_nothing_about_time_on_a_target_never_stacked(
        client, solved_library):
    """The honest answer with no history — and the state every library is in
    right after the upgrade that added the timing column."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-estimate")
    assert r.status_code == 200
    assert r.json()["time_estimate"] is None


def test_estimate_times_the_next_run_from_this_target_s_own_runs(
        client, solved_library):
    """One past min/max run of 40 subs in 80 s → 2 s a sub, and the 3 subs this
    fixture would stack are quoted at that rate. Fails before v0.399.0: the
    response carried no answer to "how long?" at all.

    Min/max on both sides on purpose: this fixture has three frames, and κ-σ
    does not dispatch below four — so a κ-σ *request* here really would combine
    as a plain mean, and matching it against 40-sub κ-σ history would be the
    very mistake the cost class exists to prevent."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _record_timed_run(solved_library, safe, n_frames=40, duration_s=80.0,
                      options={"min_max_reject": True, "sigma_clip": False})
    data = client.get(f"/api/targets/{safe}/stack-estimate",
                      params={"min_max_reject": "true"}).json()
    assert data["time_estimate"] is not None
    assert data["time_estimate"]["basis_runs"] == 1
    assert data["time_estimate"]["basis_frames"] == 40
    assert data["time_estimate"]["seconds"] == round(2.0 * data["n_frames"])


def test_a_drizzle_run_is_not_timed_from_a_plain_stack_s_rate(
        client, solved_library):
    """Drizzle does several times the per-sub work, so history of a different
    shape must not be spent on it — the form then says nothing rather than
    quoting a number that is wrong by a multiple."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _record_timed_run(solved_library, safe, n_frames=40, duration_s=80.0,
                      options={"min_max_reject": True, "sigma_clip": False})
    data = client.get(f"/api/targets/{safe}/stack-estimate",
                      params={"drizzle": "true"}).json()
    assert data["time_estimate"] is None


def test_auto_reject_is_resolved_before_the_past_runs_are_matched(
        client, solved_library):
    """With "Auto outlier removal" on, this 3-frame stack resolves to min/max —
    so a κ-σ history is *not* its evidence, and a min/max history is. The match
    has to run on the options that will actually run, not on the toggles."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _record_timed_run(solved_library, safe, n_frames=40, duration_s=80.0,
                      options={"sigma_clip": True})
    params = {"auto_reject": "true"}
    assert client.get(f"/api/targets/{safe}/stack-estimate",
                      params=params).json()["time_estimate"] is None
    _record_timed_run(solved_library, safe, n_frames=40, duration_s=120.0,
                      options={"min_max_reject": True, "sigma_clip": False})
    data = client.get(f"/api/targets/{safe}/stack-estimate", params=params).json()
    assert data["time_estimate"] is not None
    assert data["time_estimate"]["seconds"] == round(3.0 * data["n_frames"])


# --- what "Auto outlier removal" will actually do ----------------------------


def _repoint(data_root, safe: str, pointings: list[tuple[float, float, int]]) -> None:
    """Re-point a target's frames into ``[(ra, dec, count), …]`` panels.

    Rows are cloned from the fixture's own frames, so each keeps a real
    ``source_path`` and WCS — the sizing path only reads the DB. Same helper
    shape as ``tests/webapp/test_rejection_outlook.py``."""
    from dataclasses import replace

    from seestack.io.library import Library

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            rows = list(proj.iter_frames())
            template = rows[0]
            for r in rows:
                proj.update_frame(r.id, accept=False)
            n = 0
            for ra, dec, count in pointings:
                for _ in range(count):
                    n += 1
                    proj.add_frame(replace(
                        template, id=None, accept=True,
                        source_path=f"{template.source_path}.{n:03d}",
                        ra_center_deg=ra, dec_center_deg=dec,
                    ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_auto_reject_resolved_reads_a_mosaic_by_its_panel_depth(
        client, solved_library):
    """The bug, found in a running app on the owner's own shape: four panels 5
    subs deep is 20 frames, so resolving from the *frame count* says sigma
    clipping — while the stack, which sizes the same decision from the per-pixel
    depth (5), runs min/max. The form named a method the run would not use, and
    every method-specific hint and greyed toggle followed it.

    Fails before v0.399.1: ``method`` was ``"sigma_clip"`` here."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _repoint(solved_library, safe, [
        (83.6, -5.4, 5), (84.4, -5.4, 5), (83.6, -4.6, 5), (84.4, -4.6, 5),
    ])
    data = client.get(f"/api/targets/{safe}/stack-estimate",
                      params={"auto_reject": "true"}).json()
    assert data["n_frames"] == 20
    resolved = data["auto_reject_resolved"]
    assert resolved["panel_depth"] == 5
    assert resolved["method"] == "min_max"
    # …and it agrees with what the engine's own picker resolves for this stack,
    # asserted against the picker rather than against a copy of its answer.
    from seestack.io.library import Library
    from seestack.stack.stacker import (
        StackOptions,
        _resolve_auto_reject,
        estimate_stack_basis,
    )

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            basis = estimate_stack_basis(proj, "auto")
        finally:
            proj.close()
    finally:
        lib.close()
    eff = _resolve_auto_reject(StackOptions(auto_reject=True),
                               basis.n_frames, depth=basis.panel_depth)
    assert eff.min_max_reject is True and eff.sigma_clip is False


def test_auto_reject_resolved_on_a_single_field_is_unchanged(
        client, solved_library):
    """The single-field answer must be byte-for-byte what it was: no depth, and
    the method the frame count implies — 3 subs is below every κ-σ floor."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    data = client.get(f"/api/targets/{safe}/stack-estimate",
                      params={"auto_reject": "true"}).json()
    resolved = data["auto_reject_resolved"]
    assert resolved["panel_depth"] is None
    assert resolved["method"] == "min_max"
    assert resolved["n_frames"] == 3
    assert resolved["switch_at_frames"] == 11


def test_a_deep_mosaic_still_resolves_to_sigma_clipping(client, solved_library):
    """The other direction, so the fix is not just "always min/max on a mosaic":
    panels 20 deep clear the floor on the pixels that make the picture."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _repoint(solved_library, safe, [
        (83.6, -5.4, 20), (84.4, -5.4, 20), (83.6, -4.6, 20), (84.4, -4.6, 20),
    ])
    resolved = client.get(f"/api/targets/{safe}/stack-estimate",
                          params={"auto_reject": "true"}).json()["auto_reject_resolved"]
    assert resolved["panel_depth"] == 20
    assert resolved["method"] == "sigma_clip"


def test_panel_depth_is_served_even_when_auto_outlier_removal_is_off(
        client, solved_library):
    """The depth has to be readable with ``auto_reject_resolved`` null.

    That key is the only place the per-pixel depth used to appear, and it is
    ``null`` unless Auto is on and drizzle is off — which is precisely the state
    the Stack form's *drizzle* caution fires in. So the caution asked its
    "is a pixel thin?" question of the target's total and, on a nine-panel
    raster, stayed silent on the one canvas where drizzle hurts most.

    Fails before v0.420.0: there was no top-level ``panel_depth``."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _repoint(solved_library, safe, [
        (83.6, -5.4, 5), (84.4, -5.4, 5), (83.6, -4.6, 5), (84.4, -4.6, 5),
    ])
    data = client.get(f"/api/targets/{safe}/stack-estimate",
                      params={"drizzle": "true"}).json()
    assert data["auto_reject_resolved"] is None    # auto off, drizzle on
    assert data["n_frames"] == 20                  # …and the total says "plenty"
    assert data["panel_depth"] == 5                # while a pixel has five


def test_panel_depth_is_null_on_a_single_field(client, solved_library):
    """Where every sub covers every pixel there is nothing to correct, and the
    frontend reads ``null`` as "use the frame count" — byte-for-byte the
    behaviour every caution had before the field existed."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    data = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert data["is_mosaic"] is False
    assert data["panel_depth"] is None


def test_panel_depth_is_the_engine_s_own_depth_not_a_second_definition(
        client, solved_library):
    """Asserted against the engine's picker rather than against a literal, so
    the form's cautions and the method it names can never be computed from two
    different depths — the drift these fixes keep undoing."""
    from seestack.io.library import Library
    from seestack.stack.stacker import estimate_stack_basis

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _repoint(solved_library, safe, [
        (83.6, -5.4, 9), (84.4, -5.4, 4), (83.6, -4.6, 7),
    ])
    served = client.get(f"/api/targets/{safe}/stack-estimate").json()["panel_depth"]

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            basis = estimate_stack_basis(proj, "auto")
        finally:
            proj.close()
    finally:
        lib.close()
    assert served == basis.panel_depth
    assert served == 4          # the thinnest substantial panel, not the mean


def test_panel_depth_is_unmoved_by_the_knobs_the_form_cautions_about(
        client, solved_library):
    """It is a property of the canvas, so drizzle and the rejection knobs cannot
    move it. A caution whose own denominator shifted when you toggled the very
    setting it warns about would be unfalsifiable on screen."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _repoint(solved_library, safe, [
        (83.6, -5.4, 6), (84.4, -5.4, 6), (83.6, -4.6, 6),
    ])
    base = f"/api/targets/{safe}/stack-estimate"
    depths = {
        client.get(base, params=p).json()["panel_depth"]
        for p in (
            {},
            {"drizzle": "true", "drizzle_scale": "2.0"},
            {"min_max_reject": "true", "min_max_reject_count": "3"},
            {"auto_reject": "true"},
            {"sigma_clip": "false"},
        )
    }
    assert depths == {6}
