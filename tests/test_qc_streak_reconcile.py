"""Streak auto-reject guardrail: a bright stationary extended object (edge-on
galaxy, elongated nebula) trips the shape-only streak detector on most/all subs,
so the per-frame auto:streak reject would silently discard the WHOLE target.
``reconcile_streak_rejections`` re-accepts the rejections when they cover a
majority of the target — they can't be transient trails.
"""

from __future__ import annotations

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.qc.runner import (
    STREAK_RECONCILE_MIN_FRAMES,
    reconcile_streak_rejections,
)


def _add(proj, n, *, reason="auto:streak", accept=False, user_override=False):
    """Add ``n`` frames all sharing one reject state; return their ids."""
    ids = []
    for _ in range(n):
        ids.append(proj.add_frame(FrameRow(
            source_path=f"f{len(ids)}_{reason}.fit",
            streak_detected=(reason == "auto:streak"),
            accept=accept, reject_reason=reason, user_override=user_override,
        )))
    return ids


def test_majority_streak_rejections_are_reaccepted(tmp_path):
    """An edge-on galaxy: every sub flags a 'streak' → all auto-rejected. The
    guard re-accepts them (a whole target must not vanish)."""
    proj = Project.create(tmp_path / "p", name="Needle")
    try:
        streak = _add(proj, 12, reason="auto:streak")
        restored = reconcile_streak_rejections(proj)
        assert set(restored) == set(streak)
        for fid in streak:
            f = proj.get_frame(fid)
            assert f.accept is True
            assert f.reject_reason is None
            # The flag is kept so the UI still shows "N streaked" and the user
            # can bulk-reject if they really are trails.
            assert f.streak_detected is True
    finally:
        proj.close()


def test_minority_streaks_stay_rejected(tmp_path):
    """A few real satellite subs are a minority → left rejected (the guard is
    for stationary objects, not transient trails)."""
    proj = Project.create(tmp_path / "p", name="M31")
    try:
        _add(proj, 10, reason=None, accept=True)          # clean subs
        streak = _add(proj, 2, reason="auto:streak")      # 2 real satellites
        restored = reconcile_streak_rejections(proj)
        assert restored == []
        for fid in streak:
            f = proj.get_frame(fid)
            assert f.accept is False
            assert f.reject_reason == "auto:streak"
    finally:
        proj.close()


def test_reconcile_respects_user_override(tmp_path):
    """A user who explicitly rejected a streaked frame keeps that decision even
    when the majority guard fires around them."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        _add(proj, 12, reason="auto:streak")
        held = proj.add_frame(FrameRow(
            source_path="user.fit", streak_detected=True,
            accept=False, reject_reason="user", user_override=True))
        reconcile_streak_rejections(proj)
        f = proj.get_frame(held)
        assert f.accept is False
        assert f.reject_reason == "user"
    finally:
        proj.close()


def test_small_target_is_not_reconciled(tmp_path):
    """Below the minimum frame count a majority isn't meaningful (a tiny target's
    couple of streaks could genuinely be satellites), so leave them rejected."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        n = STREAK_RECONCILE_MIN_FRAMES - 1
        streak = _add(proj, n, reason="auto:streak")
        restored = reconcile_streak_rejections(proj)
        assert restored == []
        assert proj.get_frame(streak[0]).accept is False
    finally:
        proj.close()


def test_only_streak_reason_is_cleared(tmp_path):
    """The guard never touches a non-streak reject reason, even when it fires."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        _add(proj, 12, reason="auto:streak")
        fwhm = proj.add_frame(FrameRow(
            source_path="soft.fit", accept=False, reject_reason="qc:fwhm"))
        reconcile_streak_rejections(proj)
        f = proj.get_frame(fwhm)
        assert f.accept is False
        assert f.reject_reason == "qc:fwhm"
    finally:
        proj.close()
