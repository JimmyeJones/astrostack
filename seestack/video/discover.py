"""Find the Seestar's Solar/Lunar video captures in the incoming folder.

The Seestar names these folders ``<Target>_video/`` — the same suffix the FITS
scanner deliberately *skips* (``seestack.io.scanner._VIDEO_SUFFIX``) because
they hold no stackable deep-sky subs. This module is the other half of that
decision: the folders the scanner walks past are exactly the ones the lucky
stacker wants.

Nothing here reads or decodes a video; it is a cheap directory walk safe to run
on every page load.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

#: Container extensions the Seestar (and phones/cameras generally) produce.
VIDEO_EXTENSIONS = frozenset({".mp4", ".avi", ".mov", ".mkv", ".m4v"})

#: Folder suffix that marks a video capture. Matches the FITS scanner's constant
#: (kept separate so neither module has to import the other).
_VIDEO_SUFFIX = "_video"

#: How deep below the incoming root to look for ``*_video`` folders. The Seestar
#: drops them at the top level; one extra level covers a user who filed their
#: captures under a per-night folder. Deeper than that is somebody's whole
#: archive and not worth walking on every request.
_MAX_DEPTH = 2


def _kind_for(base_name: str) -> str:
    """``"lunar"`` / ``"solar"`` / ``"other"`` from the Seestar's folder prefix."""
    low = base_name.strip().lower()
    if low.startswith("lunar") or low.startswith("moon"):
        return "lunar"
    if low.startswith("solar") or low.startswith("sun"):
        return "solar"
    return "other"


#: Plain-language name for each kind, used in the UI so a beginner sees "Moon"
#: rather than "Lunar_video".
_LABELS = {"lunar": "Moon", "solar": "Sun"}


