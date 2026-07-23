"""Ingest pipeline — find files, copy to cache, register in DB."""

from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.core.cache import CacheManager  # noqa: E402
from seestack.io.ingest import find_fits_files, ingest_files  # noqa: E402
from seestack.io.project import Project  # noqa: E402
from tests.synth import write_seestar_fits  # noqa: E402


def test_find_fits_files(tmp_path):
    src = tmp_path / "raws"
    src.mkdir()
    write_seestar_fits(src / "a.fit")
    write_seestar_fits(src / "b.fits")
    (src / "ignore.txt").write_text("hi")
    sub = src / "sub"
    sub.mkdir()
    write_seestar_fits(sub / "c.fit")

    files = find_fits_files(src)
    names = sorted(p.name for p in files)
    assert names == ["a.fit", "b.fits", "c.fit"]

    # non-recursive
    flat = find_fits_files(src, recursive=False)
    assert sorted(p.name for p in flat) == ["a.fit", "b.fits"]


def test_ingest_skips_zero_byte_files(tmp_path):
    src = tmp_path / "raws"
    src.mkdir()
    good = write_seestar_fits(src / "good.fit", seed=1)
    (src / "empty.fit").write_bytes(b"")  # half-finished/stalled NAS copy

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        results = {r.source_path.name: r for r in ingest_files(proj, cache, find_fits_files(src))}
        registered = [f.source_path for f in proj.iter_frames()]
    finally:
        proj.close()

    assert results["empty.fit"].skipped is True
    assert results["empty.fit"].frame_id is None
    assert results["good.fit"].frame_id is not None
    assert str(good) in registered and str(src / "empty.fit") not in registered


def test_ingest_registers_and_caches(tmp_path):
    src = tmp_path / "raws"
    src.mkdir()
    paths = [write_seestar_fits(src / f"frame_{i}.fit", seed=i) for i in range(3)]

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        results = list(ingest_files(proj, cache, paths))
    finally:
        proj.close()

    assert len(results) == 3
    assert all(r.frame_id is not None for r in results)
    assert all(r.cached_path is not None and r.cached_path.exists() for r in results)

    proj2 = Project.open(tmp_path / "proj")
    try:
        rows = list(proj2.iter_frames())
        assert len(rows) == 3
        for row in rows:
            assert row.bayer_pattern == "RGGB"
            assert row.exposure_s == 10.0
            assert row.cached_path is not None
            assert row.width_px == 480
    finally:
        proj2.close()


def test_ingest_retries_cache_after_a_transient_copy_failure(tmp_path, monkeypatch):
    """A copy error must not leave a frame permanently uncached (a re-scan
    retries the copy instead of skipping the already-registered row forever)."""
    import seestack.io.ingest as ingest_mod

    p = write_seestar_fits(tmp_path / "a.fit", seed=7)
    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        # First scan: the copy fails (a NAS blip). The frame is still registered
        # (downstream falls back to source_path) but is left uncached.
        def boom(src, dst, **kw):
            raise OSError("NAS blip")

        monkeypatch.setattr(ingest_mod.shutil, "copy2", boom)
        first = list(ingest_files(proj, cache, [p]))
        assert len(first) == 1
        assert first[0].frame_id is not None
        assert first[0].cached_path is None
        assert next(iter(proj.iter_frames())).cached_path is None

        # Second scan: the transient error is gone. The already-registered row is
        # skipped, but its Stage-1 copy is retried and now succeeds.
        monkeypatch.undo()
        second = list(ingest_files(proj, cache, [p]))
        assert len(second) == 1
        assert second[0].skipped is True
        assert second[0].cached_path is not None and second[0].cached_path.exists()
        assert proj.count() == 1  # no duplicate row
        assert next(iter(proj.iter_frames())).cached_path is not None
    finally:
        proj.close()


def test_ingest_does_not_recopy_an_already_cached_frame(tmp_path, monkeypatch):
    """A normal re-scan of an already-cached frame must not touch the cache."""
    import seestack.io.ingest as ingest_mod

    p = write_seestar_fits(tmp_path / "a.fit", seed=8)
    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        list(ingest_files(proj, cache, [p]))

        def fail_if_called(src, dst, **kw):
            raise AssertionError("must not re-copy an already-cached frame")

        monkeypatch.setattr(ingest_mod.shutil, "copy2", fail_if_called)
        results = list(ingest_files(proj, cache, [p]))
        assert results[0].skipped is True
        assert results[0].cached_path is None  # already cached → no fresh copy
    finally:
        proj.close()


