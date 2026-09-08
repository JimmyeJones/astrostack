"""The folders a scan walked past, kept somewhere the owner will actually look.

A bare ``<T>/`` folder sitting beside ``<T>_sub/`` is skipped by the Seestar
folder convention, because on a Seestar it is the finished picture the scope made
for itself. That skip is right, and it stays. But it does not look inside, so a
plainly-named folder of the owner's **own raw subs** is passed over the same way
— the owner's ``NGC 6888`` holds 4,815 files beside an ``NGC 6888_SUB`` of 3,110
different ones. Since v0.329.2 such a folder is *reported* when its files aren't
named like the device's output, and since v0.378.0 the report carries a button
that brings it in.

Both of those live on the **Jobs page**, attached to one scan's result — and on
this install the scan that finds it is usually the watcher's, fired while nobody
is at the screen. The finding is therefore true, actionable, and unseen: it
renews itself on the next scan and scrolls away again. What was missing is a
**standing** home for it beside the Library's other hygiene nudges.

**Why it is remembered rather than recomputed.** Deriving the answer at poll time
means walking ``incoming/`` on every poll — thousands of files, on the one tree
this app may never write to (AGENTS.md §10) — which is exactly the trade the
Library's other nudges are shaped to avoid. The scan already computed it, so the
scan writes it down: one JSON value in the registry's existing ``library_meta``
key/value table (no schema change, and an older build simply never reads the
key), and the poll reads that.

**Why it stops nagging.** A standing card that renewed itself every scan would
still be shouting after the owner brought the folder in — the convention keeps
skipping the folder, so the *scan* keeps reporting it. So a remembered folder is
dropped as soon as the target it belongs to owns even one frame from inside it:
the owner acted, and "these frames aren't reaching your stack" has stopped being
true. A folder that has since left ``incoming/`` drops out too.

Read-only throughout: nothing here scans, ingests, writes to ``incoming/``, or
changes what any scan does.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from seestack.io.library import make_safe_name
from seestack.io.scanner import target_name_for_folder

#: Key in the registry's ``library_meta`` table. Additive by construction — the
#: table already exists, so remembering this needs no schema bump, and a build
#: that predates the key ignores a value it never asks for.
SKIPPED_FOLDERS_META_KEY = "unvouched_skipped_folders"

#: Never remember more than a handful. The realistic count is 0 or 1; a library
#: that somehow produced dozens has a naming problem the card cannot fix, and a
#: hundred-row alert on the Library page would be worse than silence. The cap is
#: applied on the way in, biggest-first, so what survives is what matters most.
MAX_REMEMBERED = 12


@dataclass(frozen=True)
class SkippedFolder:
    """One folder a scan passed over that it could not fully account for.

    ``path`` is the folder on disk, exactly as the server named it. It is what
    makes the record actionable — posted back as ``POST /api/scan``'s ``root`` it
    brings that one folder in — and it is re-confined server-side on the way in,
    like any other scan root.
    """

    name: str          # the folder's own name on disk
    path: str          # the folder, absolute, as the scan named it
    n_files: int       # FITS files inside it
    n_unvouched: int   # of those, files not named like the device's own picture
    #: Which rule skipped it — ``"device_output"`` (a bare ``<T>/`` beside a
    #: ``<T>_sub/``) or ``"temp_folder"`` (another program's scratch directory,
    #: by name). The card cannot describe both with one sentence, and describing
    #: a temp folder as "your Seestar's own finished picture" would be a plain
    #: untruth. Defaulted so a value remembered by an older build reads as the
    #: only case that build could produce.
    reason: str = "device_output"


def encode_skipped_folders(records: list[SkippedFolder]) -> str:
    """The remembered form: a JSON array, biggest shortfall first and capped.

    Ordering is part of the record rather than the reader's job, so every
    consumer sees the same "the one that matters most" first."""
    ordered = sorted(records, key=lambda r: (-r.n_unvouched, r.name))
    return json.dumps([
        {"name": r.name, "path": r.path,
         "n_files": r.n_files, "n_unvouched": r.n_unvouched,
         "reason": r.reason}
        for r in ordered[:MAX_REMEMBERED]
    ])


def decode_skipped_folders(raw: str | None) -> list[SkippedFolder]:
    """Read back :func:`encode_skipped_folders`, tolerating anything else.

    The value is read on a poll, so a truncated write, a hand-edited registry or
    a shape from some future version must degrade to "nothing to say" rather than
    500 the Library page."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[SkippedFolder] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        path = item.get("path")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(path, str) or not path:
            continue
        try:
            n_files = int(item.get("n_files") or 0)
            n_unvouched = int(item.get("n_unvouched") or 0)
        except (TypeError, ValueError):
            continue
        raw_reason = item.get("reason")
        reason = raw_reason if raw_reason in ("device_output", "temp_folder") \
            else "device_output"
        # A device-output skip earns its line by holding files the device's
        # naming can't vouch for; a temp folder earns it by being a guess about
        # another program's directory, so it is reported whatever is inside it
        # (and reporting it is what makes it recoverable — see the card).
        if n_unvouched <= 0 and reason != "temp_folder":
            continue
        out.append(SkippedFolder(
            name=name, path=path,
            n_files=max(n_files, n_unvouched), n_unvouched=n_unvouched,
            reason=reason,
        ))
    return out


