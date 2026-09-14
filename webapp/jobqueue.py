"""Is your import stuck behind the one worker?

AstroStack runs every job on a **single serial worker** (`webapp/jobs.py` — one
`queue.Queue`, one thread), which is deliberate: two stacks at once on a
RAM-capped NAS is how you get an OOM kill. The cost of a serial worker is that a
job which runs for days holds the worker for days, and everything behind it
simply waits its turn.

That is fine for a job a person started and is watching — they can see it on the
Jobs page and cancel it. It is **not** fine for the import (`pipeline`) job,
because that one is how the owner's new subs get into the library at all: the
watcher enqueues it, nobody asked for it, and while it waits the app looks
completely healthy. Every target still shows the frame count it had before, and
a frame that was never imported has no QC row, no reject reason and no place in
the record where it can be seen to be absent — it just is not there.

Reported 2026-09-14 by the on-NAS observer against the owner's real library:
2,259 subs across two full nights (12.6 h) sat on disk for **eleven days** while
`reprocess_all` jobs held the worker continuously, with an import job queued and
never started for the last three of them. The app surfaced no sign of it.

This module answers the one question that makes that visible — *has the import
been waiting an unreasonable time, and what is holding the worker?* — from the
job rows the Jobs page already fetches. It is pure: it takes mappings and
returns a dataclass, so it needs no job manager, no request and no clock of its
own, and it is tested without either.

It deliberately does **not** re-order the queue or add a second worker. The
observed stall is a *running* job holding the worker, which no amount of
re-ordering would have released, and a second worker is exactly the change the
memory bound exists to prevent. What the owner was missing was not throughput,
it was the sentence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from seestack.activity_calendar import parse_utc

#: The job kind the watcher enqueues to import and process new frames
#: (`pipeline.submit_pipeline`). The one kind nobody asks for by hand, and so
#: the one whose delay goes unnoticed.
IMPORT_KIND = "pipeline"

#: How long an import may sit queued before we say so, in hours. The watcher
#: polls every few minutes and an ordinary import of a night's subs finishes in
#: minutes, so anything past a couple of hours is no longer "the worker is busy"
#: — while a stack somebody started can legitimately run for an hour or two, and
#: should not raise a note. Well short of the days the observer measured.
IMPORT_WAIT_MIN_HOURS = 2.0

_QUEUED = "queued"
_RUNNING = "running"


@dataclass(frozen=True)
class ImportWaiting:
    """An import job that has been queued longer than :data:`IMPORT_WAIT_MIN_HOURS`,
    and the job holding the single worker (when there is one)."""

    job_id: str
    queued_utc: str
    #: Hours since the import was enqueued, rounded to one decimal.
    waiting_hours: float
    #: How many import jobs are waiting in total (normally 1 — `_on_batch_ready`
    #: refuses to enqueue a second — so a number above 1 is itself worth seeing).
    n_waiting: int
    #: The running job holding the worker. All ``None`` when *nothing* is
    #: running, which is the worse case: the queue is not busy, it is stalled.
    holder_id: str | None
    holder_kind: str | None
    holder_target: str | None
    #: Hours the holder has been running, rounded to one decimal; ``None`` when
    #: there is no holder or it never recorded a start.
    holder_hours: float | None


def _hours_between(earlier: str | None, now: datetime) -> float | None:
    when = parse_utc(earlier or "")
    if when is None:
        return None
    return (now - when).total_seconds() / 3600.0


def import_waiting(
    jobs: Iterable[Mapping[str, Any]],
    now_utc: datetime,
    *,
    min_hours: float = IMPORT_WAIT_MIN_HOURS,
) -> ImportWaiting | None:
    """The longest-waiting queued import, or ``None`` when nothing is stuck.

    ``jobs`` is any iterable of job mappings in the shape `Job.to_dict()` emits
    (``kind`` / ``state`` / ``created_utc`` / ``started_utc`` / ``target``);
    rows missing or misspelling a stamp are skipped rather than guessed at, so
    one unparseable row can never manufacture a warning.
    """
    queued: list[tuple[float, Mapping[str, Any]]] = []
    for job in jobs:
        if job.get("kind") != IMPORT_KIND or job.get("state") != _QUEUED:
            continue
        waited = _hours_between(job.get("created_utc"), now_utc)
        if waited is None or waited < 0:
            continue  # unparseable, or a stamp from the future — say nothing
        queued.append((waited, job))
    if not queued:
        return None
    waited, oldest = max(queued, key=lambda pair: pair[0])
    if waited < min_hours:
        return None

    # At most one job can be running on a serial worker; take the oldest start
    # if a caller ever hands us more, so the answer is the one actually holding
    # the queue rather than whichever came first in the list.
    holder: Mapping[str, Any] | None = None
    holder_hours: float | None = None
    for job in jobs:
        if job.get("state") != _RUNNING:
            continue
        ran = _hours_between(job.get("started_utc"), now_utc)
        if holder is None or (ran is not None and (holder_hours is None or ran > holder_hours)):
            holder, holder_hours = job, ran

    return ImportWaiting(
        job_id=str(oldest.get("id") or ""),
        queued_utc=str(oldest.get("created_utc") or ""),
        waiting_hours=round(waited, 1),
        n_waiting=len(queued),
        holder_id=str(holder.get("id") or "") or None if holder is not None else None,
        holder_kind=str(holder.get("kind") or "") or None if holder is not None else None,
        holder_target=(str(holder.get("target")) if holder is not None
                       and holder.get("target") else None),
        holder_hours=round(holder_hours, 1) if holder_hours is not None else None,
    )


#: The job kinds a long-haul batch stands aside for at the first safe boundary
#: it reaches. Just the import, and deliberately so: it is the one job nobody
#: starts by hand, the one whose delay costs *frames missing from the library*
#: rather than someone's patience, and the one whose own cost is minutes. A
#: stack or an export somebody clicked can wait its turn — they are watching it,
#: and they can cancel it.
YIELD_TO_KINDS: frozenset[str] = frozenset({IMPORT_KIND})


def queued_kind_to_yield_to(
    jobs: Iterable[Mapping[str, Any]],
    *,
    kinds: frozenset[str] = YIELD_TO_KINDS,
) -> str | None:
    """The kind of the queued job a long-haul batch should hand the worker to,
    or ``None`` when nothing waiting is worth pausing for.

    The companion to :func:`import_waiting`, which only *describes* the stall.
    That one is the sentence; this one is what a batch asks itself between two
    units of work so the sentence stops being needed.

    ``jobs`` is any iterable of job mappings in the shape ``Job.to_dict()``
    emits — normally the live ones (``JobManager.active()``). Only ``queued``
    counts: the batch asking the question is itself ``running``, and a job that
    is already running cannot be waiting on it.
    """
    for job in jobs:
        if job.get("state") != _QUEUED:
            continue
        kind = job.get("kind")
        if isinstance(kind, str) and kind in kinds:
            return kind
    return None
