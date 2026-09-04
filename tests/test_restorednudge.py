""""Some of your subs came back after this picture was made."

The nudge asks the owner to spend hours of NAS CPU, so the whole question here is
whether the claim is *exactly* true: it may only appear when a sub really was put
back after the published picture was stacked. Everything else — a restoration
that predates the run, a target with no runs, an unparseable stamp — must read as
silence, because a wrong nudge on this surface is a permanent one.
"""

from seestack.io.project import StackRunRow
from seestack.restorednudge import restored_since_stack

RAN = "2026-08-30T14:32:05+00:00"
BEFORE = "2026-08-30T09:00:00+00:00"
AFTER = "2026-08-31T22:10:00+00:00"


def _run(run_id=1, *, ran=RAN, n_frames_used=200):
    return StackRunRow(
        id=run_id,
        timestamp_utc=ran,
        output_basename=f"stack_{run_id}",
        fits_path=None, tiff_path=None, preview_path=None,
        n_frames_used=n_frames_used, canvas_h=1080, canvas_w=1920,
        coverage_min=1, coverage_max=200, options_json="{}",
    )


def test_subs_that_came_back_after_the_stack_are_the_whole_point():
    back = restored_since_stack([_run()], restored_stamps=[AFTER, AFTER, AFTER])
    assert back is not None
    assert back.n_restored == 3
    assert back.run_id == 1
    assert back.n_frames_used == 200      # what the picture on screen combined
    assert back.timestamp_utc == RAN


def test_a_restoration_that_predates_the_stack_says_nothing():
    """The picture already includes that sub — the app reconsidered it, *then*
    stacked. Saying anything here would send the owner off to re-make a picture
    that is already correct."""
    assert restored_since_stack([_run()], restored_stamps=[BEFORE]) is None


def test_only_the_subs_that_came_back_after_are_counted():
    """A target accumulates restorations over its life; only the ones the newest
    picture missed are news."""
    back = restored_since_stack(
        [_run()], restored_stamps=[BEFORE, AFTER, BEFORE, AFTER])
    assert back is not None
    assert back.n_restored == 2


def test_a_restoration_at_the_very_moment_of_the_stack_says_nothing():
    """Strictly-after, so the boundary can't manufacture a nudge out of a
    reconciliation that ran as part of the same processing chain."""
    assert restored_since_stack([_run()], restored_stamps=[RAN]) is None


def test_the_newest_run_is_the_one_that_matters():
    """An older run that *did* miss the sub is irrelevant — the picture on screen
    is the newest one, and it has the sub."""
    newest = _run(2, ran="2026-09-02T00:00:00+00:00")
    older = _run(1, ran="2026-08-01T00:00:00+00:00")
    assert restored_since_stack([newest, older], restored_stamps=[AFTER]) is None
    # ...and the mirror: a restoration after the newest run fires on *that* run.
    back = restored_since_stack(
        [newest, older], restored_stamps=["2026-09-03T00:00:00+00:00"])
    assert back is not None and back.run_id == 2


def test_a_target_with_no_stack_says_nothing():
    """There is no picture to be thinner than the data yet — the "process this
    target" nudge owns that state."""
    assert restored_since_stack([], restored_stamps=[AFTER]) is None


def test_no_restorations_at_all_is_silence_and_the_common_case():
    assert restored_since_stack([_run()], restored_stamps=[]) is None


def test_an_unparseable_or_empty_stamp_is_ignored_not_guessed():
    """A legacy or malformed value must not become a nudge; the honest read of
    "I can't tell when this came back" is to say nothing about it."""
    assert restored_since_stack(
        [_run()], restored_stamps=["", "not-a-date"]) is None
    back = restored_since_stack(
        [_run()], restored_stamps=["not-a-date", AFTER])
    assert back is not None and back.n_restored == 1


def test_a_naive_stamp_still_compares_against_an_aware_run():
    """Every writer stores tz-aware UTC, but the parse is deliberately forgiving;
    a naive stamp must not raise "can't compare offset-naive and aware"."""
    back = restored_since_stack([_run()], restored_stamps=["2026-08-31T22:10:00"])
    assert back is not None and back.n_restored == 1


def test_a_run_with_no_id_says_nothing():
    """Defensive: an unsaved row can't be pointed at."""
    run = _run()
    run.id = None
    assert restored_since_stack([run], restored_stamps=[AFTER]) is None
