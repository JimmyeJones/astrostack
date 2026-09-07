"""Tests for the mixed-pointing detector (seestack/stack/pointings.py).

Mirrors the frontend guard: single-linkage-cluster solved pointings so one
target (a pointing, dither, or contiguous mosaic) stays one cluster but two
well-separated targets in one folder split into two.
"""

from __future__ import annotations

import random

from seestack.stack.pointings import (
    FOLD_GRID_DEG,
    MIN_POINTING_FRAMES,
    PANEL_LINK_DIST_DEG,
    cluster_pointings,
    detect_mixed_pointings,
    fold_pointings,
    pointing_groups,
)


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


# --- pointing_groups(weights=…) --------------------------------------------
#
# Added for the mosaic depth map, which folds identical pointings together before
# clustering (the clustering is O(n²) and a target carries thousands of subs on a
# handful of panels). The gate has to keep meaning "substantial by the *frames* it
# holds", or a folded caller would see panels appear and disappear against the
# same data — which is exactly the "three hand-mirrored predicates that disagreed"
# failure this parameter exists to avoid.


def test_weights_default_to_one_each_so_nothing_changes():
    frames = _pointing(83.6, -5.4, 12) + _pointing(84.6, -5.4, 12)
    plain = pointing_groups(frames, min_members=10)
    weighted = pointing_groups(frames, min_members=10, weights=[1] * len(frames))
    assert plain is not None
    assert plain == weighted


def test_a_folded_caller_gets_the_same_answer_as_an_unfolded_one():
    """Two panels of 12 subs each, folded to one entry per panel. Without the
    weights the folded call sees two groups of *one* and refuses to split."""
    unfolded = [(83.6, -5.4)] * 12 + [(84.6, -5.4)] * 12
    folded = [(83.6, -5.4), (84.6, -5.4)]

    assert pointing_groups(unfolded, min_members=10) is not None
    assert pointing_groups(folded, min_members=10) is None            # unweighted
    assert pointing_groups(folded, min_members=10, weights=[12, 12]) is not None


def test_a_weighted_group_below_the_floor_is_still_not_a_panel():
    """The floor is on frames, so a fold does not smuggle a thin group past it."""
    folded = [(83.6, -5.4), (84.6, -5.4)]
    assert pointing_groups(folded, min_members=10, weights=[12, 4]) is None


# ---------------------------------------------------------------------------
# The fold (FOLD_GRID_DEG): ``pointing_groups`` clusters the *distinct*
# pointings, not one row per sub, because the clustering is O(n²) in pure Python
# and every caller hands it a whole target's frame list. These pin the two
# things that buys and the one thing it must not cost: the panels it returns,
# and the counts behind the gate, stay the answer the exact clustering gives.
# ---------------------------------------------------------------------------


def _exact_groups(radecs, *, min_members, link_dist_deg=PANEL_LINK_DIST_DEG):
    """What ``pointing_groups`` would return with no fold at all — the rule
    spelled out against ``cluster_pointings`` directly, so the test compares
    against the clustering rather than against another copy of the fold."""
    labels = cluster_pointings(radecs, link_dist_deg=link_dist_deg)
    counts: dict[int, int] = {}
    for label in labels:
        if label >= 0:
            counts[label] = counts.get(label, 0) + 1
    substantial = {label for label, n in counts.items() if n >= min_members}
    if len(substantial) < 2:
        return None
    return [label if label in substantial else -1 for label in labels]


