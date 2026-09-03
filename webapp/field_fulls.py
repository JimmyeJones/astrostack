"""How many single-frame *fields of sky* a target's canvas covers.

The one number the readiness verdict — "Is it enough yet?", the Dashboard's
"Target progress" bar, and the Tonight planner's "Plenty — try something new"
nudge — has been missing on a mosaic. A per-object-type goal like "6 h for a
galaxy" is a *per-pixel depth*: it means "enough integration for a clean image",
and cleanliness is a property of a pixel, not of a target row. On a mosaic no
pixel ever sees more than its own panel's subs, so a four-panel mosaic at
1 h/panel has 4 h totalled and 1 h of the goal — reading the total against the
goal without scaling tells the beginner they are done at a quarter of the light
they need. See the "fourth wrong-denominator instance" entry in
``docs/IMPROVEMENTS.md``.

The right scale for a mosaic is `canvas_area / native_frame_area` (with drizzle
divided out) — how many single-frame field-fulls of sky the target's picture
spans. A single-field stack is ≈1.0; a 2×2 no-overlap mosaic is 4.0; a 2×2
with 50% overlap is ~2.25. The readiness fraction then compares the total
integration against `goal_hours * field_fulls`, i.e. an honest per-panel depth.

Kept a pure function of the numbers themselves so it stays cheap to test and
easy to wire in wherever a caller already knows a target's newest run + its
frame shape (the two things the routers already have to hand).
"""

from __future__ import annotations

import json
import math
from typing import Any


def field_fulls_of_sky(
    canvas_w: int | float | None,
    canvas_h: int | float | None,
    *,
    frame_w: int | float | None,
    frame_h: int | float | None,
    drizzle_scale: float | None = None,
) -> float | None:
    """The number of single-frame field-fulls of sky the canvas covers.

    ``canvas_w``/``canvas_h`` are the stack canvas dimensions in pixels (as
    stored on the ``stack_runs`` row). ``frame_w``/``frame_h`` are the native
    sub dimensions (from any accepted frame — a target's subs are all the same
    shape). ``drizzle_scale`` is the run's drizzle super-sampling factor, so a
    2× drizzled single-field canvas (4× the pixels of a native frame) doesn't
    read as "4 fields of sky covered" — the sky it covers is still one field.

    Returns ``None`` when any dimension is missing or non-positive: the caller
    then falls back to the un-scaled goal, which is exactly today's behaviour on
    a target with no stacked picture yet or on an older backend. A value below
    1.0 (a run whose canvas is *smaller* than a native frame — possible when a
    stack was cropped, or a preview-only run recorded partial dims) is clamped
    up to 1.0 rather than lowering the goal: this is a beginner nudge, and
    *lowering* what "plenty" means from a canvas artefact would call a
    half-integrated target done.
    """
    if not _positive(canvas_w) or not _positive(canvas_h):
        return None
    if not _positive(frame_w) or not _positive(frame_h):
        return None

    scale = float(drizzle_scale) if drizzle_scale is not None else 1.0
    if not math.isfinite(scale) or scale < 1.0:
        scale = 1.0

    canvas_area = float(canvas_w) * float(canvas_h) / (scale * scale)
    frame_area = float(frame_w) * float(frame_h)
    if frame_area <= 0:
        return None
    ratio = canvas_area / frame_area
    if not math.isfinite(ratio) or ratio <= 0:
        return None
    # A canvas smaller than one native frame (a cropped stack, or a partial-dim
    # record on an older run) never *lowers* the goal — see the docstring. The
    # readiness verdict is a suggestion; erring below 1.0 could call a
    # half-integrated target done.
    return max(1.0, ratio)


def drizzle_scale_from_options(options_json: str | None) -> float | None:
    """Extract ``drizzle_scale`` from a stack run's stored ``options_json``.

    Returns ``None`` when the JSON is missing, malformed, or the run wasn't
    drizzled (``drizzle`` false / absent) — the caller then treats the canvas as
    native-scale, which is exactly right for the plain-mean and κ-σ paths.
    """
    if not options_json:
        return None
    try:
        opts: Any = json.loads(options_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(opts, dict):
        return None
    if not opts.get("drizzle"):
        return None
    raw = opts.get("drizzle_scale")
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val) or val <= 0:
        return None
    return val


def _positive(x: object) -> bool:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0


def target_field_fulls(proj) -> float | None:  # noqa: ANN001 — any open Project
    """The target's field-fulls figure, from its newest stack run + one native
    frame. ``None`` when the target has no stack yet, has no native frame
    dimensions recorded, or is small enough that the number would read as 1.0
    anyway (a single-field stack contributes no scaling, so callers can treat
    ``None`` and ``1.0`` interchangeably — see :func:`field_fulls_of_sky`).

    Two tiny SQL reads: the newest run's canvas + options (one row), and a
    single ``LIMIT 1`` frame row for the native shape. Runs on the
    already-open project the caller had to open for :func:`read_goal_s` and
    :func:`recent_night_pace_s`, so it costs nothing more than the two reads.
    """
    conn = getattr(proj, "_conn", None)
    if conn is None:
        return None
    try:
        run_row = conn.execute(
            "SELECT canvas_w, canvas_h, options_json FROM stack_runs "
            "ORDER BY timestamp_utc DESC LIMIT 1"
        ).fetchone()
    except Exception:  # noqa: BLE001 — a broken DB must not sink a dashboard card
        return None
    if run_row is None:
        return None
    canvas_w = run_row["canvas_w"] if "canvas_w" in run_row.keys() else None
    canvas_h = run_row["canvas_h"] if "canvas_h" in run_row.keys() else None
    options_json = (
        run_row["options_json"] if "options_json" in run_row.keys() else None
    )
    try:
        frame_row = conn.execute(
            "SELECT width_px, height_px FROM frames "
            "WHERE width_px IS NOT NULL AND height_px IS NOT NULL "
            "LIMIT 1"
        ).fetchone()
    except Exception:  # noqa: BLE001 — same rule as above
        return None
    if frame_row is None:
        return None
    frame_w = frame_row["width_px"] if "width_px" in frame_row.keys() else None
    frame_h = frame_row["height_px"] if "height_px" in frame_row.keys() else None
    drizzle = drizzle_scale_from_options(options_json)
    return field_fulls_of_sky(
        canvas_w, canvas_h,
        frame_w=frame_w, frame_h=frame_h,
        drizzle_scale=drizzle,
    )
