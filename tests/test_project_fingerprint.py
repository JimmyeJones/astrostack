"""``Project.frames_fingerprint`` — the cache key that cannot go stale.

A fingerprint over a target's frames is only worth having if it is *complete*:
a cheaper summary (a count, a max rowid, a sum of ``wcs_json`` lengths) misses
exactly the change that matters most here — a re-solve that rewrites one
frame's WCS to the same number of characters — and a cache keyed on it would
then serve a canvas built from the old sky positions.

So these pin completeness the only way it can be pinned: change one thing at a
time, and require the fingerprint to move every time.
"""

from __future__ import annotations

from seestack.io.project import FrameRow, Project


def _project(tmp_path, n: int = 4) -> Project:
    proj = Project.create(tmp_path / "p", name="fp")
    for i in range(n):
        proj.add_frame(FrameRow(
            source_path=f"sub_{i}.fit", cached_path=f"sub_{i}.fit",
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json='{"CRVAL1": 100.0, "CRVAL2": 20.0}',
            ra_center_deg=100.0, dec_center_deg=20.0,
            fwhm_px=3.0, timestamp_utc=f"2026-01-01T2{i}:00:00",
        ))
    return proj


def test_the_fingerprint_is_stable_while_nothing_changes(tmp_path):
    proj = _project(tmp_path)
    try:
        first = proj.frames_fingerprint()
        assert first == proj.frames_fingerprint()
    finally:
        proj.close()
    # And across a reopen — it is a property of the data, not of the handle.
    proj = Project.open(tmp_path / "p")
    try:
        assert proj.frames_fingerprint() == first
    finally:
        proj.close()


def test_a_resolve_that_keeps_the_wcs_the_same_length_still_moves_it(tmp_path):
    """The case a count/length summary is blind to, and the reason for ``SELECT *``.

    A re-solve rewrites ``wcs_json`` in place with different numbers of the same
    width — new sky positions, identical row count, identical max id, identical
    total length. A canvas memoised past this would be built from where the
    frames used to be.
    """
    proj = _project(tmp_path)
    try:
        before = proj.frames_fingerprint()
        first = next(iter(proj.iter_frames()))
        old = first.wcs_json or ""
        new = old.replace("100.0", "177.7")
        assert len(new) == len(old) and new != old
        proj.update_frame(first.id, wcs_json=new)
        assert proj.frames_fingerprint() != before
    finally:
        proj.close()


def test_every_kind_of_change_to_the_frames_table_moves_it(tmp_path):
    """Accept flips, an added frame, and a column the canvas never reads."""
    proj = _project(tmp_path)
    try:
        seen = {proj.frames_fingerprint()}
        rows = list(proj.iter_frames())

        proj.update_frame(rows[0].id, accept=False, reject_reason="auto:streak")
        seen.add(proj.frames_fingerprint())
        assert len(seen) == 2, "an accept flip must invalidate"

        # A column the canvas does not read: over-invalidating is the safe
        # direction, and pinning it here says that is deliberate rather than
        # lucky — a future canvas rule that starts reading it needs no change.
        proj.update_frame(rows[1].id, fwhm_px=9.9)
        seen.add(proj.frames_fingerprint())
        assert len(seen) == 3, "any column change must invalidate"

        proj.add_frame(FrameRow(
            source_path="extra.fit", cached_path="extra.fit",
            width_px=480, height_px=320,
            wcs_json='{"CRVAL1": 101.0, "CRVAL2": 20.0}',
            ra_center_deg=101.0, dec_center_deg=20.0,
        ))
        seen.add(proj.frames_fingerprint())
        assert len(seen) == 4, "an added frame must invalidate"
    finally:
        proj.close()


def test_undoing_a_change_restores_the_fingerprint(tmp_path):
    """It addresses content, not history — so a frame set that returns to what
    it was is a cache *hit* again rather than a permanent miss."""
    proj = _project(tmp_path)
    try:
        before = proj.frames_fingerprint()
        first = next(iter(proj.iter_frames()))
        proj.update_frame(first.id, accept=False, reject_reason="auto:streak")
        assert proj.frames_fingerprint() != before
        proj.update_frame(first.id, accept=True, reject_reason=None)
        assert proj.frames_fingerprint() == before
    finally:
        proj.close()


