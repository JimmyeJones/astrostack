"""GET /api/targets/{safe}/transparency-trend — the "Clouds & haze" trend card.

The engine logic (session split, min-frame gate, verdicts) is exercised
exhaustively in tests/test_session_recap.py; here we confirm the endpoint wires
it up, self-hides on too little data, and serialises the shape the frontend
consumes (points in capture order, verdict, degraded_after).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow


def _add_night(data_root: Path, safe: str, scores: list[float]) -> None:
    """Append a run of accepted, measured subs 3 minutes apart (one session)."""
    base = datetime(2026, 7, 10, 22, 0, 0)
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for i, sc in enumerate(scores):
                proj.add_frame(FrameRow(
                    source_path=f"/synthetic/transp/{safe}-{i}.fit",
                    timestamp_utc=(base + timedelta(minutes=3 * i)).isoformat(),
                    exposure_s=10.0,
                    accept=True,
                    transparency_score=sc,
                ))
        finally:
            proj.close()
    finally:
        lib.close()


def test_transparency_trend_null_when_too_few_measured(client, solved_library):
    # M_42's synth subs carry no transparency score → nothing to trend → self-hides.
    r = client.get("/api/targets/M_42/transparency-trend")
    assert r.status_code == 200
    assert r.json() is None


def test_transparency_trend_flags_clouds_rolling_in(client, solved_library, data_root):
    _add_night(data_root, "M_42", [1000, 1020, 980, 990, 700, 520, 480, 450, 420])
    body = client.get("/api/targets/M_42/transparency-trend").json()
    assert body is not None
    assert body["verdict"] == "degraded"
    assert body["n_points"] == 9
    assert len(body["points"]) == 9
    # Points are serialised in capture order, oldest first.
    ts = [p["t_utc"] for p in body["points"]]
    assert ts == sorted(ts)
    assert body["late_transparency"] < body["early_transparency"]
    assert body["degraded_after_utc"] is not None
    assert body["start_utc"] < body["degraded_after_utc"] <= body["end_utc"]


def test_transparency_trend_clear_night_has_no_marker(client, solved_library, data_root):
    _add_night(data_root, "M_42", [1000, 1030, 980, 1010, 995, 1020, 990, 1005])
    body = client.get("/api/targets/M_42/transparency-trend").json()
    assert body is not None
    assert body["verdict"] == "clear"
    assert body["degraded_after_utc"] is None
