"""The Moon/Sun capture's own sharpness distribution, turned into advice.

``stack_video`` grades every frame and then throws the scores away, so the one
decision it leaves the beginner — keep 15 %, 30 % or 50 %? — has never had any
evidence behind it. These tests pin what ``sharpness_profile`` says about the two
captures that call for opposite answers (steady air vs. jumpy seeing), that its
numbers describe the stack the user would actually get, and that it stays quiet
rather than guessing when there is nothing to measure.
"""

import math

import pytest

from seestack.video.quality import (
    CURVE_POINTS,
    DEFAULT_CANDIDATES,
    frames_kept,
    sharpness_profile,
)


def _steady(n=200):
    """A capture whose frames are all about equally sharp (steady air)."""
    return [1.0 + 0.01 * math.sin(i) for i in range(n)]


def _jumpy(n=200):
    """A capture where a handful of moments are far crisper than the rest."""
    # The best ~10% ramp up to 5x a typical frame; the rest sit near 1.0.
    out = []
    for i in range(n):
        out.append(5.0 - 4.0 * (i / (n * 0.1)) if i < n * 0.1 else 1.0)
    return out


def test_frames_kept_matches_the_stackers_own_rounding():
    """Every number reported must describe the stack the user would get."""
    # stack_video: max(1, ceil(n * pct / 100))
    for n in (3, 7, 100, 1500):
        for pct in (1.0, 15.0, 30.0, 50.0, 100.0):
            assert frames_kept(n, pct) == max(1, math.ceil(n * pct / 100.0))
    assert frames_kept(0, 30.0) == 0
    assert frames_kept(10, 100.0) == 10


def test_steady_capture_is_told_it_can_keep_more():
    """The whole point: on steady air, being picky only costs you noise."""
    p = sharpness_profile(_steady(), keep_percent=15.0)
    assert p is not None
    assert p.spread == "steady"
    # Nothing to gain by throwing frames away → the loosest offered setting.
    assert p.suggested_percent == max(DEFAULT_CANDIDATES)
    assert "keep more" in p.summary
    # And the advice is quantified, not vague.
    assert "100 frames" in p.summary


def test_jumpy_capture_is_told_to_be_picky():
    p = sharpness_profile(_jumpy(), keep_percent=50.0)
    assert p is not None
    assert p.spread == "variable"
    assert p.suggested_percent == min(DEFAULT_CANDIDATES)
    assert "pickier" in p.summary


def test_agreeing_with_the_users_choice_says_so_instead_of_nagging():
    p = sharpness_profile(_jumpy(), keep_percent=15.0)
    assert p is not None
    assert p.suggested_percent == 15.0
    assert "a good choice here" in p.summary


def test_options_measure_the_real_tradeoff_at_each_setting():
    p = sharpness_profile(_jumpy(), keep_percent=30.0)
    assert p is not None
    assert [o.percent for o in p.options] == sorted(DEFAULT_CANDIDATES)
    # Sharpness falls and the noise win grows as you keep more — the trade-off
    # the user is being asked to make, made visible.
    sharp = [o.sharpness_vs_typical for o in p.options]
    noise = [o.noise_gain for o in p.options]
    assert sharp == sorted(sharp, reverse=True)
    assert noise == sorted(noise)
    for o in p.options:
        assert o.n_frames == frames_kept(200, o.percent)
        assert o.noise_gain == pytest.approx(math.sqrt(o.n_frames))


def test_curve_is_normalised_descending_and_bucketed():
    p = sharpness_profile(_jumpy(1000), keep_percent=30.0)
    assert p is not None
    assert len(p.curve) == CURVE_POINTS
    assert p.curve[0] == pytest.approx(max(p.curve))
    assert all(a >= b - 1e-9 for a, b in zip(p.curve, p.curve[1:], strict=False))
    assert min(p.curve) >= 0.0 and max(p.curve) <= 1.0
    # The cliff at the 10% mark survives bucketing (a sampled curve can step
    # straight over it, which is why the curve averages each bucket).
    assert p.curve[len(p.curve) // 2] < 0.5 * p.curve[0]


def test_curve_keeps_every_point_for_a_short_capture():
    p = sharpness_profile([3.0, 1.0, 2.0], keep_percent=30.0)
    assert p is not None
    assert p.curve == pytest.approx([1.0, 2.0 / 3.0, 1.0 / 3.0])


def test_cut_fraction_marks_where_the_user_stacked():
    p = sharpness_profile(_steady(200), keep_percent=30.0)
    assert p is not None
    assert p.cut_fraction == pytest.approx(60 / 200)
    # No stack yet → nothing to mark.
    assert sharpness_profile(_steady(200)).cut_fraction == 0.0


@pytest.mark.parametrize("scores", [[], [1.0], [float("nan"), float("inf")], [0.0] * 50])
def test_says_nothing_when_there_is_nothing_to_measure(scores):
    """A capture with no usable scores gets no panel — never a guess."""
    assert sharpness_profile(scores, keep_percent=30.0) is None


def test_non_finite_scores_are_dropped_not_propagated():
    p = sharpness_profile([2.0, float("nan"), 1.0, float("inf")], keep_percent=50.0)
    assert p is not None
    assert all(math.isfinite(v) for v in p.curve)
    assert all(math.isfinite(o.sharpness_vs_typical) for o in p.options)


def test_a_mixed_capture_reads_as_mixed():
    # Best decile 1.3× a typical frame in raw score = √1.3 ≈ 1.14× in contrast,
    # which sits between the steady (1.07) and variable (1.22) gates.
    scores = [1.3 if i < 20 else 1.0 for i in range(200)]
    p = sharpness_profile(scores, keep_percent=30.0)
    assert p is not None
    assert p.spread == "mixed"
    assert "varied a fair bit" in p.summary