def test_ingest_refreshes_cache_when_source_grew_after_a_mid_copy_ingest(tmp_path):
    """A frame swept in while its source was still being copied leaves a truncated
    Stage-1 cache; once the source finishes copying, a re-scan must refresh the
    cache so the *complete* frame — not the truncated one — flows into QC/stack.

    Regression: a plain dedup-skip only retried the copy when ``cached_path`` was
    NULL, so a truncated-but-cached frame was never refreshed even after the
    source grew to full size (partial sub silently persisting into the stack)."""
    src = tmp_path / "raws"
    src.mkdir()
    full = write_seestar_fits(src / "a.fit", seed=9)
    full_bytes = full.read_bytes()

    # Simulate the first scan seeing a still-mid-copy (truncated) source.
    truncated = full_bytes[: len(full_bytes) // 2]
    full.write_bytes(truncated)

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        first = list(ingest_files(proj, cache, [full]))
        assert first[0].frame_id is not None
        cached = first[0].cached_path
        assert cached is not None and cached.stat().st_size == len(truncated)

        # Simulate QC having run on the truncated cache: stale metrics get stored.
        frame_id = first[0].frame_id
        proj.update_frame(frame_id, star_count=42, fwhm_px=9.9,
                          accept=False, reject_reason="auto:grade:fwhm_px")

        # The source copy finishes: the file grows to its full size.
        full.write_bytes(full_bytes)

        # A re-scan dedup-skips the registered row but must refresh the cache.
        second = list(ingest_files(proj, cache, [full]))
        assert second[0].skipped is True
        assert second[0].refreshed is True  # flagged so the caller re-QCs the target
        refreshed = second[0].cached_path
        assert refreshed is not None and refreshed.exists()
        assert refreshed.read_bytes() == full_bytes  # cache now matches the source
        assert proj.count() == 1  # no duplicate row
        row = next(iter(proj.iter_frames()))
        assert row.cached_path == str(refreshed)
        # The QC computed on the truncated data was reset, so the complete frame is
        # re-graded (star_count NULL → build_qc_arglist(only_new=True) re-offers it),
        # and the stale auto-reject is cleared.
        assert row.star_count is None and row.fwhm_px is None
        assert row.accept is True and row.reject_reason is None
    finally:
        proj.close()


def test_ingest_refresh_clears_stale_solution_and_reads_new_header(tmp_path):
    """A source path overwritten in place with a *different* capture (size
    differs) must re-solve and re-metadata from scratch, not inherit the old
    frame's WCS/header.

    Regression: the refresh branch only reset QC metrics, so the stale plate
    solution (``wcs_json`` + centre coords) survived and was reprojected onto
    the new pixels — the frame stacked at the wrong sky position, silently — and
    the old header (timestamp/exposure/gain/dimensions) was kept too."""
    src = tmp_path / "raws"
    src.mkdir()
    # First capture: a 480-wide frame that gets a plate solution.
    write_seestar_fits(src / "a.fit", seed=3, width=480, height=320)
    frame_file = src / "a.fit"

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        first = list(ingest_files(proj, cache, [frame_file]))
        frame_id = first[0].frame_id
        assert frame_id is not None
        row = proj.get_frame(frame_id)
        assert row.width_px == 480

        # Simulate the frame having been plate-solved at some sky position.
        proj.update_frame(
            frame_id,
            wcs_json='{"CRVAL1": 10.0}', ra_center_deg=10.0, dec_center_deg=20.0,
            pixscale_arcsec=5.0, rotation_deg=1.0,
        )

        # The source path is reused for a *different* capture (a re-export /
        # rename collision, or a NAS sync reusing filenames). Different width →
        # different file size → the refresh branch fires.
        write_seestar_fits(frame_file, seed=99, width=640, height=320)

        second = list(ingest_files(proj, cache, [frame_file]))
        assert second[0].skipped is True
        assert second[0].refreshed is True
        assert proj.count() == 1  # still one row, no duplicate

        row = proj.get_frame(frame_id)
        # Stale plate solution dropped → re-offered to plate-solving.
        assert row.wcs_json is None
        assert row.ra_center_deg is None and row.dec_center_deg is None
        assert row.pixscale_arcsec is None and row.rotation_deg is None
        # Header re-read from the new content (proves it wasn't left stale).
        assert row.width_px == 640
    finally:
        proj.close()


def test_ingest_content_swap_clears_solution_without_cache(tmp_path):
    """A source overwritten in place with a *different* capture must drop its
    stale plate solution and re-read its header even with ``copy_to_cache=False``
    (the webapp default), where there is no cached copy to diff against.

    Regression: the whole staleness-recovery block was gated behind
    ``copy_to_cache``, so on a default install the frame kept its old WCS and
    stacked at the wrong sky position, silently. The stored source fingerprint
    (size+mtime) now detects the swap cache-independently."""
    src = tmp_path / "raws"
    src.mkdir()
    frame_file = src / "a.fit"
    write_seestar_fits(frame_file, seed=3, width=480, height=320)

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        first = list(ingest_files(proj, cache, [frame_file], copy_to_cache=False))
        frame_id = first[0].frame_id
        assert frame_id is not None
        # No cache was made (copy_to_cache off), but the fingerprint was recorded.
        row = proj.get_frame(frame_id)
        assert row.cached_path is None
        assert row.source_size_bytes is not None and row.source_mtime is not None

        # Frame gets plate-solved at some sky position.
        proj.update_frame(
            frame_id,
            wcs_json='{"CRVAL1": 10.0}', ra_center_deg=10.0, dec_center_deg=20.0,
            pixscale_arcsec=5.0, rotation_deg=1.0,
        )

        # The source path is reused for a different capture (different width →
        # different size), while still in no-cache mode.
        write_seestar_fits(frame_file, seed=99, width=640, height=320)

        second = list(ingest_files(proj, cache, [frame_file], copy_to_cache=False))
        assert second[0].skipped is True
        assert second[0].refreshed is True  # fail-before: stayed False in no-cache mode
        assert second[0].refreshed_frame_id == frame_id  # so caller can drop previews
        assert proj.count() == 1

        row = proj.get_frame(frame_id)
        # Stale solution dropped → re-offered to plate-solving (fail-before: kept).
        assert row.wcs_json is None
        assert row.ra_center_deg is None and row.dec_center_deg is None
        assert row.pixscale_arcsec is None and row.rotation_deg is None
        # Header re-read from the new content.
        assert row.width_px == 640
        # Fingerprint advanced to the new content.
        assert row.source_size_bytes is not None
    finally:
        proj.close()


def test_ingest_no_cache_unchanged_rescan_keeps_solution(tmp_path):
    """An unchanged re-scan in no-cache mode must NOT drop the plate solution —
    the fingerprint matches, so there is no false-positive re-solve."""
    src = tmp_path / "raws"
    src.mkdir()
    frame_file = src / "a.fit"
    write_seestar_fits(frame_file, seed=7)

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        first = list(ingest_files(proj, cache, [frame_file], copy_to_cache=False))
        frame_id = first[0].frame_id
        proj.update_frame(frame_id, wcs_json='{"CRVAL1": 1.0}', ra_center_deg=1.0,
                          star_count=150)

        second = list(ingest_files(proj, cache, [frame_file], copy_to_cache=False))
        assert second[0].skipped is True
        assert second[0].refreshed is False
        row = proj.get_frame(frame_id)
        assert row.wcs_json == '{"CRVAL1": 1.0}'  # solution untouched
        assert row.star_count == 150
    finally:
        proj.close()


def test_ingest_pre_fingerprint_frame_backfills_without_resolve(tmp_path):
    """A frame ingested before the fingerprint column existed (stored NULL) is
    backfilled on its next re-scan *without* dropping its solution — so an
    in-place upgrade does not needlessly re-solve the whole library."""
    src = tmp_path / "raws"
    src.mkdir()
    frame_file = src / "a.fit"
    write_seestar_fits(frame_file, seed=5)

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        first = list(ingest_files(proj, cache, [frame_file], copy_to_cache=False))
        frame_id = first[0].frame_id
        # Simulate a pre-fingerprint (upgraded) row: NULL fingerprint + a solution.
        proj.update_frame(frame_id, source_size_bytes=None, source_mtime=None,
                          wcs_json='{"CRVAL1": 2.0}', ra_center_deg=2.0)

        second = list(ingest_files(proj, cache, [frame_file], copy_to_cache=False))
        assert second[0].refreshed is False  # NULL fingerprint != "content changed"
        row = proj.get_frame(frame_id)
        assert row.wcs_json == '{"CRVAL1": 2.0}'  # solution preserved
        # Fingerprint was backfilled from the current source.
        assert row.source_size_bytes is not None and row.source_mtime is not None
    finally:
        proj.close()


def test_ingest_does_not_reset_qc_on_a_plain_dedup_skip(tmp_path):
    """A normal (unchanged) re-scan must NOT reset QC or flag a refresh — only a
    genuine cache refresh (source grew past the cached size) does."""
    src = tmp_path / "raws"
    src.mkdir()
    p = write_seestar_fits(src / "a.fit", seed=11)
    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        first = list(ingest_files(proj, cache, [p]))
        proj.update_frame(first[0].frame_id, star_count=200, fwhm_px=2.1)
        second = list(ingest_files(proj, cache, [p]))
        assert second[0].skipped is True
        assert second[0].refreshed is False
        row = next(iter(proj.iter_frames()))
        assert row.star_count == 200 and row.fwhm_px == 2.1  # QC untouched
    finally:
        proj.close()


def test_ingest_skips_duplicates(tmp_path):
    p = write_seestar_fits(tmp_path / "a.fit")
    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        list(ingest_files(proj, cache, [p]))
        results = list(ingest_files(proj, cache, [p]))
        assert len(results) == 1
        assert results[0].skipped is True
        assert proj.count() == 1
    finally:
        proj.close()


def test_ingest_dedupes_a_symlinked_path_within_one_scan(tmp_path):
    """Two glob paths to the *same physical file* in one scan (a symlinked
    subdirectory) must register the frame once, not twice.

    Regression: dedup keyed on the raw path string, so a symlinked spelling
    missed the already-added row and the frame was ingested twice → double-
    weighted in the stack. We now dedup on the canonical (realpath) key."""
    real = tmp_path / "raws"
    real.mkdir()
    p = write_seestar_fits(real / "a.fit", seed=3)
    link = tmp_path / "raws_link"
    link.symlink_to(real, target_is_directory=True)  # second spelling of the same dir
    linked_p = link / "a.fit"
    assert linked_p.exists() and linked_p != p

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        results = list(ingest_files(proj, cache, [p, linked_p]))
        assert len(results) == 2
        added = [r for r in results if not r.skipped]
        skipped = [r for r in results if r.skipped]
        assert len(added) == 1 and len(skipped) == 1
        assert proj.count() == 1  # the physical frame is registered exactly once
    finally:
        proj.close()


def test_ingest_dedupes_across_a_relative_vs_absolute_respell(tmp_path, monkeypatch):
    """Re-scanning an already-ingested file via a *different spelling* (relative
    vs the absolute path stored on the first scan) must skip it, not re-ingest.

    This is also the upgrade-safety check: an existing library stores raw,
    non-normalised ``source_path`` values, and the fix normalises both sides at
    lookup time (never rewriting what's stored), so an old library re-scans
    clean instead of doubling every frame."""
    src = tmp_path / "raws"
    src.mkdir()
    abs_p = write_seestar_fits(src / "a.fit", seed=4)

    proj = Project.create(tmp_path / "proj", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        # First scan stores the absolute path (simulating an existing library).
        list(ingest_files(proj, cache, [abs_p]))
        assert proj.count() == 1
        stored = next(iter(proj.iter_frames())).source_path
        assert stored == str(abs_p)  # stored path is untouched by the fix

        # Second scan reaches the same file via a relative spelling.
        monkeypatch.chdir(tmp_path)
        rel_p = Path("raws") / "a.fit"
        assert str(rel_p) != stored
        results = list(ingest_files(proj, cache, [rel_p]))
        assert results[0].skipped is True
        assert proj.count() == 1  # no duplicate row
    finally:
        proj.close()
