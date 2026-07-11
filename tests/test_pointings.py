"""Tests for the mixed-pointing detector (seestack/stack/pointings.py).

Mirrors the frontend guard: single-linkage-cluster solved pointings so one
target (a pointing, dither, or contiguous mosaic) stays one cluster but two
well-separated targets in one folder split into two.
"""

from __future__ import annotations

from seestack.stack.pointings import MIN_POINTING_FRAMES, detect_mixed_pointings


def _pointing(ra: float, dec: float, n: int) -> list[tuple[float, float]]:
    """n subs jittered a few arc-minutes around (ra, dec) — one dithered pointing."""
    return [(ra + 0.02 * (i % 3), dec - 0.02 * (i % 2)) for i in range(n)]


def test_single_pointing_is_not_flagged():
    frames = _pointing(83.6, -5.4, 30)
    assert detect_mixed_pointings(frames) is None


def test_two_well_separated_targets_are_flagged():
    frames = _pointing(83.6, -5.4, 20) + _pointing(314.0, 44.0, 12)
    mixed = detect_mixed_pointings(frames)
    assert mixed is not None
    assert mixed.pointings == 2
    assert mixed.majority == 20
    assert mixed.others == 12
    # The two pointings are far apart on the sky (tens of degrees).
    assert mixed.separation_deg > 40.0


def test_contiguous_mosaic_stays_one_cluster():
    # A 4-panel mosaic stepping ~1° per panel: each panel is <3° from the next,
    # so single-linkage keeps the whole chain as one cluster even though the
    # end-to-end span (~3°) exceeds the link distance.
    frames: list[tuple[float, float]] = []
    for step in range(4):
        frames += _pointing(83.6 + 1.0 * step, -5.4, 8)
    assert detect_mixed_pointings(frames) is None


def test_too_few_frames_never_flags():
    # Fewer than two substantial groups' worth of subs → not judged.
    frames = _pointing(83.6, -5.4, MIN_POINTING_FRAMES) + _pointing(
        314.0, 44.0, MIN_POINTING_FRAMES - 1)
    assert len(frames) < 2 * MIN_POINTING_FRAMES
    assert detect_mixed_pointings(frames) is None


def test_lone_stray_frame_does_not_flag():
    # A single mis-solved frame far away isn't a substantial second pointing, so
    # the stack's own outlier rejection handles it — the guard stays quiet.
    frames = _pointing(83.6, -5.4, 30) + [(200.0, 10.0)]
    assert detect_mixed_pointings(frames) is None


def test_two_substantial_pointings_with_a_stray():
    frames = (
        _pointing(83.6, -5.4, 15)
        + _pointing(314.0, 44.0, 10)
        + [(120.0, -80.0)]  # a lone stray in a third place — not substantial
    )
    mixed = detect_mixed_pointings(frames)
    assert mixed is not None
    assert mixed.pointings == 2  # the stray is not counted as a pointing
    assert mixed.majority == 15
    assert mixed.others == 10


def test_wrap_safe_across_ra_zero():
    # Two dithered pointings straddling RA 0° (359.5 and 0.5) are only ~1° apart
    # on the sphere — one target — so the naive |Δra|≈359 must NOT split them.
    frames = _pointing(359.5, 10.0, 12) + _pointing(0.5, 10.0, 12)
    assert detect_mixed_pointings(frames) is None


def test_none_and_nonfinite_coords_ignored():
    frames: list[tuple[float | None, float | None]] = _pointing(83.6, -5.4, 20)
    frames += [(None, -5.4), (float("nan"), 1.0), (83.6, None)]
    # Only the 20 valid single-pointing frames remain → not bimodal.
    assert detect_mixed_pointings(frames) is None
