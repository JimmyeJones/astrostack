"""The Rotate op's help says which way it turns — and that is the way it turns.

``geometry.rotate`` hands its angle to ``scipy.ndimage.rotate`` on ``axes=(0, 1)``
with row 0 at the top of the picture, so a positive angle turns the picture
**anticlockwise** as it is displayed. The help under the Angle slider used to say
"clockwise", which sent a beginner the wrong way on every try. The direction itself
is not changed (a saved recipe must keep rendering the picture it rendered), so the
words are pinned against the pixels instead.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.registry import EditContext, get_op


def _brightest(img: np.ndarray) -> tuple[int, int]:
    y, x = np.unravel_index(np.nanargmax(img[..., 0]), img.shape[:2])
    return int(y), int(x)


@pytest.mark.parametrize("angle", [30.0, -30.0])
def test_the_help_names_the_direction_the_pixels_turn(angle):
    spec = get_op("geometry.rotate")
    img = np.zeros((41, 41, 3), np.float32)
    img[4, 20] = 1.0                       # a star straight above the centre
    out = spec.apply(img, {"angle": angle, "expand": False}, EditContext())
    y, x = _brightest(out)
    assert y < 20                          # still in the top half
    # A top-centre point moves left when the picture turns anticlockwise and right
    # when it turns clockwise.
    turned = "anticlockwise" if x < 20 else "clockwise"
    expected = "anticlockwise" if angle > 0 else "clockwise"
    assert turned == expected

    help_text = next(p.help for p in spec.params if p.key == "angle")
    assert "positive angle turns it anticlockwise" in help_text
    assert "negative one clockwise" in help_text