def test_two_projects_with_the_same_frames_agree(tmp_path):
    """It addresses content, so two identical targets are one cache entry's
    worth of work — and, more to the point, a fingerprint carried across a
    restart still matches the data it was taken from."""
    a = _project(tmp_path / "a")
    b = _project(tmp_path / "b")
    try:
        assert a.frames_fingerprint() == b.frames_fingerprint()
    finally:
        a.close()
        b.close()


def test_an_empty_project_has_a_fingerprint_rather_than_an_error(tmp_path):
    proj = Project.create(tmp_path / "p", name="empty")
    try:
        empty = proj.frames_fingerprint()
        assert isinstance(empty, str) and empty
        proj.add_frame(FrameRow(source_path="a.fit"))
        assert proj.frames_fingerprint() != empty
    finally:
        proj.close()


# --- what it deliberately does *not* hash -------------------------------------


def test_the_bookkeeping_stamps_are_not_part_of_the_fingerprint():
    """The three columns that record *what the app did*, not the frame's state.

    ``restored_utc``/``rejected_utc``: every change they accompany is already
    visible to the hash through ``accept``, so hashing them would buy a cache
    holder nothing — and would cost the property the test above pins, because
    ``update_frame`` stamps ``rejected_utc`` on every set-aside and the undo
    could never get back.

    ``ingested_at``: a wall clock stamped once, at insert. Hashing it makes two
    libraries holding the same subs disagree purely because they were scanned
    seconds apart, which is what ``test_two_projects_with_the_same_frames_agree``
    below measures. It can hide nothing: it is never updated, so only a *new*
    row can carry a new value, and the hash already sees a new row through every
    other column."""
    from seestack.io.project import _FINGERPRINT_PROVENANCE_COLS

    assert _FINGERPRINT_PROVENANCE_COLS == {
        "restored_utc", "rejected_utc", "ingested_at"}


def test_a_column_nobody_listed_is_hashed_by_default(tmp_path):
    """The exclusion fails *safe*: only a deliberately named column drops out,
    so a column added later over-invalidates rather than going unnoticed —
    which is the direction :meth:`frames_fingerprint`'s docstring accepts."""
    from seestack.io.project import _FRAME_COLUMNS, _FINGERPRINT_PROVENANCE_COLS

    hashed = [c for c in _FRAME_COLUMNS if c not in _FINGERPRINT_PROVENANCE_COLS]
    proj = _project(tmp_path)
    try:
        before = proj.frames_fingerprint()
        first = next(iter(proj.iter_frames()))
        # A column that is neither an id nor a provenance stamp: moving it must
        # move the hash.
        assert "sky_adu_median" in hashed
        proj.update_frame(first.id, sky_adu_median=123.0)
        assert proj.frames_fingerprint() != before
    finally:
        proj.close()


def test_putting_a_sub_back_returns_the_fingerprint_to_where_it_was(tmp_path):
    """The whole point of leaving the stamps out: a re-grade that sets a sub
    aside and a later one that puts it back leave the frame set as it was, so
    the ~1 s canvas computation ``webapp.estimate_cache`` guards is a **hit**
    again. Goes red if either stamp is hashed."""
    from seestack.io.project import restoration_stamp

    proj = _project(tmp_path)
    try:
        before = proj.frames_fingerprint()
        first = next(iter(proj.iter_frames()))
        proj.update_frame(first.id, accept=False,
                          reject_reason="auto:grade:fwhm_px")
        assert proj.get_frame(first.id).rejected_utc is not None
        assert proj.frames_fingerprint() != before
        proj.update_frame(first.id, accept=True, reject_reason=None,
                          restored_utc=restoration_stamp())
        assert proj.frames_fingerprint() == before
    finally:
        proj.close()
