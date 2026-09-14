""""Some of your subs never made it into your library."

``GET /api/incoming-lag`` answers, for the whole drop folder at once: *which
folders under ``incoming/`` hold FITS that no target has a frame row for?*

**Why it needs its own endpoint, next to the queue note.**
``GET /api/jobs/queue-health`` (:mod:`webapp.jobqueue`) says so when an import
job is **queued** behind the single serial worker. That is how the owner's
eleven-day stall happened, and it is now visible — but it is one of several ways
the same thing happens, and the others leave nothing queued at all: a poll that
walked a folder during a job that later died, a scan-side error swallowed before
a row is written, a classification skip. The queue note cannot see any of those,
because there is no job to look at. This one can, because it does not ask about
jobs: it compares what is on disk with what is in the library.

**Cost, and the rule it obeys.** Nothing here walks, opens or ``stat``s anything
under ``incoming/`` (AGENTS.md §10) — the watcher's poll already holds that
listing and :meth:`webapp.watcher.Watcher.incoming_units` hands it over. The
library side is one grouped ``COUNT`` per target off an existing index
(:meth:`seestack.io.project.Project.source_folders_under`), the same read
``/api/upload-destinations`` makes on a page a beginner opens.

**One definition, one voice.** Which folders a scan would ingest — and which are
deliberately passed over — comes from
:func:`seestack.io.scanner.plan_incoming_units`, which applies the *actual*
convention rather than a second copy of its rules. So this note cannot name a
folder the scanner skips on purpose, and cannot miss one it would take.

**It offers; it never acts.** Importing is the app's own job and it retries by
itself; the only button is the ordinary "Scan incoming", which is the same thing
the watcher would do on its next poll.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps
from webapp.incominglag import (
    INCOMING_LAG_MAX,
    SNAPSHOT_MAX_AGE_S,
    FolderLag,
    incoming_lag,
)

router = APIRouter(tags=["incoming-lag"])


class IncomingLagItem(BaseModel):
    folder: str = ""
    target_name: str = ""
    n_on_disk: int = 0
    n_imported: int = 0
    n_waiting: int = 0
    newest_utc: str = ""
    still_hours: float = 0.0


class IncomingLagResponse(BaseModel):
    #: Subs on disk with no frame row anywhere — exact, even when ``items`` is
    #: truncated. Zero is the ordinary answer and the caller renders nothing.
    n_waiting: int = 0
    #: How many folders those are spread across (exact, likewise).
    n_folders: int = 0
    #: When the listing this is measured against was taken, ISO-8601 UTC. Empty
    #: when there is no usable listing, which is also when ``n_waiting`` is 0 for
    #: a reason other than "nothing is waiting" — see :attr:`checked`.
    checked_utc: str = ""
    #: False when no fresh listing was available (the watcher is off, wedged, or
    #: the app has only just started), so a reader can tell "nothing is waiting"
    #: from "nobody has looked". Everything else is zero in that case.
    checked: bool = False
    items: list[IncomingLagItem] = []


def imported_by_folder(lib, prefix: str) -> dict[str, int]:  # noqa: ANN001
    """How many registered frames sit in each folder under ``prefix``, summed
    across every target.

    Summed rather than kept per target on purpose: a folder registered under two
    targets — the mosaic double-registration of issue #878 — must not read as
    half-imported, and summing means a double registration can only ever make the
    waiting count *smaller*. A broken project DB is skipped exactly as the other
    cross-target reads skip it, so one corrupt target cannot cost the whole
    answer; the cost of that is an under-count, i.e. a folder that may speak when
    it should not, which is why it is logged nowhere and bounded to one target.
    """
    from seestack.io.project import Project

    out: dict[str, int] = {}
    for t in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            folders = proj.source_folders_under(prefix)
        except Exception:  # noqa: BLE001 — one broken target must not 500 the note
            continue
        finally:
            if proj is not None:
                proj.close()
        for folder, n in folders:
            out[folder] = out.get(folder, 0) + int(n)
    return out


def scan_incoming_lag(
    request: Request, now_epoch: float,
) -> tuple[list[FolderLag], float]:
    """``(folders behind, when the listing was taken)``.

    ``polled_at`` is ``0.0`` when there is no fresh listing to judge — no
    watcher, none recorded yet, or one older than :data:`SNAPSHOT_MAX_AGE_S` —
    and the folder list is then empty *for that reason*, which is a different
    statement from "nothing is waiting" and is reported as one.
    """
    watcher = getattr(request.app.state, "watcher", None)
    if watcher is None:
        return ([], 0.0)
    units, polled_at = watcher.incoming_units()
    if polled_at <= 0 or (now_epoch - polled_at) > SNAPSHOT_MAX_AGE_S:
        return ([], 0.0)
    settings = deps.get_settings(request)
    # The trailing separator matters: without it a sibling like `incoming2/`
    # matches (the same reasoning as `source_frames_under`'s other callers).
    prefix = os.path.join(str(settings.resolved_incoming_dir), "")
    lib = deps.open_library(request)
    try:
        imported = imported_by_folder(lib, prefix)
    finally:
        lib.close()
    return (incoming_lag(units, imported, now_epoch), polled_at)


@router.get("/api/incoming-lag", response_model=IncomingLagResponse)
def get_incoming_lag(request: Request) -> IncomingLagResponse:
    """Subs sitting in ``incoming/`` that the library has no row for."""
    now_epoch = time.time()
    found, polled_at = scan_incoming_lag(request, now_epoch)
    if polled_at <= 0:
        return IncomingLagResponse()
    return IncomingLagResponse(
        n_waiting=sum(f.n_waiting for f in found),
        n_folders=len(found),
        checked_utc=datetime.fromtimestamp(polled_at, UTC)
        .replace(microsecond=0).isoformat(),
        checked=True,
        items=[IncomingLagItem(**asdict(f)) for f in found[:INCOMING_LAG_MAX]],
    )
