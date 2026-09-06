"""One shared *real* display-space fixture for tests that reason about
post-stretch pixels.

**Why this module exists.** The 2026-09-02 external audit's A1 finding — Auto's
contrast curve brightening the sky by ~36 % on every Auto picture — had already
had a regression test written for it four months earlier, in v0.210.6. That test
**passed while the bug was live**, because its fixture was built as
``clip(sky + noise)``: a hand-rolled approximation of a stretched image that has
no hard shadow clip, and the bug *is* the hard shadow clip. The test confirmed
the fix's model of the defect rather than the defect.

So anything that reasons about the low end of a display-space image — a
histogram, a low percentile, a "the sky is at X" claim — should measure the
output of the app's own ``autostretch`` rather than a synthesised stand-in, and
should say out loud that the clip is there:

    from displayspace import assert_shadow_clip, real_stretched_stack

    st = real_stretched_stack()
    assert_shadow_clip(st)          # the guard on the guard
    ...                             # then the actual assertion

**What this is not.** It is not a replacement for every synthetic fixture. A test
of a *degenerate* case — a flat frame, an all-NaN frame, a two-pixel frame — is
deliberately synthetic and must stay exactly as it is; running it through a
stretch would only obscure what it pins. Migrate a test onto this fixture when it
reasons about the shadows or the histogram, and leave the rest alone.

Pure and offline, like the rest of ``tests/``: no fixtures on disk, no network,
deterministic from its seed.
"""

from __future__ import annotations

import numpy as np

#: Fraction of pixels the shadow clip must land on exactly zero before a fixture
#: can exhibit the A1 class of bug at all. ``autostretch`` clips roughly 1–2 %;
#: half a per cent is a floor with margin, not a measurement.
MIN_CLIPPED_FRACTION = 0.005

#: The top-left square of :func:`real_stretched_stack` is pure background by
#: construction, so a test can measure the true sky without asking the code under
#: test where it is.
SKY_PATCH_PX = 60


def real_stretched_stack(
    seed: int = 7,
    h: int = 300,
    w: int = 420,
    noise: float = 0.002,
    target_bg: float = 0.20,
    sky: float = 0.02,
) -> np.ndarray:
    """A linear OSC-like stack put through the app's own ``autostretch``.

    Faint sky + read noise, a small extended object, a scatter of stars — then the
    real display-space transform the editor's ops actually receive, hard shadow
    clip and all. Returns float32 ``(h, w, 3)`` in roughly ``[0, 1]``.

    ``noise`` is the linear read noise; lowering it deepens the stack (the clip
    takes a fixed *fraction* of the darkest pixels either way, which is the point
    of :func:`assert_shadow_clip`). The top-left :data:`SKY_PATCH_PX` square is
    kept free of stars and of the central object, so ``np.median(st[:60, :60])``
    is the ground-truth sky a test can compare a measurement against.
    """
    from seestack.render.thumbnail import autostretch

    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), float(sky), dtype=np.float32)
    img += rng.normal(0.0, noise, img.shape).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    blob = np.exp(-(((yy - h // 2) ** 2 + (xx - w // 2) ** 2) / (2 * 35.0 ** 2)))
    img += (0.03 * blob)[..., None].astype(np.float32)
    for _ in range(50):
        cy, cx = int(rng.integers(0, h)), int(rng.integers(0, w))
        if abs(cy - h // 2) < 80 and abs(cx - w // 2) < 80:
            continue                      # keep the stars out of the object core
        img[max(0, cy - 1):cy + 2, max(0, cx - 1):cx + 2] += 0.5
    return np.asarray(autostretch(np.clip(img, 0.0, None), target_bg=target_bg),
                      dtype=np.float32)


def sky_truth(display: np.ndarray) -> float:
    """The fixture's real background level, read off its pure-sky corner."""
    return float(np.median(display[:SKY_PATCH_PX, :SKY_PATCH_PX]))


def clipped_fraction(display: np.ndarray) -> float:
    """Share of samples the stretch pushed to exactly zero."""
    return float(np.mean(display <= 0.0))


def assert_shadow_clip(display: np.ndarray) -> None:
    """Guard on the guard: fail if this fixture *can't* exhibit the A1 bug.

    Lead a display-space test with this. Without it, a future change to
    ``autostretch`` — or a fixture tweaked until it stopped clipping — would turn
    every assertion below it into a no-op silently, which is exactly how the
    v0.210.6 regression test came to pass on a live bug for four months.
    """
    frac = clipped_fraction(display)
    assert frac > MIN_CLIPPED_FRACTION, (
        f"only {frac:.4%} of samples are clipped to zero — no shadow clip means "
        "the tests below this cannot exhibit the bug they guard")
    assert float(np.percentile(display, 0.5)) == 0.0
