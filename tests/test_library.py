"""
Library: shared registry across many target sub-projects.

These tests cover the things that would silently break a campaign:
  - creating / re-opening a library and finding the same targets.
  - cross-target queries (campaign totals) match the per-project truth.
  - RA/Dec lookup picks the closest registered target.
  - adopting an existing folder of projects into a fresh library.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seestack.io.library import Library, _angular_separation_deg, make_safe_name
from seestack.io.project import FrameRow, Project


_counter = [0]


def _add_frame(proj: Project, *, exposure_s: float, ra: float, dec: float,
               accept: bool = True) -> int:
    """Insert a fake frame with a guaranteed-unique source_path."""
    _counter[0] += 1
    return proj.add_frame(FrameRow(
        source_path=f"f_{_counter[0]}.fit",
        exposure_s=exposure_s,
        ra_center_deg=ra,
        dec_center_deg=dec,
        accept=accept,
    ))


def test_make_safe_name_handles_messy_input():
    assert make_safe_name("M 42") == "M_42"
    assert make_safe_name("NGC 7000 / North America") == "NGC_7000_North_America"
    # Leading/trailing punctuation stripped.
    assert make_safe_name("...M31...") == "M31"
    # Empty / non-alphanumeric input gets a fallback.
    assert make_safe_name("   ") == "target"
    # Truncated to a sensible length.
    long = make_safe_name("X" * 200)
    assert len(long) <= 64
    # Case is preserved (so "m31" and "M31" don't collide).
    assert make_safe_name("M31") != make_safe_name("m31").lower()


def test_create_open_and_list_targets(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.create_target("M 42", ra_deg=83.82, dec_deg=-5.39)
        p1.close()
        e2, p2 = lib.create_target("NGC 7000", ra_deg=314.75, dec_deg=44.32)
        p2.close()
        names = sorted(t.safe_name for t in lib.list_targets())
        assert names == ["M_42", "NGC_7000"]
        # Stored coords preserved.
        m42 = lib.find_target("M_42")
        assert m42 and abs(float(m42.ra_deg) - 83.82) < 1e-6
    finally:
        lib.close()

    # Re-opening the same library should see both targets.
    lib2 = Library.open(tmp_path / "lib")
    try:
        assert {t.safe_name for t in lib2.list_targets()} == {"M_42", "NGC_7000"}
    finally:
        lib2.close()


def test_open_or_create_is_idempotent(tmp_path):
    a = Library.open_or_create(tmp_path / "lib")
    a.close()
    b = Library.open_or_create(tmp_path / "lib")
    b.close()
    # No exception, no duplicate registry rows.


def test_refresh_target_stats_pulls_from_per_project_db(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        entry, proj = lib.create_target("M 42")
        try:
            _add_frame(proj, exposure_s=10.0, ra=83.5, dec=-5.5)
            _add_frame(proj, exposure_s=10.0, ra=83.6, dec=-5.4)
            _add_frame(proj, exposure_s=10.0, ra=83.7, dec=-5.3, accept=False)
        finally:
            proj.close()

        refreshed = lib.refresh_target_stats("M_42")
        assert refreshed is not None
        assert refreshed.n_frames == 3
        assert refreshed.n_frames_accepted == 2
        # Total exposure should sum only ACCEPTED frames.
        assert refreshed.total_exposure_s == pytest.approx(20.0, abs=0.01)
        # Median RA/Dec from accepted frames is filled in for the registry.
        assert abs(float(refreshed.ra_deg) - 83.55) < 0.01
        assert abs(float(refreshed.dec_deg) - (-5.45)) < 0.01
    finally:
        lib.close()


def test_campaign_stats_sums_across_targets(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.create_target("M 42")
        try:
            _add_frame(p1, exposure_s=30.0, ra=83.6, dec=-5.4)
            _add_frame(p1, exposure_s=30.0, ra=83.6, dec=-5.4)
        finally:
            p1.close()
        e2, p2 = lib.create_target("M 31")
        try:
            _add_frame(p2, exposure_s=20.0, ra=10.7, dec=41.27)
        finally:
            p2.close()
        lib.refresh_target_stats("M_42")
        lib.refresh_target_stats("M_31")

        stats = lib.campaign_stats()
        assert stats["n_targets"] == 2
        assert stats["n_frames_accepted"] == 3
        assert stats["total_exposure_s"] == pytest.approx(80.0, abs=0.01)
    finally:
        lib.close()


def test_find_target_within_radius_finds_closest(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.create_target("A", ra_deg=10.0, dec_deg=0.0)
        p1.close()
        e2, p2 = lib.create_target("B", ra_deg=12.0, dec_deg=0.0)
        p2.close()
        # Point at (11.5, 0) — well within 5° of both, closer to B.
        hit = lib.find_target_within(11.5, 0.0, radius_deg=5.0)
        assert hit is not None and hit.safe_name == "B"

        # Point that's outside the radius of either.
        miss = lib.find_target_within(80.0, 80.0, radius_deg=2.0)
        assert miss is None
    finally:
        lib.close()


def test_adopt_existing_projects(tmp_path):
    """A library should be able to open a folder that already contains
    bare project sub-folders and register them."""
    root = tmp_path / "lib"
    targets_dir = root / "targets"
    targets_dir.mkdir(parents=True)
    # Pre-create two projects directly under targets/ — no library yet.
    p1 = Project.create(targets_dir / "M_42", name="M 42")
    _add_frame(p1, exposure_s=15.0, ra=83.6, dec=-5.4)
    p1.close()
    p2 = Project.create(targets_dir / "M_31", name="M 31")
    _add_frame(p2, exposure_s=15.0, ra=10.7, dec=41.27)
    p2.close()

    lib = Library.open(root)  # registry created from scratch, adopting both.
    try:
        names = sorted(t.safe_name for t in lib.list_targets())
        assert names == ["M_31", "M_42"]
        m42 = lib.find_target("M_42")
        # Coordinates inferred from accepted-frame medians.
        assert m42 is not None and m42.ra_deg is not None
    finally:
        lib.close()


def test_open_or_create_target_is_idempotent(tmp_path):
    """The scanner relies on open_or_create_target: first call creates,
    later calls re-open the same project without raising."""
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.create_target("M 42")
        p1.close()
        # Second open_or_create on the same name must re-open, not raise.
        e2, p2 = lib.open_or_create_target("M 42")
        p2.close()
        assert e1.safe_name == e2.safe_name
        assert len(lib.list_targets()) == 1
        # A genuinely new name creates a new target.
        e3, p3 = lib.open_or_create_target("M 31")
        p3.close()
        assert len(lib.list_targets()) == 2
    finally:
        lib.close()


def test_merge_targets_moves_frames_and_removes_source(tmp_path):
    """Merging target B into A copies B's frames into A and deletes B."""
    lib = Library.create(tmp_path / "lib")
    try:
        ea, pa = lib.create_target("M 31 night 1")
        try:
            _add_frame(pa, exposure_s=10.0, ra=10.7, dec=41.27)
            _add_frame(pa, exposure_s=10.0, ra=10.7, dec=41.27)
        finally:
            pa.close()
        eb, pb = lib.create_target("M 31 night 2")
        try:
            _add_frame(pb, exposure_s=10.0, ra=10.8, dec=41.30)
            _add_frame(pb, exposure_s=10.0, ra=10.8, dec=41.30)
            _add_frame(pb, exposure_s=10.0, ra=10.8, dec=41.30)
        finally:
            pb.close()

        added = lib.merge_targets("M_31_night_1", ["M_31_night_2"])
        assert added == 3

        # Source target is gone from the registry and disk.
        assert lib.find_target("M_31_night_2") is None
        assert not (lib.targets_dir / "M_31_night_2").exists()

        # Destination now has all 5 frames.
        dest = lib.find_target("M_31_night_1")
        assert dest is not None and dest.n_frames == 5

        dproj = lib.open_target("M_31_night_1")
        try:
            assert dproj.count() == 5
        finally:
            dproj.close()
    finally:
        lib.close()


def test_merge_targets_unknown_destination_raises(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        with pytest.raises(FileNotFoundError):
            lib.merge_targets("does_not_exist", ["also_missing"])
    finally:
        lib.close()


def test_angular_separation_haversine_is_symmetric():
    # Sanity: known small angle.
    d = _angular_separation_deg(0.0, 0.0, 0.0, 1.0)
    assert abs(d - 1.0) < 1e-6
    # Symmetric.
    a = _angular_separation_deg(45.0, 30.0, 100.0, -20.0)
    b = _angular_separation_deg(100.0, -20.0, 45.0, 30.0)
    assert abs(a - b) < 1e-9
    # Same point = 0.
    assert _angular_separation_deg(123.4, -5.6, 123.4, -5.6) == 0.0
