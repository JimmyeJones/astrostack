"""GET /api/targets/{safe}/best-frame — the pre-stack "First look" pick."""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library


def _set_qc(data_root: Path, safe: str, per_frame: dict[int, dict]) -> list[int]:
    """Stamp QC metrics onto specific frames (by ordinal) of a target.

    ``per_frame`` maps a 0-based frame ordinal to the fields to set, so a test
    can make one frame the sharpest, reject another, etc. Returns the frame ids
    in ingest order."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            frames = list(proj.iter_frames())
            ids = [f.id for f in frames]
            for ordinal, fields in per_frame.items():
                proj.update_frame(ids[ordinal], **fields)
            return ids
        finally:
            proj.close()
    finally:
        lib.close()


def test_best_frame_null_before_qc(client, solved_library):
    # M_42 has accepted frames but none carry a FWHM yet → nothing QC'd.
    r = client.get("/api/targets/M_42/best-frame")
    assert r.status_code == 200
    body = r.json()
    assert body["frame_id"] is None
    assert body["n_accepted"] == 3


def test_best_frame_returns_the_sharpest_accepted_sub(client, solved_library, data_root):
    ids = _set_qc(data_root, "M_42", {
        0: {"fwhm_px": 3.2, "star_count": 400, "timestamp_utc": "2026-07-14T21:10:00+00:00"},
        1: {"fwhm_px": 2.1, "star_count": 380, "timestamp_utc": "2026-07-14T21:14:00+00:00"},
        2: {"fwhm_px": 2.8, "star_count": 500, "timestamp_utc": "2026-07-14T21:18:00+00:00"},
    })
    body = client.get("/api/targets/M_42/best-frame").json()
    assert body["frame_id"] == ids[1]  # sharpest (lowest FWHM)
    assert body["fwhm_px"] == 2.1
    assert body["star_count"] == 380
    assert body["captured_utc"] == "2026-07-14T21:14:00+00:00"
    assert body["n_accepted"] == 3


def test_best_frame_ignores_a_rejected_sharper_sub(client, solved_library, data_root):
    ids = _set_qc(data_root, "M_42", {
        0: {"fwhm_px": 1.8, "star_count": 600, "accept": False, "reject_reason": "user"},
        1: {"fwhm_px": 2.6, "star_count": 400},
    })
    body = client.get("/api/targets/M_42/best-frame").json()
    # The sharper frame 0 was set aside, so the best *accepted* look is frame 1.
    assert body["frame_id"] == ids[1]
    assert body["n_accepted"] == 2  # only accepted frames counted
