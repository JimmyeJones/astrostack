"""`seestack.covernudge` — "your cleanest shot so far" cover nudge.

A pinned cover never changes on its own, so a beginner who keeps adding subs can
end up showing an older, noisier picture on every showcase surface than the one
their library already holds. These pin the exact conditions under which we say
something — and, just as importantly, all the ones where we stay quiet.
"""

from __future__ import annotations

import json

import pytest

from seestack.covernudge import (
    CLEANER_RATIO,
    MIN_SKY_SHARE,
    cleanest_shot,
    grainier_newest,
)
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


# --- the sky-extent guard ---------------------------------------------------
#
# Both nudges compare one number — each run's `noise_sigma`, which is normalised
# to its own image's robust range and measured over the whole canvas — so they
# can only compare two pictures of the SAME sky. Reproduced on the bundled 2x2
# mosaic sample by stacking real subsets through `run_stack`: one panel six subs
# deep (sigma 0.00074) and then a second panel holding a single sub (0.00089) is
# "20 % more grain" and HALF THE SKY, and the nudge offered to put the one-panel
# picture back on the Library tile, "My best pictures" and the montage wall —
# where a pin stays forever, so the mosaic being built would never show again.
# A restack of the same sky moved the canvas by 0.3 % over the same measurement,
# which is why the two cases separate rather than needing a tuned threshold.


def test_grainier_newest_does_not_offer_a_picture_that_covers_less_sky():
    """The reproduced case: the newest stack is grainier because a new mosaic
    panel has just opened, not because the night was worse."""
    newest = _run(2, sigma=0.00089)          # two panels, the new one 1 sub deep
    earlier = _run(1, sigma=0.00074)         # one panel, six subs deep
    # Unguarded — what the app did before — it fires and offers the half-size one.
    assert grainier_newest([newest, earlier], cover_run_id=None) is not None
    # With each run's own sky extent to hand it says nothing.
    assert grainier_newest([newest, earlier], cover_run_id=None,
                           sky_fields={2: 1.97, 1: 1.00}) is None


def test_grainier_newest_still_offers_an_earlier_run_of_the_same_sky():
    """The nudge's actual case — haze, or a night most of whose subs were set
    aside — is untouched: same canvas, so the sigmas compare like with like."""
    newest = _run(2, sigma=0.00083, n_frames=11)
    earlier = _run(1, sigma=0.00063, n_frames=21)
    nudge = grainier_newest([newest, earlier], cover_run_id=None,
                            sky_fields={2: 3.62, 1: 3.63})
    assert nudge is not None and nudge.run_id == 1
    assert nudge.percent_grainier == 31


def test_grainier_newest_skips_the_smaller_candidate_and_keeps_looking():
    """The filter sits on the candidate, not on the verdict: a cleaner run of
    less sky is passed over, and a same-sky one behind it is still offered."""
    newest = _run(3, sigma=0.0100)
    smaller_but_cleanest = _run(2, sigma=0.0050)
    same_sky = _run(1, sigma=0.0080)
    nudge = grainier_newest([newest, smaller_but_cleanest, same_sky],
                            cover_run_id=None,
                            sky_fields={3: 3.60, 2: 1.00, 1: 3.58})
    assert nudge is not None and nudge.run_id == 1


@pytest.mark.parametrize("sky_fields", [
    None,                        # every caller that does not pass the map
    {},                          # an empty one reads the same way
    {2: 3.6},                    # the candidate's own figure is missing
    {2: 3.6, 1: None},           # …or unanswerable (no recorded frame shape)
    {2: 3.6, 1: 0.0},            # …or a degenerate zero
    {2: 3.6, 1: float("nan")},
    {2: None, 1: 1.0},           # the picture on show is the unanswerable one
])
def test_grainier_newest_without_usable_sky_figures_is_unchanged(sky_fields):
    """No opinion means today's behaviour, never a silenced nudge: this guard can
    only ever remove an offer it can prove is smaller."""
    runs = [_run(2, sigma=0.012), _run(1, sigma=0.008)]
    assert grainier_newest(runs, cover_run_id=None,
                           sky_fields=sky_fields) is not None


def test_grainier_newest_sky_guard_boundary():
    """Exactly ``MIN_SKY_SHARE`` of the sky on show still counts as the same
    picture; a hair under it does not."""
    runs = [_run(2, sigma=0.012), _run(1, sigma=0.008)]
    at = {2: 10.0, 1: 10.0 * MIN_SKY_SHARE}
    assert grainier_newest(runs, cover_run_id=None, sky_fields=at) is not None
    under = {2: 10.0, 1: 10.0 * MIN_SKY_SHARE - 0.01}
    assert grainier_newest(runs, cover_run_id=None, sky_fields=under) is None


def test_cleanest_shot_does_not_promote_a_picture_that_covers_less_sky():
    """The mirror: a stack of fewer panels than the pinned mosaic measures
    cleaner for its own depth, and "cleaner" is no reason to hide shot sky."""
    newest = _run(2, sigma=0.008, n_frames=40)
    cover = _run(1, sigma=0.011, n_frames=80, ts="2026-04-01T00:00:00Z")
    assert cleanest_shot([newest, cover], cover_run_id=1) is not None
    assert cleanest_shot([newest, cover], cover_run_id=1,
                         sky_fields={2: 1.00, 1: 3.63}) is None
    # Same sky, so the ordinary "you kept adding subs" case still speaks.
    shot = cleanest_shot([newest, cover], cover_run_id=1,
                         sky_fields={2: 3.62, 1: 3.63})
    assert shot is not None and shot.run_id == 2


def test_cleanest_shot_may_promote_a_picture_that_covers_more_sky():
    """The guard is one-directional — it never objects to a *bigger* picture."""
    newest = _run(2, sigma=0.008)
    cover = _run(1, sigma=0.011, ts="2026-04-01T00:00:00Z")
    shot = cleanest_shot([newest, cover], cover_run_id=1,
                         sky_fields={2: 3.63, 1: 1.00})
    assert shot is not None and shot.run_id == 2
