"""`GET /api/targets/{safe}/grainier-default` — offer back the better picture.

The mirror of ``cleanest-shot``: with **nothing pinned** the cover means "newest",
so a restack through haze silently replaces a better picture on every showcase
surface. The engine half is unit-tested in ``tests/test_covernudge.py``; these pin
the endpoint's own contract — genuine runs only, silence the moment anything is
pinned, no offer of a run whose preview is gone, and the guarantee that this and
``cleanest-shot`` can never both speak about the same target.
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


def test_a_grainier_restack_offers_the_better_picture_back(client, solved_library):
    """The owner's cloudy-night case: last night's stack is genuinely newer and
    genuinely worse, and with no pin every showcase surface has already moved to
    it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    good = _register_run(solved_library, safe, ts="2026-05-14T00:00:00Z",
                         sigma=0.020, n_frames=120)
    _register_run(solved_library, safe, ts="2026-05-20T00:00:00Z",
                  sigma=0.030, n_frames=40)

    body = client.get(f"/api/targets/{safe}/grainier-default").json()
    assert body is not None
    assert body["run_id"] == good
    assert body["percent_grainier"] == 50          # 0.030/0.020 − 1
    assert body["n_frames_used"] == 40             # what's on show now
    assert body["best_n_frames_used"] == 120       # what it's offering back
    assert body["best_timestamp_utc"] == "2026-05-14T00:00:00Z"

    # Taking the offer — the same set-cover path the History page uses — clears
    # the nudge, with no state of its own to go stale.
    assert client.put(f"/api/targets/{safe}/cover",
                      json={"run_id": good}).status_code == 200
    assert client.get(f"/api/targets/{safe}/grainier-default").json() is None


def test_the_two_cover_nudges_never_both_speak(client, solved_library):
    """One needs a pin, the other needs none. The Target page renders both, so
    the exclusion is worth pinning at the endpoint level too."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    good = _register_run(solved_library, safe, ts="2026-05-14T00:00:00Z", sigma=0.020)
    _register_run(solved_library, safe, ts="2026-05-20T00:00:00Z", sigma=0.030)

    assert client.get(f"/api/targets/{safe}/grainier-default").json() is not None
    assert client.get(f"/api/targets/{safe}/cleanest-shot").json() is None

    # Pin anything and the grainier note goes quiet — a pinned cover cannot have
    # moved on its own, so there is no silent regression left to report.
    client.put(f"/api/targets/{safe}/cover", json={"run_id": good})
    assert client.get(f"/api/targets/{safe}/grainier-default").json() is None


def test_the_ordinary_deepening_night_says_nothing(client, solved_library):
    """More subs, less grain — the happy path must stay completely silent."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, ts="2026-04-01T00:00:00Z",
                  sigma=0.031, n_frames=40)
    _register_run(solved_library, safe, ts="2026-05-09T00:00:00Z",
                  sigma=0.011, n_frames=120)
    assert client.get(f"/api/targets/{safe}/grainier-default").json() is None


def test_an_editor_export_is_never_compared(client, solved_library):
    """An export's σ isn't measured on the same kind of image, so it can neither
    be blamed for a regression nor offered as the better picture."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    good = _register_run(solved_library, safe, ts="2026-05-14T00:00:00Z", sigma=0.020)
    # A very "clean" export newer than the good run: if exports were compared,
    # this would be read as the newest stack and nothing would fire at all.
    _register_run(solved_library, safe, ts="2026-05-20T00:00:00Z", sigma=0.001,
                  options={"exported_from_run": good})
    assert client.get(f"/api/targets/{safe}/grainier-default").json() is None


def test_a_better_run_without_a_preview_is_not_offered(client, solved_library):
    """Pinning a run whose picture is gone falls back to the newest stack anyway,
    which would make the nudge look broken."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, ts="2026-05-14T00:00:00Z", sigma=0.020,
                  preview=False)
    _register_run(solved_library, safe, ts="2026-05-20T00:00:00Z", sigma=0.030)
    assert client.get(f"/api/targets/{safe}/grainier-default").json() is None


def test_a_lone_stack_says_nothing(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    assert client.get(f"/api/targets/{safe}/grainier-default").json() is None
    _register_run(solved_library, safe, ts="2026-05-20T00:00:00Z", sigma=0.050)
    assert client.get(f"/api/targets/{safe}/grainier-default").json() is None


def test_unknown_target_404(client, solved_library):
    assert client.get("/api/targets/does_not_exist/grainier-default").status_code == 404
