"""Unit tests for the pure `rank_portfolio` scorer behind the *My best pictures*
wall — ordering, tie-breaks, missing-metric (old-run) fallbacks, and truncation.
No DB or webapp involved; the scorer is a pure function over `PortfolioEntry`s.
"""

from __future__ import annotations

from seestack.portfolio import (
    PORTFOLIO_WEIGHTS,
    PortfolioEntry,
    rank_portfolio,
)


def _keys(entries, *, limit=None):
    return [r.key for r in rank_portfolio(entries, limit=limit)]


def test_empty_input_returns_empty():
    assert rank_portfolio([]) == []
    assert rank_portfolio([], limit=5) == []


def test_more_integration_and_lower_noise_ranks_higher():
    # "deep" wins on every metric; "shallow" is worse everywhere.
    deep = PortfolioEntry(key="deep", n_frames_used=500, total_exposure_s=15000,
                          noise_sigma=0.01, coverage_max=500)
    shallow = PortfolioEntry(key="shallow", n_frames_used=20, total_exposure_s=600,
                             noise_sigma=0.09, coverage_max=20)
    assert _keys([shallow, deep]) == ["deep", "shallow"]


def test_score_is_in_unit_range_and_best_scores_one():
    deep = PortfolioEntry(key="deep", n_frames_used=500, total_exposure_s=15000,
                          noise_sigma=0.01, coverage_max=500)
    shallow = PortfolioEntry(key="shallow", n_frames_used=20, total_exposure_s=600,
                             noise_sigma=0.09, coverage_max=20)
    ranked = rank_portfolio([shallow, deep])
    by_key = {r.key: r.score for r in ranked}
    # The all-round best is its own max on every metric → exactly 1.0.
    assert by_key["deep"] == 1.0
    assert 0.0 <= by_key["shallow"] < by_key["deep"]


def test_single_entry_scores_one():
    only = PortfolioEntry(key="only", n_frames_used=100, total_exposure_s=3000,
                          noise_sigma=0.05, coverage_max=100)
    ranked = rank_portfolio([only])
    assert [r.key for r in ranked] == ["only"]
    assert ranked[0].score == 1.0


def test_missing_metrics_are_not_penalised():
    # An old run carrying only frame count is scored over that one metric — it
    # gets full marks for being the frame-count leader rather than being sunk to
    # zero for the missing exposure/noise/coverage columns.
    old = PortfolioEntry(key="old", n_frames_used=1000)
    modern = PortfolioEntry(key="modern", n_frames_used=100, total_exposure_s=3000,
                            noise_sigma=0.05, coverage_max=100)
    ranked = rank_portfolio([old, modern])
    by_key = {r.key: r.score for r in ranked}
    # "old" is the frame-count max, so its (frames-only) score is 1.0 and it
    # actually leads — a missing metric is a non-penalty, not a demotion.
    assert by_key["old"] == 1.0
    assert by_key["modern"] <= 1.0


def test_noise_lower_is_better():
    # Identical but for σ — the cleaner one wins.
    clean = PortfolioEntry(key="clean", n_frames_used=100, total_exposure_s=3000,
                           noise_sigma=0.02, coverage_max=100)
    noisy = PortfolioEntry(key="noisy", n_frames_used=100, total_exposure_s=3000,
                           noise_sigma=0.08, coverage_max=100)
    assert _keys([noisy, clean]) == ["clean", "noisy"]


def test_tie_breaks_are_deterministic():
    # Two entries with identical scores (same metrics) break the tie by
    # integration time, then frames, then key — so ordering is stable.
    a = PortfolioEntry(key="zebra", n_frames_used=100, total_exposure_s=3000,
                       noise_sigma=0.05, coverage_max=100)
    b = PortfolioEntry(key="alpha", n_frames_used=100, total_exposure_s=3000,
                       noise_sigma=0.05, coverage_max=100)
    # Same score → tie broken by key ascending ("alpha" before "zebra").
    assert _keys([a, b]) == ["alpha", "zebra"]
    # Longer integration wins even with the "later" key.
    c = PortfolioEntry(key="zzz", n_frames_used=100, total_exposure_s=6000,
                       noise_sigma=0.05, coverage_max=100)
    ranked = _keys([a, b, c])
    assert ranked[0] == "zzz"


def test_limit_truncates_to_top_n():
    entries = [
        PortfolioEntry(key=f"t{i}", n_frames_used=i * 10, total_exposure_s=i * 300,
                       noise_sigma=0.1 / i, coverage_max=i * 10)
        for i in range(1, 6)
    ]
    top2 = _keys(entries, limit=2)
    assert top2 == ["t5", "t4"]
    assert _keys(entries, limit=0) == []


def test_ranking_is_order_independent():
    entries = [
        PortfolioEntry(key="a", n_frames_used=50, total_exposure_s=1500,
                       noise_sigma=0.06, coverage_max=50),
        PortfolioEntry(key="b", n_frames_used=300, total_exposure_s=9000,
                       noise_sigma=0.02, coverage_max=300),
        PortfolioEntry(key="c", n_frames_used=120, total_exposure_s=3600,
                       noise_sigma=0.04, coverage_max=120),
    ]
    forward = _keys(entries)
    backward = _keys(list(reversed(entries)))
    assert forward == backward == ["b", "c", "a"]


def test_weights_are_a_sane_blend():
    # Guardrail: exposure leads and every documented metric carries weight.
    assert set(PORTFOLIO_WEIGHTS) == {"exposure", "frames", "noise", "coverage"}
    assert PORTFOLIO_WEIGHTS["exposure"] == max(PORTFOLIO_WEIGHTS.values())
    assert all(w > 0 for w in PORTFOLIO_WEIGHTS.values())
