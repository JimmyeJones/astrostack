"""
Folder scanner: organise a tree of Seestar sub-folders into library targets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.library import Library
from seestack.io.project import Project
from seestack.io.scanner import run_qc_and_solve, scan_and_organize
from tests.synth import write_seestar_fits


def _seestar_tree(root: Path) -> Path:
    """
    Build a fake Seestar dump:

      root/
        M 42/Light_001.fit, Light_002.fit
        Andromeda/sub/Light_001.fit         (nested — mosaic-style)
        Empty/                              (no FITS — ignored)
        loose_a.fit, loose_b.fit            (loose in root → Unsorted)
    """
    root.mkdir(parents=True, exist_ok=True)
    m42 = root / "M 42"
    m42.mkdir()
    write_seestar_fits(m42 / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(m42 / "Light_002.fit", n_stars=5, seed=2)

    andromeda_sub = root / "Andromeda" / "sub"
    andromeda_sub.mkdir(parents=True)
    write_seestar_fits(andromeda_sub / "Light_001.fit", n_stars=5, seed=3)

    (root / "Empty").mkdir()

    write_seestar_fits(root / "loose_a.fit", n_stars=5, seed=4)
    write_seestar_fits(root / "loose_b.fit", n_stars=5, seed=5)
    return root


def test_scan_organizes_folders_into_targets(tmp_path):
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        names = {t.safe_name for t in result.targets}
        # One target per sub-folder with FITS, plus Unsorted for loose files.
        # The empty folder produces no target.
        assert names == {"M_42", "Andromeda", "Unsorted"}

        by_name = {t.safe_name: t for t in result.targets}
        assert by_name["M_42"].n_frames_added == 2
        # Nested files inside a sub-folder still belong to that one target.
        assert by_name["Andromeda"].n_frames_added == 1
        assert by_name["Unsorted"].n_frames_added == 2
        assert result.total_added == 5

        # Registry reflects it.
        assert {t.safe_name for t in lib.list_targets()} == {
            "M_42", "Andromeda", "Unsorted",
        }
        m42 = lib.find_target("M_42")
        assert m42 is not None and m42.n_frames == 2
    finally:
        lib.close()


def test_scan_is_idempotent(tmp_path):
    """Re-scanning the same tree adds nothing the second time."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        first = scan_and_organize(lib, scan_root)
        assert first.total_added == 5

        second = scan_and_organize(lib, scan_root)
        assert second.total_added == 0
        # Everything is now "skipped existing".
        assert sum(t.n_skipped_existing for t in second.targets) == 5
        # Still exactly three targets — no duplicates created.
        assert len(lib.list_targets()) == 3
    finally:
        lib.close()


