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


def _bounds(client, safe: str, ordinal: int = 0) -> dict:
    """The start/end bounds of the target's `ordinal`-th night (newest first)."""
    nights = client.get(f"/api/targets/{safe}/nights").json()
    n = nights[ordinal]
    return {"start_utc": n["start_utc"], "end_utc": n["end_utc"]}


def test_set_aside_night_rejects_only_that_nights_accepted_subs(
    client, solved_library, data_root,
):
    # Two nights: A (one sub) and B (two subs). Set aside night B only.
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-01T22:00:00+00:00"},  # night A
        1: {"timestamp_utc": "2026-07-08T22:00:00+00:00"},  # night B
        2: {"timestamp_utc": "2026-07-08T22:05:00+00:00"},  # night B
    })
    r = client.post("/api/targets/M_42/frames/set-aside-night",
                    json=_bounds(client, "M_42", 0))  # newest = night B
    assert r.status_code == 200
    body = r.json()
    assert body["changed"] == 2
    assert len(body["changed_ids"]) == 2

    nights = client.get("/api/targets/M_42/nights").json()
    # Night A untouched; night B's two subs now set aside (bucketed as "you").
    a = next(n for n in nights if n["start_utc"].startswith("2026-07-01"))
    b = next(n for n in nights if n["start_utc"].startswith("2026-07-08"))
    assert a["n_kept"] == 1 and a["n_set_aside"] == 0
    assert b["n_kept"] == 0 and b["n_set_aside"] == 2
    assert b["reject_buckets"] == {"set aside by you": 2}


def test_set_aside_night_leaves_already_rejected_subs_untouched(
    client, solved_library, data_root,
):
    # One sub already auto-rejected as cloudy; set-aside must not re-reason it.
    _stamp(data_root, "M_42", {
        0: {"accept": False, "reject_reason": "auto:grade:sky"},
    })
    r = client.post("/api/targets/M_42/frames/set-aside-night",
                    json=_bounds(client, "M_42", 0))
    assert r.json()["changed"] == 2  # only the 2 accepted subs, not the cloudy one
    nights = client.get("/api/targets/M_42/nights").json()
    # The cloudy sub keeps its own reason; only the 2 accepted flip to "you".
    assert nights[0]["reject_buckets"] == {"cloudy": 1, "set aside by you": 2}


def test_set_aside_night_is_undoable_via_bulk_accept(
    client, solved_library, data_root,
):
    _stamp(data_root, "M_42", {
        0: {"timestamp_utc": "2026-07-08T22:00:00+00:00"},
        1: {"timestamp_utc": "2026-07-08T22:05:00+00:00"},
        2: {"timestamp_utc": "2026-07-08T22:10:00+00:00"},
    })
    changed = client.post("/api/targets/M_42/frames/set-aside-night",
                          json=_bounds(client, "M_42", 0)).json()["changed_ids"]
    assert len(changed) == 3
    # Undo re-accepts exactly the touched subs (the shipped bulk-accept path).
    client.post("/api/targets/M_42/frames/bulk",
                json={"action": "accept", "ids": changed})
    nights = client.get("/api/targets/M_42/nights").json()
    assert nights[0]["n_kept"] == 3 and nights[0]["n_set_aside"] == 0
