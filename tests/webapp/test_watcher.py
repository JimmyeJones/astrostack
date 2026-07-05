"""Watcher debounce: files are only stable after a quiet period."""

from __future__ import annotations

from types import SimpleNamespace

from webapp.watcher import StabilityTracker, Watcher


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def test_growing_file_is_not_stable():
    clock = FakeClock()
    tr = StabilityTracker(quiet_period_s=30, time_fn=clock)

    # First sighting.
    assert tr.update({"a.fit": (100, clock.t - 100)}) == set()
    # Still growing 10s later → not stable.
    clock.advance(10)
    assert tr.update({"a.fit": (200, clock.t - 100)}) == set()
    clock.advance(10)
    assert tr.update({"a.fit": (300, clock.t - 100)}) == set()


def test_file_becomes_stable_after_quiet_period():
    clock = FakeClock()
    tr = StabilityTracker(quiet_period_s=30, time_fn=clock)
    mtime = clock.t - 100  # old mtime

    assert tr.update({"a.fit": (100, mtime)}) == set()
    clock.advance(31)
    # Unchanged + quiet long enough + mtime old enough → stable now.
    assert tr.update({"a.fit": (100, mtime)}) == {"a.fit"}
    # Not reported again.
    clock.advance(5)
    assert tr.update({"a.fit": (100, mtime)}) == set()


def test_actively_rewritten_file_never_stable():
    """A file rewritten in place (constant size, mtime tracks now) is held."""
    clock = FakeClock()
    tr = StabilityTracker(quiet_period_s=30, time_fn=clock)
    for _ in range(4):
        # Same size each poll, but mtime keeps moving with the clock.
        assert tr.update({"a.fit": (100, clock.t)}) == set()
        clock.advance(31)
    # Once it stops being touched and goes quiet, it becomes stable.
    final_mtime = clock.t
    tr.update({"a.fit": (100, final_mtime)})
    clock.advance(31)
    assert tr.update({"a.fit": (100, final_mtime)}) == {"a.fit"}


def test_disappearing_file_is_forgotten_and_rearms():
    clock = FakeClock()
    tr = StabilityTracker(quiet_period_s=30, time_fn=clock)
    mtime = clock.t - 100
    tr.update({"a.fit": (100, mtime)})
    clock.advance(31)
    assert tr.update({"a.fit": (100, mtime)}) == {"a.fit"}
    # File gone.
    assert tr.update({}) == set()
    # Re-appears → must re-arm and become stable again.
    clock.advance(1)
    tr.update({"a.fit": (100, mtime)})
    clock.advance(31)
    assert tr.update({"a.fit": (100, mtime)}) == {"a.fit"}


def test_poll_fires_batch_callback_once_per_stable_batch(tmp_path):
    import os

    incoming = tmp_path / "incoming"
    incoming.mkdir()
    f = incoming / "a.fit"
    f.write_bytes(b"x" * 100)

    clock = FakeClock()
    # Pin the file's mtime into the fake clock's timeline.
    os.utime(f, (clock.t, clock.t))

    fired = []
    settings = SimpleNamespace(
        resolved_incoming_dir=incoming, watch_quiet_period_s=30,
        watch_poll_interval_s=300, watcher_enabled=True,
    )
    w = Watcher(
        get_settings=lambda: settings,
        on_batch_ready=lambda: fired.append(1),
        time_fn=clock,
    )
    # First poll: file seen, not yet stable.
    assert w.poll_once() == set()
    assert fired == []
    # After the quiet period it becomes stable and fires exactly once.
    clock.advance(31)
    assert w.poll_once() == {str(f)}
    assert fired == [1]
    # No new files → no extra firing.
    clock.advance(31)
    assert w.poll_once() == set()
    assert fired == [1]


def test_batch_pending_when_pipeline_busy_is_reoffered(tmp_path):
    """A file stabilising while a pipeline is running is re-offered, not dropped.

    Regression for the watcher silently dropping a batch: ``_on_batch_ready``
    returns ``False`` when a pipeline is already active, and the watcher must
    keep the batch pending and re-offer it on later polls until it's accepted
    — otherwise the file's one-and-only "newly stable" trigger is lost and it
    sits unimported in ``incoming/`` forever.
    """
    import os

    incoming = tmp_path / "incoming"
    incoming.mkdir()
    f = incoming / "a.fit"
    f.write_bytes(b"x" * 100)

    clock = FakeClock()
    os.utime(f, (clock.t, clock.t))

    # A pipeline is "busy" (declines the batch) for the first two accept
    # attempts, then frees up.
    busy = {"v": True}
    calls: list[float] = []

    def on_batch_ready() -> bool:
        calls.append(clock.t)
        return not busy["v"]  # False while busy → declined; True once free

    settings = SimpleNamespace(
        resolved_incoming_dir=incoming, watch_quiet_period_s=30,
        watch_poll_interval_s=300, watcher_enabled=True,
    )
    w = Watcher(
        get_settings=lambda: settings,
        on_batch_ready=on_batch_ready,
        time_fn=clock,
    )
    # Not stable yet → no call.
    assert w.poll_once() == set()
    assert calls == []
    # Stable now, but the pipeline is busy → declined; the batch stays pending.
    clock.advance(31)
    assert w.poll_once() == {str(f)}
    assert len(calls) == 1
    # No *new* files, but the pending batch is re-offered each poll while busy.
    clock.advance(31)
    assert w.poll_once() == set()
    assert len(calls) == 2
    # Pipeline finishes → the next re-offer is accepted and pending clears.
    busy["v"] = False
    clock.advance(31)
    assert w.poll_once() == set()
    assert len(calls) == 3
    # Once accepted, the batch is no longer re-offered.
    clock.advance(31)
    assert w.poll_once() == set()
    assert len(calls) == 3
