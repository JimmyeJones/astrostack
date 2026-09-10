"""The *position* half of the streak guardrail.

The fraction tiers in ``reconcile_streak_rejections`` can only ask "was a
majority of this target flagged?". Streak detection is a marginal Hough
decision, so a bright stationary extended object (an edge-on galaxy, an
elongated nebula) flags a **variable subset** of the subs — often 30–50 %, under
the majority tier — and those good subs are silently discarded, on by default.

What separates a tracked object from a transient is *where* the flagged feature
sits: the scope follows the target, so the object is in the same part of every
frame all night, while a satellite/plane/meteor lands somewhere different each
time and is over in minutes. These tests pin that rule, and — just as
importantly — pin that it stays quiet for real trails.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.qc.runner import (
    STATIONARY_CLUSTER_RADIUS,
    STATIONARY_MAX_CLUSTERS,
    STATIONARY_MIN_FRAMES,
    STATIONARY_MIN_SPAN_S,
    _chance_cluster_p,
    build_qc_arglist,
    reconcile_streak_rejections,
    stationary_streak_frames,
)

_T0 = datetime(2026, 3, 14, 21, 0, tzinfo=timezone.utc)


def _stamp(minutes: float) -> str:
    return (_T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


# --- the pure rule ---------------------------------------------------------

def test_one_spot_across_hours_reads_as_a_tracked_object():
    """The galaxy case: same place in the frame, spread over the session."""
    marks = [(i, 0.50 + 0.01 * i, 0.48, _stamp(45 * i)) for i in range(5)]
    assert stationary_streak_frames(marks) == [0, 1, 2, 3, 4]


def test_scattered_trails_are_not_a_cluster():
    """Real satellites land all over the frame — no verdict, so no re-accept."""
    spots = [(0.12, 0.20), (0.80, 0.31), (0.44, 0.90), (0.91, 0.72), (0.05, 0.55)]
    marks = [(i, x, y, _stamp(45 * i)) for i, (x, y) in enumerate(spots)]
    assert stationary_streak_frames(marks) == []


def test_a_burst_at_one_spot_is_not_stationary():
    """A Starlink train *does* put near-identical trails at one spot — and is
    over in minutes. The span test is what keeps it rejected; without it the
    position cluster alone would re-accept a train, which is the exact case
    whole-frame rejection exists for."""
    marks = [(i, 0.5, 0.5, _stamp(2 * i)) for i in range(6)]
    assert stationary_streak_frames(marks) == []
    # The same positions, spread over the night, *are* a tracked object.
    spread = [(i, 0.5, 0.5, _stamp(40 * i)) for i in range(6)]
    assert stationary_streak_frames(spread) == [0, 1, 2, 3, 4, 5]


def test_a_trail_among_the_object_frames_keeps_its_rejection():
    """The verdict is per frame, not per target: the object's own subs come
    back, the one genuine trail sitting elsewhere in the frame does not."""
    marks = [(i, 0.50, 0.50, _stamp(45 * i)) for i in range(5)]
    marks.append((99, 0.10, 0.90, _stamp(60)))  # a real satellite
    assert stationary_streak_frames(marks) == [0, 1, 2, 3, 4]


def test_too_few_flagged_frames_give_no_verdict():
    """Below the floor a "cluster" is a coincidence, so say nothing."""
    marks = [(i, 0.5, 0.5, _stamp(90 * i)) for i in range(STATIONARY_MIN_FRAMES - 1)]
    assert stationary_streak_frames(marks) == []


def test_undated_and_positionless_frames_are_not_evidence():
    """A frame QC'd before the positions existed (or with no timestamp) can't
    answer either test — it is skipped, never guessed at."""
    dated = [(i, 0.5, 0.5, _stamp(45 * i)) for i in range(4)]
    assert stationary_streak_frames([(i, None, None, s) for i, _, _, s in dated]) == []
    assert stationary_streak_frames([(i, x, y, None) for i, x, y, _ in dated]) == []


def test_the_cluster_centre_is_a_median_not_a_mean():
    """Two thirds of the flagged frames are the object; the rest are trails
    scattered to one side. A mean centre would be dragged off the object and
    rescue nothing — the median holds."""
    marks = [(i, 0.30, 0.30, _stamp(60 * i)) for i in range(4)]
    marks += [(10 + i, 0.95, 0.95, _stamp(60 * i)) for i in range(2)]
    assert stationary_streak_frames(marks) == [0, 1, 2, 3]


def test_the_radius_is_the_boundary_it_says_it_is():
    """A component drifting just inside the radius still counts; just outside
    it does not — pinned so the constant can't quietly stop meaning anything."""
    inside = [(i, 0.5, 0.5, _stamp(60 * i)) for i in range(4)]
    inside[3] = (3, 0.5 + STATIONARY_CLUSTER_RADIUS * 0.99, 0.5, _stamp(180))
    assert stationary_streak_frames(inside) == [0, 1, 2, 3]
    outside = list(inside)
    outside[3] = (3, 0.5 + STATIONARY_CLUSTER_RADIUS * 1.01, 0.5, _stamp(180))
    assert stationary_streak_frames(outside) == []  # only 3 left in the cluster


