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


# ---------------------------------------------------------------------------
# Pinned favourites — a stated preference, not a quality claim.
# ---------------------------------------------------------------------------

def _deep(key="deep", *, pinned=False):
    return PortfolioEntry(key=key, n_frames_used=500, total_exposure_s=15000,
                          noise_sigma=0.01, coverage_max=500, pinned=pinned)


def _shallow(key="shallow", *, pinned=False):
    return PortfolioEntry(key=key, n_frames_used=20, total_exposure_s=600,
                          noise_sigma=0.09, coverage_max=20, pinned=pinned)


def test_a_pinned_favourite_leads_even_a_much_deeper_stack():
    """The user's own pick outranks the automatic winner — that's the whole point
    of pinning it."""
    assert _keys([_deep(), _shallow(pinned=True)]) == ["shallow", "deep"]


def test_pinning_does_not_change_the_score():
    """A pin floats an entry; it never inflates the transparent quality number the
    wall shows, so the caption stays honest."""
    plain = rank_portfolio([_deep(), _shallow()])
    pinned = rank_portfolio([_deep(), _shallow(pinned=True)])
    assert {r.key: r.score for r in plain} == {r.key: r.score for r in pinned}


def test_pinned_flag_is_echoed_on_the_ranked_entry():
    ranked = {r.key: r.pinned for r in rank_portfolio([_deep(), _shallow(pinned=True)])}
    assert ranked == {"shallow": True, "deep": False}


def test_a_pinned_favourite_survives_the_limit_cut():
    """A favourite must not be dropped by a wall of deeper stacks — the failure
    the pin exists to prevent."""
    entries = [_deep(f"deep{i}") for i in range(5)] + [_shallow(pinned=True)]
    assert _keys(entries, limit=1) == ["shallow"]


def test_several_pins_stay_ranked_among_themselves():
    """Pinning is a band, not a shuffle: pinned entries still come best-first."""
    entries = [_shallow("weak", pinned=True), _deep("strong", pinned=True),
               _deep("unpinned")]
    assert _keys(entries) == ["strong", "weak", "unpinned"]


def test_entries_built_without_the_new_field_are_unpinned_and_rank_by_score():
    """The default path is untouched: an entry constructed the old way (no
    ``pinned`` argument) is unpinned, so ordering is purely the quality blend."""
    old_style = [
        PortfolioEntry(key="shallow", n_frames_used=20, total_exposure_s=600,
                       noise_sigma=0.09, coverage_max=20),
        PortfolioEntry(key="deep", n_frames_used=500, total_exposure_s=15000,
                       noise_sigma=0.01, coverage_max=500),
    ]
    assert all(not e.pinned for e in old_style)
    ranked = rank_portfolio(old_style)
    assert [r.key for r in ranked] == ["deep", "shallow"]
    assert all(not r.pinned for r in ranked)


# ---------------------------------------------------------------------------
# Per-pixel reading — a mosaic's totals are the target's, not the picture's
#
# The wall ranks *pictures*, and three of its four axes (integration, frame
# count, peak coverage) are facts about the **target**: a mosaic spreads its subs
# across the raster. The fourth, σ, is measured on the pixels themselves, so
# before `field_fulls` reached this scorer the blend's two halves disagreed about
# the same picture — a raster nine subs deep in total scored as "nine frames"
# here while the Gallery card of the same run called it one sub deep everywhere.
# Measured on the bundled 2x2 mosaic sample (webapp/sample_data): 21 subs over
# 3.63 field-fulls is 5.8 a pixel, its 210 s of integration is 58 s a pixel, and
# its `coverage_max` is **21** — every sub the target has, at the one corner
# where four panels meet, while half the picture sits at 6.
# ---------------------------------------------------------------------------


def test_a_single_field_is_byte_for_byte_what_it_always_was():
    """The scale only ever divides by more than one field, so a single field —
    `None`, absent, 1.0, and the clamped sub-1.0 case alike — must score exactly
    as it did before the field existed."""
    def scores(**extra):
        return [
            r.score for r in rank_portfolio([
                PortfolioEntry(key="a", n_frames_used=500, total_exposure_s=15000,
                               noise_sigma=0.01, coverage_max=500, **extra),
                PortfolioEntry(key="b", n_frames_used=20, total_exposure_s=600,
                               noise_sigma=0.09, coverage_max=20, **extra),
            ])
        ]

    baseline = scores()
    assert scores(field_fulls=1.0) == baseline
    assert scores(field_fulls=None) == baseline
    # A canvas measuring *under* one frame would otherwise inflate the depth —
    # the direction that hides the bug — so it clamps rather than being honoured.
    assert scores(field_fulls=0.25) == baseline


