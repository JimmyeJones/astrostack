"""GET /api/targets/{safe}/nights — the per-target "Nights" breakdown.

The engine logic (session split, verdicts, best/soft/hazy) is exercised
exhaustively in tests/test_session_recap.py; here we confirm the endpoint wires
it up and serialises the shape the frontend consumes (newest-first, verdict,
reject buckets).
"""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library


def _stamp(data_root: Path, safe: str, per_frame: dict[int, dict]) -> list[int]:
    """Stamp fields onto specific frames (by 0-based ordinal) of a target."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            ids = [f.id for f in proj.iter_frames()]
            for ordinal, fields in per_frame.items():
                proj.update_frame(ids[ordinal], **fields)
            return ids
        finally:
            proj.close()
    finally:
        lib.close()


def test_nights_default_is_one_night(client, solved_library):
    # The synth frames share one DATE-OBS, so M_42's subs are a single night.
    r = client.get("/api/targets/M_42/nights")
    assert r.status_code == 200
    nights = r.json()
    assert len(nights) == 1
    assert nights[0]["n_frames"] == 3
    assert nights[0]["n_set_aside"] == 0
    # No FWHM measured and no cloud problem → no sharpness verdict.
    assert nights[0]["median_fwhm_px"] is None
    assert nights[0]["verdict"] == ""
    assert nights[0]["is_best"] is False


def test_nights_lists_two_nights_newest_first(client, solved_library, data_root):
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-01T22:00:00+00:00"},               # night A
        1: {"timestamp_utc": "2026-07-08T22:00:00+00:00"},               # night B
        2: {"timestamp_utc": "2026-07-08T22:05:00+00:00"},               # night B
    })
    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 2
    assert nights[0]["start_utc"].startswith("2026-07-08")  # newest first
    assert nights[0]["n_frames"] == 2
    assert nights[1]["start_utc"].startswith("2026-07-01")
    assert nights[1]["n_frames"] == 1


def test_nights_serialises_verdict_and_reject_buckets(client, solved_library, data_root):
    # 2 of 3 subs set aside as cloudy (67% ≥ the 40% floor) → a "hazy" night.
    _stamp(data_root, "M_42", {
        0: {"accept": False, "reject_reason": "auto:grade:transparency"},
        1: {"accept": False, "reject_reason": "auto:grade:sky"},
    })
    nights = client.get("/api/targets/M_42/nights").json()
    assert len(nights) == 1
    assert nights[0]["verdict"] == "hazy"
    assert nights[0]["reject_buckets"] == {"cloudy": 2}
    assert nights[0]["n_set_aside"] == 2
    assert nights[0]["n_kept"] == 1
