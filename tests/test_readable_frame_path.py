"""Frames fall back to their readable source when the Stage-1 cache is gone.

Clearing the Stage-1 cache (a UI-exposed, documented-*safe* action) deletes the
``frame_NNNNNN.fit`` files that each frame's ``cached_path`` column points at
**without** nulling the column. The old ``cached_path or source_path`` idiom then
short-circuited onto the (truthy) dead cache path and, when the existence check
failed, dropped the frame entirely — silently breaking QC / solve / stack for a
target whose original subs are still perfectly readable on disk.

``readable_frame_path`` returns the first of ``(cached_path, source_path)`` that
actually exists, so a dangling cache now falls through to the source instead of
disabling the frame.
"""

from __future__ import annotations

from seestack.io.project import FrameRow, readable_frame_path
from seestack.qc.runner import build_qc_arglist
from seestack.solve.runner import build_solve_arglist


class _Project:
    def __init__(self, frames):
        self._frames = frames

    def iter_frames(self):
        return iter(self._frames)

    def get_meta(self, key):  # for build_solve_arglist
        return None


def _frame(fid, *, cached_path, source_path, wcs_json=None):
    return FrameRow(
        id=fid,
        source_path=source_path,
        cached_path=cached_path,
        bayer_pattern="RGGB",
        wcs_json=wcs_json,
    )


# ---- unit: the helper itself -------------------------------------------------

def test_helper_prefers_cache_when_it_exists(tmp_path):
    cache = tmp_path / "cache.fit"
    src = tmp_path / "src.fit"
    cache.write_bytes(b"c")
    src.write_bytes(b"s")
    f = _frame(1, cached_path=str(cache), source_path=str(src))
    assert readable_frame_path(f) == str(cache)


def test_helper_falls_back_to_source_when_cache_is_gone(tmp_path):
    src = tmp_path / "src.fit"
    src.write_bytes(b"s")
    # cached_path is a *dangling* pointer — the file was deleted (cache cleared).
    f = _frame(1, cached_path=str(tmp_path / "gone.fit"), source_path=str(src))
    assert readable_frame_path(f) == str(src)


def test_helper_returns_none_when_neither_exists(tmp_path):
    f = _frame(1, cached_path=str(tmp_path / "a.fit"), source_path=str(tmp_path / "b.fit"))
    assert readable_frame_path(f) is None


def test_helper_handles_missing_cache_column(tmp_path):
    src = tmp_path / "src.fit"
    src.write_bytes(b"s")
    f = _frame(1, cached_path=None, source_path=str(src))
    assert readable_frame_path(f) == str(src)


# ---- integration: the consumers that used to drop the frame ------------------

def test_qc_arglist_stacks_from_source_when_cache_is_gone(tmp_path):
    src = tmp_path / "src.fit"
    src.write_bytes(b"s")
    live = _frame(1, cached_path=str(tmp_path / "gone.fit"), source_path=str(src))
    dead = _frame(2, cached_path=str(tmp_path / "x.fit"), source_path=str(tmp_path / "y.fit"))

    args = build_qc_arglist(_Project([live, dead]))
    # Fail-before: the dead cache pointer dropped frame 1 despite a live source.
    assert {a[0] for a in args} == {1}
    assert args[0][1] == str(src)  # path offered is the readable source


def test_solve_arglist_falls_back_to_source_when_cache_is_gone(tmp_path):
    src = tmp_path / "src.fit"
    src.write_bytes(b"s")
    live = _frame(1, cached_path=str(tmp_path / "gone.fit"), source_path=str(src))
    dead = _frame(2, cached_path=str(tmp_path / "x.fit"), source_path=str(tmp_path / "y.fit"))

    args = build_solve_arglist(_Project([live, dead]))
    assert {a[0] for a in args} == {1}
    assert args[0][1] == str(src)
