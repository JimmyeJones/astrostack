"""`GET /api/targets/{safe}/grainier-newest` — offer to pin back a better shot.

The mirror of ``cleanest-shot``, for the state a beginner is actually in: with
nothing pinned the cover *follows* the newest stack, so a hazy night's restack
silently replaces a better picture on every showcase surface.

The engine half is unit-tested in ``tests/test_covernudge.py``; these pin the
endpoint's own contract — genuine runs only, silence the moment anything is
pinned (so it and ``cleanest-shot`` can never both speak), no offer of a run
whose picture is gone, and no offer at all when the grainy stack isn't the
picture actually on show.
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
            png = (Path(lib.target_dir(lib.find_target(safe)))
                   / f"preview_{ts[:19].replace(':', '')}.png")
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


def test_grainier_newest_offers_the_better_earlier_picture(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    good = _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z",
                         sigma=0.008, n_frames=90)
    hazy = _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z",
                         sigma=0.012, n_frames=22)

    body = client.get(f"/api/targets/{safe}/grainier-newest").json()
    assert body is not None
    assert body["run_id"] == good and body["newest_run_id"] == hazy
    assert body["percent_grainier"] == 50  # 0.012/0.008 - 1
    assert body["n_frames_used"] == 90 and body["newest_n_frames_used"] == 22

    # Taking the offer pins the good one — which is exactly the state where this
    # nudge must fall silent, with no state of its own to go stale.
    assert client.put(f"/api/targets/{safe}/cover",
                      json={"run_id": good}).status_code == 200
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is None


def test_the_two_cover_nudges_are_mutually_exclusive(client, solved_library):
    """One needs a pin, the other needs none — so whatever the library holds,
    at most one of them ever has something to say."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    good = _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z", sigma=0.008)
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.012)

    # Unpinned: the grainier-newest nudge speaks, the cleanest-shot one cannot.
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is not None
    assert client.get(f"/api/targets/{safe}/cleanest-shot").json() is None

    # Pinned: they swap places — and still never overlap.
    client.put(f"/api/targets/{safe}/cover", json={"run_id": good})
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is None
    assert client.get(f"/api/targets/{safe}/cleanest-shot").json() is None


def test_a_cleaner_newest_stack_says_nothing(client, solved_library):
    """The ordinary, happy night: more subs, less grain."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z", sigma=0.012)
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.008)
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is None


def test_editor_export_run_is_not_compared(client, solved_library):
    """An editor export's σ isn't measured on the same kind of image, so a newer
    export must never be reported as a 'grainier' stack."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    good = _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z", sigma=0.008)
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.900,
                  options={"exported_from_run": good})
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is None


def test_silent_when_the_grainy_stack_is_not_the_picture_on_show(
    client, solved_library,
):
    """An editor export is newer still, so *it* is what the Library tile and the
    montage wall show. Telling the owner their picture got grainier while a
    different image is on screen would simply be wrong."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z", sigma=0.008)
    hazy = _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.012)
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is not None

    _register_run(solved_library, safe, ts="2026-05-10T00:00:00Z", sigma=None,
                  options={"exported_from_run": hazy})
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is None


def test_better_run_without_a_preview_is_not_offered(client, solved_library):
    """Pinning a run whose picture is gone falls straight back to the newest
    stack, which would make the nudge look broken."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z", sigma=0.008,
                  preview=False)
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.012)
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is None


def test_a_single_stack_says_nothing(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z", sigma=0.012)
    assert client.get(f"/api/targets/{safe}/grainier-newest").json() is None


def test_unknown_target_404(client, solved_library):
    assert client.get(
        "/api/targets/does_not_exist/grainier-newest").status_code == 404
