""""Is it enough yet?" honours the panel count on a mosaic.

The fourth wrong-denominator instance the audit sweep turned up. A per-object-
type integration goal ("Nebula 4 h", "Galaxy 6 h") is a *per-pixel depth*: it
means "enough integration for a clean image", and cleanliness is a property of a
pixel, not of a target row. On a mosaic no pixel ever sees more than its own
panel's subs, so a four-panel mosaic at 1 h/panel was told it had
**"plenty for a clean image"** — and the Tonight planner turned the same
verdict into *"Plenty — try something new"*, i.e. advice to abandon a mosaic
that has a quarter of the light it needs.

The fix ships one number, ``field_fulls``, from the newest stack run
(``canvas_area / one_native_frame_area``, drizzle divided out) on every surface
that reads the readiness inputs — Dashboard (``/api/library-progress``), Target
detail (``/api/targets/{safe}``), and the Tonight planner (``/api/plan/tonight``).
The client-side verdict scales the goal by it so the honest per-panel yardstick
is what the beginner reads.

Every mosaic case here is written against a fixture with the same canvas +
native-frame *shape* the owner actually has, and the assertions are on the
served value the frontend consumes, not on an intermediate function. See
``docs/IMPROVEMENTS.md`` → "the fourth wrong-denominator instance".
"""

from __future__ import annotations

import json
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import StackRunRow


# Match the ``solved_library`` fixture: every seeded frame has these native
# dimensions (see ``tests/webapp/conftest.py`` — ``FRAME_W`` / ``FRAME_H``).
FRAME_W, FRAME_H = 480, 320


def _add_run(
    data_root: Path,
    safe: str,
    *,
    canvas_w: int,
    canvas_h: int,
    drizzle: bool = False,
    drizzle_scale: float = 1.0,
) -> int:
    """Attach one stack run of the given canvas to a fixture target.

    ``field_fulls`` is derived from the newest run's canvas and one native frame
    row (the fixture sets both). Anything else about the run is unused by the
    readiness path, so this stays a minimal shape rather than a real stack.
    """
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None,
                timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master",
                fits_path=None, tiff_path=None, preview_path=None,
                n_frames_used=200,
                canvas_h=canvas_h, canvas_w=canvas_w,
                coverage_min=1, coverage_max=200,
                options_json=json.dumps({
                    "drizzle": drizzle, "drizzle_scale": drizzle_scale,
                }),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


# ---------------------------------------------------------------------------
# Dashboard — /api/library-progress
# ---------------------------------------------------------------------------


def test_library_progress_reports_field_fulls_1_for_a_single_field_stack(
    client, solved_library,
):
    """A single-field stack must read as ``1.0`` — the sums cancel and the
    verdict is bit-for-bit today's."""
    _add_run(solved_library, "M_42", canvas_w=FRAME_W, canvas_h=FRAME_H)

    body = client.get("/api/library-progress").json()
    by_safe = {row["safe"]: row for row in body}
    assert by_safe["M_42"]["field_fulls"] == 1.0


def test_library_progress_reports_field_fulls_4_for_a_2x2_mosaic(
    client, solved_library,
):
    """The canonical bug shape: a 2×2 no-overlap mosaic reads as 4 fields, so
    the client-side verdict scales the goal by 4 rather than telling a mosaic
    owner they are done at a quarter of the light they need."""
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2,
    )

    body = client.get("/api/library-progress").json()
    by_safe = {row["safe"]: row for row in body}
    assert by_safe["M_42"]["field_fulls"] == 4.0


def test_library_progress_field_fulls_ignores_drizzle_super_sampling(
    client, solved_library,
):
    """A 2× drizzled *single field* is not four fields — without this the fix
    would quadruple the goal on every drizzled single-field stack. Divide the
    canvas back through the drizzle scale."""
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2,
        drizzle=True, drizzle_scale=2.0,
    )

    body = client.get("/api/library-progress").json()
    by_safe = {row["safe"]: row for row in body}
    assert by_safe["M_42"]["field_fulls"] == 1.0


