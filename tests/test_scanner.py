"""
Folder scanner: organise a tree of Seestar sub-folders into library targets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.library import Library
from seestack.io.project import REJECT_REASON_SEESTAR_OUTPUT, FrameRow, Project
from seestack.io.scanner import (
    _apply_seestar_convention,
    _seestar_output_bases,
    run_qc_and_solve,
    scan_and_organize,
)
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


def _fake(*names: str) -> list:
    """Build ``[(name, [Path]), ...]`` units for the pure-classifier test."""
    return [(n, [Path(f"{n}/x.fit")]) for n in names]


def test_apply_seestar_convention_maps_sub_and_skips_output_and_video():
    """The pure folder-classifier: raw '_sub' folders become targets, the
    Seestar's own output sibling and any '*_video' folder are skipped, and a
    mosaic gets its own '(mosaic)' target distinct from the single field."""
    units = _apply_seestar_convention(_fake(
        "M 31_sub", "M 31",                 # raw subs + on-device output
        "M 3_mosaic_sub", "M 3_mosaic",     # mosaic raw subs + mosaic output
        "M 3",                              # single-field output, but no _sub
        "Lunar_video", "Solar_video",       # videos
    ))
    names = [n for n, _ in units]
    # "M 31_sub" -> "M 31"; its bare "M 31" output is skipped.
    # "M 3_mosaic_sub" -> "M 3 (mosaic)"; its "M 3_mosaic" output is skipped.
    # bare "M 3" (no "M 3_sub" sibling) still ingests. Videos are gone.
    assert names == ["M 31", "M 3 (mosaic)", "M 3"]


def test_apply_seestar_convention_bare_folder_without_sub_sibling_kept():
    """A plainly-named folder with no '_sub' sibling is a non-Seestar layout
    and must still ingest exactly as before (no regression)."""
    units = _apply_seestar_convention(_fake("Andromeda", "M 42"))
    assert [n for n, _ in units] == ["Andromeda", "M 42"]


def test_apply_seestar_convention_is_case_insensitive():
    """Folder casing varies across firmware; suffix tests ignore case but the
    target name keeps the folder's original casing."""
    units = _apply_seestar_convention(_fake("Ngc 7000_SUB", "Ngc 7000", "Clip_VIDEO"))
    assert [n for n, _ in units] == ["Ngc 7000"]


