"""Execute a recipe: apply ordered operations across the stretch boundary.

The pipeline owns the linear→stretch→nonlinear contract:

* operations run in recipe order;
* the (single) stretch op maps linear data into display space ``[0, 1]`` and flips
  ``ctx.stage`` to ``"nonlinear"``;
* if no stretch op is enabled, a default asinh stretch is applied after the last
  enabled op so the preview is never black (matching the existing renderer, which
  always stretches).

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
) -> np.ndarray:
    """Return the edited RGB in display space ``[0, 1]``.

    ``for_preview`` skips ops marked ``proxy_safe=False`` (heavy ops apply on
    export / explicit apply, not on every slider drag).
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
        if for_preview and not spec.proxy_safe:
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

    if not stretched:
        # Auto-insert a default stretch so the output is viewable.
        from seestack.render.thumbnail import asinh_stretch
        out = asinh_stretch(out)
        ctx.stage = "nonlinear"

    return out


def has_stretch(recipe: Recipe) -> bool:
    return any(op.enabled and op.id == STRETCH_OP_ID for op in recipe.ops)
