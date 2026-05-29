"""Job manager: a single background worker that serializes all heavy engine work.

Why one worker? The engine's QC/solve fan out to a ``ProcessPoolExecutor`` that
already saturates every core, and stacking holds full-canvas float buffers in
RAM. Running two such jobs at once would oversubscribe CPU and blow memory. So
every job (whether triggered by the watcher or the user) goes through one queue
consumed by one thread. That thread is also the only writer to each project's
SQLite, which keeps per-project DB access single-threaded.

Live job state is kept in memory (hot path for the SSE progress stream); state
transitions + throttled progress are persisted to a single global
``jobs.sqlite`` so history survives and interrupted jobs can be detected on
restart.
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

JobFn = Callable[["Job"], dict[str, Any] | None]

_TERMINAL = {"done", "error", "cancelled", "interrupted"}
_PROGRESS_FLUSH_S = 1.5


def _utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Job:
    kind: str
    target: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: str = "queued"
    phase: str = ""
    done: int = 0
    total: int = 0
    detail: str = ""
    created_utc: str = field(default_factory=_utc)
    started_utc: str | None = None
    finished_utc: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _last_flush: float = field(default=0.0, repr=False)

    # ---- callbacks handed to the engine --------------------------------
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def set_progress(self, phase: str, done: int, total: int, detail: str = "") -> None:
        self.phase = phase
        self.done = done
        self.total = total
        if detail:
            self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "target": self.target,
            "state": self.state, "phase": self.phase, "done": self.done,
            "total": self.total, "detail": self.detail,
            "created_utc": self.created_utc, "started_utc": self.started_utc,
            "finished_utc": self.finished_utc, "error": self.error,
            "result": self.result,
        }


class JobManager:
    def __init__(self, db_path: Path, *, max_history: int = 200) -> None:
        self.db_path = Path(db_path)
        self.max_history = max_history
        self._queue: queue.Queue[tuple[Job, JobFn]] = queue.Queue()
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._init_db()
        self._recover_interrupted()

    # ---- lifecycle ------------------------------------------------------

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run, name="job-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        # Unblock the worker if it's waiting on the queue.
        self._queue.put((None, None))  # type: ignore[arg-type]

    # ---- db -------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    target TEXT,
                    state TEXT NOT NULL,
                    phase TEXT, done INTEGER, total INTEGER, detail TEXT,
                    created_utc TEXT, started_utc TEXT, finished_utc TEXT,
                    error TEXT, result_json TEXT
                )
                """
            )

    def _recover_interrupted(self) -> None:
        """Any job left running/queued when the process died is interrupted."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET state='interrupted', finished_utc=? "
                "WHERE state IN ('running','queued')",
                (_utc(),),
            )

    def _persist(self, job: Job) -> None:
        import json
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(id, kind, target, state, phase, done, total, detail,
                                 created_utc, started_utc, finished_utc, error, result_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    state=excluded.state, phase=excluded.phase, done=excluded.done,
                    total=excluded.total, detail=excluded.detail,
                    started_utc=excluded.started_utc, finished_utc=excluded.finished_utc,
                    error=excluded.error, result_json=excluded.result_json
                """,
                (
                    job.id, job.kind, job.target, job.state, job.phase, job.done,
                    job.total, job.detail, job.created_utc, job.started_utc,
                    job.finished_utc, job.error,
                    json.dumps(job.result) if job.result is not None else None,
                ),
            )

    # ---- submit / query -------------------------------------------------

    def submit(self, kind: str, fn: JobFn, *, target: str | None = None) -> Job:
        job = Job(kind=kind, target=target)
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        self._queue.put((job, fn))
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        return self._load_from_db(job_id)

    def _load_from_db(self, job_id: str) -> Job | None:
        import json
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        job = Job(kind=row["kind"], target=row["target"], id=row["id"])
        job.state = row["state"]
        job.phase = row["phase"] or ""
        job.done = row["done"] or 0
        job.total = row["total"] or 0
        job.detail = row["detail"] or ""
        job.created_utc = row["created_utc"]
        job.started_utc = row["started_utc"]
        job.finished_utc = row["finished_utc"]
        job.error = row["error"]
        job.result = json.loads(row["result_json"]) if row["result_json"] else None
        return job

    def list(self, limit: int = 100) -> list[Job]:
        """Active jobs (in-memory) first, then recent history from the DB."""
        import json
        with self._lock:
            live = {j.id: j for j in self._jobs.values()}
        out: list[Job] = list(live.values())
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_utc DESC LIMIT ?", (limit,)
            ).fetchall()
        for row in rows:
            if row["id"] in live:
                continue
            job = Job(kind=row["kind"], target=row["target"], id=row["id"])
            job.state, job.phase = row["state"], row["phase"] or ""
            job.done, job.total = row["done"] or 0, row["total"] or 0
            job.detail = row["detail"] or ""
            job.created_utc, job.started_utc = row["created_utc"], row["started_utc"]
            job.finished_utc, job.error = row["finished_utc"], row["error"]
            job.result = json.loads(row["result_json"]) if row["result_json"] else None
            out.append(job)
        out.sort(key=lambda j: j.created_utc or "", reverse=True)
        return out[:limit]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.state in _TERMINAL:
            return False
        job._cancel.set()
        if job.state == "queued":
            # Not yet picked up — mark cancelled immediately.
            job.state = "cancelled"
            job.finished_utc = _utc()
            self._persist(job)
        return True

    def maybe_flush(self, job: Job) -> None:
        """Throttled progress persistence — called by the engine progress cb."""
        now = time.monotonic()
        if now - job._last_flush >= _PROGRESS_FLUSH_S:
            job._last_flush = now
            self._persist(job)

    # ---- worker loop ----------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            job, fn = self._queue.get()
            if job is None:  # stop sentinel
                break
            if job.state == "cancelled":  # cancelled while queued
                continue
            job.state = "running"
            job.started_utc = _utc()
            self._persist(job)
            try:
                result = fn(job)
                if job.cancel_requested():
                    job.state = "cancelled"
                else:
                    job.state = "done"
                    job.result = result or job.result
            except Exception as exc:  # noqa: BLE001
                log.exception("job %s (%s) failed", job.id, job.kind)
                job.state = "error"
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                job.finished_utc = _utc()
                self._persist(job)
                self._evict_old()

    def _evict_old(self) -> None:
        """Drop finished jobs from the in-memory map (DB keeps history)."""
        with self._lock:
            finished = [j for j in self._jobs.values() if j.state in _TERMINAL]
            if len(finished) <= self.max_history:
                return
            finished.sort(key=lambda j: j.finished_utc or "")
            for j in finished[: len(finished) - self.max_history]:
                self._jobs.pop(j.id, None)