def test_scan_is_seestar_aware_end_to_end(tmp_path):
    """A realistic Seestar dump produces exactly the two real targets — one
    single-field, one mosaic — with the raw subs, and NO junk target from the
    on-device output or video folders."""
    scan_root = tmp_path / "incoming"
    (scan_root / "M 3_sub").mkdir(parents=True)
    write_seestar_fits(scan_root / "M 3_sub" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(scan_root / "M 3_sub" / "Light_002.fit", n_stars=5, seed=2)
    write_seestar_fits(scan_root / "M 3_sub" / "Light_003.fit", n_stars=5, seed=3)
    # The Seestar's own single stacked output for M 3 (must be ignored).
    (scan_root / "M 3").mkdir()
    write_seestar_fits(scan_root / "M 3" / "Stacked.fit", n_stars=5, seed=10)
    # A mosaic of the same object — its raw subs + its own output.
    (scan_root / "M 3_mosaic_sub").mkdir()
    write_seestar_fits(scan_root / "M 3_mosaic_sub" / "Light_001.fit", n_stars=5, seed=4)
    write_seestar_fits(scan_root / "M 3_mosaic_sub" / "Light_002.fit", n_stars=5, seed=5)
    (scan_root / "M 3_mosaic").mkdir()
    write_seestar_fits(scan_root / "M 3_mosaic" / "Stacked.fit", n_stars=5, seed=11)
    # A video capture (must be ignored).
    (scan_root / "Lunar_video").mkdir()
    write_seestar_fits(scan_root / "Lunar_video" / "clip_001.fit", n_stars=5, seed=6)

    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        by_name = {t.target_name: t for t in result.targets}
        # Exactly two real targets, kept distinct (mosaic never merged in).
        assert set(by_name) == {"M 3", "M 3 (mosaic)"}
        assert by_name["M 3"].n_frames_added == 3           # the raw subs, not the 1 output
        assert by_name["M 3 (mosaic)"].n_frames_added == 2
        # No bogus output/video targets in the registry.
        assert {t.name for t in lib.list_targets()} == {"M 3", "M 3 (mosaic)"}
    finally:
        lib.close()


def test_seestar_output_bases_maps_single_field_sub_only():
    """``_sub`` single-field folders yield a bare-output base to reject; mosaic
    ``_mosaic_sub`` and plain non-Seestar folders yield nothing."""
    bases = _seestar_output_bases(_fake("M 31_sub", "M 31", "M 3_mosaic_sub", "Andromeda"))
    assert bases == {"M 31": "M 31"}


def test_reject_seestar_output_frames_rejects_output_and_video_not_subs(tmp_path):
    """The Project helper additively rejects frames whose source lives in the
    bare ``<T>/`` output folder or any ``*_video`` folder, leaves the raw ``_sub``
    frames accepted, and never touches a user-overridden accept."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        root = tmp_path / "incoming"
        sub_a = proj.add_frame(FrameRow(source_path=str(root / "M 31_sub" / "Light_001.fit")))
        sub_b = proj.add_frame(FrameRow(source_path=str(root / "M 31_sub" / "Light_002.fit")))
        out = proj.add_frame(FrameRow(source_path=str(root / "M 31" / "Stacked_60s.fit")))
        vid = proj.add_frame(FrameRow(source_path=str(root / "M 31_video" / "clip.fit")))
        # A frame the user manually accepted must survive even if it looks like output.
        kept = proj.add_frame(FrameRow(
            source_path=str(root / "M 31" / "Stacked_keep.fit"), user_override=True))

        rejected = proj.reject_seestar_output_frames("M 31")
        assert set(rejected) == {out, vid}
        assert proj.get_frame(out).accept is False
        assert proj.get_frame(out).reject_reason == REJECT_REASON_SEESTAR_OUTPUT
        assert proj.get_frame(vid).accept is False
        assert proj.get_frame(sub_a).accept is True and proj.get_frame(sub_b).accept is True
        assert proj.get_frame(kept).accept is True  # user override preserved

        # Idempotent: a second call rejects nothing more.
        assert proj.reject_seestar_output_frames("M 31") == []
    finally:
        proj.close()


def test_rescan_rejects_pre_v0_184_9_output_pollution_end_to_end(tmp_path):
    """Upgrade path: a library first scanned before the Seestar convention
    shipped merged the on-device output into the ``<T>`` target. Re-scanning with
    the fixed scanner ingests the raw ``<T>_sub`` subs and additively rejects that
    output frame so it leaves the stack/reference pool (regression for the ⭐⭐
    upgrade-path pollution bug)."""
    scan_root = tmp_path / "incoming"
    (scan_root / "M 31_sub").mkdir(parents=True)
    write_seestar_fits(scan_root / "M 31_sub" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(scan_root / "M 31_sub" / "Light_002.fit", n_stars=5, seed=2)
    write_seestar_fits(scan_root / "M 31_sub" / "Light_003.fit", n_stars=5, seed=3)
    # The Seestar's own on-device output, sitting in the bare "M 31/" folder.
    (scan_root / "M 31").mkdir()
    output_file = write_seestar_fits(scan_root / "M 31" / "Stacked_60s.fit", n_stars=5, seed=10)

    lib = Library.create(tmp_path / "lib")
    try:
        # Seed the pre-fix polluted state: the OLD scanner made "M 31" a target
        # and ingested the on-device output frame into it as if it were a sub.
        entry, proj = lib.open_or_create_target("M 31")
        try:
            proj.add_frame(FrameRow(source_path=str(output_file)))
        finally:
            proj.close()

        result = scan_and_organize(lib, scan_root)
        m31 = next(t for t in result.targets if t.safe_name == "M_31")
        assert m31.n_frames_added == 3               # the three raw subs
        assert m31.n_output_frames_rejected == 1     # the on-device output

        proj = lib.open_target("M_31")
        try:
            frames = list(proj.iter_frames())
            assert len(frames) == 4                  # 3 subs + 1 seeded output
            accepted = [f for f in proj.iter_frames(accepted_only=True)]
            assert len(accepted) == 3                # output no longer in the pool
            out = next(f for f in frames if f.source_path == str(output_file))
            assert out.accept is False
            assert out.reject_reason == REJECT_REASON_SEESTAR_OUTPUT
        finally:
            proj.close()
    finally:
        lib.close()


def test_scan_expands_a_whole_device_container_drop(tmp_path):
    """A whole Seestar share/card copied in with its container level intact
    (incoming/MyWorks/{...}) must expand into the real per-target folders, not
    lump every object + output + video into one giant 'MyWorks' target
    (regression for the whole-device-drop bug)."""
    scan_root = tmp_path / "incoming"
    works = scan_root / "MyWorks"
    (works / "M 31_sub").mkdir(parents=True)
    write_seestar_fits(works / "M 31_sub" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(works / "M 31_sub" / "Light_002.fit", n_stars=5, seed=2)
    (works / "M 31").mkdir()  # on-device output for M 31 — must be skipped
    write_seestar_fits(works / "M 31" / "Stacked.fit", n_stars=5, seed=10)
    (works / "NGC 7000_mosaic_sub").mkdir()
    write_seestar_fits(works / "NGC 7000_mosaic_sub" / "Light_001.fit", n_stars=5, seed=3)
    write_seestar_fits(works / "NGC 7000_mosaic_sub" / "Light_002.fit", n_stars=5, seed=4)
    (works / "Lunar_video").mkdir()  # video — must be skipped
    write_seestar_fits(works / "Lunar_video" / "clip.fit", n_stars=5, seed=6)

    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        by_name = {t.target_name: t for t in result.targets}
        assert set(by_name) == {"M 31", "NGC 7000 (mosaic)"}   # no "MyWorks"
        assert by_name["M 31"].n_frames_added == 2             # subs, not the output
        assert by_name["NGC 7000 (mosaic)"].n_frames_added == 2
        assert {t.name for t in lib.list_targets()} == {"M 31", "NGC 7000 (mosaic)"}
    finally:
        lib.close()


def test_scan_keeps_a_plain_nested_non_seestar_folder_as_one_target(tmp_path):
    """A plainly-nested non-Seestar folder (children share no '_sub' convention
    name) must still ingest as ONE target — the container expansion must not
    fire for it (no regression for the Andromeda/sub layout)."""
    scan_root = tmp_path / "incoming"
    proj = scan_root / "MyProject"
    (proj / "night1").mkdir(parents=True)
    (proj / "night2").mkdir()
    write_seestar_fits(proj / "night1" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(proj / "night2" / "Light_002.fit", n_stars=5, seed=2)

    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        by_name = {t.target_name: t for t in result.targets}
        assert set(by_name) == {"MyProject"}       # one target, both nights folded in
        assert by_name["MyProject"].n_frames_added == 2
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
