"""Auto-grade endpoints + the opt-in pipeline hook.

Frames are seeded with controlled metrics directly in the project DB so the
grading statistics are deterministic (no real QC runs against these values).
"""

from __future__ import annotations

import random

from seestack.io.library import Library
from seestack.io.project import FrameRow
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job


def _seed_metrics(data_root, safe: str = "M_42", n_clean: int = 30,
                  bad: dict | None = None,
                  fwhm_cycle: list[float] | None = None) -> int | None:
    """Give every existing frame + ``n_clean`` synthetic rows clean metrics,
    then (optionally) add one bad frame. Returns the bad frame's id.
    ``fwhm_cycle`` replaces the random FWHM draw with deterministic cycling
    values when a test needs an exact population spread."""
    rng = random.Random(5)
    counter = {"i": 0}

    def _fwhm() -> float:
        if fwhm_cycle is not None:
            v = fwhm_cycle[counter["i"] % len(fwhm_cycle)]
            counter["i"] += 1
            return v
        return 3.0 + rng.gauss(0, 0.15)

    def clean(i: int) -> dict:
        return {
            "fwhm_px": _fwhm(),
            "star_count": int(400 + rng.gauss(0, 25)),
            "sky_adu_median": 1200.0 + rng.gauss(0, 60),
            "eccentricity_median": 0.40 + rng.gauss(0, 0.02),
            "transparency_score": 5000.0 + rng.gauss(0, 200),
        }

    lib = Library.open_or_create(data_root / "library")
    bad_id: int | None = None
    try:
        proj = lib.open_target(safe)
        try:
            # Existing (real) frames get clean metrics too, so real QC never
            # re-runs on them (star_count set) and can't skew the population.
            for f in proj.iter_frames():
                proj.update_frame(f.id, **clean(0))
            for i in range(n_clean):
                proj.add_frame(FrameRow(
                    source_path=f"/synthetic/clean_{i:03d}.fit", **clean(i),
                ))
            if bad is not None:
                bad_id = proj.add_frame(FrameRow(
                    source_path="/synthetic/awful.fit", **{**clean(0), **bad},
                ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()
    return bad_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def test_auto_grade_preview_flags_outlier_without_changing_anything(
        client, built_library, data_root):
    bad_id = _seed_metrics(data_root, bad={"fwhm_px": 9.0})
    r = client.get("/api/targets/M_42/frames/auto-grade")
    assert r.status_code == 200
    body = r.json()
    assert body["sensitivity"] == "balanced"
    assert body["changed_ids"] is None
    assert [rec["frame_id"] for rec in body["recommendations"]] == [bad_id]
    rec = body["recommendations"][0]
    assert rec["name"] == "awful.fit"
    reason = rec["reasons"][0]
    assert reason["metric"] == "fwhm_px"
    assert "softer than typical" in reason["label"]
    assert reason["z"] >= 3.5
    # Pure preview: the frame is still accepted.
    frames = {f["id"]: f for f in client.get("/api/targets/M_42/frames").json()}
    assert frames[bad_id]["accept"] is True


def test_auto_grade_preview_quiet_on_clean_target(client, built_library, data_root):
    _seed_metrics(data_root)  # no bad frame
    body = client.get("/api/targets/M_42/frames/auto-grade").json()
    assert body["recommendations"] == []
    assert set(body["metrics_used"]) == {
        "fwhm_px", "eccentricity_median", "sky_adu_median",
        "star_count", "transparency_score",
    }


def test_auto_grade_small_target_skips_metrics(client, built_library):
    # The stock fixture has only 3 frames (and no metrics) — far below the
    # min-frames rail, so every metric is skipped and nothing is recommended.
    body = client.get("/api/targets/M_42/frames/auto-grade").json()
    assert body["recommendations"] == []
    assert body["metrics_used"] == []
    assert len(body["metrics_skipped"]) == 5


def test_auto_grade_bad_sensitivity_is_422(client, built_library):
    r = client.get("/api/targets/M_42/frames/auto-grade?sensitivity=yolo")
    assert r.status_code == 422


def test_auto_grade_unknown_target_404(client, built_library):
    assert client.get("/api/targets/NOPE/frames/auto-grade").status_code == 404
    assert client.post("/api/targets/NOPE/frames/auto-grade/apply").status_code == 404


def test_auto_grade_apply_rejects_then_undo_and_no_regrade(
        client, built_library, data_root):
    bad_id = _seed_metrics(data_root, bad={"star_count": 20, "sky_adu_median": 9000.0})
    r = client.post("/api/targets/M_42/frames/auto-grade/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["changed_ids"] == [bad_id]

    frames = {f["id"]: f for f in client.get("/api/targets/M_42/frames").json()}
    f = frames[bad_id]
    assert f["accept"] is False
    assert f["reject_reason"].startswith("auto:grade:")
    # Machine decision — the user hasn't weighed in yet.
    assert f["user_override"] is False

    # The rejection shows up in the reject-reason breakdown.
    summary = client.get("/api/targets/M_42/frames/reject-summary").json()
    assert any(k.startswith("auto:grade:") for k in summary["counts"])

    # One-click undo (the same path the UI uses): bulk accept of changed_ids.
    r = client.post("/api/targets/M_42/frames/bulk",
                    json={"action": "accept", "ids": body["changed_ids"]})
    assert r.json()["changed"] == 1
    frames = {f["id"]: f for f in client.get("/api/targets/M_42/frames").json()}
    assert frames[bad_id]["accept"] is True
    assert frames[bad_id]["user_override"] is True

    # Re-applying respects the user's re-accept: nothing changes again.
    r = client.post("/api/targets/M_42/frames/auto-grade/apply")
    assert r.json()["changed_ids"] == []
    frames = {f["id"]: f for f in client.get("/api/targets/M_42/frames").json()}
    assert frames[bad_id]["accept"] is True


def test_auto_grade_apply_updates_accepted_count(client, built_library, data_root):
    _seed_metrics(data_root, bad={"transparency_score": 500.0})
    before = client.get("/api/targets").json()
    t_before = next(t for t in before if t["safe_name"] == "M_42")
    applied = client.post("/api/targets/M_42/frames/auto-grade/apply").json()
    after = client.get("/api/targets").json()
    t_after = next(t for t in after if t["safe_name"] == "M_42")
    assert t_after["n_frames_accepted"] == t_before["n_frames_accepted"] - 1

    # The one-click undo (bulk accept) must restore the count too — the bulk
    # endpoint refreshes the registry stats like apply does.
    client.post("/api/targets/M_42/frames/bulk",
                json={"action": "accept", "ids": applied["changed_ids"]})
    restored = client.get("/api/targets").json()
    t_restored = next(t for t in restored if t["safe_name"] == "M_42")
    assert t_restored["n_frames_accepted"] == t_before["n_frames_accepted"]


def test_manual_grade_updates_accepted_count(client, built_library):
    # Pre-existing staleness: a single-frame accept/reject PATCH left the
    # registry's accepted count (Target badge, Library cards) stale until some
    # pipeline ran. It must refresh immediately now.
    frames = client.get("/api/targets/M_42/frames").json()
    t = client.get("/api/targets/M_42").json()
    n0 = t["n_frames_accepted"]
    client.patch(f"/api/targets/M_42/frames/{frames[0]['id']}",
                 json={"accept": False})
    assert client.get("/api/targets/M_42").json()["n_frames_accepted"] == n0 - 1
    client.patch(f"/api/targets/M_42/frames/{frames[0]['id']}",
                 json={"accept": True})
    assert client.get("/api/targets/M_42").json()["n_frames_accepted"] == n0


def test_auto_grade_sensitivity_setting_is_used(client, built_library, data_root):
    # FWHM population cycling 2.6–3.4 (median 3.0, MAD 0.2 → robust scale
    # ≈0.297). The 4.0 px frame has z ≈ 3.37: balanced (3.5) misses it,
    # aggressive (2.5) catches it, and it clears the 1.25× practical floor.
    _seed_metrics(data_root, bad={"fwhm_px": 4.0},
                  fwhm_cycle=[2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4])
    assert client.get("/api/targets/M_42/frames/auto-grade").json()["recommendations"] == []
    r = client.put("/api/settings", json={"auto_grade_sensitivity": "aggressive"})
    assert r.status_code == 200
    body = client.get("/api/targets/M_42/frames/auto-grade").json()
    assert body["sensitivity"] == "aggressive"
    assert len(body["recommendations"]) == 1
    # An explicit query param still overrides the setting.
    body = client.get("/api/targets/M_42/frames/auto-grade?sensitivity=conservative").json()
    assert body["recommendations"] == []


def test_settings_reject_bad_sensitivity(client):
    r = client.put("/api/settings", json={"auto_grade_sensitivity": "nuke-everything"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Pipeline hook (opt-in automation)
# ---------------------------------------------------------------------------


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _run_pipeline(data_root, **overrides):
    settings = Settings(
        data_root=str(data_root), auto_ingest=False, auto_qc=True,
        auto_solve=False, auto_stack=False, **overrides,
    )
    return pipeline._pipeline_body(settings, _FakeJM(), Job(kind="pipeline"), root=None)


def test_pipeline_auto_grades_when_enabled(built_library, data_root):
    bad_id = _seed_metrics(data_root, bad={"fwhm_px": 9.0})
    summary = _run_pipeline(data_root, auto_grade_frames=True)
    assert summary["auto_graded"] == {"M_42": 1}
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            f = proj.get_frame(bad_id)
            assert f.accept is False
            assert f.reject_reason == "auto:grade:fwhm_px"
            assert f.user_override is False
        finally:
            proj.close()
    finally:
        lib.close()


def test_pipeline_leaves_frames_alone_when_disabled(built_library, data_root):
    bad_id = _seed_metrics(data_root, bad={"fwhm_px": 9.0})
    summary = _run_pipeline(data_root)  # auto_grade_frames defaults off
    assert "auto_graded" not in summary
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            assert proj.get_frame(bad_id).accept is True
        finally:
            proj.close()
    finally:
        lib.close()
