"""Cache manager — directory layout and stats / clear."""

from seestack.core.cache import CacheManager


def test_ensure_dirs_creates_layout(tmp_path):
    cm = CacheManager(tmp_path / "proj")
    cm.ensure_dirs()
    assert cm.stage1.is_dir()
    assert cm.stage2.is_dir()


def test_paths_are_deterministic(tmp_path):
    cm = CacheManager(tmp_path / "proj")
    a1 = cm.stage1_path_for(7, "frame_007.fit")
    a2 = cm.stage1_path_for(7, "anything.fit")
    # path is keyed on the frame id, not the original name
    assert a1 == a2
    assert a1.name.startswith("frame_000007")
    assert a1.parent == cm.stage1

    b = cm.stage2_path_for(42)
    assert b.parent == cm.stage2
    assert b.suffix == ".mmap"


def test_stats_and_clear(tmp_path):
    cm = CacheManager(tmp_path / "proj")
    cm.ensure_dirs()
    f = cm.stage1_path_for(1, "x.fit")
    f.write_bytes(b"hello world")

    stats = cm.stats("stage1")
    assert stats.file_count == 1
    assert stats.bytes_total == len(b"hello world")

    cm.clear("stage1")
    assert cm.stats("stage1").file_count == 0
    assert cm.stage1.is_dir()  # recreated, not destroyed
