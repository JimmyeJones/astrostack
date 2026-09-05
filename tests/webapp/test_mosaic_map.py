"""`GET /api/targets/{safe}/mosaic-map` — "your mosaic, panel by panel".

Against a real Library/Project, so these pin the two things the engine tests
can't: that the endpoint reads exactly the frames the stacker would combine
(accepted **and** solved), and that a target which isn't a mosaic gets ``null``
rather than an invented grid.
"""

from __future__ import annotations

import math

from seestack.io.library import Library
from seestack.io.project import FrameRow

SUB_S = 10.0


def _seed_panels(data_root, panels, *, safe: str = "M_42", solved: bool = True,
                 accepted: bool = True, prefix: str = "panel") -> None:
    """Add ``{(ra, dec): n_subs}`` worth of solved, accepted frames to a target."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            i = 0
            for (ra, dec), n in panels.items():
                for _ in range(n):
                    proj.add_frame(FrameRow(
                        source_path=f"/synthetic/{prefix}_{i:04d}.fit",
                        ra_center_deg=ra, dec_center_deg=dec,
                        exposure_s=SUB_S,
                        wcs_json='{"synthetic": true}' if solved else None,
                        accept=accepted,
                    ))
                    i += 1
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def _mosaic(rows: int, cols: int, *, ra0: float = 200.0, dec0: float = 30.0,
            step: float = 0.5, subs: int = 40,
            per_panel: dict[tuple[int, int], int] | None = None):
    out: dict[tuple[float, float], int] = {}
    for r in range(rows):
        for c in range(cols):
            dec = dec0 + (rows - 1 - r) * step
            ra = ra0 + (cols - 1 - c) * step / math.cos(math.radians(dec))
            out[(ra, dec)] = (per_panel or {}).get((r, c), subs)
    return out


def test_a_single_field_target_gets_nothing(client, built_library):
    """The conftest target is one pointing, so the card must not appear at all —
    a beginner shooting one field is unaffected by this feature existing."""
    r = client.get("/api/targets/M_42/mosaic-map")
    assert r.status_code == 200
    assert r.json() is None


def test_a_mosaic_comes_back_as_a_grid_with_a_sentence(client, built_library, data_root):
    _seed_panels(data_root, _mosaic(2, 2))

    r = client.get("/api/targets/M_42/mosaic-map")
    assert r.status_code == 200
    body = r.json()
    assert body is not None
    assert (body["rows"], body["cols"]) == (2, 2)
    assert len(body["panels"]) == 4
    assert {(p["row"], p["col"]) for p in body["panels"]} \
        == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert body["thin"] is None                       # every panel got 40 subs
    assert "similar amount of time" in body["text"]


def test_the_thin_panel_is_named(client, built_library, data_root):
    """The sentence the feature exists for, end to end."""
    _seed_panels(data_root, _mosaic(2, 2, subs=120, per_panel={(1, 1): 10}))

    body = client.get("/api/targets/M_42/mosaic-map").json()
    assert body["thin"] is not None
    assert (body["thin"]["row"], body["thin"]["col"]) == (1, 1)
    assert body["thin"]["n_frames"] == 10
    assert "bottom-right" in body["text"]


def test_only_the_subs_the_stacker_would_use_are_mapped(client, built_library, data_root):
    """Set-aside subs are not in the picture, so they must not count toward a
    panel's depth — otherwise a clouded-out night would make a thin panel look
    healthy and the map would point the owner somewhere else."""
    _seed_panels(data_root, _mosaic(1, 2, subs=60))
    thin_panel = list(_mosaic(1, 2, subs=60))[1]      # the right-hand panel
    _seed_panels(data_root, {thin_panel: 200}, accepted=False, prefix="setaside")

    body = client.get("/api/targets/M_42/mosaic-map").json()
    assert body is not None
    assert all(p["n_frames"] == 60 for p in body["panels"]), body["panels"]


def test_unsolved_subs_have_no_pointing_to_map(client, built_library, data_root):
    """An unsolved sub has no place on the sky, so it is ignored — and cannot,
    by being ignored, turn a mosaic into a non-mosaic."""
    _seed_panels(data_root, _mosaic(1, 2, subs=60))
    _seed_panels(data_root, {(200.0, 30.0): 500}, solved=False, prefix="unsolved")

    body = client.get("/api/targets/M_42/mosaic-map").json()
    assert body is not None
    assert sum(p["n_frames"] for p in body["panels"]) == 120


def test_a_missing_target_is_a_404(client, built_library):
    assert client.get("/api/targets/NOPE/mosaic-map").status_code == 404
