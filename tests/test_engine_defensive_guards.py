"""Defensive guards on the stack path — the "unreachable today" batch.

Each of these was traced by an engine audit as a *latent* defect: a real hole in
a guard whose trigger no current code path can produce. They are collected here
rather than scattered because the value is uniform — the stack path decides what
the final image is made of, so a guard there should fail closed even against an
input the app cannot currently make (an imported row, a hand-edited DB, a future
edit that changes what an upstream helper can return).

Every test drives the hole directly, and every one fails against the pre-fix
code.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from seestack.io.project import FrameRow
from seestack.stack.reference import pick_central_frame
from seestack.stack.weighting import compute_frame_weights


def _frame(fid: int, **kw) -> FrameRow:
    base = dict(id=fid, source_path=f"/tmp/f{fid}.fit", cached_path=None,
                wcs_json=None, width_px=100, height_px=100,
                bayer_pattern="RGGB", accept=True)
    base.update(kw)
    return FrameRow(**base)  # type: ignore[arg-type]


def test_a_pathologically_tiny_fwhm_saturates_instead_of_crashing_the_stack():
    """``(best/fwhm)**2`` on Python floats raises ``OverflowError`` before
    ``np.clip`` can clamp it, which sinks the whole run rather than the one row.
    Unreachable through the app (``median_fwhm`` persists only (0.5, 20)), so
    the guard is against an imported or hand-edited frame row."""
    frames = [
        _frame(1, fwhm_px=3.0),
        _frame(2, fwhm_px=3.2),
        _frame(3, fwhm_px=1e-300),
    ]
    weights, _ = compute_frame_weights(frames)
    # The tiny-FWHM frame reads as impossibly sharp, so its factor saturates at
    # the formula's own 1.0 ceiling — not an exception, and not a NaN.
    assert weights[3] == pytest.approx(1.0)
    assert all(math.isfinite(w) for w in weights.values())


def test_a_nan_pointing_never_becomes_the_reference_frame():
    """``is not None`` lets a NaN centre through; it then propagates into the RA
    unwrap, the median and the score, and picks an arbitrary reference for the
    whole stack. ``pointings.py`` already filters on ``isfinite``; this matches."""
    good = _frame(1, ra_center_deg=83.6, dec_center_deg=-5.4, fwhm_px=3.0)
    nan_frame = _frame(2, ra_center_deg=float("nan"),
                       dec_center_deg=float("nan"), fwhm_px=1.0)
    picked = pick_central_frame([nan_frame, good])
    assert picked is not None and picked.id == 1
    # And a list of nothing but NaN pointings has no reference at all, rather
    # than one chosen by comparisons that are all False.
    assert pick_central_frame([nan_frame]) is None


def test_a_nan_subpixel_shift_is_refused_rather_than_smeared_over_the_frame():
    """``abs(dy) > CAP or abs(dx) > CAP`` is False for NaN — so a NaN shift slipped
    past the sanity check and ``nd_shift`` turned the whole frame into NaN. Written
    as "not (both within the cap)", NaN correctly reads as "too large"."""
    pytest.importorskip("scipy")
    pytest.importorskip("skimage")
    from seestack.stack import align

    rgb = np.random.default_rng(5).random((60, 60, 3)).astype(np.float32)
    patch, origin = align.extract_reference_patch(rgb)

    def _nan_shift(*_a, **_kw):
        return np.array([float("nan"), 0.0]), 0.0, 0.0

    # ``_apply_subpixel_shift`` imports the correlator from ``skimage`` inside the
    # function, so patch it at its source.
    import skimage.registration as reg

    stats: dict = {}
    real = reg.phase_cross_correlation
    reg.phase_cross_correlation = _nan_shift
    try:
        out = align._apply_subpixel_shift(rgb.copy(), patch, origin, stats=stats)
    finally:
        reg.phase_cross_correlation = real

    assert stats.get("over_cap") is True
    assert np.isfinite(out).all(), "a NaN shift was applied and wiped the frame"
    assert np.array_equal(out, rgb)
