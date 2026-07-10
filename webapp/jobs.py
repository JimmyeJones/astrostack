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


def classify_job_error(exc: BaseException) -> str | None:
    """Map a fatal job exception to a *stable canonical* ``error_kind`` string.

    The frontend translates a failed job into a plain-language sentence. It used
    to do so by string-matching the raw ``error`` text, which is brittle if an
    engine message is ever reworded. Classifying here — at the point the exception
    is caught, where the exception *type* and the full untruncated message are both
    available — gives the frontend a stable key to prefer (falling back to its own
    matcher on an older backend). Returns ``None`` for anything unrecognised, so
    the raw text is still shown verbatim and no information is hidden.

    The kinds mirror the frontend's known-fatal signatures:
    ``memory_budget`` (the OOM guard refused the stack before running),
    ``no_solved_frames`` (nothing accepted + plate-solved to stack),
    ``no_alignment`` (frames didn't overlap / solved to different fields),
    ``no_reference_wcs`` (the reference frame isn't plate-solved), and
    ``no_fits_in_folder`` (a Build-master job pointed at a folder with no FITS).
    """
    # Type-based first — reword-proof. The stacker refuses an over-budget canvas
    # by raising MemoryError (see stacker.py's memory guard).
    msg = str(exc).lower()
    if isinstance(exc, MemoryError) or "working memory" in msg:
        return "memory_budget"
    if ("plate-solve" in msg or "plate solved" in msg or "plate-solved" in msg):
        return "no_solved_frames"
    if ("no frames could be aligned" in msg or "no usable frames" in msg
            or "did not intersect the canvas" in msg
            or "produced no usable frames" in msg):
        return "no_alignment"
    if ("missing wcs" in msg or "wcs could not be parsed" in msg
            or "reference wcs" in msg):
        return "no_reference_wcs"
    # A calibration Build-master job pointed at an empty / wrong folder (a common
    # beginner mistake). Match the specific "no FITS files found" phrase, not
    # FileNotFoundError generally — other FileNotFoundErrors (missing target/run)
    # are internal and shouldn't be dressed up as a folder problem.
    if "no fits files found" in msg:
        return "no_fits_in_folder"
    return None


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
    error_kind: str | None = None
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
            "error_kind": self.error_kind,
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
            # Additive migration: a DB created before v0.84.4 has no error_kind
            # column. Add it in place (never a reset) so old job history survives.
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
            if "error_kind" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN error_kind TEXT")

    _INTERRUPT_MSG = (
        "Container restarted while this job was running — likely an out-of-memory "
        "kill (very large mosaic stacks can exhaust RAM) or a manual redeploy. "
        "The job was not completed; re-queue it. If it's a big stack that keeps "
        "crashing, reject bad plate-solve frames or lower the frame count, and see "
        "the Logs page for the last lines before the restart."
    )

    def _recover_interrupted(self) -> None:
        """Any job left running/queued when the process died is interrupted.

        We record an explanatory error so the user isn't left with a silent
        ``interrupted`` + ``error: null`` (a SIGKILL/OOM gives the worker no
        chance to write its own error). A running job almost certainly died to a
        crash; a merely-queued one just never started.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET state='interrupted', finished_utc=?, error=? "
                "WHERE state='running'",
                (_utc(), self._INTERRUPT_MSG),
            )
            conn.execute(
                "UPDATE jobs SET state='interrupted', finished_utc=? "
                "WHERE state='queued'",
                (_utc(),),
            )

    def _persist(self, job: Job) -> None:
        import json
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(id, kind, target, state, phase, done, total, detail,
                                 created_utc, started_utc, finished_utc, error,
                                 error_kind, result_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    state=excluded.state, phase=excluded.phase, done=excluded.done,
                    total=excluded.total, detail=excluded.detail,
                    started_utc=excluded.started_utc, finished_utc=excluded.finished_utc,
                    error=excluded.error, error_kind=excluded.error_kind,
                    result_json=excluded.result_json
                """,
                (
                    job.id, job.kind, job.target, job.state, job.phase, job.done,
                    job.total, job.detail, job.created_utc, job.started_utc,
                    job.finished_utc, job.error, job.error_kind,
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

    def active_of_kind(self, kind: str) -> Job | None:
        """The first non-terminal (queued/running) job of ``kind``, or ``None``.

        Active jobs always live in the in-memory map, so this is a cheap way for
        an endpoint to avoid enqueuing a duplicate long-running batch job.
        """
        with self._lock:
            for j in self._jobs.values():
                if j.kind == kind and j.state not in _TERMINAL:
                    return j
        return None

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
        job.error_kind = row["error_kind"]
        job.result = json.loads(row["result_json"]) if row["result_json"] else None
        return job

    def list(self, limit: int = 100) -> list[Job]:
        """Active jobs (in-memory) first, then recent history from the DB.

        Active (non-terminal) jobs are **never** truncated away: they lead the
        result and ``limit`` only bounds the *history* that fills the remaining
        slots. A single serial worker can have many queued jobs plus one running
        one whose ``created_utc`` is older than ``limit`` newer jobs — sorting the
        merged list by ``created_utc`` and truncating (the previous behaviour)
        dropped that running job out of the response entirely, so ``GET
        /api/jobs`` couldn't show or offer to cancel the job actually executing.
        """
        import json
        with self._lock:
            live = list(self._jobs.values())
        live_ids = {j.id for j in live}
        active = [j for j in live if j.state not in _TERMINAL]
        # Terminal in-memory jobs count as history (they're also persisted, but
        # the in-memory copy is authoritative — dedup the DB row against it).
        history: list[Job] = [j for j in live if j.state in _TERMINAL]
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_utc DESC LIMIT ?", (limit,)
            ).fetchall()
        for row in rows:
            if row["id"] in live_ids:
                continue
            job = Job(kind=row["kind"], target=row["target"], id=row["id"])
            job.state, job.phase = row["state"], row["phase"] or ""
            job.done, job.total = row["done"] or 0, row["total"] or 0
            job.detail = row["detail"] or ""
            job.created_utc, job.started_utc = row["created_utc"], row["started_utc"]
            job.finished_utc, job.error = row["finished_utc"], row["error"]
            job.error_kind = row["error_kind"]
            job.result = json.loads(row["result_json"]) if row["result_json"] else None
            history.append(job)
        active.sort(key=lambda j: j.created_utc or "", reverse=True)
        history.sort(key=lambda j: j.created_utc or "", reverse=True)
        remaining = max(limit - len(active), 0)
        return active + history[:remaining]

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
                completed = result or job.result
                if job.cancel_requested() and not completed:
                    # Cancel was requested and the job honored it — it aborted
                    # without producing a result. But a job that isn't
                    # cancel-aware runs to completion and returns its result
                    # even after cancel is pressed; in that case the work is
                    # already done, so keep the result and mark it done rather
                    # than discarding a finished stack and making the user redo
                    # it.
                    job.state = "cancelled"
                else:
                    job.state = "done"
                    job.result = result or job.result
            except Exception as exc:  # noqa: BLE001
                log.exception("job %s (%s) failed", job.id, job.kind)
                job.state = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                job.error_kind = classify_job_error(exc)
            finally:
                job.finished_utc = _utc()
                self._persist(job)
                self._evict_old()

    def clear_history(self) -> int:
        """Delete all finished jobs (DB + memory); keep running/queued. Returns
        how many were removed."""
        with self._lock:
            removed = [jid for jid, j in self._jobs.items() if j.state in _TERMINAL]
            for jid in removed:
                self._jobs.pop(jid, None)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    f"DELETE FROM jobs WHERE state IN ({','.join('?' * len(_TERMINAL))})",
                    tuple(_TERMINAL),
                )
                return cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(removed)
        except sqlite3.Error as exc:  # noqa: BLE001
            log.warning("clear job history failed: %s", exc)
            return len(removed)

    def _evict_old(self) -> None:
        """Drop old finished jobs from the in-memory map AND prune the DB so
        jobs.sqlite doesn't grow without bound on a long-running watcher."""
        with self._lock:
            finished = [j for j in self._jobs.values() if j.state in _TERMINAL]
            if len(finished) > self.max_history:
                finished.sort(key=lambda j: j.finished_utc or "")
                for j in finished[: len(finished) - self.max_history]:
                    self._jobs.pop(j.id, None)
        # Keep at most ~10× the in-memory cap on disk (history for the UI).
        keep = max(self.max_history * 10, 50)
        try:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM jobs WHERE id NOT IN "
                    "(SELECT id FROM jobs ORDER BY COALESCE(created_utc,'') DESC LIMIT ?)",
                    (keep,),
                )
        except sqlite3.Error as exc:  # noqa: BLE001 — pruning is best-effort
            log.warning("jobs DB prune failed: %s", exc)
