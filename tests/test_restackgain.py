""""This picture was made by an older AstroStack" — what a re-stack would give.

Every test here is really about the same question: is the offer *honest*? The
note asks the owner to spend hours of NAS CPU, so it may only appear when a
re-stack would actually supply what it says it would.
"""

from seestack.io.project import StackRunRow
from seestack.restackgain import restack_gain


def _run(run_id=1, *, start=None, hours=None, n_frames_used=200):
    return StackRunRow(
        id=run_id,
        timestamp_utc="2026-08-30T14:32:05+00:00",
        output_basename=f"stack_{run_id}",
        fits_path=None, tiff_path=None, preview_path=None,
        n_frames_used=n_frames_used, canvas_h=1080, canvas_w=1920,
        coverage_min=1, coverage_max=200, options_json="{}",
        capture_start_utc=start,
        capture_end_utc=start,
        capture_hours_json=hours,
    )


def test_an_old_picture_that_cannot_say_which_night_it_is_from():
    """The case the whole note exists for: no capture window, and subs that do
    carry their capture times — so a re-stack really would fix the captions."""
    gain = restack_gain([_run()], n_accepted=512, n_accepted_datable=512)
    assert gain is not None
    assert gain.missing_capture_window is True
    assert gain.missing_night_count is False   # subsumed by the window
    assert gain.run_id == 1
    assert gain.n_frames_used == 200           # what the old picture combined
    assert gain.n_frames_ready == 512          # what a re-stack would combine


def test_a_picture_that_records_everything_says_nothing():
    gain = restack_gain(
        [_run(start="2024-11-15T21:00:00+00:00", hours='["2024-11-15T21:00:00Z"]')],
        n_accepted=512, n_accepted_datable=512,
    )
    assert gain is None


def test_a_window_without_a_night_count_is_its_own_smaller_gain():
    """The in-between run: it can name two dates but never say "over 4 nights",
    which is the part a person says out loud about their own picture."""
    gain = restack_gain(
        [_run(start="2024-11-15T21:00:00+00:00")],
        n_accepted=512, n_accepted_datable=512,
    )
    assert gain is not None
    assert gain.missing_capture_window is False
    assert gain.missing_night_count is True


def test_it_never_promises_a_date_the_restack_could_not_supply():
    """A window can be missing because the app didn't record windows *or*
    because the subs carry no capture time at all — and only the first is
    fixable. Undatable subs must leave the note silent."""
    assert restack_gain([_run()], n_accepted=512, n_accepted_datable=0) is None


def test_a_handful_of_datable_subs_is_not_enough():
    """One datable sub in five hundred *would* record a window — a single-night
    one, describing a picture made of many. Below the majority share, silence."""
    assert restack_gain([_run()], n_accepted=500, n_accepted_datable=40) is None
    # ...and at the majority it speaks.
    assert restack_gain([_run()], n_accepted=500, n_accepted_datable=250) is not None


def test_only_the_newest_run_is_judged():
    """The newest genuine stack *is* the picture on show, so it is the one the
    offer is about — an older run being complete or incomplete changes nothing."""
    newest = _run(2)
    older = _run(1, start="2024-11-15T21:00:00+00:00",
                 hours='["2024-11-15T21:00:00Z"]')
    gain = restack_gain([newest, older], n_accepted=100, n_accepted_datable=100)
    assert gain is not None and gain.run_id == 2


def test_a_target_with_no_stack_yet_says_nothing():
    assert restack_gain([], n_accepted=100, n_accepted_datable=100) is None


def test_a_run_with_no_id_says_nothing():
    """Defensive: an unsaved row can't be pointed at, so there is nothing to
    offer about it."""
    assert restack_gain([_run(None)], n_accepted=100, n_accepted_datable=100) is None