def test_the_span_is_the_boundary_it_says_it_is():
    """Just under the required span says nothing; just over it decides."""
    short = STATIONARY_MIN_SPAN_S / 60.0 * 0.99
    marks = [(i, 0.5, 0.5, _stamp(short * i / 3)) for i in range(4)]
    assert stationary_streak_frames(marks) == []
    long = STATIONARY_MIN_SPAN_S / 60.0 * 1.01
    marks = [(i, 0.5, 0.5, _stamp(long * i / 3)) for i in range(4)]
    assert stationary_streak_frames(marks) == [0, 1, 2, 3]


# --- end to end, through the database --------------------------------------

def _galaxy_target(tmp_path, *, n_clean: int, n_streaked: int):
    """A session where a stationary object flagged a *minority* of the subs —
    the band the fraction tiers structurally cannot see."""
    proj = Project.create(tmp_path / "p", name="NGC 4565")
    clean, streaked = [], []
    for i in range(n_clean):
        clean.append(proj.add_frame(FrameRow(
            source_path=f"clean{i}.fit", timestamp_utc=_stamp(7 * i), accept=True)))
    for i in range(n_streaked):
        streaked.append(proj.add_frame(FrameRow(
            source_path=f"streak{i}.fit", timestamp_utc=_stamp(40 * i),
            streak_detected=True, streak_count=1,
            streak_cx=0.51 + 0.005 * i, streak_cy=0.49,
            accept=False, reject_reason="auto:streak")))
    return proj, clean, streaked


def test_a_minority_flagged_galaxy_is_rescued(tmp_path):
    """**The bug.** An edge-on galaxy flagged on 6 of 16 subs (37 %) sits under
    the >50 % tier, so before this guard those six good subs stayed discarded.
    Fails before: ``reconcile_streak_rejections`` returned ``[]``."""
    proj, _clean, streaked = _galaxy_target(tmp_path, n_clean=10, n_streaked=6)
    try:
        restored = reconcile_streak_rejections(proj)
        assert set(restored) == set(streaked)
        for fid in streaked:
            f = proj.get_frame(fid)
            assert f.accept is True
            assert f.reject_reason is None
            assert f.streak_detected is True  # the UI still counts them
    finally:
        proj.close()


def test_scattered_satellites_are_still_dropped(tmp_path):
    """The other side of the same fixture: four *real* trails, spread over the
    night but landing in different corners, keep their rejection."""
    proj = Project.create(tmp_path / "p", name="M 31")
    try:
        for i in range(12):
            proj.add_frame(FrameRow(source_path=f"c{i}.fit",
                                    timestamp_utc=_stamp(7 * i), accept=True))
        spots = [(0.13, 0.22), (0.86, 0.35), (0.40, 0.92), (0.72, 0.08)]
        sats = [proj.add_frame(FrameRow(
            source_path=f"sat{i}.fit", timestamp_utc=_stamp(50 * i),
            streak_detected=True, streak_count=1, streak_cx=x, streak_cy=y,
            accept=False, reject_reason="auto:streak"))
            for i, (x, y) in enumerate(spots)]
        assert reconcile_streak_rejections(proj) == []
        for fid in sats:
            assert proj.get_frame(fid).accept is False
    finally:
        proj.close()


