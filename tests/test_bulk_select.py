"""The bulk "Reject worst N% by …" cut, and why a mosaic is ranked per panel.

``star_count`` / ``transparency_score`` / ``sky_adu_median`` are properties of
where the scope pointed as much as of the night, so one global sort on a mosaic
puts the whole of the emptiest-framed panel at the bottom — "drop my haziest
10%" then thins one panel's *coverage* instead of dropping the haziest subs.
FWHM and eccentricity are properties of the seeing and stay target-wide.
"""

import pytest

from seestack.io.project import FrameRow
from seestack.qc.bulk_select import worst_frames_by_metric

PANELS = [(10.0, 20.0), (11.0, 20.0), (12.0, 20.0)]
FIELD = [10000.0, 5000.0, 4000.0]  # each panel's intrinsic star field


def _f(name, *, ra=None, dec=None, **metrics):
    return FrameRow(id=None, source_path=name, ra_center_deg=ra,
                    dec_center_deg=dec, **metrics)


def _mosaic(per_panel=6, metric="transparency_score", dim=None):
    """Three panels, ``per_panel`` subs each, under one steady sky."""
    out = []
    for p, (ra, dec) in enumerate(PANELS):
        for k in range(per_panel):
            v = FIELD[p] + k
            if dim is not None:
                v *= dim(p, k)
            out.append(_f(f"p{p}_{k}.fit", ra=ra, dec=dec, **{metric: v}))
    return out


def _panel_of(frame):
    return next(i for i, (ra, _) in enumerate(PANELS) if frame.ra_center_deg == ra)


def test_a_mosaic_cut_by_transparency_takes_from_every_panel():
    """The bug: a global sort rejects all six subs of the sparsest panel — a
    coverage hole in the finished mosaic — and none of the richest panel's."""
    frames = _mosaic()
    worst, n_panels = worst_frames_by_metric(frames, "transparency_score", 1 / 3)
    assert n_panels == 3
    assert len(worst) == 6
    per_panel = sorted(_panel_of(f) for f in worst)
    assert per_panel == [0, 0, 1, 1, 2, 2]


def test_a_mosaic_cut_drops_each_panels_own_haziest():
    """Within a panel the ranking is unchanged — the two lowest of that panel."""
    frames = _mosaic()
    worst, _ = worst_frames_by_metric(frames, "transparency_score", 1 / 3)
    names = {f.source_path for f in worst}
    assert names == {f"p{p}_{k}.fit" for p in range(3) for k in (0, 1)}


def test_one_genuinely_hazy_panel_still_loses_only_its_share():
    """Per-panel means a hazy panel is not wholesale rejected either — the cut is
    a fraction of each panel, so coverage stays even whatever the sky did."""
    frames = _mosaic(dim=lambda p, k: 0.3 if p == 1 else 1.0)
    worst, n_panels = worst_frames_by_metric(frames, "transparency_score", 1 / 3)
    assert n_panels == 3
    assert sorted(_panel_of(f) for f in worst) == [0, 0, 1, 1, 2, 2]


def test_star_count_and_sky_level_split_too():
    """The other two position-dependent metrics take the same treatment."""
    for metric in ("star_count", "sky_adu_median"):
        frames = _mosaic(metric=metric)
        worst, n_panels = worst_frames_by_metric(frames, metric, 1 / 3)
        assert n_panels == 3, metric
        assert sorted(_panel_of(f) for f in worst) == [0, 0, 1, 1, 2, 2], metric


def test_sky_level_worst_are_the_brightest():
    """Direction is preserved: a brighter sky is worse, a fainter one is not."""
    frames = _mosaic(metric="sky_adu_median")
    worst, _ = worst_frames_by_metric(frames, "sky_adu_median", 1 / 3)
    # Highest two of each panel (k = 4, 5), not the lowest.
    assert {f.source_path for f in worst} == {
        f"p{p}_{k}.fit" for p in range(3) for k in (4, 5)}


def test_fwhm_is_ranked_target_wide_even_on_a_mosaic():
    """Seeing is a property of the night, not of the pointing — so the softest
    subs are the softest subs, wherever the scope was pointed."""
    frames = _mosaic(metric="fwhm_px")
    worst, n_panels = worst_frames_by_metric(frames, "fwhm_px", 1 / 3)
    assert n_panels == 0  # not split — the caller reports no panel note
    # Highest FWHM overall: all six live on panel 0 (its values are the largest).
    assert {_panel_of(f) for f in worst} == {0}


def test_a_single_field_target_keeps_the_global_ranking():
    ra, dec = PANELS[0]
    frames = [_f(f"s{i}.fit", ra=ra, dec=dec, transparency_score=float(v))
              for i, v in enumerate([900, 100, 500, 800, 200, 700])]
    worst, n_panels = worst_frames_by_metric(frames, "transparency_score", 1 / 3)
    assert n_panels == 0
    assert {f.source_path for f in worst} == {"s1.fit", "s4.fit"}


def test_unsolved_frames_keep_the_global_ranking():
    frames = [_f(f"u{i}.fit", transparency_score=float(v))
              for i, v in enumerate([900, 100, 500, 800, 200, 700])]
    worst, n_panels = worst_frames_by_metric(frames, "transparency_score", 1 / 3)
    assert n_panels == 0
    assert {f.source_path for f in worst} == {"u1.fit", "u4.fit"}


def test_a_sub_in_no_substantial_panel_is_ranked_only_against_its_kind():
    """An unsolved sub in an otherwise-mosaic target can't be compared with a
    panel's population, so it forms its own bucket rather than being cut against
    a yardstick from another patch of sky."""
    frames = _mosaic()
    stray = [_f(f"x{i}.fit", transparency_score=float(v))
             for i, v in enumerate([100.0, 200.0, 300.0])]
    worst, n_panels = worst_frames_by_metric(frames + stray, "transparency_score", 1 / 3)
    assert n_panels == 3
    # Two from each panel plus one of the three strays (int(3 × 1/3) == 1).
    assert sorted(_panel_of(f) for f in worst if f.ra_center_deg is not None) == \
        [0, 0, 1, 1, 2, 2]
    assert [f.source_path for f in worst if f.ra_center_deg is None] == ["x0.fit"]


def test_frames_without_the_metric_are_ignored():
    frames = _mosaic() + [_f("nometric.fit", ra=10.0, dec=20.0)]
    worst, _ = worst_frames_by_metric(frames, "transparency_score", 1 / 3)
    assert "nometric.fit" not in {f.source_path for f in worst}


def test_an_all_unmeasured_batch_rejects_nothing():
    worst, n_panels = worst_frames_by_metric(
        [_f("a.fit"), _f("b.fit")], "transparency_score", 1.0)
    assert worst == [] and n_panels == 0


@pytest.mark.parametrize("fraction, expected", [(0.0, 0), (-1.0, 0), (1.0, 18)])
def test_the_fraction_is_clamped_and_truncated(fraction, expected):
    worst, _ = worst_frames_by_metric(_mosaic(), "transparency_score", fraction)
    assert len(worst) == expected


def test_a_fraction_too_small_to_reach_one_frame_per_panel_rejects_nothing():
    """Truncation is per bucket, exactly as the old global cut truncated once —
    a cut that can't reach a whole frame does nothing rather than rounding up."""
    worst, _ = worst_frames_by_metric(_mosaic(), "transparency_score", 0.1)
    assert worst == []