def test_scan_picks_up_new_frames_on_rescan(tmp_path):
    """Adding a night to an existing folder and re-scanning ingests just
    the new frames into the existing target."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        # New frame dropped into the existing M 42 folder.
        write_seestar_fits(scan_root / "M 42" / "Light_003.fit", n_stars=5, seed=9)
        result = scan_and_organize(lib, scan_root)
        m42 = next(t for t in result.targets if t.safe_name == "M_42")
        assert m42.n_frames_added == 1
        assert lib.find_target("M_42").n_frames == 3
    finally:
        lib.close()


def test_scan_counts_a_cache_refresh_as_refreshed_not_added(tmp_path):
    """A mid-copy-truncated sub whose source later completes is refreshed (not
    re-added) on re-scan, so the scanner reports it under n_frames_refreshed —
    which the pipeline uses to re-QC the target even with no new frames."""
    scan_root = tmp_path / "seestar"
    (scan_root / "M 42").mkdir(parents=True)
    full = write_seestar_fits(scan_root / "M 42" / "Light_001.fit", n_stars=5, seed=1)
    full_bytes = full.read_bytes()
    full.write_bytes(full_bytes[: len(full_bytes) // 2])  # simulate still-copying

    lib = Library.create(tmp_path / "lib")
    try:
        # copy_to_cache=True so the truncated bytes land in the Stage-1 cache.
        first = scan_and_organize(lib, scan_root, copy_to_cache=True)
        m42_first = next(t for t in first.targets if t.safe_name == "M_42")
        assert m42_first.n_frames_added == 1 and m42_first.n_frames_refreshed == 0

        full.write_bytes(full_bytes)  # the copy finishes
        second = scan_and_organize(lib, scan_root, copy_to_cache=True)
        m42 = next(t for t in second.targets if t.safe_name == "M_42")
        assert m42.n_frames_added == 0        # nothing new
        assert m42.n_frames_refreshed == 1    # but the cache was refreshed
        # The refreshed frame's id is surfaced so the pipeline can drop its
        # now-stale cached previews (which key on id alone).
        assert len(m42.refreshed_frame_ids) == 1
        proj = lib.open_target("M_42")
        try:
            assert m42.refreshed_frame_ids[0] == next(iter(proj.iter_frames())).id
        finally:
            proj.close()
    finally:
        lib.close()


def test_scan_counts_a_still_copying_empty_sub_as_skip_not_error(tmp_path):
    """A 0-byte (still-copying / stalled-transfer) sub is a benign skip that will
    be retried once it has bytes — not a failure. It must land in the scan's
    n_skipped tally, never inflate the scary n_errors count a beginner sees."""
    scan_root = tmp_path / "seestar"
    (scan_root / "M 42").mkdir(parents=True)
    write_seestar_fits(scan_root / "M 42" / "Light_001.fit", n_stars=5, seed=1)
    (scan_root / "M 42" / "Light_002.fit").write_bytes(b"")  # still copying

    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        m42 = next(t for t in result.targets if t.safe_name == "M_42")
        assert m42.n_frames_added == 1          # the complete sub ingested
        assert m42.n_errors == 0                # the empty one is NOT an error...
        assert m42.n_skipped_existing == 1      # ...it is a skip (retried next scan)
    finally:
        lib.close()


def test_scan_empty_root_produces_no_targets(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, empty)
        assert result.n_targets == 0
        assert lib.list_targets() == []
    finally:
        lib.close()


def test_scan_missing_root_raises(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        with pytest.raises(NotADirectoryError):
            scan_and_organize(lib, tmp_path / "does_not_exist")
    finally:
        lib.close()


def test_scan_progress_callback_fires(tmp_path):
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    calls: list[tuple[str, int, int]] = []
    try:
        scan_and_organize(lib, scan_root, progress=lambda *a: calls.append(a))
        assert calls, "progress callback never fired"
        assert all(phase == "Organizing" for phase, _d, _t in calls)
        # Final call reports done == total.
        assert calls[-1][1] == calls[-1][2]
    finally:
        lib.close()


def test_run_qc_serial_populates_metrics(tmp_path):
    """run_qc_and_solve(serial=True, run_solve=False) fills QC metrics for
    every frame without needing ASTAP."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        proj = lib.open_target("M_42")
        try:
            calls: list[tuple] = []
            summary = run_qc_and_solve(
                proj, run_qc=True, run_solve=False, serial=True,
                progress=lambda *a: calls.append(a),
            )
            assert summary["qc_total"] == 2
            assert summary["qc_done"] == 2
            # Every frame now has a star_count metric written.
            for f in proj.iter_frames():
                assert f.star_count is not None
            # Progress reported under the "QC" phase.
            assert calls and all(c[0] == "QC" for c in calls)
        finally:
            proj.close()
    finally:
        lib.close()


def test_run_qc_and_solve_honours_should_stop(tmp_path):
    """A should_stop that returns True immediately means no QC work runs."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        proj = lib.open_target("M_42")
        try:
            summary = run_qc_and_solve(
                proj, run_qc=True, run_solve=False, serial=True,
                should_stop=lambda: True,
            )
            assert summary["qc_done"] == 0
        finally:
            proj.close()
    finally:
        lib.close()