def test_a_user_override_is_still_untouched(tmp_path):
    """The un-reject-only contract is unchanged: a frame the user rejected by
    hand stays rejected even while the cluster around it is rescued."""
    proj, _clean, streaked = _galaxy_target(tmp_path, n_clean=10, n_streaked=6)
    try:
        held = proj.add_frame(FrameRow(
            source_path="user.fit", timestamp_utc=_stamp(30),
            streak_detected=True, streak_cx=0.51, streak_cy=0.49,
            accept=False, reject_reason="user", user_override=True))
        restored = reconcile_streak_rejections(proj)
        assert set(restored) == set(streaked)
        f = proj.get_frame(held)
        assert f.accept is False
        assert f.reject_reason == "user"
    finally:
        proj.close()


def test_the_majority_tier_still_wins_where_it_applies(tmp_path):
    """A target flagged wholesale is reconciled by the fraction guard exactly as
    before, positions or no positions — the new path is additive, not a
    replacement (these frames span 4 minutes, far under the stationary span)."""
    proj = Project.create(tmp_path / "p", name="Needle")
    try:
        ids = [proj.add_frame(FrameRow(
            source_path=f"s{i}.fit", timestamp_utc=_stamp(0.4 * i),
            streak_detected=True, accept=False, reject_reason="auto:streak"))
            for i in range(12)]
        assert set(reconcile_streak_rejections(proj)) == set(ids)
    finally:
        proj.close()


def test_frames_checked_before_positions_existed_behave_as_they_did(tmp_path):
    """Upgrade safety: an old library's rows carry no position, so the new guard
    cannot fire and the target is left exactly as this build's predecessor left
    it — rejected, awaiting the one-time re-check below."""
    proj = Project.create(tmp_path / "p", name="NGC 891")
    try:
        for i in range(10):
            proj.add_frame(FrameRow(source_path=f"c{i}.fit",
                                    timestamp_utc=_stamp(7 * i), accept=True))
        for i in range(6):
            proj.add_frame(FrameRow(
                source_path=f"s{i}.fit", timestamp_utc=_stamp(40 * i),
                streak_detected=True, accept=False, reject_reason="auto:streak"))
        assert reconcile_streak_rejections(proj) == []
    finally:
        proj.close()


def test_an_old_streak_rejection_is_re_offered_for_its_position(tmp_path):
    """...and this is how it stops waiting. ``build_qc_arglist(only_new=True)``
    skips anything already QC'd, so without a re-offer an upgraded install would
    keep discarding the very subs the new guard exists for. Only the *rejected,
    positionless* streak frames come back — never a clean sub, never a frame
    that already has its position."""
    proj = Project.create(tmp_path / "p", name="NGC 891")
    try:
        for row in (
            FrameRow(source_path=str(tmp_path / "clean.fit"),
                     star_count=120, accept=True),
            FrameRow(source_path=str(tmp_path / "old.fit"),
                     star_count=90, streak_detected=True,
                     accept=False, reject_reason="auto:streak"),
            FrameRow(source_path=str(tmp_path / "new.fit"),
                     star_count=90, streak_detected=True,
                     streak_cx=0.5, streak_cy=0.5,
                     accept=False, reject_reason="auto:streak"),
            FrameRow(source_path=str(tmp_path / "held.fit"),
                     star_count=90, streak_detected=True,
                     accept=False, reject_reason="auto:streak",
                     user_override=True),
        ):
            Path(row.source_path).write_bytes(b"x")
            proj.add_frame(row)
        offered = {p for _fid, p, _b, _s in build_qc_arglist(proj, only_new=True)}
        assert offered == {str(tmp_path / "old.fit")}
    finally:
        proj.close()