def _inside(folder: str, source_path: str) -> bool:
    """Is ``source_path`` a file inside ``folder``?

    Both sides are put through ``os.path.realpath`` before comparing, for the
    same reason ingest's own dedup key is: one physical file has several
    spellings (a symlinked share, a relative root, a trailing ``..``), and a
    prefix test on raw strings would answer "no" for a frame that is plainly
    inside the folder. Compared with a separator appended so ``/data/M 42`` never
    swallows ``/data/M 42_sub``."""
    try:
        base = os.path.realpath(folder)
        candidate = os.path.realpath(source_path)
    except (OSError, ValueError):  # pragma: no cover — realpath is lenient
        return False
    return candidate.startswith(base.rstrip(os.sep) + os.sep)


def already_brought_in(lib, record: SkippedFolder) -> bool:  # noqa: ANN001
    """Has the owner already brought this folder in?

    True once the target the folder belongs to owns **any** frame from inside it.
    Any, not all: the question the card answers is "is this folder missing from
    my pictures?", and the moment the owner pressed the button the answer became
    no. A handful of files that failed to read are the scan job's business to
    report, not a reason to keep a standing alert up for ever.

    The folder is mapped to its target through the scanner's own
    :func:`~seestack.io.scanner.target_name_for_folder`, the same function the
    scoped scan names its target with — so this cannot disagree with where those
    frames actually landed.

    Read-only: opens the one project, reads one column, closes it."""
    entry = lib.find_target(make_safe_name(target_name_for_folder(record.name)))
    if entry is None:
        return False
    proj = lib.open_target(entry.safe_name)
    try:
        return any(_inside(record.path, s) for s in proj.source_paths())
    finally:
        proj.close()


def still_missing(lib, records: list[SkippedFolder]) -> list[SkippedFolder]:  # noqa: ANN001
    """The records still worth showing: the folder is still on disk, and none of
    its frames have reached the library yet.

    Cheap because the list is normally empty — one ``exists()`` and, at most, one
    project read per remembered folder."""
    out: list[SkippedFolder] = []
    for record in records:
        if not os.path.isdir(record.path):
            continue
        if already_brought_in(lib, record):
            continue
        out.append(record)
    return out


def remember_skipped_folders(lib, records: list[SkippedFolder]) -> None:  # noqa: ANN001
    """Replace what the library remembers with ``records``.

    An empty list is written, not skipped: a whole-incoming scan that finds
    nothing unexplained is the signal that a previously-remembered folder has
    been dealt with (renamed on the NAS, brought in, or removed), and the card
    must go quiet."""
    lib.set_meta(SKIPPED_FOLDERS_META_KEY, encode_skipped_folders(records))


def recall_skipped_folders(lib) -> list[SkippedFolder]:  # noqa: ANN001
    """What the last scan remembered, filtered to what is still true."""
    return still_missing(
        lib, decode_skipped_folders(lib.get_meta(SKIPPED_FOLDERS_META_KEY)))
