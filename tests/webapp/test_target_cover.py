"""Target "cover" pin: PUT endpoint + thumbnail resolution + History is_cover.

Lets a beginner pin a favourite stack run as the target's showcase image
instead of the tile always showing the newest stack. Read-only fallback to the
newest preview when nothing is pinned or the pinned run was pruned.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, *, color: tuple[int, int, int],
                  ts: str) -> tuple[int, Path]:
    """Add a stack run to ``safe`` with a distinct 1×1 PNG preview on disk so a
    test can tell which run's pixels the thumbnail served. Returns (run_id, png)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            preview = Path(lib.target_dir(lib.find_target(safe))) / f"preview_{ts[:10]}_{color[0]}.png"
            Image.new("RGB", (1, 1), color).save(preview)
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts,
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=str(preview), n_frames_used=5,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=5,
                options_json=json.dumps({"output_name": "m42"}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id, preview
    finally:
        lib.close()


def _pixel(content: bytes, tmp_path: Path) -> tuple[int, int, int]:
    p = tmp_path / "got.png"
    p.write_bytes(content)
    with Image.open(p) as im:
        return im.convert("RGB").getpixel((0, 0))


def test_pin_and_clear_cover(client, solved_library, tmp_path):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    old_id, _ = _register_run(solved_library, safe, color=(200, 0, 0),
                              ts="2026-05-01T00:00:00Z")
    new_id, _ = _register_run(solved_library, safe, color=(0, 0, 200),
                              ts="2026-05-09T00:00:00Z")

    # Default (unpinned): the thumbnail shows the NEWEST run's preview (blue).
    r = client.get(f"/api/targets/{safe}/thumbnail")
    assert r.status_code == 200
    assert _pixel(r.content, tmp_path) == (0, 0, 200)

    # No run is flagged as the cover, and the target payload has no pin.
    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    assert all(not run["is_cover"] for run in runs)
    assert client.get("/api/targets").json()[0]["cover_stack_run_id"] is None

    # Pin the OLDER run as the cover.
    r = client.put(f"/api/targets/{safe}/cover", json={"run_id": old_id})
    assert r.status_code == 200
    assert r.json()["cover_stack_run_id"] == old_id

    # The thumbnail now serves the pinned (older, red) run's pixels …
    r = client.get(f"/api/targets/{safe}/thumbnail")
    assert _pixel(r.content, tmp_path) == (200, 0, 0)
    # … and exactly that run is flagged is_cover in History.
    runs = {run["id"]: run["is_cover"] for run in
            client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs[old_id] is True and runs[new_id] is False

    # Clear the pin → back to newest (blue).
    r = client.put(f"/api/targets/{safe}/cover", json={"run_id": None})
    assert r.status_code == 200 and r.json()["cover_stack_run_id"] is None
    r = client.get(f"/api/targets/{safe}/thumbnail")
    assert _pixel(r.content, tmp_path) == (0, 0, 200)


def test_pin_rejects_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, color=(1, 2, 3), ts="2026-05-01T00:00:00Z")
    r = client.put(f"/api/targets/{safe}/cover", json={"run_id": 99999})
    assert r.status_code == 404


def test_pinned_run_pruned_falls_back_to_newest(client, solved_library, tmp_path):
    """A pinned run that is later deleted must degrade gracefully to the newest
    preview, never a broken image."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    old_id, _ = _register_run(solved_library, safe, color=(200, 0, 0),
                              ts="2026-05-01T00:00:00Z")
    _register_run(solved_library, safe, color=(0, 0, 200),
                  ts="2026-05-09T00:00:00Z")

    client.put(f"/api/targets/{safe}/cover", json={"run_id": old_id})

    # Delete the pinned run out from under the (still-set) cover id.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.delete_stack_run(old_id)
        finally:
            proj.close()
    finally:
        lib.close()

    # Thumbnail falls back to the newest (blue) preview rather than 404-ing.
    r = client.get(f"/api/targets/{safe}/thumbnail")
    assert r.status_code == 200
    assert _pixel(r.content, tmp_path) == (0, 0, 200)


def test_pin_missing_target_404(client, solved_library):
    r = client.put("/api/targets/does_not_exist/cover", json={"run_id": 1})
    assert r.status_code == 404
