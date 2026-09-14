"""Are there subs in your incoming folder that never reached your library?

The failure this answers is **silent by construction**. A frame that was never
imported has no QC row, no reject reason and no place in the record where it can
be *seen* to be absent — it simply is not there, and every target keeps showing
the count it had before. So a library can quietly stop growing while the app
looks completely healthy, and the only person who can notice is the one who
counts the files on disk by hand.

Reported 2026-09-14 by the on-NAS observer against the owner's real library:
2,259 subs across two full nights sat in ``incoming/`` for eleven days, in no
``frames`` table anywhere. :mod:`webapp.jobqueue` (v0.441.1) says so when an
import job is *queued* behind the single worker, which is how it happened that
time — but that is only one of the ways it happens. A watcher poll that walked a
folder during a job that later died, a scan-side error swallowed before a row is
written, or a classification skip all leave **nothing queued**, so the queue note
stays quiet. The one signal that catches every shape is the direct one: files
under ``incoming/`` that no target has a frame row for.

**Nothing here walks ``incoming/``.** The watcher already stats every FITS under
it on every poll (:meth:`webapp.watcher.Watcher.poll_once`), so the listing is a
by-product this module is handed rather than a second walk of the one tree the
app may never write to (AGENTS.md §10). The library side is
:meth:`seestack.io.project.Project.source_folders_under`, one grouped ``COUNT``
per target off an existing index.

**It is shaped to under-report rather than cry wolf.** Three rules:

* Only folders a scan would actually *ingest* count. The convention's skips —
  a Seestar's own on-device output beside its raw subs, ``*_video``/``*_photo``
  captures, another program's scratch directory — are deliberate, not lag, and
  they are excluded by asking :func:`seestack.io.scanner.plan_incoming_units`,
  which is the convention itself rather than a second copy of its rules.
* A folder speaks only once its newest file has stopped moving for
  :data:`LAG_MIN_AGE_S`. A night still being copied over SMB is *supposed* to be
  ahead of the library, and so is one the watcher noticed four minutes ago.
* Registered frames are rolled up **by folder prefix**, so a target whose subs
  sit deeper than its unit folder still counts against it, and a folder
  registered under two targets (the mosaic double-registration of issue #878)
  can only ever make the waiting count *smaller*, never larger.

Pure: mappings in, dataclasses out, the clock passed in. No request, no library,
no filesystem.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from seestack.io.scanner import PlannedUnit

#: How long a folder's newest file must have been still before its unimported
#: files are called lag, in seconds. Two hours, deliberately the same number as
#: :data:`webapp.jobqueue.IMPORT_WAIT_MIN_HOURS` — the two notes describe the
#: same delay from opposite ends and should not disagree about when it starts
#: being one. Comfortably longer than a poll interval (5 min) and than an
#: ordinary import of a night's subs, and far short of the days that were
#: measured.
LAG_MIN_AGE_S = 2 * 3600.0

#: How stale the watcher's listing may be before this declines to answer at all.
#: The listing is a snapshot; a folder imported since it was taken would still
#: read as waiting. One hour is many poll intervals, so a *live* watcher is never
#: refused, while a watcher that is switched off, wedged, or was never started
#: leaves the note silent rather than repeating an old count forever.
SNAPSHOT_MAX_AGE_S = 3600.0

#: How many folders the response names outright. The counts are exact; this only
#: bounds the list, the same way the other library-wide notes bound theirs.
INCOMING_LAG_MAX = 12


@dataclass(frozen=True)
class FolderLag:
    """One folder of ``incoming/`` holding subs the library has no row for."""

    #: The folder, relative to ``incoming/`` (``""`` = loose in the root).
    folder: str
    #: The target a scan would file these under — which may not exist yet.
    target_name: str
    n_on_disk: int
    n_imported: int
    #: ``n_on_disk - n_imported``, floored at zero.
    n_waiting: int
    #: When the folder last changed, ISO-8601 UTC — i.e. how long these have
    #: been sitting there. Empty when the listing carried no usable mtime.
    newest_utc: str
    #: Hours since that moment, rounded to one decimal.
    still_hours: float


def _rollup(imported: Mapping[str, int], folder: str) -> int:
    """Registered frames belonging to unit ``folder``.

    A unit folder is scanned recursively, so a frame at
    ``M 42_sub/night2/x.fit`` belongs to the ``M 42_sub`` unit and is reported by
    ``source_folders_under`` under the deeper name. Summing by prefix is what
    keeps those from reading as never-imported. The root unit (``""``, the
    ``Unsorted`` catch-all) is the exception and matches exactly: its files sit
    *loose* in the root, and rolling every folder in the library into it would
    make the one unit that cannot be nested swallow all the others.
    """
    if not folder:
        return int(imported.get("", 0))
    prefix = folder + os.sep
    return sum(int(n) for key, n in imported.items()
               if key == folder or key.startswith(prefix))


def incoming_lag(
    planned: Sequence[PlannedUnit],
    imported: Mapping[str, int],
    now_epoch: float,
    *,
    min_age_s: float = LAG_MIN_AGE_S,
) -> list[FolderLag]:
    """Folders whose files a scan would ingest but the library has no row for,
    most-waiting first.

    ``planned`` is :func:`seestack.io.scanner.plan_incoming_units` over the
    watcher's listing; ``imported`` maps a folder (as
    ``Project.source_folders_under`` spells it) to how many registered frames sit
    in it, summed across every target.
    """
    out: list[FolderLag] = []
    for unit in planned:
        n_imported = _rollup(imported, unit.folder)
        waiting = unit.n_files - n_imported
        if waiting <= 0:
            continue
        # A folder that is still growing is not behind — it is being written.
        # An unknown mtime (0.0) is treated as "not old enough to judge" for the
        # same reason: silence is the safe answer when the evidence is missing.
        still_s = now_epoch - unit.newest_mtime if unit.newest_mtime > 0 else 0.0
        if still_s < min_age_s:
            continue
        out.append(FolderLag(
            folder=unit.folder,
            target_name=unit.target_name,
            n_on_disk=unit.n_files,
            n_imported=n_imported,
            n_waiting=waiting,
            newest_utc=datetime.fromtimestamp(unit.newest_mtime, UTC)
            .replace(microsecond=0).isoformat(),
            still_hours=round(still_s / 3600.0, 1),
        ))
    # Most waiting first, name as a tiebreak so the order is stable between
    # polls and a folder does not jump around under the reader's cursor.
    out.sort(key=lambda f: (-f.n_waiting, f.folder))
    return out
