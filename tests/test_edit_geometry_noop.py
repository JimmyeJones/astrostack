"""A geometry op at its own defaults reshapes nothing — and the surfaces that
switch themselves off "because the recipe reshapes the frame" have to know it.

``geometry.crop``, ``geometry.rotate`` and ``geometry.resize`` each default to a
no-op: a whole-frame rectangle, 0°, scale 1.0. That is on purpose — an op added
from the editor's Add menu must not move the picture before the user has aimed it
— but it means "the recipe carries an *enabled* geometry op" is not the same
question as "the frame has been reshaped", and two editor surfaces were asking the
first while answering the second.

:func:`reshapes_frame` is the question they should ask. These tests pin it against
the ops themselves: for every case below, the op is actually applied and the claim
is checked against whether the pixels moved.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.ops.geometry import GEOMETRY_OP_IDS, reshapes_frame
from seestack.edit.registry import EditContext, get_op

# Defaults straight off each op's own param schema — what the Add menu hands the
# user. Every one of these must read as "reshapes nothing".
DEFAULTS = {op_id: get_op(op_id).defaults() for op_id in GEOMETRY_OP_IDS}

REAL = {
    "geometry.crop": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9},
    "geometry.rotate": {"angle": 7.5},
    "geometry.resize": {"scale": 0.5},
}


def _scene(h: int = 64, w: int = 80) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = (0.1 + 0.3 * (xx / w) + 0.2 * (yy / h)).astype(np.float32)
    return np.repeat(img[..., None], 3, axis=2)


def _applied(op_id: str, params: dict) -> np.ndarray:
    return np.asarray(
        get_op(op_id).apply(_scene(), dict(params),
                            EditContext(stage="nonlinear")),
        dtype=np.float32)


@pytest.mark.parametrize("op_id", GEOMETRY_OP_IDS)
def test_each_op_at_its_own_defaults_reshapes_nothing(op_id):
    """The claim, and the op's own behaviour, on the params the Add menu gives."""
    assert reshapes_frame(op_id, DEFAULTS[op_id]) is False
    # …and that really is a no-op: same shape, same pixels.
    out = _applied(op_id, DEFAULTS[op_id])
    src = _scene()
    assert out.shape == src.shape
    assert np.array_equal(out, src)


@pytest.mark.parametrize("op_id", GEOMETRY_OP_IDS)
def test_each_op_with_a_real_setting_does_reshape(op_id):
    assert reshapes_frame(op_id, REAL[op_id]) is True
    out = _applied(op_id, REAL[op_id])
    src = _scene()
    assert out.shape != src.shape or not np.array_equal(out, src)


def test_an_empty_param_dict_is_the_defaults(_=None):
    """The editor stores only the params it has touched, so ``{}`` is reachable."""
    for op_id in GEOMETRY_OP_IDS:
        assert reshapes_frame(op_id, {}) is False


def test_a_crop_dragged_back_out_to_the_whole_frame_reshapes_nothing():
    """A user who tries a crop and widens it again still carries the op."""
    assert reshapes_frame("geometry.crop",
                          {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}) is False
    # A degenerate rectangle is one `_crop` ignores too, so it moves nothing.
    assert reshapes_frame("geometry.crop",
                          {"x0": 0.4, "y0": 0.0, "x1": 0.4, "y1": 1.0}) is False


def test_a_tone_op_is_not_a_geometry_op():
    assert reshapes_frame("tone.saturation", {"amount": 2.0}) is False
    assert reshapes_frame("detail.sharpen", {"amount": 1.0}) is False


def test_anything_it_cannot_be_sure_of_counts_as_reshaping():
    """The conservative direction: an unparseable or non-finite setting keeps the
    old answer, so a caller can only ever gain a correct offer."""
    assert reshapes_frame("geometry.rotate", {"angle": "x"}) is True
    assert reshapes_frame("geometry.rotate", {"angle": float("nan")}) is True
    assert reshapes_frame("geometry.resize", {"scale": None}) is True
    assert reshapes_frame("geometry.resize", {"scale": float("nan")}) is True
    assert reshapes_frame("geometry.crop", {"x0": float("nan")}) is False  # ignored by _crop
    assert reshapes_frame("geometry.rotate", None) is True
    assert reshapes_frame("geometry.rotate", "not a dict") is True


def test_a_rotation_just_over_the_ops_own_threshold_reshapes():
    """The thresholds are the ops' own, not a second set."""
    assert reshapes_frame("geometry.rotate", {"angle": 0.0009}) is False
    assert reshapes_frame("geometry.rotate", {"angle": 0.01}) is True
    assert reshapes_frame("geometry.resize", {"scale": 1.0005}) is False
    assert reshapes_frame("geometry.resize", {"scale": 1.01}) is True
    assert reshapes_frame("geometry.resize", {"scale": 0.0}) is False