def _dithered_mosaic(panels: int, per_panel: int, step: float = 0.6):
    """A realistic mosaic: ``panels`` pointings a half-field apart, each carrying
    ``per_panel`` subs dithered continuously over ~±0.03° — arc-minutes, the way
    a Seestar dithers, so many subs share a fold cell without landing on the
    same coordinate. Seeded, so the fixture is the same every run."""
    rng = random.Random(20260907)
    frames = []
    for k in range(panels * per_panel):
        p = k % panels
        ra = 83.0 + step * (p % 3)
        dec = -5.0 + step * (p // 3)
        frames.append((ra + rng.uniform(-0.03, 0.03), dec + rng.uniform(-0.03, 0.03)))
    return frames


def test_the_fold_returns_the_same_panels_as_the_exact_clustering():
    """A 9-panel mosaic with ~70 dithered subs each — the owner's data shape.
    The fold must be invisible: same panels, same membership, same numbering."""
    frames = _dithered_mosaic(9, 70)
    got = pointing_groups(frames, min_members=3)
    assert got == _exact_groups(frames, min_members=3)
    assert got is not None
    assert len(set(got)) == 9                      # nine panels, none stray
    assert all(got.count(label) == 70 for label in set(got))


def test_the_fold_actually_collapses_a_dithered_panel():
    """The point of the exercise: hundreds of subs become dozens of pointings,
    and every sub still maps to the cell it landed in."""
    frames = _dithered_mosaic(9, 200)
    cells, cell_of = fold_pointings(frames)
    assert len(cells) < len(frames) / 3            # 1,800 subs → a few hundred cells
    assert len(cell_of) == len(frames)
    assert all(0 <= c < len(cells) for c in cell_of)
    # A cell's coordinate is the mean of its own members, and no member is
    # further from it than one grid cell.
    for i, (ra, dec) in enumerate(frames):
        cra, cdec = cells[cell_of[i]]
        assert abs(ra - cra) <= FOLD_GRID_DEG
        assert abs(dec - cdec) <= FOLD_GRID_DEG


def test_the_fold_keeps_unsolved_subs_out_of_every_panel():
    """A missing or non-finite pointing has nowhere to fold to, and must come
    back ``-1`` exactly as the exact clustering leaves it."""
    frames = _dithered_mosaic(2, 20)
    frames = frames[:20] + [(None, None), (float("nan"), -5.0)] + frames[20:]
    cells, cell_of = fold_pointings(frames)
    assert cell_of[20] == -1 and cell_of[21] == -1
    assert len(cells) == len(set(c for c in cell_of if c >= 0))
    got = pointing_groups(frames, min_members=3)
    assert got == _exact_groups(frames, min_members=3)
    assert got is not None and got[20] == -1 and got[21] == -1


def test_the_fold_is_wrap_safe_across_ra_zero():
    """Cell keys come from rounding, so a cell never straddles the 0°/360° seam
    and its plain mean can never be flung to the far side of the sky."""
    frames = ([(359.995 + 0.001 * (i % 4), 20.0) for i in range(30)]
              + [(0.004 + 0.001 * (i % 4), 20.0) for i in range(30)])
    cells, _ = fold_pointings(frames)
    # Every cell centre stays beside its own members, not out at ~180°.
    assert all(ra > 359.9 or ra < 0.1 for ra, _ in cells)
    # And the two sides are one dithered pointing, not two panels.
    assert pointing_groups(frames, min_members=3) is None


def test_a_link_distance_near_the_fold_grid_uses_the_exact_clustering():
    """The rail: a caller asking for a link distance the size of the fold itself
    gets the exact answer rather than an approximation of the same size."""
    frames = [(83.0, -5.0)] * 8 + [(83.02, -5.0)] * 8
    # 0.02° apart, asked at a 0.005° link: two groups, and the fold (0.01°) must
    # not be what decides that.
    got = pointing_groups(frames, min_members=3, link_dist_deg=0.005)
    assert got == _exact_groups(frames, min_members=3, link_dist_deg=0.005)
    assert got is not None and len(set(got)) == 2


def test_the_mixed_pointing_verdict_counts_subs_not_folded_cells():
    """``detect_mixed_pointings`` clusters the distinct pointings too, so its
    numbers must still be about *subs*: a folded cell stands for everything that
    landed in it. Counting cells instead would report a fraction of the batch."""
    frames = (_dithered_mosaic(1, 300)                      # 300 subs, one place
              + [(314.0 + 0.001 * (i % 5), 44.0) for i in range(120)])
    mixed = detect_mixed_pointings(frames)
    assert mixed is not None
    assert mixed.pointings == 2
    assert mixed.majority == 300                            # subs, not cells
    assert mixed.others == 120
    assert mixed.separation_deg > 40.0


def test_the_fold_does_not_move_the_mixed_pointing_verdict():
    """Panel separations swept right through the 3° link distance agree with the
    exact clustering — the fold is 300× finer, so it cannot decide the split."""
    for sep in (2.0, 2.9, 3.0, 3.1, 5.0):
        frames = [
            (83.0 + sep * (k % 3) + 0.004 * (k % 9),
             -5.0 + 0.004 * (k % 7))
            for k in range(150)
        ]
        got = detect_mixed_pointings(frames)
        exact = detect_mixed_pointings(list(dict.fromkeys(frames)))
        # Same verdict shape either way; the deduplicated list is the same sky.
        assert (got is None) == (exact is None), sep
        if got is not None and exact is not None:
            assert got.pointings == exact.pointings, sep
