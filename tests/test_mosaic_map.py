"""`seestack.mosaicmap` — "your mosaic, panel by panel".

The readiness number tells a mosaic owner *how much* is left; this says *where*.
These tests pin the two things that make it trustworthy: it must stay silent on
anything that isn't clearly a mosaic (it reuses the engine's one panel-clustering
gate for that), and when it does speak, the grid and the thin-panel call must be
about the sky, not about the order the frames happened to arrive in.
"""

from __future__ import annotations

import math

import pytest

from seestack.mosaicmap import (
    MIN_PANEL_FRAMES,
    THIN_FRACTION,
    mosaic_depth_map,
    panel_position_words,
)

SUB_S = 10.0          # a Seestar sub


def _grid(rows: int, cols: int, *, ra0: float = 200.0, dec0: float = 30.0,
          step: float = 0.5, subs: int = 12,
          per_panel: dict[tuple[int, int], int] | None = None):
    """Frames for a `rows`×`cols` mosaic, `subs` subs a panel unless overridden.

    Panel (0, 0) is the north-east corner — highest Dec, highest RA — so it is
    the one the map must draw top-left."""
    frames = []
    for r in range(rows):
        for c in range(cols):
            n = (per_panel or {}).get((r, c), subs)
            dec = dec0 + (rows - 1 - r) * step
            ra = ra0 + (cols - 1 - c) * step / math.cos(math.radians(dec))
            for _ in range(n):
                frames.append((ra, dec, SUB_S))
    return frames


def test_a_single_field_is_not_a_mosaic():
    """One pointing (with dither) must produce nothing at all — the card is for
    mosaics, and a beginner shooting one field should never see it."""
    frames = [(200.0 + 0.01 * (i % 5), 30.0, SUB_S) for i in range(60)]

    assert mosaic_depth_map(frames) is None


def test_an_unsolved_target_is_not_a_mosaic():
    """No pointings, no panels — and no crash."""
    assert mosaic_depth_map([(None, None, SUB_S)] * 40) is None
    assert mosaic_depth_map([]) is None


def test_a_handful_of_strays_is_not_a_second_panel():
    """A few frames a degree off the field are mis-solves or a slew, not a panel.
    The shared `MIN_PANEL_FRAMES` floor is what keeps them out."""
    frames = [(200.0, 30.0, SUB_S)] * 80
    frames += [(203.0, 30.0, SUB_S)] * (MIN_PANEL_FRAMES - 1)

    assert mosaic_depth_map(frames) is None


def test_a_real_mosaic_lays_out_as_the_sky_tiles():
    """A 2×3 mosaic comes back as a 2×3 grid with one cell per panel, North up
    and East left — the orientation every astro image is drawn in."""
    m = mosaic_depth_map(_grid(2, 3))

    assert m is not None
    assert (m.rows, m.cols) == (2, 3)
    assert len(m.panels) == 6
    assert {(p.row, p.col) for p in m.panels} == {(r, c) for r in range(2) for c in range(3)}

    top_left = next(p for p in m.panels if (p.row, p.col) == (0, 0))
    bottom_right = next(p for p in m.panels if (p.row, p.col) == (1, 2))
    assert top_left.dec_deg > bottom_right.dec_deg      # North is up
    assert top_left.ra_deg > bottom_right.ra_deg        # East is left


def test_each_panels_own_time_is_counted():
    """The whole point: a panel's integration is *its* subs, not the target's."""
    m = mosaic_depth_map(_grid(1, 2, subs=20, per_panel={(0, 1): 5}))

    assert m is not None
    by_col = {p.col: p for p in m.panels}
    assert by_col[0].n_frames == 20
    assert by_col[0].exposure_s == pytest.approx(200.0)
    assert by_col[1].n_frames == 5
    assert by_col[1].exposure_s == pytest.approx(50.0)


def test_the_thin_corner_is_named_in_plain_language():
    """The sentence the feature exists to say. A 2×2 mosaic with one starved
    corner must name *that* corner, in words, with both numbers."""
    m = mosaic_depth_map(_grid(2, 2, subs=60, per_panel={(1, 1): 6}))

    assert m is not None
    assert m.thin is not None
    assert (m.thin.row, m.thin.col) == (1, 1)
    assert "bottom-right" in m.text
    assert "grainier" in m.text
    # Both sides of the comparison, in the app's one duration vocabulary.
    assert "1 min" in m.text and "10 min" in m.text


def test_an_even_mosaic_is_told_it_is_even_and_names_nobody():
    """No "worst panel" out of a 3 % spread — that would send a beginner chasing
    noise. An even mosaic gets a reassurance and `thin is None`."""
    m = mosaic_depth_map(_grid(2, 2, subs=60, per_panel={(0, 1): 58, (1, 0): 61}))

    assert m is not None
    assert m.thin is None
    assert "similar amount of time" in m.text
    assert "grainier" not in m.text


