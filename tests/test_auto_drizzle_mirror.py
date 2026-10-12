"""The automatic drizzle's two numbers, checked against the ones already shipped.

Two bars and one denominator have to agree across three modules, and the history
of this repo is that they quietly stop: the Stack form told the owner to turn
Drizzle off on six pictures measured 117–153 subs deep (observer issue #901)
because the surface quoting a per-pixel bar was fed a *frame total*. So:

* :func:`seestack.stack.autodrizzle.samples_per_output_pixel` must be the same
  arithmetic ``webapp.routers.stack._pixel_depth`` quotes on the Stack form —
  canvas area ÷ frame footprint, via ``webapp.field_fulls.field_fulls_of_sky``.
  The engine cannot import the webapp (AGENTS.md §6), so the copy is guarded
  here instead, the way ``tests/test_drizzle_bar_mirror.py`` guards the
  TypeScript copy of the warn bar.
* the *auto* bar must sit above the *warn* bar, because they answer different
  questions: one is "don't nag a user who asked for it", the other is "don't
  turn it on for a user who didn't".
"""

from __future__ import annotations

import pytest

from seestack.stack.autodrizzle import (
    AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL,
    AUTO_DRIZZLE_MIN_SCALE,
    AUTO_DRIZZLE_SCALE,
    samples_per_output_pixel,
)
from seestack.stack.drizzle_path import DRIZZLE_MIN_SAMPLES_PER_PIXEL
from webapp.field_fulls import field_fulls_of_sky

FRAME_W, FRAME_H = 480, 320


@pytest.mark.parametrize("n_frames", [1, 6, 200, 5477, 35894])
@pytest.mark.parametrize("canvas", [
    (320, 480),              # a single field
    (321, 481),              # a hair bigger — a dithered single pointing
    (640, 960),              # 2x2, no overlap
    (480, 720),              # 2x2 with 50% overlap
    (960, 1440),             # 3x3
    (1100, 2900),            # a long strip
])
def test_the_engines_per_pixel_depth_is_the_one_the_stack_form_quotes(
        n_frames, canvas):
    """``_pixel_depth``'s own expression, term for term, on both sides."""
    fulls = field_fulls_of_sky(canvas[1], canvas[0],
                               frame_w=FRAME_W, frame_h=FRAME_H)
    expected = (None if fulls is None or fulls <= 1.0 or n_frames <= 0
                else float(n_frames) / fulls)
    got = samples_per_output_pixel(n_frames, dst_shape=canvas,
                                   ref_shape=(FRAME_H, FRAME_W))
    assert (got is None) == (expected is None)
    if expected is not None:
        assert got == pytest.approx(expected, rel=1e-12)


def test_the_auto_bar_sits_above_the_warn_bar():
    """They are deliberately different numbers, and the order is the claim: a
    depth the app would *nag* about must never be one it turns drizzle on at."""
    assert AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL > DRIZZLE_MIN_SAMPLES_PER_PIXEL


def test_the_auto_bar_is_the_engines_own_recommendation():
    """``drizzle_path``'s module docstring recommends drizzle "when lots of
    dithered subs land on each output pixel (typically 200+)". That sentence is
    the provenance of this bar, so the two must not drift — if the
    recommendation is ever revised, this fails and the constant is revisited
    with it."""
    from seestack.stack import drizzle_path

    assert AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL == 200
    assert "200+" in (drizzle_path.__doc__ or "")


def test_the_offered_scales_stay_inside_what_the_form_allows():
    """The automatic scale has to be a value the Stack form could hold, or the
    owner cannot reproduce — or undo — what the app chose for him."""
    from webapp.schemas import stack_option_fields

    field = next(f for f in stack_option_fields() if f.key == "drizzle_scale")
    assert field.min is not None and field.max is not None
    assert field.min <= AUTO_DRIZZLE_MIN_SCALE <= AUTO_DRIZZLE_SCALE <= field.max
