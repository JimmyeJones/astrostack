"""What the reveal's representative-sub pick *costs* at the owner's depth.

:func:`webapp.routers.stack._pick_reference_sub` is asked for on the pages he
opens most — the Target page's noise badge fires on every view, and the Jobs
page fires one per recent stack run — and it reads four small fields off every
sub of the target. It used to get them by building a whole
:class:`~seestack.io.project.FrameRow` for every one of them at once:
``SELECT *``, whose biggest column on a solved sub is the plate-solution header
text. ``Project.iter_health_frames`` exists for exactly this read and already
carries ``sky_adu_median`` *for this pick*; the Target page's "How's my stack?"
card went through it in v0.471.x and these four endpoints did not.

So this file pins the two halves that make the cheap read safe: the retained set
is a fraction of the rows', and the sub it chooses is the same one.
"""

from __future__ import annotations

import tracemalloc

import pytest

from seestack.io.project import FrameRow, Project
from webapp.routers.stack import (
    _pick_reference_sub,
    _reference_sub_row,
    reference_sub_from_frames,
)

# A plate solution is a FITS header *text* of ~25 eighty-character cards, and it
# is what makes a solved row expensive — the same stand-in
# `tests/test_project_health_frames.py` measures the health read against.
WCS = "\n".join(f"{'CTYPE1':<8}= 'RA---TAN'  / card {i:02d}" for i in range(25))

N = 1000


@pytest.fixture
def deep_project(tmp_path):
    """A target shaped like a deep one: ``N`` accepted, solved subs, with one
    unambiguous sharpest-under-a-typical-sky winner."""
    proj = Project.create(tmp_path / "deep", "D")
    try:
        proj.add_frames([
            FrameRow(source_path=f"/incoming/D/sub_{i:05d}.fit", wcs_json=WCS,
                     fwhm_px=3.0 + (i % 97) * 0.01,
                     eccentricity_median=0.4, exposure_s=10.0, gain=80.0,
                     sky_adu_median=1000.0 + (i % 23), accept=True)
            for i in range(N)])
        yield proj
    finally:
        proj.close()


def _peak_of(read):
    tracemalloc.start()
    got = read()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return got, peak


def test_the_pick_holds_a_fraction_of_what_the_whole_rows_cost(deep_project):
    """The claim in its own right, measured rather than reasoned.

    Measured on a synthetic project the size of the owner's deepest target
    (35,894 subs) the whole-row read peaks at ~144 MB against ~9.8 MB for the
    records — see :meth:`Project.iter_health_frames`. A quarter is a deliberately
    wide bar here: the point is the order of the cost, not a byte count that
    would drift with a field.
    """
    rows, rows_peak = _peak_of(lambda: list(deep_project.iter_frames()))
    assert len(rows) == N
    pick, pick_peak = _peak_of(lambda: _pick_reference_sub(deep_project))
    assert pick is not None

    assert pick_peak < rows_peak / 4, (
        f"the pick peaked at {pick_peak / 1024:.0f} KiB against "
        f"{rows_peak / 1024:.0f} KiB for the same frames as rows")


def test_the_cheap_read_chooses_the_sub_the_row_read_chose(deep_project):
    """The other half, and the one a cheaper read could silently break: the
    stamp the noise cache is fingerprinted on is this sub's id, so a pick that
    moved would miss every remembered ratio in the library."""
    rows = list(deep_project.iter_frames(accepted_only=True))
    assert _pick_reference_sub(deep_project).id == reference_sub_from_frames(rows).id


def test_a_target_with_no_accepted_sub_still_picks_one(tmp_path):
    """The fallback the row read had, kept: a target whose every sub was
    rejected still has a representative frame, so the reveal does not vanish on
    the targets most in need of explaining."""
    proj = Project.create(tmp_path / "rejected", "R")
    try:
        proj.add_frames([
            FrameRow(source_path=f"r{i}.fit", fwhm_px=4.0 - i * 0.1,
                     sky_adu_median=1000.0, accept=False,
                     reject_reason="auto:fwhm")
            for i in range(5)])
        pick = _pick_reference_sub(proj)
        assert pick is not None and pick.accept is False
        assert pick.fwhm_px == pytest.approx(3.6)  # the sharpest of them
    finally:
        proj.close()


def test_a_target_with_no_frames_at_all_picks_nothing(tmp_path):
    """Reached on every target before anything is ingested."""
    proj = Project.create(tmp_path / "empty", "E")
    try:
        assert _pick_reference_sub(proj) is None
        assert _reference_sub_row(proj) is None
    finally:
        proj.close()


def test_the_render_callers_get_that_same_sub_as_a_whole_row(deep_project):
    """A caller that goes on to *render* the sub needs two fields a
    :class:`FrameHealth` deliberately drops — where the file is, and how it is
    Bayered — so it takes the one winning row in full."""
    pick = _pick_reference_sub(deep_project)
    row = _reference_sub_row(deep_project)

    assert row is not None and row.id == pick.id
    assert row.source_path.endswith(".fit")
    assert row.wcs_json == WCS


def test_the_row_read_answers_none_when_the_chosen_sub_has_gone(
    deep_project, monkeypatch,
):
    """The pick and the row are two reads, so the sub can be deleted between
    them. The callers already answer that as "no frame to render for this run",
    which is what they must keep doing rather than raising."""
    monkeypatch.setattr(Project, "get_frame", lambda self, frame_id: None)
    assert _reference_sub_row(deep_project) is None
