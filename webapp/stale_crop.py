""""An older version trimmed this picture too far."

The D1 family of bugs (fixed across v0.386–v0.399) was the border trim cropping a
**mosaic** to its panel overlaps: correct arithmetic on a single field, and on a
union canvas a sliver. Every one of those fixes re-derives the *trim*
(:func:`webapp.routers.editor._trim_rect_for_run`), so a mosaic stacked and
Auto-edited on the fixed build is right.

**Nothing re-derives a crop that was already saved.** A recipe is stored per run
(``editor_recipe:<id>`` in the target's project DB) and is replayed verbatim by
the editor, the hero image, the Library card, the thumbnail and the share sheet —
so a target the owner Auto-edited on, say, v0.277.0 still shows the sliver on
v0.407.1, under a stored auto-note that reports the 97 % trim as if it were the
right answer. That is the state the fourth external audit reproduced in the
shipped image over a v0.277.0 data volume (2026-09-10): the picture is wrong and
the sentence beside it calls it right.

**This module only ever *judges*.** It compares a stored crop against what the
current border rule would keep and says "these disagree by more than any framing
choice would explain". It never rewrites a recipe: a small crop may well be the
owner's own framing, and silently replacing it would be the same class of
mistake in the other direction (AGENTS.md §10 — additive, reversible, opt-in).
The surfaces built on it offer a one-click re-seed that replaces **only** the
crop op, and leave everything else alone.

The verdict is deliberately a pure function of two numbers so it can be tested
without a stack on disk, and so the Target page, the editor, and the library-wide
Dashboard count can never disagree about which pictures are affected.
"""

from __future__ import annotations

from typing import Any

#: A stored crop is stale when it keeps less than this share of what the current
#: border rule would keep.
#:
#: **This number has a second copy**, ``OVER_TRIM_KEEP_RATIO`` in
#: ``frontend/src/components/editor/mosaicTrim.ts``, which the editor's own note
#: (v0.416.0) decides by. Two implementations of one rule is how the Dashboard
#: and the editor end up naming different pictures, so
#: ``tests/test_stale_crop.py`` greps the TypeScript and fails if they drift.
#: Change them together or not at all.
#:
#: A quarter, not a half — the editor's reasoning, adopted here verbatim so the
#: two agree: the population that has to be told apart from a bug is a person
#: cropping in on their object, and at 0.5 someone deliberately framing on the
#: middle 40 % of their mosaic is accused. The case this exists for is a 27x gap
#: (the audit's run kept 3.4 % where the rule keeps 92.4 %).
STALE_CROP_KEEP_RATIO = 0.25

#: The op a stale crop lives in. One spelling, shared by every caller.
CROP_OP_ID = "geometry.crop"


def crop_keep_fraction(crop: dict[str, Any] | None) -> float | None:
    """The share of the canvas a fractional crop rectangle keeps (0..1), or
    ``None`` when the rectangle is missing or degenerate.

    ``crop`` is a mapping with ``x0``/``y0``/``x1``/``y1`` in 0..1 — the shape
    both the ``geometry.crop`` op's params and the trim suggestion use. Bounds
    are read defensively (a hand-edited recipe reaches here) and an inverted or
    zero-area rectangle answers ``None`` rather than a negative area."""
    if not isinstance(crop, dict):
        return None
    try:
        x0 = float(crop.get("x0", 0.0))
        y0 = float(crop.get("y0", 0.0))
        x1 = float(crop.get("x1", 1.0))
        y1 = float(crop.get("y1", 1.0))
    except (TypeError, ValueError):
        return None
    w, h = x1 - x0, y1 - y0
    if not (w > 0 and h > 0):
        return None
    return max(0.0, min(1.0, w * h))


def enabled_crop_op(ops: list[Any]) -> dict[str, Any] | None:
    """The first **enabled** ``geometry.crop`` op's params in a recipe's op list,
    or ``None``. Accepts op dicts (the stored/JSON shape) and
    :class:`seestack.edit.recipe.OpInstance` alike, so the same helper serves the
    router (which holds dicts) and anything holding a parsed recipe.

    A *disabled* crop is not what the viewer is looking at, so it is not what this
    note is about."""
    for op in ops or []:
        if isinstance(op, dict):
            op_id, enabled, params = op.get("id"), op.get("enabled", True), op.get("params")
        else:
            op_id, enabled = getattr(op, "id", None), getattr(op, "enabled", True)
            params = getattr(op, "params", None)
        if op_id != CROP_OP_ID or not enabled:
            continue
        return params if isinstance(params, dict) else {}
    return None


def crop_is_stale(stored_keep: float | None, suggested_keep: float | None) -> bool:
    """Whether a stored crop keeping ``stored_keep`` of the canvas disagrees with
    the current border rule (which would keep ``suggested_keep``) by more than a
    framing choice explains.

    ``None`` on either side answers ``False``: with no stored crop there is
    nothing to be wrong, and with no coverage map to re-derive the trim from
    there is nothing to compare against — an unmeasurable picture must not be
    accused (AGENTS.md §5, and the audit's own note that a green test looking at
    the wrong thing is worse than no test)."""
    if stored_keep is None or suggested_keep is None:
        return False
    if stored_keep >= suggested_keep:
        return False
    return stored_keep < STALE_CROP_KEEP_RATIO * suggested_keep


def stale_crop_verdict(stored_crop: dict[str, Any] | None,
                       suggested_crop: dict[str, Any] | None,
                       *, measurable: bool = True) -> dict[str, Any]:
    """The whole judgement for one run, as the shape every surface reports.

    ``suggested_crop`` is what the current border rule would keep — the same rect
    the editor's "Trim border" suggestion offers.

    ``None`` there means the rule proposes no trim, and this **declines to
    judge**, exactly as the editor's own note does (``overTrimmedVerdict`` returns
    ``null`` on a null suggestion). It is the weaker half of the rule and it is
    deliberate: the share to measure a crop against is what the canvas *offers*,
    and with no proposal there is no measured offer to use — only the whole
    frame, which a legitimately tight hand-crop is also a small share of. A sliver
    saved on a run the rule would not trim is therefore missed here; it is a
    narrower case than the one this exists for (the audit's run had a 92.4 %
    proposal), and catching it in one surface and not the others would be worse
    than missing it in all three.

    ``measurable`` is the *other* null: the caller could not re-derive the trim at
    all (no coverage sibling). Kept distinct because the two mean different things
    to a caller even where they lead to the same verdict here.

    Returns ``stale``, the two keep-fractions behind it, and the replacement crop
    a one-click re-seed would write."""
    stored_keep = crop_keep_fraction(stored_crop)
    suggested_keep = (crop_keep_fraction(suggested_crop)
                      if measurable and suggested_crop is not None else None)
    stale = crop_is_stale(stored_keep, suggested_keep)
    return {
        "stale": stale,
        "stored_keep_fraction": None if stored_keep is None else round(stored_keep, 4),
        "suggested_keep_fraction": (None if suggested_keep is None
                                    else round(suggested_keep, 4)),
        "suggested_crop": suggested_crop,
    }
