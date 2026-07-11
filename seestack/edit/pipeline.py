"""Execute a recipe: apply ordered operations across the stretch boundary.

The pipeline owns the linear→stretch→nonlinear contract:

* operations run in recipe order;
* the (single) stretch op maps linear data into display space ``[0, 1]`` and flips
  ``ctx.stage`` to ``"nonlinear"``;
* if no stretch op is enabled, a default STF autostretch is applied after the last
  enabled op so the preview is never black (matching the stored thumbnail's
  stretch, which is also STF).

Every op is best-effort: a failing op is skipped (its error collected) rather than
sinking the whole render — important for live preview responsiveness.
"""

from __future__ import annotations

import logging

import numpy as np

from seestack.edit.recipe import Recipe
from seestack.edit.registry import EditContext, as_rgb, get_op

log = logging.getLogger(__name__)

STRETCH_OP_ID = "tone.stretch"


def apply_recipe(
    rgb: np.ndarray,
    recipe: Recipe,
    ctx: EditContext | None = None,
    *,
    for_preview: bool = False,
    errors: list[str] | None = None,
    auto_stretch: bool = True,
) -> np.ndarray:
    """Return the edited RGB in display space ``[0, 1]``.

    The preview renders **every** enabled operation — that's the whole point of a
    live preview: what you see is what you'll export. Heavy ops just run on the
    small proxy (and size their pixel-scaled effects via ``ctx.scaled_px`` so the
    proxy result matches the full-res export). ``for_preview`` is kept for API
    symmetry but no longer skips anything.

    ``auto_stretch`` (default ``True``) inserts a default STF autostretch when no
    stretch op is enabled, so a preview is never black (the same adaptive stretch
    the stored thumbnail uses). Pass ``False`` to get the *linear* result of the
    enabled ops unchanged (used by the Stretch suggestion, which needs to measure
    the linear image the stretch op will receive, not a tone-mapped one).

    When ``ctx.already_display`` is set the input is *itself* a tone-mapped
    display-space image (an editor export re-opened for editing), so the default
    fallback stretch is suppressed too — otherwise an empty recipe would stretch
    an already-stretched picture again (the re-edit double-stretch). An explicit
    stretch op the user adds still runs.
    """
    ctx = ctx or EditContext()
    ctx.stage = "linear"
    out = as_rgb(rgb)
    stretched = False

    enabled = [op for op in recipe.ops if op.enabled]
    for op in enabled:
        spec = get_op(op.id)
        if spec is None:
            continue
        try:
            out = as_rgb(spec.apply(out, op.params, ctx))
        except Exception as exc:  # noqa: BLE001 — one bad op must not blank the render
            msg = f"{spec.label}: {type(exc).__name__}: {exc}"
            log.warning("edit op failed: %s", msg)
            if errors is not None:
                errors.append(msg)
            continue
        if spec.is_stretch:
            stretched = True
            ctx.stage = "nonlinear"

    if not stretched and auto_stretch and not ctx.already_display:
        # Auto-insert a default stretch so the output is viewable. Use the
        # per-channel STF autostretch — the same stretch the stored preview/
        # thumbnail (render.thumbnail.generate_thumbnail) and the one-click Auto
        # recipe already use — rather than a fixed-slider asinh. STF anchors each
        # channel's robust sky median to a neutral target grey and adapts to the
        # data, so a beginner's first-open view of an unedited stack is a
        # good-looking, correctly-exposed image (and consistent with the History/
        # Target thumbnail they already saw), instead of a middling one-size-fits-
        # all asinh. Like asinh it renders uncovered (NaN) pixels black, so we
        # restore NaN afterwards to keep "no coverage" out of the histogram/levels.
        from seestack.edit.registry import finite_mask
        from seestack.render.thumbnail import autostretch
        uncovered = ~finite_mask(out)
        out = as_rgb(autostretch(out)).copy()
        out[uncovered] = np.nan  # keep "no coverage" out of the histogram/levels
        ctx.stage = "nonlinear"

    return out


def has_stretch(recipe: Recipe) -> bool:
    return any(op.enabled and op.id == STRETCH_OP_ID for op in recipe.ops)
