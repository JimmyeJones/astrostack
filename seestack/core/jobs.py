"""
Background job runner with Qt-friendly progress signals.

Three constraints shape this design:

1. The GUI must never freeze. Long ops run on a worker pool, never on the Qt
   main thread.
2. Heavy CPU work (QC, alignment, stacking) needs real parallelism — that means
   processes, not threads, because of the GIL and because some libraries
   (photutils, scipy.ndimage) hold the GIL during numerical work.
3. The work item must be picklable, since ``ProcessPoolExecutor`` ships it to a
   worker. So jobs are plain functions that take simple args and return simple
   results — no live DB connection, no Qt object, no method on a GUI class.

The DB-write side runs on the main thread when each result comes back. SQLite
on a single connection from one thread is the simplest correct setup.

This module deliberately avoids importing PySide6 at the top level so that
non-GUI code (tests, scripts) can use ``run_serial`` and ``JobResult`` without
a Qt install. The ``JobRunner`` class lazy-imports Qt inside ``__init__``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class JobResult:
    """Carries the outcome of one work item."""

    index: int
    args: tuple[Any, ...]
    value: Any
    error: str | None


def run_serial(
    func: Callable[..., Any],
    arg_tuples: Iterable[tuple[Any, ...]],
) -> list[JobResult]:
    """
    Synchronous, in-process equivalent of ``JobRunner.run``.

    Useful for tests and for short jobs where spinning up a process pool isn't
    worth it (e.g. fewer than ~10 items).
    """
    out: list[JobResult] = []
    for i, args in enumerate(arg_tuples):
        try:
            value = func(*args)
            out.append(JobResult(index=i, args=args, value=value, error=None))
        except Exception as exc:  # noqa: BLE001
            out.append(JobResult(
                index=i, args=args, value=None, error=f"{type(exc).__name__}: {exc}"
            ))
    return out


def _build_job_runner_class():
    """Build the Qt-dependent JobRunner class lazily."""
    from PySide6.QtCore import QObject, QTimer, Signal

    class JobRunner(QObject):
        """
        Run a function over many argument tuples in worker processes.

        Signals
        -------
        progress(int done, int total) : emitted as items complete.
        result(JobResult)              : emitted once per item.
        finished()                     : emitted when everything is done or cancelled.
        """

        progress = Signal(int, int)
        result = Signal(object)  # JobResult
        finished = Signal()

        def __init__(
            self,
            parent: QObject | None = None,
            max_workers: int | None = None,
        ) -> None:
            super().__init__(parent)
            self.max_workers = max_workers
            self._executor: ProcessPoolExecutor | None = None
            self._futures: dict[Future, tuple[int, tuple[Any, ...]]] = {}
            self._cancelled = False
            self._done = 0
            self._total = 0
            self._poll = QTimer(self)
            self._poll.setInterval(50)
            self._poll.timeout.connect(self._poll_once)

        def run(
            self,
            func: Callable[..., Any],
            arg_tuples: Sequence[tuple[Any, ...]],
        ) -> None:
            if self._executor is not None:
                raise RuntimeError("JobRunner is already running")
            self._cancelled = False
            self._done = 0
            self._total = len(arg_tuples)
            if self._total == 0:
                self.finished.emit()
                return
            self._executor = ProcessPoolExecutor(max_workers=self.max_workers)
            for i, args in enumerate(arg_tuples):
                fut = self._executor.submit(func, *args)
                self._futures[fut] = (i, args)
            self._poll.start()

        def cancel(self) -> None:
            self._cancelled = True
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)

        def _poll_once(self) -> None:
            completed = [f for f in self._futures if f.done()]
            for fut in completed:
                idx, args = self._futures.pop(fut)
                value: Any = None
                err: str | None = None
                try:
                    value = fut.result()
                except Exception as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}: {exc}"
                    log.warning("job %d failed: %s", idx, err)
                self._done += 1
                self.result.emit(JobResult(index=idx, args=args, value=value, error=err))
                self.progress.emit(self._done, self._total)

            if not self._futures:
                self._poll.stop()
                if self._executor is not None:
                    self._executor.shutdown(wait=False)
                    self._executor = None
                self.finished.emit()

    return JobRunner


def __getattr__(name: str):
    """Lazy-load JobRunner only when first accessed; keeps Qt out of test deps."""
    if name == "JobRunner":
        cls = _build_job_runner_class()
        globals()["JobRunner"] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
