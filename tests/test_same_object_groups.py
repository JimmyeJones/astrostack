"""Same-object target grouping — the detection behind the "combine these into one
deep picture" nudge. Pure, offline: clusters targets whose plate-solved centres
agree to within a tight tolerance (the Seestar writes a new folder per night, so
the same object ends up split across shallow targets)."""

from __future__ import annotations

from dataclasses import dataclass

from seestack.io.library import (
    SAME_OBJECT_TOL_DEG,
    find_same_object_target_groups,
)


@dataclass
class _T:
    """A lightweight stand-in for a registry TargetEntry — just the fields the
    grouper reads."""

    safe_name: str
    name: str
    ra_deg: float | None
    dec_deg: float | None
    n_frames_accepted: int = 0
    total_exposure_s: float = 0.0


# M 31 (Andromeda) centre; two nearby-but-distinct neighbours a beginner might
# also shoot, far enough to never fuse: M 32 ≈ 0.4°, M 110 ≈ 0.6°.
M31 = (10.685, 41.269)
M32 = (10.674, 40.865)   # ~0.40° south of M 31
M110 = (10.092, 41.685)  # ~0.55° from M 31


def _near(ra_dec, d_ra=0.0, d_dec=0.0):
    return (ra_dec[0] + d_ra, ra_dec[1] + d_dec)


def test_two_folders_of_the_same_object_group():
    # Two nights of M 31, each re-centred to within a couple of arcmin.
    targets = [
        _T("m31_n1", "M31 night 1", *M31, n_frames_accepted=120, total_exposure_s=1200.0),
        _T("m31_n2", "M31 night 2", *_near(M31, d_ra=0.01, d_dec=-0.01),
           n_frames_accepted=90, total_exposure_s=900.0),
    ]
    groups = find_same_object_target_groups(targets)
    assert len(groups) == 1
    g = groups[0]
    assert {m.safe_name for m in g.members} == {"m31_n1", "m31_n2"}
    # Deepest integration leads (the natural "merge into").
    assert g.members[0].safe_name == "m31_n1"
    assert g.max_sep_deg <= SAME_OBJECT_TOL_DEG


def test_singletons_are_excluded():
    targets = [
        _T("m31", "M31", *M31),
        _T("m42", "M42", 83.82, -5.39),   # Orion — nowhere near
    ]
    assert find_same_object_target_groups(targets) == []


def test_distinct_nearby_objects_are_not_fused():
    # M 31, M 32 and M 110 are close on the sky but genuinely different targets;
    # the tight tolerance must keep them apart.
    targets = [
        _T("m31", "M31", *M31),
        _T("m32", "M32", *M32),
        _T("m110", "M110", *M110),
    ]
    assert find_same_object_target_groups(targets) == []


def test_targets_without_a_solved_centre_are_skipped():
    targets = [
        _T("m31_n1", "M31 night 1", *M31),
        _T("m31_n2", "M31 night 2", *_near(M31, d_ra=0.01)),
        _T("unsolved", "Unknown", None, None),  # never plate-solved
    ]
    groups = find_same_object_target_groups(targets)
    assert len(groups) == 1
    assert "unsolved" not in {m.safe_name for m in groups[0].members}


def test_three_nights_form_one_group_deepest_first():
    targets = [
        _T("a", "M31 a", *M31, total_exposure_s=600.0),
        _T("b", "M31 b", *_near(M31, d_dec=0.02), total_exposure_s=1800.0),
        _T("c", "M31 c", *_near(M31, d_ra=-0.02), total_exposure_s=1200.0),
    ]
    groups = find_same_object_target_groups(targets)
    assert len(groups) == 1
    order = [m.safe_name for m in groups[0].members]
    assert order == ["b", "c", "a"]  # by total_exposure_s descending


def test_two_separate_objects_each_split_give_two_groups_biggest_first():
    m42 = (83.82, -5.39)
    targets = [
        # M 31 split across two shallow nights (small total).
        _T("m31_1", "M31 1", *M31, total_exposure_s=300.0),
        _T("m31_2", "M31 2", *_near(M31, d_ra=0.01), total_exposure_s=300.0),
        # M 42 split across two deeper nights (larger total → leads).
        _T("m42_1", "M42 1", *m42, total_exposure_s=2000.0),
        _T("m42_2", "M42 2", *_near(m42, d_dec=0.01), total_exposure_s=2000.0),
    ]
    groups = find_same_object_target_groups(targets)
    assert len(groups) == 2
    # Most-integrated group first.
    assert {m.safe_name for m in groups[0].members} == {"m42_1", "m42_2"}
    assert {m.safe_name for m in groups[1].members} == {"m31_1", "m31_2"}


def test_wrap_safe_across_ra_zero():
    # A target straddling RA=0 (359.99° vs 0.01°) is really ~0.02° apart, not ~360.
    targets = [
        _T("w1", "wrap 1", 359.99, 20.0, total_exposure_s=100.0),
        _T("w2", "wrap 2", 0.01, 20.0, total_exposure_s=100.0),
    ]
    groups = find_same_object_target_groups(targets)
    assert len(groups) == 1
    assert groups[0].max_sep_deg < SAME_OBJECT_TOL_DEG


def test_empty_input():
    assert find_same_object_target_groups([]) == []
