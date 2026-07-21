"""GET /api/targets/{safe}/focus-trend — the "Focus & sharpness" trend card.

The engine logic (session split, min-frame gate, verdicts) is exercised
exhaustively in tests/test_session_recap.py; here we confirm the endpoint wires
it up, self-hides on too little data, and serialises the shape the frontend
consumes (points in capture order, verdict, soft_after).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow


def _add_night(data_root: Path, safe: str, fwhms: list[float]) -> None:
    """Append a run of accepted, measured subs 3 minutes apart (one session)."""
    base = datetime(2026, 7, 10, 22, 0, 0)
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for i, fw in enumerate(fwhms):
                proj.add_frame(FrameRow(
                    source_path=f"/synthetic/focus/{safe}-{i}.fit",
                    timestamp_utc=(base + timedelta(minutes=3 * i)).isoformat(),
                    exposure_s=10.0,
                    accept=True,
                    fwhm_px=fw,
                ))
        finally:
            proj.close()
    finally:
        lib.close()


def test_focus_trend_null_when_too_few_measured(client, solved_library):
    # M_42's synth subs carry no FWHM → nothing to trend → the card self-hides.
    r = client.get("/api/targets/M_42/focus-trend")
    assert r.status_code == 200
    assert r.json() is None


def test_focus_trend_flags_a_softening_night(client, solved_library, data_root):
    _add_night(data_root, "M_42", [2.6, 2.7, 2.5, 2.8, 3.6, 4.2, 4.5, 4.8, 5.0])
    body = client.get("/api/targets/M_42/focus-trend").json()
    assert body is not None
    assert body["verdict"] == "softened"
    assert body["n_points"] == 9
    assert len(body["points"]) == 9
    # Points are serialised in capture order, oldest first.
    ts = [p["t_utc"] for p in body["points"]]
    assert ts == sorted(ts)
    assert body["late_fwhm_px"] > body["early_fwhm_px"]
    assert body["soft_after_utc"] is not None
    assert body["start_utc"] < body["soft_after_utc"] <= body["end_utc"]


def test_focus_trend_steady_night_has_no_soft_marker(client, solved_library, data_root):
    _add_night(data_root, "M_42", [2.8, 3.0, 2.7, 2.9, 2.8, 3.1, 2.7, 2.9])
    body = client.get("/api/targets/M_42/focus-trend").json()
    assert body is not None
    assert body["verdict"] == "steady"
    assert body["soft_after_utc"] is None
