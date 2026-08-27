"""`seestack.covernudge` — "your cleanest shot so far" cover nudge.

A pinned cover never changes on its own, so a beginner who keeps adding subs can
end up showing an older, noisier picture on every showcase surface than the one
their library already holds. These pin the exact conditions under which we say
something — and, just as importantly, all the ones where we stay quiet.
"""

from __future__ import annotations

import json

import pytest

from seestack.covernudge import CLEANER_RATIO, cleanest_shot, grainier_newest
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


# --- grainier_newest: the mirror case, where *nothing* is pinned -------------


def test_grainier_newest_offers_the_cleanest_earlier_run():
    """Unpinned, the cover follows the newest stack — so a hazy restack demotes a
    better picture everywhere with nothing said. Say it, and offer the best
    earlier run (not merely the previous one)."""
    newest = _run(3, sigma=0.013, ts="2026-05-20T00:00:00Z", n_frames=22)
    middling = _run(2, sigma=0.011, ts="2026-05-14T00:00:00Z", n_frames=40)
    best = _run(1, sigma=0.010, ts="2026-05-01T00:00:00Z", n_frames=55)
    nudge = grainier_newest([newest, middling, best], cover_run_id=None)
    assert nudge is not None
    assert nudge.run_id == 1 and nudge.newest_run_id == 3
    assert nudge.n_frames_used == 55 and nudge.newest_n_frames_used == 22
    assert nudge.timestamp_utc == "2026-05-01T00:00:00Z"
    # 0.013/0.010 = 1.2999… → 29 % more grain: rounded DOWN, so the headline can
    # only ever understate how much worse the newest picture got.
    assert nudge.percent_grainier == 29


def test_grainier_newest_is_silent_when_a_cover_is_pinned():
    """A pinned cover is the user's own choice and cannot drift — that is
    `cleanest_shot`'s case. The two must never both speak."""
    runs = [_run(2, sigma=0.02), _run(1, sigma=0.01)]
    assert grainier_newest(runs, cover_run_id=1) is None
    assert cleanest_shot(runs, cover_run_id=None) is None


def test_grainier_newest_is_silent_when_the_newest_is_the_cleanest():
    """The happy, ordinary night: more subs, less grain, nothing to say."""
    assert grainier_newest([_run(2, sigma=0.008), _run(1, sigma=0.011)],
                           cover_run_id=None) is None


def test_grainier_newest_ignores_a_marginally_grainier_night():
    """A few percent is noise about noise; the threshold is the same one the
    cleaner nudge uses, applied in the other direction."""
    newest = _run(2, sigma=0.0105)
    earlier = _run(1, sigma=0.0100)
    assert grainier_newest([newest, earlier], cover_run_id=None) is None
    # Exactly at the threshold fires; a hair under it does not.
    at = _run(2, sigma=0.0100 / CLEANER_RATIO)
    assert grainier_newest([at, earlier], cover_run_id=None) is not None
    just_under = _run(2, sigma=0.0100 / CLEANER_RATIO - 1e-6)
    assert grainier_newest([just_under, earlier], cover_run_id=None) is None


def test_grainier_newest_needs_an_earlier_run():
    assert grainier_newest([_run(1, sigma=0.02)], cover_run_id=None) is None
    assert grainier_newest([], cover_run_id=None) is None


@pytest.mark.parametrize("new_sigma,old_sigma", [
    (None, 0.01),           # pre-schema-6 newest
    (0.02, None),           # pre-schema-6 earlier run
    (0.0, 0.01),            # degenerate measurement
    (0.02, 0.0),
    (float("nan"), 0.01),
    (float("inf"), 0.01),
])
def test_grainier_newest_unusable_sigma_is_silent(new_sigma, old_sigma):
    runs = [_run(2, sigma=new_sigma), _run(1, sigma=old_sigma)]
    assert grainier_newest(runs, cover_run_id=None) is None


def test_grainier_newest_skips_earlier_runs_without_a_usable_sigma():
    """One pre-schema-6 run in the history must not silence the nudge — it just
    isn't a candidate."""
    runs = [_run(3, sigma=0.02), _run(2, sigma=None), _run(1, sigma=0.01)]
    nudge = grainier_newest(runs, cover_run_id=None)
    assert nudge is not None and nudge.run_id == 1


def test_grainier_newest_breaks_a_tie_towards_the_more_recent_picture():
    """Two equally-clean earlier stacks: offer the newer one, which is more
    likely to be the framing the owner recognises."""
    runs = [_run(3, sigma=0.02, ts="2026-05-20T00:00:00Z"),
            _run(2, sigma=0.010, ts="2026-05-14T00:00:00Z"),
            _run(1, sigma=0.010, ts="2026-05-01T00:00:00Z")]
    nudge = grainier_newest(runs, cover_run_id=None)
    assert nudge is not None and nudge.run_id == 2


def test_grainier_newest_percent_never_reports_zero():
    at = _run(2, sigma=0.0100 / CLEANER_RATIO)
    nudge = grainier_newest([at, _run(1, sigma=0.0100)], cover_run_id=None)
    assert nudge is not None and nudge.percent_grainier >= 1
