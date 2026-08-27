"""`seestack.covernudge` — "your cleanest shot so far" cover nudge.

A pinned cover never changes on its own, so a beginner who keeps adding subs can
end up showing an older, noisier picture on every showcase surface than the one
their library already holds. These pin the exact conditions under which we say
something — and, just as importantly, all the ones where we stay quiet.
"""

from __future__ import annotations

import json

import pytest

from seestack.covernudge import CLEANER_RATIO, cleanest_shot, grainier_default
from seestack.io.project import StackRunRow


def _run(run_id: int, *, sigma: float | None, ts: str = "2026-05-09T00:00:00Z",
         n_frames: int = 40) -> StackRunRow:
    return StackRunRow(
        id=run_id, timestamp_utc=ts, output_basename="master",
        fits_path=None, tiff_path=None, preview_path=f"/tmp/p{run_id}.png",
        n_frames_used=n_frames, canvas_h=320, canvas_w=480,
        coverage_min=1, coverage_max=n_frames,
        options_json=json.dumps({"output_name": "m42"}),
        noise_sigma=sigma,
    )


def test_newest_materially_cleaner_than_pinned_cover_nudges():
    newest = _run(2, sigma=0.008, n_frames=80)
    cover = _run(1, sigma=0.011, ts="2026-04-01T00:00:00Z", n_frames=40)
    shot = cleanest_shot([newest, cover], cover_run_id=1)
    assert shot is not None
    assert shot.run_id == 2 and shot.cover_run_id == 1
    assert shot.n_frames_used == 80 and shot.cover_n_frames_used == 40
    assert shot.timestamp_utc == "2026-05-09T00:00:00Z"
    # 0.008/0.011 = 0.727 → 27.2 % cleaner, rounded DOWN so we never overstate.
    assert shot.percent_cleaner == 27


def test_nothing_pinned_is_silent():
    """With no cover pinned the cover already *is* the newest stack."""
    runs = [_run(2, sigma=0.001), _run(1, sigma=0.05)]
    assert cleanest_shot(runs, cover_run_id=None) is None


def test_newest_is_already_the_cover_is_silent():
    runs = [_run(2, sigma=0.008), _run(1, sigma=0.011)]
    assert cleanest_shot(runs, cover_run_id=2) is None


def test_marginally_cleaner_is_silent():
    """A few percent is noise about noise — it must not train the owner to
    ignore the nudge."""
    cover = _run(1, sigma=0.0100)
    assert cleanest_shot([_run(2, sigma=0.0095), cover], cover_run_id=1) is None
    # Exactly at the threshold does fire (<= ratio), a hair above does not.
    at = _run(2, sigma=0.0100 * CLEANER_RATIO)
    assert cleanest_shot([at, cover], cover_run_id=1) is not None
    just_over = _run(2, sigma=0.0100 * CLEANER_RATIO + 1e-6)
    assert cleanest_shot([just_over, cover], cover_run_id=1) is None


def test_noisier_newest_is_silent():
    runs = [_run(2, sigma=0.02), _run(1, sigma=0.01)]
    assert cleanest_shot(runs, cover_run_id=1) is None


@pytest.mark.parametrize("new_sigma,cover_sigma", [
    (None, 0.01),       # pre-schema-6 candidate
    (0.008, None),      # pre-schema-6 cover
    (0.0, 0.01),        # degenerate measurement
    (0.008, 0.0),
    (float("nan"), 0.01),
    (0.008, float("inf")),
])
def test_unusable_sigma_is_silent(new_sigma, cover_sigma):
    runs = [_run(2, sigma=new_sigma), _run(1, sigma=cover_sigma)]
    assert cleanest_shot(runs, cover_run_id=1) is None


def test_pinned_run_not_among_genuine_runs_is_silent():
    """A pruned cover — or an editor export pinned by hand — has no comparable
    σ, so we compare nothing rather than compare unlike things."""
    runs = [_run(2, sigma=0.008), _run(3, sigma=0.02)]
    assert cleanest_shot(runs, cover_run_id=1) is None


def test_no_runs_is_silent():
    assert cleanest_shot([], cover_run_id=1) is None


def test_percent_never_reports_zero():
    """A nudge that fired always has something to say — rounding down must not
    turn a real improvement into '0 % cleaner'."""
    # Right at the threshold: 15 % exactly, which floating point can land a hair
    # under. The floor keeps the copy honest either way.
    shot = cleanest_shot([_run(2, sigma=0.01 * CLEANER_RATIO), _run(1, sigma=0.01)],
                         cover_run_id=1)
    assert shot is not None and shot.percent_cleaner >= 1


# --- the mirror case: nothing pinned, so the cover follows the newest stack ---
# `cleanest_shot` is deliberately silent with no pin — there is no cover to
# compare against. But that is the state a beginner is actually in, and the one
# where the *default* can go backwards on its own.