def test_library_progress_field_fulls_is_null_for_a_never_stacked_target(
    client, solved_library,
):
    """A target with accepted subs but no run yet has no canvas to divide, so
    the field is present-but-null. The client falls back to the un-scaled goal
    (today's behaviour) rather than guessing a mosaic shape from ingest alone."""
    # Neither seeded target has a stack run in the base fixture.
    body = client.get("/api/library-progress").json()
    for row in body:
        assert "field_fulls" in row  # present so an older frontend doesn't crash
        assert row["field_fulls"] is None


# ---------------------------------------------------------------------------
# Target detail — /api/targets/{safe}
# ---------------------------------------------------------------------------


def test_target_detail_carries_field_fulls_for_the_readiness_card(
    client, solved_library,
):
    """The Target page's "Is it enough yet?" card scales the per-type goal by
    this — it opens the project once per detail read (the light Library list
    endpoint deliberately does not, to keep an O(N) refresh cheap)."""
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2,
    )

    body = client.get("/api/targets/M_42").json()
    assert body["field_fulls"] == 4.0


def test_target_list_does_not_pay_for_field_fulls_on_every_row(
    client, solved_library,
):
    """The Library list endpoint (``GET /api/targets``) is polled on every
    refresh and iterates every target. Its ``field_fulls`` stays ``None`` — the
    O(N) per-project open would be pure waste on a screen that never reads the
    field, and the Dashboard/Target-page paths serve their own copy."""
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2,
    )

    rows = client.get("/api/targets").json()
    by_safe = {row["safe_name"]: row for row in rows}
    assert by_safe["M_42"]["field_fulls"] is None


# ---------------------------------------------------------------------------
# Tonight planner — /api/plan/tonight
# ---------------------------------------------------------------------------


def test_tonight_plan_carries_field_fulls_on_already_targeted_rows(
    client, solved_library,
):
    """The row hint on the planner is where the bug is *worst* — the same
    verdict becomes *"Plenty — try something new"*, i.e. advice to abandon a
    mosaic that is a quarter done. The plan must serve the panel count so the
    row can scale its goal, not just its total exposure."""
    _add_run(
        solved_library, "M_42",
        canvas_w=FRAME_W * 2, canvas_h=FRAME_H * 2,
    )
    # Configure a location so the plan can actually rank targets, then pick a
    # night both fixture targets are visible.
    client.put("/api/settings", json={"site_lat": 30.0, "site_lon": 0.0})

    body = client.get(
        "/api/plan/tonight",
        params={"when": "2026-01-15T20:00:00+00:00"},
    ).json()
    by_id = {t["id"]: t for t in body["targets"]}
    assert by_id["M_42"]["already_targeted"] is True
    assert by_id["M_42"]["field_fulls"] == 4.0
    # NGC_7000 has no stack run yet → null (present so older frontends see it).
    assert by_id["NGC_7000"]["already_targeted"] is True
    assert by_id["NGC_7000"]["field_fulls"] is None


def test_tonight_plan_catalog_rows_carry_no_field_fulls(client, solved_library):
    """Catalog candidates (targets the user hasn't shot yet) never have a
    canvas of their own — the field is absent/null on those rows. This pins
    what "no scaling" means for the frontend readiness fallback."""
    client.put("/api/settings", json={"site_lat": 30.0, "site_lon": 0.0})
    body = client.get(
        "/api/plan/tonight",
        params={"when": "2026-01-15T20:00:00+00:00"},
    ).json()
    catalog_rows = [t for t in body["targets"] if not t["already_targeted"]]
    assert catalog_rows  # sanity: the plan really did include some catalog rows
    for t in catalog_rows:
        # Absent or null — either is a signal to fall back to the un-scaled
        # goal on the frontend, and the shape must not carry a number.
        assert t.get("field_fulls") in (None,)
