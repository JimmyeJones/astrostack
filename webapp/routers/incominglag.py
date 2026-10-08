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
``/api/upload-destinations`` makes on a page a beginner opens — plus, **only for
a folder more than one target registered**, that folder's ``source_path``s off
the same index, so the two tallies can be de-duplicated instead of added
together (:func:`imported_by_folder`). A library with no double-registered
folder reads not one extra row.

**One definition, one voice.** Which folders a scan would ingest comes from
:func:`seestack.io.scanner.plan_incoming_units`, which applies the *actual*
convention rather than a second copy of its rules, so this note cannot miss a
folder the scan would take or invent one it would not.

**Which folders it deliberately passes over is a second question, and answering
it from a second walk was wrong** (observer issue #1088). The calibration skip is
decided from the frames' own headers, which the plan may not read — so this note
asks what the scan *recorded* as skipped (:mod:`webapp.calibrationskips`),
unioned with the Calibration page's own offer for the builds that predate the
record. See :func:`_skip_folders`. Before that, the exclusion compared a planned
*unit* against a *directory* walk and the two disagreed about where a folder
begins, so a folder of darks one level down was named as waiting over a **Scan
incoming** button that could never import it.

**It offers; it never acts.** Importing is the app's own job and it retries by
itself; the only button is the ordinary "Scan incoming", which is the same thing
the watcher would do on its next poll.

**…except where a scan cannot help, and saying so is the point.** A file the app
has opened and cannot read has no frame row *permanently*, so it counts as
waiting forever and the offer above is a promise nothing can keep — on the
owner's own library, about six files, since May. ``n_unreadable`` carries how
many of the waiting files are in that state, per folder and in total, read off
the record the scan leaves behind (:mod:`webapp.unreadablesubs`) rather than by
opening anything. When it equals ``n_waiting``, nothing is waiting at all and
the reader must drop the offer.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps
from webapp.calibrationskips import recall_calibration_skips
from webapp.incominglag import (
    INCOMING_LAG_MAX,
    SNAPSHOT_MAX_AGE_S,
    FolderLag,
    incoming_lag,
)
from webapp.unreadablesubs import recall_unreadable

router = APIRouter(tags=["incoming-lag"])


class IncomingLagItem(BaseModel):
    folder: str = ""
    target_name: str = ""
    n_on_disk: int = 0
    n_imported: int = 0
    n_waiting: int = 0
    #: Of ``n_waiting``, how many the last whole-library scan opened and could
    #: not read. Those are not waiting for anything — see ``n_unreadable`` on the
    #: response. Additive and defaulted, so an older frontend ignores it.
    n_unreadable: int = 0
    newest_utc: str = ""
    still_hours: float = 0.0


class IncomingLagResponse(BaseModel):
    #: Subs on disk with no frame row anywhere — exact, even when ``items`` is
    #: truncated. Zero is the ordinary answer and the caller renders nothing.
    n_waiting: int = 0
    #: How many folders those are spread across (exact, likewise).
    n_folders: int = 0
    #: Of ``n_waiting``, how many the last whole-library scan **opened and could
    #: not read** — damaged or headerless files that no scan will ever import.
    #: Zero until a scan has run on this build, and zero on every healthy
    #: install, so the note reads exactly as it did before. When it equals
    #: ``n_waiting``, *nothing* is actually waiting and the note must not offer a
    #: scan. See ``webapp/unreadablesubs.py``.
    n_unreadable: int = 0
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
    """How many **distinct** registered frames sit in each folder under
    ``prefix``, across every target.

    This was a plain sum across targets until v0.492.35, and the sum is what made
    the note go quiet exactly where it was built to speak. ``source_path`` is
    ``UNIQUE`` per target, so a folder only *one* target registered is already
    exact and is still answered by the one grouped ``COUNT``. A folder **two**
    targets registered — issue #878's mosaic double-registration, which covers
    76 % of the owner's frames — had its two tallies added together, so the
    folder read as about twice as imported as it is; :func:`incoming_lag`'s
    ``waiting <= 0`` guard then dropped it, and the one signal built to catch
    subs that silently never imported (v0.442.0) was dark on 30 of 54 of his drop
    folders, a combined 41,727 subs.

    The sum was a deliberate choice and its reasoning still holds in *direction*:
    a double registration can only ever make the waiting count smaller, so this
    note could only under-report, never cry wolf. What was never measured is by
    **how much** — enough to hide whole nights.

    So a folder more than one target claims is counted by its distinct
    ``source_path``s (:meth:`~seestack.io.project.Project.source_paths_in_folder`)
    in :func:`_count_shared_folders_distinctly`, which is right by construction in
    both directions: it cannot over-count the way the sum did, and it cannot
    *under*-count the way a ``max`` across targets would on two targets holding
    genuinely disjoint subsets of one folder — which would make this note
    over-report, the one direction it is designed never to go. The extra read is
    paid only where targets really overlap, so on a library with no double
    registration — every other install, and this one for every folder but
    those — not one extra row is read and the answer is byte-for-byte the old one.

    A broken project DB is skipped exactly as the other cross-target reads skip
    it, so one corrupt target cannot cost the whole answer.
    """
    from seestack.io.project import Project

    out: dict[str, int] = {}
    # Which targets registered each folder, so the de-duplication below can tell
    # "already exact" from "two tallies of possibly the same files".
    claimed_by: dict[str, list] = {}
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
            claimed_by.setdefault(folder, []).append(t)
    _count_shared_folders_distinctly(lib, prefix, out, claimed_by)
    return out


def _count_shared_folders_distinctly(lib, prefix: str, out: dict[str, int],  # noqa: ANN001
                                     claimed_by: dict[str, list]) -> None:
    """Replace the summed tally of each folder **two or more targets claim** with
    its distinct ``source_path`` count, in place. See :func:`imported_by_folder`.

    Grouped by target rather than by folder, so a project opens once however many
    shared folders it holds. Peak memory is the relative paths of the shared
    folders alone and nothing at all on a library with none; the paths are
    relative to ``prefix`` because that is the part that tells two frames apart.

    **A folder whose de-duplication could not be completed keeps its summed
    tally** — a target that opened for the counts above and not here leaves its
    frames out of the union, and an under-count is the direction that makes this
    note cry wolf. Falling back to the old, quieter number is the safe failure.
    """
    from seestack.io.project import Project

    entries: dict[str, object] = {}
    wanted: dict[str, list[str]] = {}
    for folder, targets in claimed_by.items():
        if len(targets) < 2:
            continue
        for t in targets:
            entries[t.safe_name] = t
            wanted.setdefault(t.safe_name, []).append(folder)
    if not wanted:
        return

    seen: dict[str, set[str]] = {}
    incomplete: set[str] = set()
    for safe, folders in wanted.items():
        proj = None
        try:
            proj = Project.open(lib.target_dir(entries[safe]))
            for folder in folders:
                seen.setdefault(folder, set()).update(
                    proj.source_paths_in_folder(prefix, folder))
        except Exception:  # noqa: BLE001 — a refinement must not 500 the note
            incomplete.update(folders)
        finally:
            if proj is not None:
                proj.close()
    for folder, paths in seen.items():
        if folder not in incomplete:
            out[folder] = len(paths)


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
        # What the last whole-library scan opened and could not read, off the
        # registry's own meta table — one keyed read beside the per-target counts
        # already being made, and still nothing opened under ``incoming/``.
        try:
            unreadable = recall_unreadable(lib)
        except Exception:  # noqa: BLE001 — a side note must not 500 the note
            unreadable = {}
        # Which units the last whole-library scan actually passed over as
        # calibration data, off the same meta table — see ``_skip_folders``.
        try:
            scan_skipped = recall_calibration_skips(lib)
        except Exception:  # noqa: BLE001 — a side note must not 500 the note
            scan_skipped = set()
    finally:
        lib.close()
    return (incoming_lag(units, imported, now_epoch, unreadable=unreadable,
                         skip_folders=_skip_folders(request, scan_skipped)),
            polled_at)


def _skip_folders(request: Request, scan_skipped: set[str]) -> set[str]:
    """Folders this note must not name, from the two things that know.

    Both sides answer with a :attr:`~seestack.io.scanner.PlannedUnit.folder`
    spelling, so :func:`~webapp.incominglag.incoming_lag` compares them with
    plain equality — which is what keeps a dark folder nested inside a **light**
    unit (``M 42_sub/darks/``) from silencing that unit's genuine lag, as a prefix
    roll-up would.

    * What the last whole-library scan **passed over** (``scan_skipped``,
      :mod:`webapp.calibrationskips`) — authoritative, because it is the unit the
      scan really skipped, read off the frames' own headers. Empty until a scan
      has run on this build, which is why the second source stays.
    * What the Calibration page's ``incoming/`` walk **offers**
      (:func:`_calibration_folders`) — today's behaviour exactly, and right
      whenever the frames sit directly in a top-level folder, which is the shape
      the page's own build form asks for.

    The union, because each is sound on its own: a folder either side names is
    one no scan will import. Neither can over-silence a folder of real subs —
    the first is a verdict the scan reached from the frames, the second a verdict
    ``discover`` reached from the frames.
    """
    return _calibration_folders(request) | scan_skipped


def _calibration_folders(request: Request) -> set[str]:
    """Folders under ``incoming/`` the scan passes over as calibration data.

    These hold darks or flats — the Calibration page's own build form asks the
    owner to put them exactly there — and since v0.455.0 the scan leaves them
    alone instead of minting a "Darks 10s" target of six lights. They are
    therefore not waiting for an import and never will be, so this note must not
    name them; without this it would complain forever about the folder the app
    itself asked for.

    Read off the walk :func:`webapp.calibration.cached_incoming_folders` already
    keeps for the Calibration page's offer, so nothing extra is opened under
    ``incoming/`` and the two surfaces answer from one list.

    **One of two sources, not the whole answer** — see :func:`_skip_folders`.
    v0.455.0 argued this *was* the whole answer, because the scanner's skip
    carries ``discover.MIN_FRAMES`` and so "a folder could not fall between
    them". That holds only while the calibration frames sit **directly** in a
    top-level folder: the scan plans a *recursive unit* (``Darks``) where this
    walk names an *individual directory* (``Darks/20s``), and the Calibration
    page's own ``discover.MAX_DEPTH = 2`` invites that nesting — so the note
    offered a scan it could never fulfil (observer issue #1088). What the scan
    actually skipped now travels from the scan itself
    (:mod:`webapp.calibrationskips`); this stays because it is right for the flat
    shape and answers on a build that has not scanned yet.

    Never raises — on any failure the note simply behaves as it did before.
    """
    from webapp import calibration

    try:
        settings = deps.get_settings(request)
        folders = calibration.cached_incoming_folders(
            request.app.state, settings.resolved_incoming_dir)
    except Exception:  # noqa: BLE001 — a refinement must not 500 the note
        return set()
    # ``rel_path`` is posix-spelled for display; ``PlannedUnit.folder`` uses the
    # platform separator, and these two strings have to compare equal.
    return {str(f.rel_path).replace("/", os.sep) for f in folders}


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
        n_unreadable=sum(f.n_unreadable for f in found),
        checked_utc=datetime.fromtimestamp(polled_at, UTC)
        .replace(microsecond=0).isoformat(),
        checked=True,
        items=[IncomingLagItem(**asdict(f)) for f in found[:INCOMING_LAG_MAX]],
    )