def test_a_grainier_newest_stack_offers_the_better_earlier_one():
    """A restack through haze publishes a legitimately newer, noisier stack, and
    an unpinned cover switches every showcase surface to it with nothing said."""
    newest = _run(3, sigma=0.026, ts="2026-05-20T00:00:00Z", n_frames=40)
    good = _run(2, sigma=0.020, ts="2026-05-14T00:00:00Z", n_frames=120)
    older = _run(1, sigma=0.031, ts="2026-04-01T00:00:00Z", n_frames=30)
    hit = grainier_default([newest, good, older], cover_run_id=None)
    assert hit is not None
    # It points at the *best* earlier stack, not merely the previous one.
    assert hit.run_id == 2 and hit.newest_run_id == 3
    assert hit.best_timestamp_utc == "2026-05-14T00:00:00Z"
    assert hit.timestamp_utc == "2026-05-20T00:00:00Z"
    assert hit.n_frames_used == 40 and hit.best_n_frames_used == 120
    # 0.026/0.020 = 1.2999999999999998 in binary floating point → 29 % more
    # grain. Rounded DOWN, deliberately: a regression note that overstates the
    # damage is worse than one that undersells it.
    assert hit.percent_grainier == 29


def test_the_two_nudges_can_never_both_speak():
    """They are mutually exclusive by construction — one needs a pin, the other
    needs none — but the app renders both, so pin it."""
    runs = [_run(2, sigma=0.03), _run(1, sigma=0.01)]
    assert grainier_default(runs, cover_run_id=None) is not None
    assert cleanest_shot(runs, cover_run_id=None) is None
    # …and with a pin, the other way round (here the newest is the cleaner one).
    cleaner = [_run(2, sigma=0.008), _run(1, sigma=0.011)]
    assert cleanest_shot(cleaner, cover_run_id=1) is not None
    assert grainier_default(cleaner, cover_run_id=1) is None


def test_something_pinned_is_silent():
    """A pinned cover cannot have moved on its own, so there is no regression to
    report — whatever the newest stack's grain looks like."""
    runs = [_run(2, sigma=0.05), _run(1, sigma=0.01)]
    assert grainier_default(runs, cover_run_id=1) is None
    assert grainier_default(runs, cover_run_id=2) is None


def test_the_happy_case_says_nothing():
    """The ordinary night: the newest stack is the cleanest the target has."""
    runs = [_run(2, sigma=0.010, n_frames=120), _run(1, sigma=0.031, n_frames=40)]
    assert grainier_default(runs, cover_run_id=None) is None


def test_a_marginally_grainier_restack_is_silent():
    """Two stacks of one target differ by a few percent for reasons nobody can
    see; the same bar as the other direction keeps this from firing on those."""
    newest = _run(2, sigma=0.0105)
    good = _run(1, sigma=0.0100)
    assert grainier_default([newest, good], cover_run_id=None) is None
    # Exactly at the threshold fires (<= ratio), a hair inside it does not.
    at = _run(2, sigma=0.0100 / CLEANER_RATIO)
    assert grainier_default([at, good], cover_run_id=None) is not None
    just_inside = _run(2, sigma=0.0100 / CLEANER_RATIO - 1e-6)
    assert grainier_default([just_inside, good], cover_run_id=None) is None


def test_a_lone_stack_is_silent():
    """Nothing to fall back to — and a first stack is never a regression."""
    assert grainier_default([_run(2, sigma=0.05)], cover_run_id=None) is None
    assert grainier_default([], cover_run_id=None) is None


@pytest.mark.parametrize("new_sigma,best_sigma", [
    (None, 0.01),          # pre-schema-6 newest
    (0.05, None),          # pre-schema-6 candidate
    (0.0, 0.01),           # degenerate measurement
    (0.05, 0.0),
    (float("nan"), 0.01),
    (float("inf"), 0.01),
    (0.05, float("nan")),
])
def test_grainier_unusable_sigma_is_silent(new_sigma, best_sigma):
    runs = [_run(2, sigma=new_sigma), _run(1, sigma=best_sigma)]
    assert grainier_default(runs, cover_run_id=None) is None


def test_earlier_runs_without_a_sigma_are_skipped_not_fatal():
    """A pre-schema-6 run in the middle of the history must not hide the good
    one behind it."""
    newest = _run(4, sigma=0.030)
    unmeasured = _run(3, sigma=None)
    good = _run(2, sigma=0.015)
    hit = grainier_default([newest, unmeasured, good], cover_run_id=None)
    assert hit is not None and hit.run_id == 2


def test_grainier_percent_never_reports_zero():
    """A nudge that fired always has something to say."""
    hit = grainier_default(
        [_run(2, sigma=0.01 / CLEANER_RATIO), _run(1, sigma=0.01)],
        cover_run_id=None,
    )
    assert hit is not None and hit.percent_grainier >= 1
