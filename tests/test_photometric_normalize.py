"""Photometric (multiplicative) frame normalization for the stack."""

import numpy as np

from seestack.io.project import FrameRow
from seestack.stack.photometric import compute_photometric_scales


def _f(id_, transp=None):
    return FrameRow(id=id_, source_path=f"x{id_}.fit", transparency_score=transp)


def test_scales_gain_match_to_the_median():
    # Median transparency is 5000 → the median frame is neutral, the hazy frame
    # (dimmer signal) is scaled *up* to match, the clear frame *down*.
    frames = [_f(1, transp=8000), _f(2, transp=5000), _f(3, transp=2500)]
    scales, stats = compute_photometric_scales(frames)
    assert scales[2] == 1.0                     # at the median → neutral
    assert abs(scales[1] - 5000 / 8000) < 1e-6  # clearer → scaled down
    assert abs(scales[3] - 5000 / 2500) < 1e-6  # hazier → scaled up
    assert stats.n_scaled == 3
    assert stats.n_adjusted == 2                 # the median frame didn't move
    assert stats.n_neutral == 0


def test_scale_is_bounded_by_max_ratio():
    # A frame far dimmer than the median would want a >2× boost; it's capped.
    frames = [_f(1, transp=10000), _f(2, transp=10000), _f(3, transp=1000)]
    scales, _ = compute_photometric_scales(frames, max_ratio=2.0)
    assert scales[3] == 2.0            # ref/1000 = 10 → clamped to 2.0
    # And a wildly *bright* frame is clamped on the low side.
    frames2 = [_f(1, transp=1000), _f(2, transp=1000), _f(3, transp=99999)]
    scales2, _ = compute_photometric_scales(frames2, max_ratio=2.0)
    assert scales2[3] == 0.5


def test_missing_transparency_is_neutral_not_penalised():
    # A frame with no usable score keeps scale 1.0 while its neighbours normalise.
    frames = [_f(1, transp=None), _f(2, transp=5000), _f(3, transp=2500), _f(4, transp=5000)]
    scales, stats = compute_photometric_scales(frames)
    assert scales[1] == 1.0
    assert stats.n_neutral == 1
    assert stats.n_scaled == 3


def test_too_few_measured_frames_is_fully_neutral():
    # With < min_frames usable scores the median reference isn't trustworthy, so
    # every frame stays at 1.0 (no measured scale) rather than normalise on noise.
    frames = [_f(1, transp=5000), _f(2, transp=2500), _f(3, transp=None)]
    scales, stats = compute_photometric_scales(frames, min_frames=3)
    assert all(v == 1.0 for v in scales.values())
    assert stats.n_scaled == 0
    assert stats.n_neutral == 3


def test_identical_transparency_gives_all_neutral_scales():
    frames = [_f(i, transp=5000) for i in range(1, 5)]
    scales, stats = compute_photometric_scales(frames)
    assert all(v == 1.0 for v in scales.values())
    assert stats.n_scaled == 4
    assert stats.n_adjusted == 0     # measured, but nothing needed moving


def test_non_positive_and_none_scores_are_ignored_for_the_reference():
    # Zero/negative scores don't poison the median; they're treated as unmeasured.
    frames = [_f(1, transp=0), _f(2, transp=-5), _f(3, transp=4000),
              _f(4, transp=4000), _f(5, transp=2000)]
    scales, stats = compute_photometric_scales(frames)
    # Reference median is over {4000, 4000, 2000} = 4000.
    assert scales[1] == 1.0 and scales[2] == 1.0
    assert abs(scales[5] - 4000 / 2000) < 1e-6
    assert stats.n_neutral == 2
    assert stats.n_scaled == 3


def test_scaling_a_frame_preserves_nan_coverage():
    # Applying a scale must not turn a NaN gap into a number (coverage invariant).
    img = np.array([[1.0, np.nan], [2.0, 3.0]], dtype=np.float32)
    scaled = img * np.float32(1.7)
    assert np.isnan(scaled[0, 1])
    assert abs(scaled[0, 0] - 1.7) < 1e-6


# ---- Mosaic panels ----------------------------------------------------------
#
# ``transparency_score`` is the median flux of a frame's *brightest stars*, so on
# a mosaic it measures where the scope pointed as much as how clear the sky was.
# Referenced against the whole mosaic, a panel over an emptier field asks for the
# maximum boost — a visibly brighter panel, i.e. a coloured grid.


def _panel_frames(n_panels=6, per_panel=8, poor_panel=None, poor_transp=2000.0,
                  cloud_sub=None):
    frames = []
    fid = 0
    for p in range(n_panels):
        ra = 83.6 + p * 0.9
        poor = p == poor_panel
        for k in range(per_panel):
            fid += 1
            transp = poor_transp if poor else 5000.0
            if cloud_sub is not None and poor and k == cloud_sub:
                transp = 500.0
            frames.append(FrameRow(
                id=fid, source_path=f"p{p}_{k}.fit", transparency_score=transp,
                ra_center_deg=ra + (k % 2) * 0.01, dec_center_deg=-5.4,
            ))
    return frames


def test_star_poor_mosaic_panel_is_not_gain_matched_up():
    # Mosaic-wide the reference is 5000, so this panel would be multiplied by
    # 5000/2000 = 2.5 → the 2.0 bound: a panel twice as bright as its neighbours.
    frames = _panel_frames(poor_panel=3)
    scales, stats = compute_photometric_scales(frames)
    assert stats.n_panels == 6
    assert all(scales[f.id] == 1.0 for f in frames)
    assert stats.n_adjusted == 0


def test_a_hazy_sub_inside_a_panel_is_still_gain_matched():
    # Judging each panel against itself must still catch haze *within* a panel —
    # the variation photometric normalization actually exists to correct.
    frames = _panel_frames(poor_panel=3, cloud_sub=0)
    scales, stats = compute_photometric_scales(frames)
    hazy = frames[3 * 8].id
    assert scales[hazy] == 2.0        # 2000/500 = 4 → clamped to the 2× bound
    assert stats.n_adjusted == 1


def test_single_pointing_target_still_normalizes_target_wide():
    # One pointing never splits, so the run-wide median is the reference exactly
    # as before — the no-regression guard for every ordinary stack.
    frames = _panel_frames(n_panels=1, per_panel=8)
    frames[0].transparency_score = 2500.0
    scales, stats = compute_photometric_scales(frames)
    assert stats.n_panels == 0
    assert abs(scales[frames[0].id] - 2.0) < 1e-6


def test_unsolved_frames_reference_the_whole_run():
    # No pointing to cluster on → one population, today's behaviour.
    frames = _panel_frames(poor_panel=3)
    for f in frames:
        f.ra_center_deg = None
        f.dec_center_deg = None
    scales, stats = compute_photometric_scales(frames)
    assert stats.n_panels == 0
    assert all(scales[f.id] == 2.0 for f in frames[3 * 8:4 * 8])
