""""This target stopped producing pictures, and here's why."

``GET /api/stack-failures`` answers, for the whole library at once: *which
targets' most recent stack attempt failed, and has nothing succeeded since?*

It exists because a walk-away stack that refuses goes dark otherwise. The
engine's refusal already names the one lever that would make the run fit and the
memory it lands at (``stacker._best_memory_fix``), but on the unattended path
that sentence is caught per target and filed in the scan job's result — a place
nobody looks. This carries it to the two screens the owner does look at.

Deliberately read-only and cheap: it scans the recent job history (one query),
and opens a project DB **only** for a target that actually has a failure to
report — normally none at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps
from webapp.stackfailure import latest_stack_failures, superseded_by_success

router = APIRouter(tags=["stack-failures"])

#: How far back through the job history to look. A failure older than this has
#: had hundreds of jobs run since it — on an install that busy, a later stack has
#: almost certainly succeeded and would have retired the note anyway.
_JOB_SCAN_LIMIT = 200

#: Sort floor for a failure with no usable stamp — it sorts last rather than
#: dropping out of the list.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class StackFailureOut(BaseModel):
    safe: str
    name: str
    message: str
    kind: str | None = None
    when_utc: str | None = None
    unattended: bool = False


class StackFailuresResponse(BaseModel):
    failures: list[StackFailureOut]


def _last_stack_utc(lib, entry) -> str | None:  # noqa: ANN001, ANN202
    """Timestamp of this target's newest stack run, or ``None`` if it has none."""
    from seestack.io.project import Project

    proj = None
    try:
        proj = Project.open(lib.target_dir(entry))
    except Exception:  # noqa: BLE001 — an unreadable project must not 500 the page
        if proj is not None:
            proj.close()
        return None
    try:
        run = next(iter(proj.iter_stack_runs()), None)
        return run.timestamp_utc if run is not None else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        proj.close()


@router.get("/api/stack-failures", response_model=StackFailuresResponse)
def get_stack_failures(request: Request) -> StackFailuresResponse:
    """Targets whose most recent stack attempt failed with nothing since."""
    jm = deps.get_job_manager(request)
    failures = latest_stack_failures(jm.list(limit=_JOB_SCAN_LIMIT))
    if not failures:
        return StackFailuresResponse(failures=[])

    out: list[StackFailureOut] = []
    lib = deps.open_library(request)
    try:
        by_safe = {t.safe_name: t for t in lib.list_targets()}
        for safe, failure in failures.items():
            entry = by_safe.get(safe)
            if entry is None:
                # The target was deleted (or renamed) since it failed — there is
                # nothing left to fix, so there is nothing to say.
                continue
            if superseded_by_success(failure, _last_stack_utc(lib, entry)):
                continue
            out.append(StackFailureOut(
                safe=safe, name=entry.name, message=failure.message,
                kind=failure.kind, when_utc=failure.when_utc,
                unattended=failure.unattended,
            ))
    finally:
        lib.close()

    # Newest first, so the Dashboard's first line is the freshest problem.
    # Parsed rather than string-compared: these stamps all come from the job
    # manager today, but a raw string sort silently mis-orders the moment one
    # arrives in another of the app's UTC shapes.
    from seestack.activity_calendar import parse_utc
    out.sort(key=lambda f: (parse_utc(f.when_utc or "") or _EPOCH), reverse=True)
    return StackFailuresResponse(failures=out)
