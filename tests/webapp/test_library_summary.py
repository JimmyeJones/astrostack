"""GET /api/library/summary — the "Your sky, so far" whole-library roll-up."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def test_summary_empty(client):
    r = client.get("/api/library/summary")
    assert r.status_code == 200
    b = r.json()
    assert b["n_targets_imaged"] == 0
    assert b["n_subs_kept"] == 0
    assert b["total_integration_s"] == 0.0
    assert b["integration_hours"] == 0.0
    assert b["first_light_utc"] is None
    assert b["longest_target"] is None
    assert b["most_imaged_target"] is None
    assert b["heroes"] == []


def test_summary_rolls_up_library(client, solved_library):
    b = client.get("/api/library/summary").json()
    # The solved_library fixture ingests two targets with accepted light.
    assert b["n_targets_imaged"] == 2
    assert b["n_subs_kept"] > 0
    assert b["total_integration_s"] > 0.0
    assert b["integration_hours"] >= 0.0
    assert b["first_light_utc"] is not None
    assert b["longest_target"] is not None
    assert b["most_imaged_target"] is not None
    # No stacks registered yet → no finished pictures to show.
    assert b["heroes"] == []


def _register_preview(root, safe, preview="master_preview.png"):
    """Register a stack run with a preview file that exists on disk, so the
    library stamps ``last_stack_preview`` at a real path."""
    lib = Library.open_or_create(root / "library")
    try:
        entry = lib.find_target(safe)
        target_dir = lib.target_dir(entry)
        preview_path = target_dir / preview
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(b"\x89PNG\r\n")  # non-empty; existence is what matters
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
                options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_summary_lists_finished_pictures_as_heroes(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_preview(solved_library, safe)

    b = client.get("/api/library/summary").json()
    heroes = b["heroes"]
    assert len(heroes) == 1
    assert heroes[0]["safe"] == safe
    assert heroes[0]["thumbnail_url"] == f"/api/targets/{safe}/thumbnail"
    # And the thumbnail actually serves (the endpoint the URL points at).
    assert client.get(heroes[0]["thumbnail_url"]).status_code == 200