def video_capture_id(folder_name: str) -> str:
    """Stable, path-safe id for a capture folder.

    The web layer addresses captures by this id and re-discovers the folder
    server-side, so a client can never hand us a filesystem path (the same rule
    the calibration masters follow).
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", folder_name.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "video"


@dataclass(frozen=True)
class VideoCapture:
    """One ``*_video/`` folder and the video files inside it."""

    id: str
    #: The folder name as it is on disk, e.g. ``"Lunar_video"``.
    folder_name: str
    #: Absolute path of the folder.
    folder: str
    #: ``"lunar"`` | ``"solar"`` | ``"other"``.
    kind: str
    #: Friendly name for the UI: "Moon", "Sun", or the folder's base name.
    label: str
    #: Absolute paths of the video files, sorted by name (stable ordering).
    files: tuple[str, ...]
    total_bytes: int
    #: The per-night folder this capture sits in, set only when another capture
    #: has the same folder name (``2026-10-05/Lunar_video`` beside
    #: ``2026-10-01/Lunar_video``) so the list can tell them apart; else ``""``.
    night: str = ""

    @property
    def n_files(self) -> int:
        return len(self.files)


def _video_files_in(folder: Path) -> list[Path]:
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    return [
        p for p in entries
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS and not p.name.startswith(".")
    ]


#: ``claimed_by(bare_id)`` → the file name of the clip a stored result under that
#: id was made from, or ``None``. Supplied by the web layer, which owns the
#: result store; the engine only uses it to keep an existing result attached.
ClaimLookup = Callable[[str], "str | None"]


def find_video_captures(
    root: str | Path, *, claimed_by: ClaimLookup | None = None,
) -> list[VideoCapture]:
    """List every ``*_video/`` folder under ``root`` that holds a video file.

    Folders with no readable video file are omitted — an empty ``Lunar_video/``
    left behind by a previous transfer is not something to offer the user a
    "Stack video" button for. Results are sorted by label so the list is stable
    between calls.

    Ids: a folder whose name is unique keeps the bare :func:`video_capture_id`,
    so every result stored before this rule existed stays attached. Folders
    that share a name — the per-night layout repeats ``Lunar_video`` every
    night — are all listed; one of them keeps the bare id (see
    :func:`_bare_id_holder`) and the others get an id that includes their night
    folder (``2026-10-05_Lunar_video``), derived from the *path*, so it does not
    change as more nights are added.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return []

    # (folder, video files, depth), in walk order: depth-first, each directory's
    # children sorted by name — the "path order" every tie below falls back to.
    candidates: list[tuple[Path, list[Path], int]] = []

    def walk(folder: Path, depth: int) -> None:
        # ``os.scandir`` rather than ``iterdir`` + ``sorted``: it streams dirents
        # and answers ``is_dir()`` from the entry itself, so a target folder
        # holding thousands of subs costs one readdir instead of thousands of
        # stats plus a full sort of paths we're going to ignore.
        #
        # Every entry is examined, deliberately. An earlier revision capped the
        # entries read per directory to bound the work on a poll — but ``scandir``
        # returns entries in filesystem order, so the cap decided *at random*
        # whether a capture filed alongside a lot of sub-frames was found at all.
        # A user's video going missing depending on inode order is far worse than
        # one extra readdir, and the directory listing is a single streamed
        # syscall either way; the caller keeps the poll rate low instead.
        children: list[Path] = []
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            children.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            return
        children.sort(key=lambda p: p.name.lower())
        for child in children:
            if child.name.startswith("."):
                continue
            if child.name.lower().endswith(_VIDEO_SUFFIX):
                files = _video_files_in(child)
                if files:
                    candidates.append((child, files, depth))
            elif depth < _MAX_DEPTH:
                walk(child, depth + 1)

    walk(root_path, 1)

    groups: dict[str, list[int]] = {}
    for i, (child, _files, _depth) in enumerate(candidates):
        groups.setdefault(video_capture_id(child.name), []).append(i)

    # First the ids nobody else can take: every unique folder's bare id and each
    # collision's holder. Then the rest, qualified by night and, if even that is
    # taken (two spellings of one name in one folder), numbered in path order.
    ids: dict[int, str] = {}
    nights: dict[int, str] = {}
    pending: list[tuple[int, str]] = []
    for bare, members in groups.items():
        if len(members) == 1:
            ids[members[0]] = bare
            continue
        holder = _bare_id_holder(bare, [candidates[m] for m in members], claimed_by)
        for pos, m in enumerate(members):
            child, _files, depth = candidates[m]
            if depth > 1:
                nights[m] = child.parent.name
            if pos == holder:
                ids[m] = bare
            elif depth > 1:
                pending.append((m, video_capture_id(f"{child.parent.name}_{child.name}")))
            else:
                pending.append((m, bare))
    taken = set(ids.values())
    for m, wanted in sorted(pending):
        cid, n = wanted, 1
        while cid in taken:
            n += 1
            cid = f"{wanted}-{n}"
        taken.add(cid)
        ids[m] = cid

    found: list[VideoCapture] = []
    for i, (child, files, _depth) in enumerate(candidates):
        base = child.name[: -len(_VIDEO_SUFFIX)] or child.name
        kind = _kind_for(base)
        total = 0
        for f in files:
            with contextlib.suppress(OSError):
                total += f.stat().st_size
        found.append(VideoCapture(
            id=ids[i],
            folder_name=child.name,
            folder=str(child),
            kind=kind,
            label=_LABELS.get(kind, base or child.name),
            files=tuple(str(f) for f in files),
            total_bytes=total,
            night=nights.get(i, ""),
        ))
    found.sort(key=lambda c: (c.label.lower(), c.folder_name.lower(), c.night.lower()))
    return found


def _bare_id_holder(
    bare: str,
    members: list[tuple[Path, list[Path], int]],
    claimed_by: ClaimLookup | None,
) -> int | None:
    """Which of several same-named folders keeps the bare id, by index, or ``None``.

    1. The folder holding the clip a stored result under the bare id was made
       from — so a still stacked before a second night's folder appeared stays
       with *its* capture rather than being attached to whichever folder now
       sorts first (a night folder named by date sorts before ``Lunar_video``).
    2. Otherwise the one shallowest folder — the Seestar's own drop at the top
       of ``incoming/``. Several at that depth and nothing stored: nobody needs
       the bare id, and each keeps its path-derived one.
    """
    source = None
    if claimed_by is not None:
        with contextlib.suppress(Exception):
            source = claimed_by(bare)
    if source:
        for pos, (_child, files, _depth) in enumerate(members):
            if any(f.name == source for f in files):
                return pos
    shallowest = min(depth for _c, _f, depth in members)
    at_top = [pos for pos, (_c, _f, depth) in enumerate(members) if depth == shallowest]
    return at_top[0] if len(at_top) == 1 else None


def find_video_capture(
    root: str | Path, capture_id: str, *, claimed_by: ClaimLookup | None = None,
) -> VideoCapture | None:
    """Look up one capture by the id :func:`find_video_captures` gave it, or ``None``."""
    for cap in find_video_captures(root, claimed_by=claimed_by):
        if cap.id == capture_id:
            return cap
    return None
