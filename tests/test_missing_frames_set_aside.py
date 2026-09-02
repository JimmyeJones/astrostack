"""A target whose missing subs never come back can be released, reversibly.

A8. The walk-away readability preflight holds a target back while
``readable < prior_max`` — right while a flapping drive is coming back, a dead
end when it isn't. If the owner deletes a session from ``incoming/`` (their
folder, their right) the DB rows stay, ``unreadable`` never drops, and the target
is held until brand-new subs outnumber the best run it ever made. He was told,
and offered nothing to do.

These pin the pair that fixes it: setting the missing subs aside is
database-only, respects a hand grade, is idempotent, and lifts the hold; and
putting them back is automatic the moment the files reappear.
"""

from __future__ import annotations

from pathlib import Path

from seestack.io.project import (
    REJECT_REASON_FILE_MISSING,
    FrameRow,
    Project,
    count_unreadable_frames,
)


def _frame(proj: Project, path: Path, *, exists: bool = True, **kw) -> int:
    if exists:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return proj.add_frame(FrameRow(source_path=str(path), wcs_json="WCS", **kw))


def test_set_aside_takes_only_the_subs_whose_files_are_gone(tmp_path):
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        here = [_frame(proj, tmp_path / "in" / f"a{i}.fit") for i in range(3)]
        gone = [_frame(proj, tmp_path / "in" / f"b{i}.fit", exists=False)
                for i in range(2)]

        assert set(proj.set_missing_frames_aside()) == set(gone)
        for fid in gone:
            f = proj.get_frame(fid)
            assert f.accept is False
            assert f.reject_reason == REJECT_REASON_FILE_MISSING
            # Reversible by construction: never stamped as the user's own choice.
            assert f.user_override is False
        for fid in here:
            assert proj.get_frame(fid).accept is True
        assert proj.count_frames_set_aside_as_missing() == 2

        # Idempotent — a second call finds nothing left to set aside.
        assert proj.set_missing_frames_aside() == []
    finally:
        proj.close()


def test_set_aside_leaves_a_hand_graded_sub_alone(tmp_path):
    """A user's own accept is a decision, not an assumption the app may revisit."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        mine = _frame(proj, tmp_path / "in" / "mine.fit", exists=False,
                      user_override=True)
        theirs = _frame(proj, tmp_path / "in" / "theirs.fit", exists=False)
        assert proj.set_missing_frames_aside() == [theirs]
        assert proj.get_frame(mine).accept is True
    finally:
        proj.close()


def test_set_aside_never_touches_an_already_rejected_sub(tmp_path):
    """A cloudy/streak auto-reject keeps its own reason."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        cloudy = _frame(proj, tmp_path / "in" / "cloudy.fit", exists=False,
                        accept=False, reject_reason="qc:sky")
        proj.set_missing_frames_aside()
        f = proj.get_frame(cloudy)
        assert f.accept is False and f.reject_reason == "qc:sky"
    finally:
        proj.close()


def test_the_files_coming_back_puts_the_subs_back_by_itself(tmp_path):
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        p = tmp_path / "in" / "b0.fit"
        gone = _frame(proj, p, exists=False)
        still_gone = _frame(proj, tmp_path / "in" / "b1.fit", exists=False)
        proj.set_missing_frames_aside()

        assert proj.restore_missing_frames() == []  # nothing back yet

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        assert proj.restore_missing_frames() == [gone]
        back = proj.get_frame(gone)
        assert back.accept is True and back.reject_reason is None
        # …and the one still missing is left exactly as it was.
        assert proj.get_frame(still_gone).accept is False
    finally:
        proj.close()


def test_restore_ignores_every_other_kind_of_rejection(tmp_path):
    """Only the app's own "file missing" stamp is undone automatically — a manual
    reject and a QC verdict are somebody's judgement about a *readable* file."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        by_user = _frame(proj, tmp_path / "in" / "u.fit",
                         accept=False, reject_reason="user", user_override=True)
        by_qc = _frame(proj, tmp_path / "in" / "q.fit",
                       accept=False, reject_reason="qc:fwhm")
        assert proj.restore_missing_frames() == []
        assert proj.get_frame(by_user).accept is False
        assert proj.get_frame(by_qc).accept is False
    finally:
        proj.close()


def test_setting_aside_lifts_the_readability_hold(tmp_path):
    """The point of the whole thing, asserted on the hold's own inputs.

    The hold compares ``readable`` against the best run this target has already
    made. Before: 6 accepted, 4 of them gone, so 2 readable against a prior best
    of 6 — held, and no number of scans changes that. After: the 4 are not
    accepted any more, so nothing is unreadable and the hold's own ``unreadable
    <= 0`` gate returns before it compares anything.
    """
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        for i in range(2):
            _frame(proj, tmp_path / "in" / f"here{i}.fit")
        for i in range(4):
            _frame(proj, tmp_path / "in" / f"gone{i}.fit", exists=False)

        def unreadable() -> int:
            return count_unreadable_frames(
                f for f in proj.iter_frames(accepted_only=True) if f.wcs_json)

        assert unreadable() == 4
        proj.set_missing_frames_aside()
        assert unreadable() == 0
        assert len(list(proj.iter_frames(accepted_only=True))) == 2
    finally:
        proj.close()


def test_nothing_happens_on_a_healthy_target(tmp_path):
    """Every file present — every healthy install — and both calls are no-ops."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        for i in range(4):
            _frame(proj, tmp_path / "in" / f"a{i}.fit")
        assert proj.set_missing_frames_aside() == []
        assert proj.restore_missing_frames() == []
        assert proj.count_frames_set_aside_as_missing() == 0
        assert all(f.accept for f in proj.iter_frames())
    finally:
        proj.close()


def test_a_cached_copy_still_counts_as_present(tmp_path):
    """``readable_frame_path`` falls through cache → source, and so must this: a
    sub whose original is gone but whose Stage-1 cache is on disk is readable and
    must not be set aside."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        cache = tmp_path / "cache" / "frame_000001.fit"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"x")
        cached = proj.add_frame(FrameRow(
            source_path=str(tmp_path / "in" / "gone.fit"),
            cached_path=str(cache), wcs_json="WCS"))
        assert proj.set_missing_frames_aside() == []
        assert proj.get_frame(cached).accept is True
    finally:
        proj.close()