def test_a_real_qc_pass_rescues_a_fixed_feature(tmp_path):
    """End to end from pixels, not from hand-written rows: real frames through
    the real detector, the real DB write and the real reconciliation.

    Ten clean subs and six carrying the same feature at the same place, dated
    across the night — 37 %, under every fraction tier. This is what pins that
    the position actually *reaches* the database from a QC pass, which no
    fixture-level test can show."""
    from seestack.qc.runner import QCResult, apply_qc_result_to_db
    from tests.synth import write_seestar_fits

    pytest.importorskip("skimage")
    from seestack.qc.metrics import compute_frame_metrics

    proj = Project.create(tmp_path / "p", name="NGC 4565")
    try:
        streaked = []
        for i in range(16):
            has_feature = i >= 10
            path = write_seestar_fits(
                tmp_path / f"sub{i:02d}.fit", seed=100 + i, streak=has_feature)
            fid = proj.add_frame(FrameRow(
                source_path=str(path), timestamp_utc=_stamp(40 * i)))
            apply_qc_result_to_db(proj, QCResult(
                frame_id=fid, metrics=compute_frame_metrics(path), error=None))
            if has_feature:
                streaked.append(fid)

        rejected = [f.id for f in proj.iter_frames()
                    if (f.reject_reason or "") == "auto:streak"]
        assert set(rejected) == set(streaked), "the detector should flag exactly the six"
        # Every one carries a position now, and they agree on it.
        rows = [proj.get_frame(fid) for fid in streaked]
        assert all(r.streak_cx is not None and r.streak_cy is not None for r in rows)

        restored = reconcile_streak_rejections(proj)
        assert set(restored) == set(streaked)
        assert sum(1 for f in proj.iter_frames() if f.accept) == 16
    finally:
        proj.close()


# --- more than one stationary object: the mosaic case -----------------------
#
# A mosaic's panels point at different sky, so one extended object spanning the
# mosaic forms its flagged component at a *different* place in each panel's
# frames. The owner is a heavy mosaic user (AGENTS.md §1), so this is the shape
# the rule meets in practice — and a single anchor cannot see it at all.

def _panel_marks(spots, *, per_panel: int, minutes: float = 40.0):
    """``per_panel`` flagged frames at each of ``spots``, spread over the night."""
    marks, fid = [], 0
    for cx, cy in spots:
        for i in range(per_panel):
            marks.append((fid, cx, cy, _stamp(minutes * i)))
            fid += 1
    return marks


def test_two_mosaic_panels_each_with_their_own_object_are_both_rescued():
    """**The bug.** Two panels, each carrying the object at its own place in the
    frame. One anchor lands *between* the two clusters, so no frame is within the
    radius of it and the whole flagged set keeps its rejection — adding a second
    stationary object made the detector strictly worse than one.

    Fails before: ``[]`` for all sixteen, while the same eight alone are rescued.
    """
    marks = _panel_marks([(0.20, 0.80), (0.80, 0.20)], per_panel=8)
    assert stationary_streak_frames(marks) == list(range(16))
    # The half that already worked still works, unchanged.
    assert stationary_streak_frames(marks[:8]) == list(range(8))


def test_a_four_panel_mosaic_rescues_every_panel():
    """A 2×2 of an elongated nebula: four clusters, none of them a majority of
    the flagged set, all four tracked objects."""
    spots = [(0.25, 0.25), (0.25, 0.75), (0.75, 0.25), (0.75, 0.75)]
    marks = _panel_marks(spots, per_panel=6)
    assert stationary_streak_frames(marks) == list(range(24))


def test_a_trail_among_several_clusters_still_keeps_its_rejection():
    """The per-frame contract survives the multi-cluster search: the panels come
    back, the satellite that landed between them does not."""
    marks = _panel_marks([(0.20, 0.80), (0.80, 0.20)], per_panel=6)
    marks.append((99, 0.50, 0.50, _stamp(70)))  # a real trail, on neither object
    assert stationary_streak_frames(marks) == list(range(12))


