""""Why did this target stop producing pictures?" — the last stack that failed.

A walk-away stack that *refuses* has, until now, gone dark in complete silence.
The engine's own refusal message is excellent — it names the one lever that would
make the run fit and the memory it lands at (``stacker._best_memory_fix``) — but
it is raised into a job record nobody opens at 3 a.m. Nothing on the Target page
or the Dashboard ever said the target had stopped making pictures, or why.

This module is the reading half. It is deliberately **pure**: it takes job
records (whatever shape carries ``kind``/``state``/``target``/``error``/
``result``) and answers *"what is the newest stack failure per target?"* The
router supplies the jobs and decides which failures a later success has already
made moot.

Two kinds of failure have to be read, because they are recorded in two places:

  * A **manual** stack (``kind="stack"`` / ``"process_target"``) fails the job
    itself: ``state="error"`` with the message on the record.
  * The **walk-away** auto-stack runs *inside* the scan job and catches per
    target on purpose, so one target can't sink the batch
    (``webapp/pipeline.py``). Its failures land in the scan job's own result
    under ``stack_errors: {safe: message}`` and the scan job itself finishes
    ``done``. Reading only failed jobs would therefore miss the unattended case
    entirely — which is the one this exists for.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from seestack.activity_calendar import parse_utc
from webapp.jobs import classify_error_message

#: Job kinds that stack a target directly, so their own failure is the target's.
STACK_JOB_KINDS = frozenset({"stack", "process_target"})

#: The key the scan job's result uses for per-target auto-stack failures.
SCAN_STACK_ERRORS_KEY = "stack_errors"


@dataclass(frozen=True)
class StackFailure:
    """The newest failed stack for one target, as the UI needs to say it."""

    safe: str
    message: str
    #: The canonical ``error_kind`` (``memory_budget`` …) when it is known, so the
    #: frontend can use the plain-language translation it already has. ``None``
    #: leaves the raw message to be shown verbatim — never hidden.
    kind: str | None
    when_utc: str | None
    #: True when it failed on the unattended path (a scan's auto-stack), i.e.
    #: nobody was there to read the refusal. That changes the wording, not the
    #: fix.
    unattended: bool
    job_id: str | None


def _stamp(job: Any) -> str:  # noqa: ANN401 — duck-typed job record
    """The best "when did this fail" stamp a job record can offer."""
    return getattr(job, "finished_utc", None) or getattr(job, "created_utc", None) or ""


def _newer(a: StackFailure, b: StackFailure) -> StackFailure:
    """Whichever failure happened later; ties keep the first seen (list order)."""
    ta, tb = parse_utc(a.when_utc or ""), parse_utc(b.when_utc or "")
    if ta is None:
        return b if tb is not None else a
    if tb is None:
        return a
    return b if tb > ta else a


def latest_stack_failures(jobs: Iterable[Any]) -> dict[str, StackFailure]:
    """Newest stack failure per target ``safe``, from a job history.

    Reads both recording sites (see the module docstring). Job order doesn't
    matter — the newest stamp wins — so a caller can hand over
    ``JobManager.list()`` exactly as it comes.
    """
    out: dict[str, StackFailure] = {}

    def offer(f: StackFailure) -> None:
        prev = out.get(f.safe)
        out[f.safe] = f if prev is None else _newer(prev, f)

    for job in jobs:
        kind = getattr(job, "kind", "")
        if kind in STACK_JOB_KINDS and getattr(job, "state", "") == "error":
            safe = getattr(job, "target", None)
            message = getattr(job, "error", None)
            if safe and message:
                offer(StackFailure(
                    safe=safe, message=str(message),
                    kind=getattr(job, "error_kind", None),
                    when_utc=_stamp(job) or None, unattended=False,
                    job_id=getattr(job, "id", None),
                ))
            continue
        # The unattended half: a *successful* scan job whose result records that
        # one target's auto-stack blew up.
        result = getattr(job, "result", None)
        errors = result.get(SCAN_STACK_ERRORS_KEY) if isinstance(result, dict) else None
        if not isinstance(errors, dict):
            continue
        for safe, message in errors.items():
            if not safe or not message:
                continue
            offer(StackFailure(
                safe=str(safe), message=str(message),
                kind=classify_error_message(str(message)),
                when_utc=_stamp(job) or None, unattended=True,
                job_id=getattr(job, "id", None),
            ))
    return out


def superseded_by_success(failure: StackFailure, last_success_utc: str | None) -> bool:
    """Has a stack succeeded for this target *since* the failure?

    A long-fixed failure from three weeks ago must never nag, so the note
    self-hides the moment a later stack lands. An unparseable or missing stamp on
    either side is treated as "not superseded": the failure is real and saying so
    once too often beats going quiet about a target that is genuinely stuck.
    """
    if not last_success_utc:
        return False
    success = parse_utc(last_success_utc)
    failed = parse_utc(failure.when_utc or "")
    if success is None or failed is None:
        return False
    return success > failed
