"""Which files in ``incoming/`` the app has tried to read and could not.

``GET /api/incoming-lag`` answers *"are there subs on disk that my library has no
row for?"* by comparing the watcher's listing against the ``frames`` tables. It
is a good question and it catches every shape of import failure — but it cannot
tell the two *causes* apart, because both look identical from the outside:

* a sub that **hasn't been imported yet** (a stalled job, a queue, a poll that
  died mid-folder) — which the next scan fixes by itself, and
* a sub that **can never be imported**, because the file is not a readable FITS.

The note it feeds was written for the first, and says so: *"haven't been imported
yet"*, with a **Scan incoming now** button. On the owner's own library six files
of the second kind have sat in five folders since May, so that note has been
promising a fix that no scan can deliver, and will go on promising it for as long
as the files are there. Since v0.452.0 the Jobs page says plainly that those six
could not be read, which makes the contradiction visible rather than merely
wrong: two of the app's own screens, about the same six files, disagreeing about
whether anything is waiting.

**Why it is remembered rather than derived.** Deciding whether a file is readable
means *opening* it, and the lag note's whole design is that nothing it does
walks, opens or ``stat``s anything under ``incoming/`` (AGENTS.md §10) — it is
handed the watcher's existing listing. The scan already opened every one of these
files, so the scan writes down what it found: one JSON value in the registry's
existing ``library_meta`` key/value table, exactly as
:mod:`webapp.skipped_folders` remembers its own finding. No schema change, and a
build that predates the key simply never asks for it.

**Folders, not file names.** The record is keyed by the file's directory
*relative to* ``incoming/``, ``os.sep``-joined — deliberately the spelling both
:attr:`seestack.io.scanner.PlannedUnit.folder` and
:meth:`seestack.io.project.Project.source_folders_under` use, so the reader can
roll it up by prefix beside the other two numbers without translating anything.
The file names live on the Jobs page, where there is room for them.

**Why it cannot go stale into a lie.** Every whole-library scan re-tries every
file it could not read before — that is what made the silence permanent in the
first place — so each scan's answer is complete and simply replaces the last. A
file that has been repaired or deleted is gone from the record the next time a
scan runs, and the note goes back to saying "waiting" about whatever is genuinely
waiting. A *scoped* scan ("bring this one folder in") sees only its own folder
and therefore never rewrites the whole record; it would report every other folder
as clean.

Read-only throughout: nothing here scans, ingests, or writes to ``incoming/``.
"""

from __future__ import annotations

import json
import os

#: Key in the registry's ``library_meta`` table. Additive by construction — the
#: table already exists, so remembering this needs no schema bump.
UNREADABLE_SUBS_META_KEY = "unreadable_incoming_files"

#: Never remember more than a handful of folders. The realistic count is 0; the
#: owner's measured worst case is 5. A library that somehow produced hundreds has
#: a storage problem no note can express, and the reader bounds its list anyway.
#: The cap is applied on the way in, biggest-first, so what survives is what
#: matters most — and the *total* is carried separately so it stays exact.
MAX_REMEMBERED_FOLDERS = 24


def folders_from_scan(scan, incoming_root: str) -> dict[str, int]:  # noqa: ANN001
    """``{folder relative to incoming: n unreadable}`` for one scan's result.

    ``scan`` is a :class:`seestack.io.scanner.ScanResult`. A directory that isn't
    under ``incoming_root`` at all is dropped rather than guessed at — the only
    way that happens is a scan pointed somewhere else, whose answer does not
    belong in this record.
    """
    root = os.path.join(str(incoming_root), "")
    out: dict[str, int] = {}
    for target in getattr(scan, "targets", []):
        for abs_dir, n in getattr(target, "unreadable_dirs", {}).items():
            path = str(abs_dir)
            if path == str(incoming_root).rstrip(os.sep):
                folder = ""          # loose in the drop folder itself
            elif path.startswith(root):
                folder = path[len(root):]
            else:
                continue
            out[folder] = out.get(folder, 0) + int(n)
    return out


def encode_unreadable(folders: dict[str, int]) -> str:
    """The remembered form: ``{"total": N, "folders": [[folder, n], …]}``.

    The total is stored rather than summed from the list so that a library whose
    folder list was capped still reports an honest headline — the list is a
    sample above the cap, the number never is.
    """
    kept = sorted(
        ((f, int(n)) for f, n in folders.items() if int(n) > 0),
        key=lambda item: (-item[1], item[0]),
    )
    return json.dumps({
        "total": sum(n for _f, n in kept),
        "folders": [[f, n] for f, n in kept[:MAX_REMEMBERED_FOLDERS]],
    })


def decode_unreadable(raw: str | None) -> dict[str, int]:
    """Read back :func:`encode_unreadable`, tolerating anything else.

    Read on a poll, so a truncated write, a hand-edited registry or a shape from
    some future version must degrade to "nothing known" rather than 500 the
    Dashboard. The total is deliberately *not* returned: a caller that needs one
    sums the folders it can actually name, so it can never report more than it
    can account for.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    rows = parsed.get("folders")
    if not isinstance(rows, list):
        return {}
    out: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            continue
        folder, n = row
        if not isinstance(folder, str):
            continue
        try:
            count = int(n)
        except (TypeError, ValueError):
            continue
        if count > 0:
            out[folder] = out.get(folder, 0) + count
    return out


def remember_unreadable(lib, folders: dict[str, int]) -> None:  # noqa: ANN001
    """Write one whole-library scan's answer down, replacing the last.

    Replacing rather than merging is the point: the scan re-tries every file, so
    its answer is complete, and a repaired file must be able to leave the record.
    """
    lib.set_meta(UNREADABLE_SUBS_META_KEY, encode_unreadable(folders))


def recall_unreadable(lib) -> dict[str, int]:  # noqa: ANN001
    """What the last whole-library scan could not read, by folder."""
    return decode_unreadable(lib.get_meta(UNREADABLE_SUBS_META_KEY))
