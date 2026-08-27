"""`GET /api/targets/{safe}/cleanest-shot` — offer to promote a cleaner stack.

The engine half is unit-tested in ``tests/test_covernudge.py``; these pin the
endpoint's own contract: it compares only *genuine* stack runs, it stays silent
when nothing is pinned, and it never offers a candidate whose preview file is
gone (pinning that would silently fall back to the newest stack anyway).
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, *, ts: str, sigma: float | None,
                  n_frames: int = 40, options: dict | None = None,
                  preview: bool = True) -> int:
    """Add a stack run with a real 1×1 preview on disk. ``options=None`` writes a
    genuine ``StackOptions`` payload; pass a bare dict for a non-genuine run."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            png = Path(lib.target_dir(lib.find_target(safe))) / f"preview_{ts[:19].replace(':', '')}.png"
            if preview:
                Image.new("RGB", (1, 1), (7, 7, 7)).save(png)
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts,
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=str(png), n_frames_used=n_frames,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=n_frames,
                options_json=json.dumps(
                    options if options is not None else {"output_name": "m42"}),
                noise_sigma=sigma,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_cleaner_newest_stack_offers_the_swap(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    old = _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z",
                        sigma=0.012, n_frames=40)
    new = _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z",
                        sigma=0.008, n_frames=90)

    # Nothing pinned yet → the cover already is the newest stack, so: silence.
    assert client.get(f"/api/targets/{safe}/cleanest-shot").json() is None

    client.put(f"/api/targets/{safe}/cover", json={"run_id": old})
    body = client.get(f"/api/targets/{safe}/cleanest-shot").json()
    assert body is not None
    assert body["run_id"] == new and body["cover_run_id"] == old
    assert body["percent_cleaner"] == 33  # 1 - 0.008/0.012
    assert body["n_frames_used"] == 90 and body["cover_n_frames_used"] == 40

    # Taking the offer — the same set-cover path the History page uses — clears
    # the nudge, with no state of its own to go stale.
    assert client.put(f"/api/targets/{safe}/cover",
                      json={"run_id": new}).status_code == 200
    assert client.get(f"/api/targets/{safe}/cleanest-shot").json() is None


def test_noisier_newest_stack_says_nothing(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    old = _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z", sigma=0.008)
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.020)
    client.put(f"/api/targets/{safe}/cover", json={"run_id": old})
    assert client.get(f"/api/targets/{safe}/cleanest-shot").json() is None


def test_editor_export_run_is_not_compared(client, solved_library):
    """An editor export's σ isn't measured on the same kind of image, so a newer
    export must never be offered as 'cleaner' than a genuine stack."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    old = _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z", sigma=0.012)
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.001,
                  options={"exported_from_run": old})
    client.put(f"/api/targets/{safe}/cover", json={"run_id": old})
    assert client.get(f"/api/targets/{safe}/cleanest-shot").json() is None


def test_candidate_without_a_preview_is_not_offered(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    old = _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z", sigma=0.012)
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.008,
                  preview=False)
    client.put(f"/api/targets/{safe}/cover", json={"run_id": old})
    assert client.get(f"/api/targets/{safe}/cleanest-shot").json() is None


def test_unknown_target_404(client, solved_library):
    assert client.get("/api/targets/does_not_exist/cleanest-shot").status_code == 404