def test_a_mosaic_is_ranked_on_what_one_patch_of_sky_got():
    """The bug, at the wall's own scale: two pictures with identical totals and
    identical grain, one of them a 2x2 raster. Before, they tied on every axis
    and the mosaic could take the lead on a tie-break; now the single field —
    which really is four times as deep everywhere — wins."""
    field = PortfolioEntry(key="field", n_frames_used=400, total_exposure_s=12000,
                           noise_sigma=0.02, coverage_max=400)
    mosaic = PortfolioEntry(key="mosaic", n_frames_used=400, total_exposure_s=12000,
                            noise_sigma=0.02, coverage_max=400, field_fulls=4.0)
    ranked = rank_portfolio([mosaic, field])
    assert [r.key for r in ranked] == ["field", "mosaic"]
    by_key = {r.key: r.score for r in ranked}
    assert by_key["field"] > by_key["mosaic"]
    # …and by the amount the axes are worth: the three data axes fall to a
    # quarter, only σ is untouched (it was measured on the pixels all along).
    expected = (
        PORTFOLIO_WEIGHTS["exposure"] * 0.25
        + PORTFOLIO_WEIGHTS["frames"] * 0.25
        + PORTFOLIO_WEIGHTS["coverage"] * 0.25
        + PORTFOLIO_WEIGHTS["noise"] * 1.0
    ) / sum(PORTFOLIO_WEIGHTS.values())
    assert by_key["mosaic"] == expected


def test_a_thin_raster_no_longer_outranks_a_genuinely_deep_picture():
    """The shape a beginner actually hits, and the one the wall exists to get
    right: a 3x3 raster nine subs deep *everywhere* against a modest but real
    single-field stack. The raster's 90 frames and 45 min are the target's; no
    pixel of it saw more than ten subs."""
    raster = PortfolioEntry(key="raster", n_frames_used=90, total_exposure_s=2700,
                            noise_sigma=0.06, coverage_max=90, field_fulls=9.0)
    honest = PortfolioEntry(key="honest", n_frames_used=40, total_exposure_s=1200,
                            noise_sigma=0.04, coverage_max=40)
    assert _keys([raster, honest]) == ["honest", "raster"]


def test_the_peak_coverage_yardstick_is_capped_at_what_a_pixel_got():
    """`coverage_max` is the deepest *single* pixel — on the bundled 2x2 sample
    that is the corner where all four panels meet, carrying every sub the target
    has. Left alone it would both flatter the mosaic and normalise every other
    entry against a depth no picture is at."""
    from seestack.portfolio import _entry_coverage

    sample_like = PortfolioEntry(key="sample", n_frames_used=21,
                                 total_exposure_s=210, noise_sigma=0.00063,
                                 coverage_max=21, field_fulls=3.63)
    # Capped to the depth a typical pixel got, which is the measured median
    # depth (6.0) to within the scale's own precision.
    assert 5.5 < _entry_coverage(sample_like) < 6.0
    # A single field keeps its peak untouched — there the two *are* one number.
    plain = PortfolioEntry(key="plain", n_frames_used=21, coverage_max=21)
    assert _entry_coverage(plain) == 21.0
    # The cap can only ever lower a figure: a heavily dithered stack whose peak
    # is already below the mean depth keeps its own, smaller peak.
    dithered = PortfolioEntry(key="dithered", n_frames_used=100, coverage_max=60)
    assert _entry_coverage(dithered) == 60.0


def test_per_pixel_total_refuses_every_scale_that_would_inflate_depth():
    from seestack.portfolio import per_pixel_total

    assert per_pixel_total(400.0, 4.0) == 100.0
    assert per_pixel_total(400.0, None) == 400.0
    assert per_pixel_total(400.0, 1.0) == 400.0
    assert per_pixel_total(400.0, 0.5) == 400.0
    assert per_pixel_total(400.0, float("nan")) == 400.0
    assert per_pixel_total(400.0, float("inf")) == 400.0


def test_two_equally_deep_pictures_rank_equally_however_the_sky_was_tiled():
    """The positive half of the same claim, and the one that also pins the
    tie-breaks: a 2x2 mosaic shot four times as long as a single field has the
    *same* picture depth, so it must score the same rather than four times
    better. Before, its raw totals took every data axis outright."""
    field = PortfolioEntry(key="aaa-field", n_frames_used=100,
                           total_exposure_s=3000, noise_sigma=0.04,
                           coverage_max=100)
    mosaic = PortfolioEntry(key="zzz-mosaic", n_frames_used=400,
                            total_exposure_s=12000, noise_sigma=0.04,
                            coverage_max=400, field_fulls=4.0)
    ranked = rank_portfolio([mosaic, field])
    assert ranked[0].score == ranked[1].score == 1.0
    # Every tie-break (integration, then frames) is now tied too, so the order
    # falls all the way through to the key — which is what "equal" means here.
    assert [r.key for r in ranked] == ["aaa-field", "zzz-mosaic"]
