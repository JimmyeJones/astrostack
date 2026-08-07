"""Gentle sharpening for a finished Moon/Sun still.

A lucky-imaging stack is an *average*, and averaging is a low-pass filter: the
result is cleaner than any single frame but also slightly softer than the
sharpest one that went into it. Every planetary tool answers this the same way —
RegiStax's wavelets, AutoStakkert's hand-off to a sharpening step — because the
noise floor a stack of 30 % of the frames buys is exactly what makes sharpening
affordable in the first place.

The deep-sky editor already has a sharpen op, but a Moon/Sun still is not a
stack run and can't be opened there, so without this the picture the beginner
downloads is the soft one. This module is that one step and nothing more: an
unsharp mask, in display space, on the picture that has already been rendered.

Deliberately one knob (**how much**), not two. The radius that suits a lunar
surface is small and does not vary the way a deep-sky star profile does, so
exposing it would be a knob with one right answer — the sort of expert surface
this app is meant to spare its user.
"""

from __future__ import annotations

import numpy as np

#: Radius of the blur the detail is measured against, in pixels. Lunar and solar
#: detail — crater rims, the terminator, granulation — lives at the scale of a
#: pixel or two, so a tight radius lifts *that* rather than the disk's overall
#: shading. It is also what keeps the limb honest: a wide radius on a
#: high-contrast edge is what produces the dark halo that makes an over-cooked
#: planetary image obvious at a glance.
SHARPEN_SIGMA_PX = 1.1

#: The strengths offered to the user, and what each is called. Kept here rather
#: than in the UI so the numbers and the words can't drift apart, and so a
#: caller can validate an amount against the same ceiling the page offers.
SHARPEN_PRESETS: tuple[tuple[str, float], ...] = (
    ("Off", 0.0),
    ("Gentle", 0.6),
    ("Medium", 1.2),
    ("Strong", 2.0),
)

#: Nothing above this is accepted. Past ~2 the halo around the limb is more
#: noticeable than the detail gained, which is not a trade a beginner is being
#: offered here.
SHARPEN_MAX = 2.0


def sharpen_still(rgb: np.ndarray, amount: float) -> np.ndarray:
    """Unsharp-mask an already display-rendered still (values 0–1).

    ``amount`` is how much of the fine detail to add back: 0 returns the input
    untouched (byte-for-byte — this is the default path and must stay free), and
    :data:`SHARPEN_MAX` is the most that is offered.

    The mask is built per channel from the same blur, so sharpening lifts detail
    without shifting colour, and the result is clipped back into 0–1 so it can
    still be written as an ordinary 8- or 16-bit picture. Uncovered pixels
    (NaN, from an alignment shift) stay NaN rather than smearing a hole's edge
    into the picture around it.
    """
    arr = np.asarray(rgb, dtype=np.float32)
    a = float(amount)
    if not np.isfinite(a) or a <= 0.0:
        return arr
    a = min(a, SHARPEN_MAX)

    from scipy.ndimage import gaussian_filter

    holes = ~np.isfinite(arr)
    # Blur a hole-free copy: a NaN would otherwise spread SHARPEN_SIGMA_PX in
    # every direction and eat a ring of real picture around each gap.
    filled = np.where(holes, 0.0, arr).astype(np.float32)
    blurred = np.empty_like(filled)
    for c in range(filled.shape[2]):
        blurred[..., c] = gaussian_filter(filled[..., c], sigma=SHARPEN_SIGMA_PX)

    out = np.clip(filled + a * (filled - blurred), 0.0, 1.0).astype(np.float32)
    if holes.any():
        out[holes] = np.nan
    return out


def sharpen_label(amount: float) -> str:
    """The preset name for an amount, for a result that explains itself.

    Falls back to the nearest preset name for a value that didn't come from the
    list (an older result, or a hand-written API call), so the picture can always
    say how hard it was sharpened in words rather than as a bare number.
    """
    a = float(amount) if np.isfinite(amount) else 0.0
    if a <= 0.0:
        return SHARPEN_PRESETS[0][0]
    return min(SHARPEN_PRESETS, key=lambda p: abs(p[1] - a))[0]
