"""'One frame vs your stack' reveal — info endpoint + rendered reference sub.

A beginner drops hundreds of subs in and gets one clean picture but never sees
the *before*. These read-only endpoints power a card that puts a single raw sub
next to the finished stack, stretched identically so the only visible difference
is the noise/detail stacking bought.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, *, with_preview: bool,
                  ts: str = "2026-05-01T00:00:00Z") -> int:
    """Add a stack run to ``safe`` (optionally with a real preview PNG on disk)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            preview_path = None
            if with_preview:
                preview = Path(lib.target_dir(lib.find_target(safe))) / f"prev_{ts[:10]}.png"
                Image.new("RGB", (4, 4), (10, 20, 30)).save(preview)
                preview_path = str(preview)
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts,
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=preview_path, n_frames_used=42,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=42,
                options_json=json.dumps({"output_name": "m42"}),
                total_exposure_s=1260.0,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_info_available_carries_the_caption_fields(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    # Caption fields come from the run's own provenance (best-effort, may be null
    # for sub_exposure_s if a frame carries no exposure).
    assert body["n_frames"] == 42
    assert body["integration_s"] == 1260.0
    assert "sub_exposure_s" in body


def test_info_unavailable_without_a_preview_to_compare(client, solved_library):
    # A run with no stored preview has nothing to compare against → available
    # false (the card self-hides), not a 404.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=False)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_info_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/one-sub-vs-stack")
    assert r.status_code == 404


def test_reference_sub_renders_a_real_png(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/reference-sub")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    im = Image.open(BytesIO(r.content))
    # A genuine debayered sub, not a 1×1 placeholder: decodes and has real extent.
    assert im.mode == "RGB"
    assert im.width > 1 and im.height > 1


def test_reference_sub_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/reference-sub")
    assert r.status_code == 404
