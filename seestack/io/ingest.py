"""
Ingest: scan a folder of Seestar raw `.fit` files, copy to the local Stage 1
cache, and register each frame in the project database.

Ingest is the first thing the user does after creating a project. It's a pure
file/header operation — no plate solving, no QC. Quality metrics run as a
separate pass so the user gets the frame list immediately and metric updates
stream in afterward.

Why copy upfront? NAS random reads are slow. Every later pipeline stage reads
each frame at least once; pre-staging amortises the network cost into a single
sequential pass. Copy is skipped automatically for files that already live on
local disk (same drive as the project).

Yields per-file results so a Qt model can update the frame table live.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from seestack.core.cache import CacheManager
from seestack.io.fits_loader import load_header
from seestack.io.project import FrameRow, Project

log = logging.getLogger(__name__)

FITS_SUFFIXES = (".fit", ".fits", ".fts")


@dataclass
class IngestResult:
    """Outcome of ingesting a single file."""

    source_path: Path
    frame_id: int | None
    cached_path: Path | None
    skipped: bool
    error: str | None = None


def find_fits_files(root: str | Path, *, recursive: bool = True) -> list[Path]:
    """List FITS files under ``root``. Sorted for deterministic ingest order."""
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        return [root] if root.suffix.lower() in FITS_SUFFIXES else []
    pattern = "**/*" if recursive else "*"
    files = [
        p for p in root.glob(pattern)
        if p.is_file() and p.suffix.lower() in FITS_SUFFIXES
    ]
    files.sort()
    return files


def _copy_to_stage1(
    project: Project, cache: CacheManager, src: Path, frame_id: int
) -> Path | None:
    """
    Copy ``src`` into the Stage-1 cache under ``frame_id`` and record the path on
    the frame row. Returns the cached path, or ``None`` if the copy failed (a NAS
    blip): the frame stays usable via ``source_path``, and a later scan retries.
    """
    cached = cache.stage1_path_for(frame_id, src.name)
    try:
        if not cached.exists() or cached.stat().st_size != src.stat().st_size:
            shutil.copy2(src, cached)
    except OSError as exc:
        log.warning("could not cache %s: %s", src, exc)
        return None
    project.update_frame(frame_id, cached_path=str(cached))
    return cached


def ingest_files(
    project: Project,
    cache: CacheManager,
    sources: Iterable[Path],
    *,
    copy_to_cache: bool = True,
) -> Iterator[IngestResult]:
    """
    Register each source file in the project database, optionally copying it
    to Stage 1 first. Yields one ``IngestResult`` per file.

    Already-ingested files (same ``source_path``) are skipped silently — but if a
    previous ingest failed to cache one (a transient copy error left
    ``cached_path`` NULL), the copy is retried here instead of being abandoned
    forever.
    """
    cache.ensure_dirs()
    existing: dict[str, FrameRow] = {f.source_path: f for f in project.iter_frames()}

    for src in sources:
        src = Path(src)
        s_str = str(src)
        prior = existing.get(s_str)
        if prior is not None:
            # Registered already → skip. But if a NAS blip during an earlier copy
            # left this frame uncached, retry the Stage-1 copy now; otherwise the
            # row is skipped on every future scan and the cache is never populated.
            recovered: Path | None = None
            if copy_to_cache and not prior.cached_path and prior.id is not None:
                recovered = _copy_to_stage1(project, cache, src, prior.id)
            # frame_id stays None on a skip (a registered frame is not "added"),
            # so existing consumers that gate on frame_id don't re-list it.
            yield IngestResult(
                source_path=src, frame_id=None, cached_path=recovered, skipped=True
            )
            continue

        # Zero-byte files are half-finished copies (or a stalled NAS transfer);
        # skip them cleanly instead of letting astropy raise a confusing error.
        try:
            if src.stat().st_size == 0:
                log.info("skipping empty file %s", src)
                yield IngestResult(source_path=src, frame_id=None, cached_path=None,
                                   skipped=True, error="empty file")
                continue
        except OSError as exc:
            yield IngestResult(source_path=src, frame_id=None, cached_path=None,
                               skipped=False, error=str(exc))
            continue

        try:
            info = load_header(src)
        except Exception as exc:  # noqa: BLE001 — astropy raises a zoo of exceptions
            log.warning("could not read header for %s: %s", src, exc)
            yield IngestResult(
                source_path=src, frame_id=None, cached_path=None, skipped=False, error=str(exc)
            )
            continue

        # Insert first so we get an id, then (optionally) copy to a path keyed on it.
        row = FrameRow(
            source_path=s_str,
            timestamp_utc=info.timestamp_utc,
            exposure_s=info.exposure_s,
            gain=info.gain,
            sensor_temp_c=info.sensor_temp_c,
            width_px=info.width_px,
            height_px=info.height_px,
            bayer_pattern=info.bayer_pattern,
            ra_hint_deg=info.ra_target_deg,
            dec_hint_deg=info.dec_target_deg,
        )
        frame_id = project.add_frame(row)

        cached: Path | None = None
        if copy_to_cache:
            cached = _copy_to_stage1(project, cache, src, frame_id)

        row.id = frame_id
        row.cached_path = str(cached) if cached is not None else None
        existing[s_str] = row
        yield IngestResult(
            source_path=src, frame_id=frame_id, cached_path=cached, skipped=False
        )
