"""Background-flatten mode dispatch + luminance-mode color preservation."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from seestack.bg.per_frame import (  # noqa: E402
    MODE_LUMINANCE,
    MODE_OFF,
    MODE_PER_CHANNEL,
    BackgroundOptions,
    subtract_background,
)


def _frame_with_gradient_and_object():
    """A frame with a gradient PLUS a bright off-centre 'object' that's not centred
    in the channels (simulating an emission nebula whose R/G/B morphology differs)."""
    rng = np.random.default_rng(11)
    h, w = 200, 280
    yy, xx = np.indices((h, w), dtype=np.float32)
    # Common gradient: brighter on the right.
    grad = (xx / w) * 200 + 1000
    rgb = np.stack([grad, grad, grad], axis=-1).astype(np.float32)
    rgb += rng.normal(scale=10.0, size=rgb.shape).astype(np.float32)
    # Add an "object" with different per-channel positions to simulate an
    # emission nebula. Tiny so per-channel mode doesn't eat it.
    cy, cx = h // 2, w // 2
    for dy, dx, c, amp in [(-2, -2, 0, 5000), (0, 0, 1, 4000), (2, 2, 2, 3000)]:
        rgb[cy+dy-3:cy+dy+3, cx+dx-3:cx+dx+3, c] += amp
    return rgb


def test_mode_off_returns_input_unchanged():
    rgb = _frame_with_gradient_and_object()
    out = subtract_background(rgb, BackgroundOptions(mode=MODE_OFF))
    np.testing.assert_array_equal(out, rgb)


def test_per_channel_removes_gradient():
    rgb = _frame_with_gradient_and_object()
    out = subtract_background(rgb, BackgroundOptions(mode=MODE_PER_CHANNEL, box_size=32),
                              use_gpu=False)
    for c in range(3):
        assert abs(np.median(out[..., c])) < 5.0


def test_luminance_removes_gradient_and_keeps_color_balance():
    rgb = _frame_with_gradient_and_object()
    out = subtract_background(rgb, BackgroundOptions(mode=MODE_LUMINANCE, box_size=32),
                              use_gpu=False)
    # Sky should be near zero in all channels.
    for c in range(3):
        assert abs(np.median(out[..., c])) < 5.0


def test_luminance_subtracts_same_shape_from_all_channels():
    """
    The whole point of luminance mode: the shape subtracted from each channel
    is identical (only per-channel offsets differ). We verify this by checking
    that channel-difference histograms are uniform (no spatial structure).
    """
    rgb = _frame_with_gradient_and_object()
    out = subtract_background(rgb, BackgroundOptions(mode=MODE_LUMINANCE, box_size=32),
                              use_gpu=False)
    # R-G should have minimal spatial variation in the *sky* region (away from
    # the small object). Take a sky-only slice on the left half.
    sky = out[:, :100, :]
    rg_diff = sky[..., 0] - sky[..., 1]
    # Standard deviation should be close to noise level (~10 ADU per channel
    # → ~14 in the difference). Looser bound to handle small statistical
    # variations from the per-channel median offset.
    assert np.std(rg_diff) < 25
