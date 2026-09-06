"""Find calibration frames the user already has sitting in ``incoming/``.

A beginner with a Seestar does not know what a "master dark" is, let alone that
building one means finding the right folder on the NAS and driving a build form.
But the frames are often already there — the scope shoots darks, and they land
in ``incoming/`` alongside the lights. This module is the detector that lets the
app *notice* them and offer the build, instead of making the owner know.

**The frames decide, never the folder name.** Every candidate is confirmed from
the frames' own ``IMAGETYP`` card via
:func:`seestack.io.fits_loader.frame_kind_from_header`, which answers
one-sidedly: a recognised value is an answer, and anything else — a missing
card, a capture program's private wording — is "this frame didn't say". A
folder whose frames don't say is simply **not offered**. That asymmetry is the
whole safety property: guessing from a folder name is how light subs get built
into a "master dark" that then subtracts a picture of the sky out of every stack
it touches, and no naming convention for a Seestar's dark captures has ever been
confirmed for this repo (see ``docs/IMPROVEMENTS.md``). If the camera writes no
card, this module finds nothing and the feature stays silent, which is the
honest answer rather than a guess.

Read-only, and deliberately cheap on the common case. ``incoming/`` is strictly
read-only (AGENTS.md §10) and nothing here opens it for anything but a directory
listing and a header read. The scan reads **one** header per folder before it
can rule the folder out, so a library of target folders full of light subs costs
one header read each; only a folder that keeps declaring calibration frames pays
for the rest of its sample.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: FITS extensions we treat as calibration frames. Mirrors
#: ``webapp.calibration.FITS_GLOBS`` (kept separate so the engine module doesn't
#: import the web layer); matched case-insensitively on the suffix instead.
FITS_SUFFIXES = frozenset({".fit", ".fits"})

#: How deep below the incoming root to look. The Seestar drops its capture
#: folders at the top level; one extra level covers an owner who filed them
#: under a per-night or per-scope folder. Deeper than that is somebody's whole
#: archive and not worth walking.
MAX_DEPTH = 2

#: Fewer frames than this is not worth combining into a master (and a stray
#: pair of files is exactly the kind of accident a confident offer must not be
#: built on). The build itself has no such floor — this is the *offer's* bar.
MIN_FRAMES = 5

#: How many headers to read per candidate folder. Evenly spaced through the
#: folder so a set that changes kind half way through is caught, rather than the
#: first few files deciding for the rest.
SAMPLE_HEADERS = 4

#: Upper bound on how many folders one scan will header-sample, so a pathological
#: incoming tree can't turn a page load into thousands of NAS round-trips.
#: Folders are walked in sorted order, so the cap is deterministic.
MAX_FOLDERS_SAMPLED = 200

#: Declared frame kind → the master kind it can be built into. A *flat-dark* is
#: physically a dark exposure matched to the flats, so it belongs in the dark
#: slot — the same mapping ``webapp.calibration._KIND_ACCEPTS`` already applies
#: when it checks a built master's frames against its slot. ``light`` is
#: deliberately absent: a folder of subs is never a calibration folder.
_KIND_TO_MASTER: dict[str, str] = {
    "dark": "dark",
    "dark_flat": "dark",
    "flat": "flat",
    "bias": "bias",
}


@dataclass(frozen=True)
class CalibrationFolder:
    """One folder under ``incoming/`` whose own frames say they are calibration
    frames, and what a master built from it would look like."""

    #: Stable, path-safe id. The web layer addresses folders by this and
    #: re-discovers the path server-side, so a client never hands us a
    #: filesystem path (the same rule the video captures and masters follow).
    id: str
    #: Folder name as it is on disk.
    folder_name: str
    #: Path relative to the incoming root, for display ("Darks/30s").
    rel_path: str
    #: Absolute path — server-side only; never round-trips through a client.
    folder: str
    #: ``"dark"`` | ``"flat"`` | ``"bias"`` — the master slot this folder fills.
    kind: str
    #: What the frames actually said, tallied over the sampled headers
    #: (``{"dark_flat": 4}`` where the master kind is ``"dark"``).
    declared: dict[str, int]
    #: FITS files in the folder, and how many of their headers were read.
    n_frames: int
    n_sampled: int
    #: Median acquisition settings over the sampled headers, for the suggested
    #: name and for "do I already have a master like this?". ``None`` where the
    #: frames didn't record it.
    exposure_s: float | None
    gain: float | None
    sensor_temp_c: float | None
    width_px: int | None
    height_px: int | None


def calibration_folder_id(rel_path: str) -> str:
    """Stable, path-safe id for a folder, derived from its path relative to the
    incoming root (so ``Darks/30s`` and ``Flats/30s`` can't collide)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", rel_path.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "folder"


def _fits_files_in(folder: Path) -> list[Path]:
    """FITS files directly inside ``folder``, sorted by name.

    Sorted so the even sampling below picks the same frames on every scan — an
    offer that appeared and vanished with filesystem ordering would be worse
    than no offer.
    """
    try:
        with os.scandir(folder) as entries:
            found = [
                Path(e.path) for e in entries
                if not e.name.startswith(".")
                and _has_fits_suffix(e.name)
                and _is_file(e)
            ]
    except OSError:
        return []
    found.sort(key=lambda p: p.name.lower())
    return found


def _has_fits_suffix(name: str) -> bool:
    """``.fit``/``.fits``, with or without a ``.gz``. Case-insensitive."""
    low = name.lower()
    if low.endswith(".gz"):
        low = low[: -len(".gz")]
    return any(low.endswith(s) for s in FITS_SUFFIXES)


def _is_file(entry: os.DirEntry) -> bool:
    try:
        return entry.is_file()
    except OSError:
        return False


def _median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def _sample_indices(n: int, k: int) -> list[int]:
    """Up to ``k`` evenly-spaced indices into ``range(n)``, first one first.

    The first index is 0 so the cheap single-header rule-out below reads a file
    that is definitely there, and the rest spread through the folder so a set
    whose kind changes half way is not judged by its opening files alone.
    """
    if n <= k:
        return list(range(n))
    step = (n - 1) / float(k - 1) if k > 1 else 0.0
    seen: list[int] = []
    for i in range(k):
        idx = int(round(i * step))
        if idx not in seen:
            seen.append(idx)
    return seen


def classify_folder(
    folder: str | Path,
    *,
    min_frames: int = MIN_FRAMES,
    sample: int = SAMPLE_HEADERS,
    load_header: Any = None,
) -> tuple[str, dict[str, int], list[Any], int] | None:
    """Decide whether ``folder`` holds calibration frames of one kind.

    Returns ``(master_kind, declared_tally, sampled_header_infos, n_files)``, or
    ``None`` when the folder is not a confident calibration folder. The rule is
    deliberately strict, because the cost of a false positive (a "master dark"
    built out of somebody's subs) is far higher than the cost of staying quiet:

    * at least ``min_frames`` FITS files directly inside it;
    * **every** sampled frame declares a kind we recognise — one that said
      nothing means we don't know, and "don't know" is not an offer;
    * every declaration maps to the **same** master slot (``dark``/``flat``/
      ``bias``), with flat-darks counting as darks;
    * nothing declares itself a **light**. One sub in the sample rules the
      folder out immediately.

    ``load_header`` is injectable for tests; it defaults to
    :func:`seestack.io.fits_loader.load_header`.
    """
    if load_header is None:
        from seestack.io.fits_loader import load_header as _load
        load_header = _load
    from seestack.io.fits_loader import frame_kind_from_header

    paths = _fits_files_in(Path(folder))
    if len(paths) < min_frames:
        return None

    declared: dict[str, int] = {}
    infos: list[Any] = []
    master_kind: str | None = None
    for idx in _sample_indices(len(paths), sample):
        path = paths[idx]
        try:
            info = load_header(path)
        except Exception as exc:  # noqa: BLE001 — an unreadable file is "didn't say"
            log.debug("calibration scan: unreadable header %s (%s)", path, exc)
            return None
        kind = frame_kind_from_header(getattr(info, "raw_header", None) or {})
        slot = _KIND_TO_MASTER.get(kind or "")
        if slot is None:
            # A light, or a frame that didn't say. Either way we stop here — and
            # because index 0 is read first, an ordinary folder of subs costs
            # exactly one header read.
            return None
        if master_kind is None:
            master_kind = slot
        elif slot != master_kind:
            return None
        declared[kind] = declared.get(kind, 0) + 1  # type: ignore[arg-type]
        infos.append(info)

    if master_kind is None or not infos:
        return None
    return master_kind, declared, infos, len(paths)


def find_calibration_folders(
    root: str | Path,
    *,
    min_frames: int = MIN_FRAMES,
    sample: int = SAMPLE_HEADERS,
    max_folders: int = MAX_FOLDERS_SAMPLED,
    load_header: Any = None,
) -> list[CalibrationFolder]:
    """Every folder under ``root`` whose frames declare themselves calibration
    frames of one kind.

    Sorted by kind then path so the list is stable between scans. Never raises
    on an unreadable directory — it is simply not offered.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return []

    found: list[CalibrationFolder] = []
    seen_ids: set[str] = set()
    budget = [max_folders]

    def walk(folder: Path, depth: int) -> None:
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
            if budget[0] <= 0:
                return
            budget[0] -= 1
            verdict = classify_folder(
                child, min_frames=min_frames, sample=sample,
                load_header=load_header,
            )
            if verdict is not None:
                kind, declared, infos, n_files = verdict
                rel = child.relative_to(root_path).as_posix()
                fid = calibration_folder_id(rel)
                if fid in seen_ids:
                    continue
                seen_ids.add(fid)
                found.append(CalibrationFolder(
                    id=fid,
                    folder_name=child.name,
                    rel_path=rel,
                    folder=str(child),
                    kind=kind,
                    declared=declared,
                    n_frames=n_files,
                    n_sampled=len(infos),
                    exposure_s=_median([i.exposure_s for i in infos]),
                    gain=_median([i.gain for i in infos]),
                    sensor_temp_c=_median([i.sensor_temp_c for i in infos]),
                    width_px=_modal_int([i.width_px for i in infos]),
                    height_px=_modal_int([i.height_px for i in infos]),
                ))
                # A calibration folder's children are its own business; nothing
                # nests darks inside darks, and descending would re-read them.
                continue
            if depth < MAX_DEPTH:
                walk(child, depth + 1)

    walk(root_path, 1)
    found.sort(key=lambda c: (c.kind, c.rel_path.lower()))
    return found


def _modal_int(values: list[Any]) -> int | None:
    counts: dict[int, int] = {}
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool) and int(v) > 0:
            counts[int(v)] = counts.get(int(v), 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: (counts[k], -k))


def find_calibration_folder(
    root: str | Path, folder_id: str, **kwargs: Any,
) -> CalibrationFolder | None:
    """Look up one discovered folder by :func:`calibration_folder_id`."""
    for cand in find_calibration_folders(root, **kwargs):
        if cand.id == folder_id:
            return cand
    return None


def _fmt_temp(celsius: float) -> str:
    # U+2212 MINUS SIGN, matching the Calibration page's own "−5°C" wording.
    rounded = round(celsius)
    return f"{'−' if rounded < 0 else ''}{abs(rounded):g}°C"


def suggested_master_name(folder: CalibrationFolder) -> str:
    """A name a beginner can tell apart later: ``"Dark 30s gain 80 −5°C"``.

    Built from what the frames actually recorded, falling back to the folder's
    own name when they recorded nothing — a master called "Dark" and another
    called "Dark" is exactly the confusion this avoids.
    """
    bits: list[str] = [folder.kind.capitalize()]
    if folder.exposure_s:
        secs = folder.exposure_s
        bits.append(f"{secs:g}s" if secs >= 1 else f"{secs:.3g}s")
    if folder.gain is not None:
        bits.append(f"gain {folder.gain:g}")
    if folder.sensor_temp_c is not None:
        bits.append(_fmt_temp(folder.sensor_temp_c))
    if len(bits) == 1:
        bits.append(folder.folder_name)
    return " ".join(bits)
