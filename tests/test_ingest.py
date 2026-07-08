"""Ingest pipeline — find files, copy to cache, register in DB."""

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
