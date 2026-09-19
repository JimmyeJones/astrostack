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


def test_the_card_streams_the_target_instead_of_listing_it(
        client, solved_library, monkeypatch):
    """The card reads four small fields off one sub and a count, and it was
    building a `FrameRow` for every accepted sub of the target to get them.

    Fail-before: `list(proj.iter_frames(accepted_only=True))` — 35,894 rows on
    the owner's deepest target, each carrying its own plate solution, measured
    at **1,181 ms / 135.3 MB peak** against **858 ms / ~0 MB** for the same
    pick and the same count (AGENTS.md §10 — this box has an OOM history).

    Asserted structurally rather than by bytes: what the endpoint hands
    `best_frame` is what decides whether anything is retained, and `best_frame`
    holds only the winner (pinned in `tests/test_qc_grading.py`).
    """
    from seestack.qc.grading import best_frame as real_best_frame

    seen: list[str] = []

    def watching(frames):
        seen.append(type(frames).__name__)
        assert not isinstance(frames, (list, tuple)), (
            f"the endpoint materialised the target as a {type(frames).__name__}")
        return real_best_frame(frames)

    # The endpoint imports it inside the handler, so the module attribute is
    # what it will resolve on the call.
    monkeypatch.setattr("seestack.qc.grading.best_frame", watching)
    body = client.get("/api/targets/M_42/best-frame").json()
    assert seen, "best_frame was not called"
    assert body["n_accepted"] == 3


def test_the_accepted_count_is_the_one_the_frames_table_would_give(
        client, solved_library, data_root):
    """It comes from `COUNT(*)` now rather than `len()` of the rows the pick
    walked, and the two are only the same number while they share a filter —
    so it is pinned against the rows themselves, with a rejected sub present so
    "all frames" and "accepted frames" are different answers."""
    _set_qc(data_root, "M_42", {
        0: {"accept": False, "reject_reason": "user"},
        1: {"fwhm_px": 2.6, "star_count": 400},
    })
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            accepted = len(list(proj.iter_frames(accepted_only=True)))
            everything = len(list(proj.iter_frames()))
        finally:
            proj.close()
    finally:
        lib.close()
    assert accepted != everything, "the fixture must have a rejected sub"
    assert client.get("/api/targets/M_42/best-frame").json()["n_accepted"] == accepted
