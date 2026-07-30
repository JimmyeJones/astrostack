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


def find_video_captures(root: str | Path) -> list[VideoCapture]:
    """List every ``*_video/`` folder under ``root`` that holds a video file.

    Folders with no readable video file are omitted — an empty ``Lunar_video/``
    left behind by a previous transfer is not something to offer the user a
    "Stack video" button for. Results are sorted by label so the list is stable
    between calls.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return []

    found: list[VideoCapture] = []
    seen: set[str] = set()

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
                if not files:
                    continue
                base = child.name[: -len(_VIDEO_SUFFIX)] or child.name
                kind = _kind_for(base)
                cid = video_capture_id(child.name)
                if cid in seen:
                    # Two folders sanitising to the same id (e.g. "Lunar video"
                    # and "Lunar_video"): keep the first, deterministically.
                    continue
                seen.add(cid)
                total = 0
                for f in files:
                    with contextlib.suppress(OSError):
                        total += f.stat().st_size
                found.append(VideoCapture(
                    id=cid,
                    folder_name=child.name,
                    folder=str(child),
                    kind=kind,
                    label=_LABELS.get(kind, base or child.name),
                    files=tuple(str(f) for f in files),
                    total_bytes=total,
                ))
            elif depth < _MAX_DEPTH:
                walk(child, depth + 1)

    walk(root_path, 1)
    found.sort(key=lambda c: (c.label.lower(), c.folder_name.lower()))
    return found


def find_video_capture(root: str | Path, capture_id: str) -> VideoCapture | None:
    """Look up one capture by :func:`video_capture_id`, or ``None``."""
    for cap in find_video_captures(root):
        if cap.id == capture_id:
            return cap
    return None
