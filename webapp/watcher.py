"""Folder watcher.

Watches the incoming dataset folder for new Seestar raws and, once they've
finished arriving, enqueues a single pipeline job (scan → QC → solve).

The hard part is not *noticing* files — it's not reacting to a file that's
still being copied over SMB/NFS. We solve that with a size+mtime quiet period:
a file is only "stable" once its size and mtime haven't changed for
``quiet_period_s`` and its mtime is at least that old. The debounce core
(:class:`StabilityTracker`) is pure and clock-injectable so it can be unit
tested without real files.

watchdog (inotify) is used only as a hint to wake the poll loop sooner; the
poll itself is the source of truth, because inotify is unreliable on network
filesystems.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from seestack.io.ingest import find_fits_files

log = logging.getLogger(__name__)

# (size, mtime) for a path.
StatFn = Callable[[Path], tuple[int, float] | None]
TimeFn = Callable[[], float]


@dataclass
class _Pending:
    size: int
    mtime: float
    first_seen: float


class StabilityTracker:
    """Decides which files have finished arriving.

    Feed it the current directory snapshot via :meth:`update`; it returns the
    set of paths that have newly become stable (and won't return them again).
    """

    def __init__(self, quiet_period_s: float, *, time_fn: TimeFn) -> None:
        self.quiet_period_s = quiet_period_s
        self._time = time_fn
        self._pending: dict[str, _Pending] = {}
        self._stable: set[str] = set()

    def update(self, snapshot: dict[str, tuple[int, float]]) -> set[str]:
        """``snapshot`` maps path -> (size, mtime). Returns newly stable paths."""
        now = self._time()
        newly_stable: set[str] = set()
        seen = set(snapshot.keys())

        for path, (size, mtime) in snapshot.items():
            if path in self._stable:
                continue
            prev = self._pending.get(path)
            if prev is None or prev.size != size or prev.mtime != mtime:
                # New or still-changing: (re)start its quiet timer.
                self._pending[path] = _Pending(size=size, mtime=mtime, first_seen=now)
                continue
            # Unchanged since last poll. Stable once it's been quiet long enough
            # AND the file itself hasn't been touched recently.
            quiet_long_enough = (now - prev.first_seen) >= self.quiet_period_s
            mtime_old_enough = (now - mtime) >= self.quiet_period_s
            if quiet_long_enough and mtime_old_enough:
                self._stable.add(path)
                self._pending.pop(path, None)
                newly_stable.add(path)

        # Forget files that disappeared (moved/deleted) so re-adds re-arm.
        for gone in set(self._pending) - seen:
            self._pending.pop(gone, None)
        self._stable &= seen
        return newly_stable


class Watcher:
    def __init__(
        self,
        *,
        get_settings: Callable[[], object],
        on_batch_ready: Callable[[], bool | None],
        time_fn: TimeFn | None = None,
        stat_fn: StatFn | None = None,
    ) -> None:
        import time as _time

        self._get_settings = get_settings
        self._on_batch_ready = on_batch_ready
        # A batch we couldn't hand off yet because a pipeline was already
        # running when it stabilised. Re-offered on later polls until accepted,
        # so a file that stabilises mid-pipeline is never permanently dropped.
        self._pending_batch = False
        # Wall-clock, not monotonic: we compare it against filesystem mtimes.
        self._time = time_fn or _time.time
        self._stat = stat_fn or self._default_stat
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer = None  # watchdog observer, if available
        s = get_settings()
        self._tracker = StabilityTracker(
            getattr(s, "watch_quiet_period_s", 30), time_fn=self._time
        )

    @staticmethod
    def _default_stat(path: Path) -> tuple[int, float] | None:
        try:
            st = path.stat()
            return st.st_size, st.st_mtime
        except OSError:
            return None

    # ---- lifecycle ------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="watcher", daemon=True)
        self._thread.start()
        self._start_observer()

    def stop(self) -> None:
        import contextlib

        self._stop.set()
        self._wake.set()
        if self._observer is not None:
            with contextlib.suppress(Exception):
                self._observer.stop()

    def _start_observer(self) -> None:
        s = self._get_settings()
        incoming = Path(s.resolved_incoming_dir)
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            wake = self._wake

            class _Handler(FileSystemEventHandler):
                def on_any_event(self, event):  # noqa: ANN001
                    wake.set()

            obs = Observer()
            incoming.mkdir(parents=True, exist_ok=True)
            obs.schedule(_Handler(), str(incoming), recursive=True)
            obs.daemon = True
            obs.start()
            self._observer = obs
            log.info("watchdog observing %s", incoming)
        except Exception as exc:  # noqa: BLE001 — fall back to pure polling
            log.warning("watchdog unavailable (%s); polling only", exc)

    # ---- loop -----------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            s = self._get_settings()
            if getattr(s, "watcher_enabled", True):
                try:
                    self.poll_once()
                except Exception:  # noqa: BLE001
                    log.exception("watcher poll failed")
            interval = max(2, int(getattr(s, "watch_poll_interval_s", 300)))
            # Wake early if watchdog fired; otherwise sleep up to `interval`.
            self._wake.wait(timeout=interval)
            self._wake.clear()

    def poll_once(self) -> set[str]:
        """One poll. Returns newly stable paths and fires the batch callback."""
        s = self._get_settings()
        self._tracker.quiet_period_s = getattr(s, "watch_quiet_period_s", 30)
        incoming = Path(s.resolved_incoming_dir)
        if not incoming.exists():
            return set()
        snapshot: dict[str, tuple[int, float]] = {}
        for p in find_fits_files(incoming):
            st = self._stat(p)
            if st is not None:
                snapshot[str(p)] = st
        newly_stable = self._tracker.update(snapshot)
        if newly_stable:
            log.info("%d new file(s) stable in %s", len(newly_stable), incoming)
        # Fire the batch callback when there is newly-stable work OR a batch
        # left pending because a prior poll couldn't hand it off (a pipeline was
        # already running). The callback returns False when it declined to
        # enqueue (a pipeline is still active); we keep the batch pending and
        # re-offer it next poll until it's accepted, so a file that stabilises
        # while a pipeline is mid-run is picked up once that pipeline finishes
        # instead of being silently dropped forever.
        if newly_stable or self._pending_batch:
            try:
                accepted = self._on_batch_ready()
            except Exception:  # noqa: BLE001 — re-raised below after keeping the batch
                # The callback failed mid-hand-off (e.g. a transient DB-locked /
                # disk-full while enqueuing the pipeline). The newly-stable files
                # are already consumed from the tracker and won't be re-offered on
                # their own, so keep the batch pending — the next poll re-offers it
                # — and re-raise so the poll loop logs the failure. Without this a
                # single failed hand-off would silently drop the batch forever.
                self._pending_batch = True
                raise
            self._pending_batch = accepted is False
        return newly_stable
