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
