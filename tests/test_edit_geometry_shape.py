"""``geometry.edited_shape`` — the size a recipe renders at, without rendering.

The editor's print-size menu promises sizes off this number and the print export
then refuses any it cannot fill from the *rendered* pixels, so the two must agree
on every geometry op exactly, not approximately.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.ops.geometry import edited_shape, rotated_shape
from seestack.edit.recipe import recipe_from_dict
from seestack.edit.registry import EditContext, as_rgb, get_op


def _rendered_shape(recipe, h: int, w: int) -> tuple[int, int]:
    out = as_rgb(np.zeros((h, w, 3), np.float32))
    ctx = EditContext(is_proxy=False, proxy_scale=1.0)
    for op in recipe.ops:
        if op.enabled:
            out = as_rgb(get_op(op.id).apply(out, op.params, ctx))
    return out.shape[0], out.shape[1]


@pytest.mark.parametrize("ops", [
    [],
    [{"id": "tone.stretch", "params": {"stretch": 0.6}}],
    [{"id": "geometry.crop", "params": {"x0": 0.055, "y0": 0.0, "x1": 1.0, "y1": 0.97}}],
    [{"id": "geometry.crop", "params": {"x0": 0.9, "y0": 0.1, "x1": 0.2, "y1": 0.8}}],
    [{"id": "geometry.crop", "params": {"x0": 0.5, "x1": 0.5001}}],          # degenerate
    [{"id": "geometry.resize", "params": {"scale": 0.37}}],
    [{"id": "geometry.rotate", "params": {"angle": 17.5}}],
    [{"id": "geometry.rotate", "params": {"angle": -33.0, "expand": False}}],
    [{"id": "geometry.crop", "params": {"x0": 0.1, "y0": 0.2, "x1": 0.8, "y1": 0.9}},
     {"id": "geometry.rotate", "params": {"angle": 90.0}},
     {"id": "geometry.resize", "params": {"scale": 1.5}},
     {"id": "geometry.crop", "params": {"x0": 0.05, "y0": 0.0, "x1": 0.95, "y1": 1.0}}],
    [{"id": "geometry.crop", "enabled": False,
      "params": {"x0": 0.3, "y0": 0.3, "x1": 0.6, "y1": 0.6}}],
])
@pytest.mark.parametrize("shape", [(123, 211), (300, 97)])
def test_edited_shape_matches_what_the_ops_render(ops, shape):
    recipe = recipe_from_dict({"ops": ops})
    assert edited_shape(recipe, shape) == _rendered_shape(recipe, *shape)


def test_rotated_shape_is_none_where_rotate_is_a_no_op():
    assert rotated_shape(100, 200, {"angle": 0.0}) is None
    assert rotated_shape(2, 200, {"angle": 30.0}) is None