def test_a_young_mosaic_is_not_nagged_about_minutes():
    """Half of four minutes is still nothing worth a sentence: the fractional
    test alone would fire on a mosaic's first half hour, so an absolute
    shortfall has to clear too."""
    thin_but_tiny = _grid(1, 2, subs=24, per_panel={(0, 1): 6})   # 4 min vs 1 min
    assert (m := mosaic_depth_map(thin_but_tiny)) is not None
    assert m.thin is None

    # The same *ratio*, an hour in: now it matters and is called out.
    thin_and_real = _grid(1, 2, subs=360, per_panel={(0, 1): 90})  # 60 min vs 15
    assert (m := mosaic_depth_map(thin_and_real)) is not None
    assert m.thin is not None


def test_the_median_is_the_yardstick_not_the_mean():
    """Two starved panels out of five must not drag the comparison down to where
    they look normal. With the mean, 3×60 subs and 2×5 would put the bar at 38
    subs and the thin panels at 13 % under it — inside the threshold, so nothing
    would be said."""
    m = mosaic_depth_map(_grid(1, 5, subs=60, per_panel={(0, 3): 5, (0, 4): 5}))

    assert m is not None
    assert m.median_exposure_s == pytest.approx(600.0)      # the mean is ~384 s
    assert m.thin is not None
    assert m.thin.exposure_s == pytest.approx(50.0)
    assert m.thin.exposure_s < THIN_FRACTION * m.median_exposure_s


def test_a_mosaic_across_the_ra_wrap_still_lays_out_side_by_side():
    """RA 359°→1° is one step, not a 358° one. Averaged and differenced on the
    unit sphere it has to stay a two-cell row."""
    m = mosaic_depth_map(_grid(1, 3, ra0=359.4, dec0=10.0))

    assert m is not None
    assert (m.rows, m.cols) == (1, 3)


def test_frame_order_does_not_change_the_map():
    """The same night, shuffled, is the same mosaic."""
    import random

    frames = _grid(2, 2, subs=30, per_panel={(1, 0): 4})
    shuffled = frames[:]
    random.Random(11).shuffle(shuffled)

    a, b = mosaic_depth_map(frames), mosaic_depth_map(shuffled)
    assert a is not None and b is not None
    assert a.text == b.text
    assert [(p.row, p.col, p.n_frames) for p in a.panels] \
        == [(p.row, p.col, p.n_frames) for p in b.panels]


def test_a_missing_exposure_costs_time_not_the_frame():
    """A sub with no recorded exposure still happened — it counts toward its
    panel's frame count, it just cannot add seconds."""
    frames = _grid(1, 2, subs=20)
    frames += [(frames[0][0], frames[0][1], None)] * 5

    m = mosaic_depth_map(frames)
    assert m is not None
    thick = max(m.panels, key=lambda p: p.n_frames)
    assert thick.n_frames == 25
    assert thick.exposure_s == pytest.approx(200.0)


def test_position_words_read_like_a_person_pointing_at_the_picture():
    assert panel_position_words(0, 0, 2, 2) == "top-left"
    assert panel_position_words(1, 1, 2, 2) == "bottom-right"
    assert panel_position_words(1, 1, 3, 3) == "middle"
    assert panel_position_words(1, 0, 3, 3) == "middle-left"
    assert panel_position_words(0, 1, 1, 3) == "middle"     # a single row
    assert panel_position_words(0, 2, 1, 3) == "right"
    assert panel_position_words(2, 0, 3, 1) == "bottom"


def test_folding_identical_pointings_does_not_change_the_map():
    """Pointings are folded onto a fine grid before the O(n²) clustering (5,400
    subs: 2.2 s unfolded, 0.06 s folded). The fold is a performance measure, so
    the map it produces has to be the one the unfolded data would have given —
    same panels, same counts, same integration, same sentence."""
    import random

    from seestack.mosaicmap import FOLD_GRID_DEG

    rng = random.Random(4)
    frames = []
    for r in range(2):
        for c in range(2):
            dec = 30.0 + r * 0.5
            ra = 200.0 + c * 0.5 / math.cos(math.radians(dec))
            for _ in range(150):
                # Real dither/solve scatter — a couple of arc-minutes, several
                # times the fold grid, so the fold genuinely merges frames rather
                # than no-opping, and far inside the 0.5° panel step.
                frames.append((ra + rng.gauss(0, 2 * FOLD_GRID_DEG),
                               dec + rng.gauss(0, 2 * FOLD_GRID_DEG), SUB_S))

    m = mosaic_depth_map(frames)
    assert m is not None
    assert (m.rows, m.cols) == (2, 2)
    assert sum(p.n_frames for p in m.panels) == len(frames)
    assert all(p.n_frames == 150 for p in m.panels)
    assert all(p.exposure_s == pytest.approx(1500.0) for p in m.panels)


def test_the_fold_keeps_each_panel_centre_where_the_frames_are():
    """A folded cell carries the mean of the frames in it, so a panel's centre is
    still its subs' own centre — the layout is derived from these."""
    frames = [(200.0, 30.0, SUB_S)] * 30 + [(200.0 + 0.5 / math.cos(math.radians(30.0)),
                                             30.0, SUB_S)] * 30

    m = mosaic_depth_map(frames)
    assert m is not None
    left, right = sorted(m.panels, key=lambda p: p.col)
    assert left.ra_deg == pytest.approx(200.0 + 0.5 / math.cos(math.radians(30.0)))
    assert right.ra_deg == pytest.approx(200.0)
    assert left.dec_deg == pytest.approx(30.0)
