"""The walk-away minimum-frames floor must judge a *pixel*, not a frame count.

``auto_stack_min_frames`` exists to stop the hands-off scan publishing (and
auto-editing) single-frame colour speckle as a target's newest picture. It asks
the question of the target's frame count, which is exactly right on a single
field — every sub lands on every pixel — and wrong on a mosaic, where the subs
are spread across the panels: a 3×3 mosaic one pass in has nine subs and a
picture that is one sub deep *everywhere*, and ``9 >= 3`` waves it through.

:func:`panel_frame_counts` + :func:`typical_panel_depth` are the honest number.
These tests pin the rule; ``tests/webapp/test_auto_stack_pipeline.py`` pins the
hold it drives.
"""

from __future__ import annotations

from seestack.stack.stacker import panel_frame_counts, typical_panel_depth

# Panel step, in degrees: well beyond ``PANEL_LINK_DIST_DEG`` (0.25), so panels
# cluster apart while a dither does not. A Seestar steps ~0.8 of its field.
_STEP_DEG = 0.5
_BASE = (83.6, -5.4)


def _mosaic(n_side: int, per_panel: list[int] | int) -> list[tuple[float, float]]:
    """``n_side × n_side`` panel centres, repeated per that panel's sub count."""
    depths = ([per_panel] * (n_side * n_side) if isinstance(per_panel, int)
              else per_panel)
    out: list[tuple[float, float]] = []
    for k, (j, i) in enumerate((j, i) for j in range(n_side) for i in range(n_side)):
        for _ in range(depths[k]):
            out.append((_BASE[0] + i * _STEP_DEG, _BASE[1] + j * _STEP_DEG))
    return out


# --- the counts -------------------------------------------------------------

def test_a_dithered_single_field_is_one_panel():
    """A dither is arcseconds; the panel link distance is a quarter of a degree.
    One cluster, so nothing downstream sees a mosaic."""
    radecs = [(_BASE[0] + 0.002 * i, _BASE[1]) for i in range(30)]
    assert panel_frame_counts(radecs) == [30]


def test_the_panels_of_a_mosaic_are_counted_separately_largest_first():
    counts = panel_frame_counts(_mosaic(2, [6, 6, 6, 3]))
    assert counts == [6, 6, 6, 3]


def test_unsolved_and_non_finite_pointings_are_skipped_not_counted():
    radecs: list[tuple[float | None, float | None]] = [
        *_mosaic(2, 4), (None, None), (float("nan"), _BASE[1]),
        (_BASE[0], float("inf")),
    ]
    assert panel_frame_counts(radecs) == [4, 4, 4, 4]


def test_nothing_solved_yet_counts_nothing():
    assert panel_frame_counts([(None, None), (None, None)]) == []


# --- the depth --------------------------------------------------------------

def test_a_single_field_has_no_typical_panel_depth_so_nothing_changes():
    """The whole no-regression guarantee in one line: a target that doesn't split
    into panels returns ``None``, which the caller reads as "use the frame count"
    — i.e. exactly what every single-field target has always been judged on."""
    assert typical_panel_depth(panel_frame_counts(
        [(_BASE[0] + 0.002 * i, _BASE[1]) for i in range(30)])) is None
    assert typical_panel_depth([]) is None
    assert typical_panel_depth([500]) is None


def test_a_mosaic_one_pass_in_is_one_sub_deep_not_nine_subs_thick():
    """The bug this whole module exists for: nine subs, nine panels, and a
    picture that is a single sub deep at every pixel."""
    counts = panel_frame_counts(_mosaic(3, 1))
    assert sum(counts) == 9                       # the number the floor saw
    assert typical_panel_depth(counts) == 1       # the number it should have seen


def test_a_two_deep_mosaic_reads_two():
    assert typical_panel_depth(panel_frame_counts(_mosaic(2, 2))) == 2


def test_one_thin_corner_does_not_speak_for_the_whole_mosaic():
    """A corner lost to cloud after three subs is a good picture with a grainy
    corner — the *thinnest* panel (``auto_reject_depth``'s number, and the right
    one for its question) would strand the whole target."""
    assert typical_panel_depth(panel_frame_counts(_mosaic(2, [40, 40, 40, 3]))) == 40


def test_a_stray_mis_solved_sub_cannot_hold_back_a_single_field():
    """One sub solved a degree off the target forms a one-frame "panel". An
    unweighted median of [200, 1] is 1 and would hold a perfectly good deep
    target back for ever; weighting by frames it is 200, as it should be."""
    radecs = [(_BASE[0], _BASE[1])] * 200 + [(_BASE[0] + 1.5, _BASE[1] + 1.5)]
    counts = panel_frame_counts(radecs)
    assert counts == [200, 1]
    assert typical_panel_depth(counts) == 200


def test_the_median_is_taken_over_subs_so_a_half_shot_mosaic_reads_honestly():
    """Half the panels deep and half of them one sub: exactly half the subs sit
    in a panel below any sane floor, and the answer must not round in favour of
    publishing."""
    counts = panel_frame_counts(_mosaic(2, [8, 8, 1, 1]))
    assert counts == [8, 8, 1, 1]
    # 18 subs; the two deep panels hold 16 of them, so a typical sub is 8 deep.
    assert typical_panel_depth(counts) == 8
    # …and when most of the subs really are in one-deep panels, it flips: three
    # subs on one panel and one on each of the other eight is 8 of 11 subs at
    # depth 1, and reads as 1.
    assert typical_panel_depth(
        panel_frame_counts(_mosaic(3, [3, 1, 1, 1, 1, 1, 1, 1, 1]))) == 1


def test_the_counts_may_arrive_in_any_order():
    """The rule is about the population, not the caller's ordering."""
    assert typical_panel_depth([1, 6, 6, 6]) == typical_panel_depth([6, 6, 6, 1]) == 6
