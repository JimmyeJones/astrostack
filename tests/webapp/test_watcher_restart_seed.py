"""A container restart does not re-import the whole library.

Full audit 2026-11-26 (``perf.md`` D-6): ``StabilityTracker`` lives in memory and
starts empty, so after any restart or update every file already in
``incoming/`` became "newly stable" and ``_on_batch_ready`` queued a
whole-library scan → QC → solve. The watcher is now seeded with the subs the
library has already imported and finished, and only those are skipped.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from seestack.io.library import Library
from webapp.main import _library_finished_sources
from webapp.watcher import StabilityTracker, Watcher


class _Clock:
    def __init__(self):
        self.t = 2_000_000_000.0

    def __call__(self) -> float:
        return self.t


def _store(data_root: Path):
    s = SimpleNamespace(resolved_library_root=data_root / "library",
                        resolved_incoming_dir=data_root / "incoming",
                        watch_quiet_period_s=30, watcher_enabled=True)
    return SimpleNamespace(get=lambda: s)


def _finish_pipeline(data_root: Path, *, skip_qc: set[str] = frozenset()) -> None:
    """Stand in for a finished QC pass (``solved_library`` already placed them)."""
    lib = Library.open(data_root / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                for f in proj.iter_frames():
                    if Path(f.source_path).name not in skip_qc:
                        proj.update_frame(f.id, star_count=40)
            finally:
                proj.close()
    finally:
        lib.close()


def _restarted_watcher(data_root: Path, fired: list, clock: _Clock) -> Watcher:
    store = _store(data_root)
    return Watcher(
        get_settings=store.get,
        on_batch_ready=lambda: (fired.append(clock.t), True)[1],
        known_sources=lambda: _library_finished_sources(store),
        time_fn=clock,
    )


def _settle(w: Watcher, clock: _Clock) -> set[str]:
    out = set(w.poll_once())
    clock.t += 31
    out |= w.poll_once()
    return out


def test_a_restart_does_not_queue_the_whole_library(solved_library):
    """FAIL-BEFORE: all six imported subs came back newly stable and fired."""
    _finish_pipeline(solved_library)
    fired: list = []
    clock = _Clock()
    w = _restarted_watcher(solved_library, fired, clock)
    assert _settle(w, clock) == set()
    assert fired == []


def test_a_sub_that_arrived_while_the_app_was_down_still_fires(solved_library):
    _finish_pipeline(solved_library)
    new = solved_library / "incoming" / "M_42" / "frame_009.fit"
    new.write_bytes((solved_library / "incoming" / "M_42" / "frame_000.fit").read_bytes())
    fired: list = []
    clock = _Clock()
    w = _restarted_watcher(solved_library, fired, clock)
    assert _settle(w, clock) == {str(new)}
    assert len(fired) == 1


def test_a_sub_rewritten_while_the_app_was_down_still_fires(solved_library):
    _finish_pipeline(solved_library)
    f = solved_library / "incoming" / "NGC_7000" / "frame_001.fit"
    st = f.stat()
    os.utime(f, (st.st_atime, st.st_mtime + 3600))
    fired: list = []
    clock = _Clock()
    w = _restarted_watcher(solved_library, fired, clock)
    assert _settle(w, clock) == {str(f)}
    assert len(fired) == 1


def test_a_sub_the_pipeline_never_finished_still_fires(solved_library):
    """Imported, then the container stopped before QC: the restart finishes it."""
    _finish_pipeline(solved_library, skip_qc={"frame_002.fit"})
    fired: list = []
    clock = _Clock()
    w = _restarted_watcher(solved_library, fired, clock)
    got = _settle(w, clock)
    assert {Path(p).name for p in got} == {"frame_002.fit"}
    assert len(got) == 2  # one per target folder
    assert len(fired) == 1


def test_no_library_yet_is_no_seed(tmp_path):
    root = tmp_path / "data"
    assert _library_finished_sources(_store(root)) == {}
    assert not (root / "library").exists()  # nothing created


def test_a_failing_seed_falls_back_to_the_old_behaviour(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    f = incoming / "a.fit"
    f.write_bytes(b"x" * 100)
    clock = _Clock()
    os.utime(f, (clock.t - 100, clock.t - 100))
    fired: list = []
    s = SimpleNamespace(resolved_incoming_dir=incoming, watch_quiet_period_s=30)

    def boom():
        raise RuntimeError("library locked")

    w = Watcher(get_settings=lambda: s, on_batch_ready=lambda: (fired.append(1), True)[1],
                known_sources=boom, time_fn=clock)
    assert _settle(w, clock) == {str(f)}
    assert fired == [1]


def test_the_seed_is_used_once_and_rewrites_after_it_still_re_arm():
    clock = _Clock()
    tr = StabilityTracker(quiet_period_s=30, time_fn=clock)
    tr.seed({"a.fit": (100, 5.0)})
    assert tr.update({"a.fit": (100, 5.0)}) == set()
    clock.t += 31
    assert tr.update({"a.fit": (100, 5.0)}) == set()
    # An in-place rewrite later is still seen, exactly as for any stable file.
    tr.update({"a.fit": (200, 6.0)})
    clock.t += 31
    assert tr.update({"a.fit": (200, 6.0)}) == {"a.fit"}
    # A file that only appears after the first update was never seeded.
    tr.update({"a.fit": (200, 6.0), "b.fit": (100, 5.0)})
    clock.t += 31
    assert tr.update({"a.fit": (200, 6.0), "b.fit": (100, 5.0)}) == {"b.fit"}
