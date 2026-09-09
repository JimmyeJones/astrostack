"""The grain verdict travels with a run, so the History chip can stop promising
there is nothing to see.

A mosaic panel differs from its neighbours in its sky *level* — which levelling
removes, and which ``seam_verdict`` reports — or in its *grain*, because a panel
shot with fewer subs is noisier and no processing puts those photons back. The
two routinely disagree on one picture, and the chip's tooltip said the level
half out loud ("you shouldn't see seams between them") on canvases that plainly
showed a grainier rectangle. It now reads both.
"""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, **kw) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-09-09T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=21,
                canvas_h=615, canvas_w=907, coverage_min=1, coverage_max=21,
                options_json=json.dumps({"sigma_clip": True}), **kw))
        finally:
            proj.close()
    finally:
        lib.close()


def test_the_run_listing_carries_both_mosaic_verdicts(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    uneven = _register_run(solved_library, safe, is_mosaic=True,
                           seam_residual=0.7, grain_ratio=1.43,
                           grain_thin_frames=3, grain_deep_frames=6,
                           grain_thin_share=0.2257)
    even = _register_run(solved_library, safe, is_mosaic=True,
                         seam_residual=0.7, grain_ratio=1.02,
                         grain_thin_frames=5, grain_deep_frames=6,
                         grain_thin_share=0.3)
    old = _register_run(solved_library, safe, is_mosaic=True, seam_residual=0.7)

    runs = {r["id"]: r
            for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    # Level in all three cases — only what "even" *means* differs.
    assert runs[uneven]["seam_verdict"] == "flat"
    assert runs[uneven]["grain_verdict"] == "uneven"
    assert runs[even]["grain_verdict"] is None
    # A run stacked before the measurement existed says nothing rather than
    # claiming its panels are equally deep — same contract as seam_verdict.
    assert runs[old]["grain_verdict"] is None


def test_a_single_field_run_carries_neither(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe)
    runs = {r["id"]: r
            for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs[run_id]["seam_verdict"] is None
    assert runs[run_id]["grain_verdict"] is None