def test_the_cluster_count_is_capped_but_takes_the_biggest_first():
    """The rounds are bounded (:data:`STATIONARY_MAX_CLUSTERS`) so the search can
    never walk a huge flagged set cluster by cluster. Past the cap the *largest*
    clusters are the ones kept, so the bound can only drop the least
    significant."""
    spots = [(0.06 + 0.06 * i, 0.5 if i % 2 else 0.1) for i in range(STATIONARY_MAX_CLUSTERS + 3)]
    # Give the first clusters more frames, so "largest first" is observable.
    marks, fid = [], 0
    sizes = []
    for n, (cx, cy) in enumerate(spots):
        size = 30 - n
        sizes.append(size)
        for i in range(size):
            marks.append((fid, cx, cy, _stamp(40 * i)))
            fid += 1
    got = set(stationary_streak_frames(marks))
    # Exactly the first STATIONARY_MAX_CLUSTERS clusters (the biggest) come back.
    kept = sum(sizes[:STATIONARY_MAX_CLUSTERS])
    assert len(got) == kept
    assert got == set(range(kept))


# --- the price of searching: a coincidence is not an object -----------------

def test_a_chance_cluster_among_scattered_trails_decides_nothing():
    """Searching every candidate centre asks "is anything clustered here?" once
    per flagged frame, and enough tries turn the radius's own coincidence budget
    into an event. Twenty real trails, scattered over a night, must still decide
    nothing however luckily four of them fall together.

    This is a *statistical* claim, so it is asserted over many independent
    scatters rather than one lucky seed.
    """
    rng = random.Random(20260910)
    verdicts = 0
    for _ in range(200):
        marks = [(i, rng.random(), rng.random(), _stamp(7 * i)) for i in range(20)]
        if stationary_streak_frames(marks):
            verdicts += 1
    assert verdicts == 0, f"{verdicts}/200 scatters were called tracked objects"


def test_the_chance_score_pays_for_every_centre_the_search_tries():
    """The rule the guard above rests on: a cluster of a given size gets *less*
    surprising as the flagged set it was found in grows, because a bigger set
    both crowds the frame and offers more places to look. Pinned so the
    correction can't quietly be dropped."""
    assert _chance_cluster_p(4, 6) < _chance_cluster_p(4, 20) < _chance_cluster_p(4, 60)
    # A bigger cluster in the same set is rarer than a smaller one.
    assert _chance_cluster_p(8, 40) < _chance_cluster_p(5, 40)
    # Degenerate inputs are "no information", never a licence to re-accept.
    assert _chance_cluster_p(1, 50) == 1.0
    assert _chance_cluster_p(4, 1) == 1.0


def test_a_real_mosaic_sized_object_is_not_blocked_by_the_chance_test(tmp_path):
    """The other side of that guard: the owner's mosaics carry hundreds of subs
    per panel, so a genuine panel-sized cluster must sail through it."""
    marks = _panel_marks([(0.30, 0.30), (0.70, 0.70)], per_panel=60, minutes=3.0)
    assert len(stationary_streak_frames(marks)) == 120


def test_two_panel_mosaic_rescue_end_to_end(tmp_path):
    """Through the database, on the population the fraction tiers cannot see:
    two panels' worth of flagged subs (24 of 60 frames, 40 %) come back, and the
    clean frames are untouched."""
    proj = Project.create(tmp_path / "p", name="Veil (mosaic)")
    try:
        for i in range(36):
            proj.add_frame(FrameRow(source_path=f"clean{i}.fit",
                                    timestamp_utc=_stamp(5 * i), accept=True))
        streaked = []
        for panel, (cx, cy) in enumerate([(0.22, 0.78), (0.78, 0.22)]):
            for i in range(12):
                streaked.append(proj.add_frame(FrameRow(
                    source_path=f"p{panel}_{i}.fit", timestamp_utc=_stamp(20 * i + panel),
                    streak_detected=True, streak_count=1,
                    streak_cx=cx + 0.004 * i, streak_cy=cy,
                    accept=False, reject_reason="auto:streak")))
        restored = reconcile_streak_rejections(proj)
        assert set(restored) == set(streaked)
        assert sum(1 for f in proj.iter_frames() if f.accept) == 60
        for fid in streaked:
            f = proj.get_frame(fid)
            assert f.reject_reason is None
            assert f.streak_detected is True  # still counted in the UI
    finally:
        proj.close()
