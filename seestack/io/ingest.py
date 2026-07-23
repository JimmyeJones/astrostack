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
import os
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
    # Plain-language reason a file was *skipped* (not an error): e.g. a still-copying
    # zero-byte sub. Distinct from ``error`` so a benign skip isn't miscounted as a
    # failure in the scan summary. Only set when ``skipped`` is True.
    skip_reason: str | None = None
    # True when a dedup-skipped frame's Stage-1 cache was *refreshed* because the
    # source grew past the cached size (a mid-copy-truncated sub whose source
    # later finished). Its QC was reset, so the caller should re-QC its target.
    refreshed: bool = False


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


def _dedup_key(path: str | Path) -> str:
    """Canonical key for deciding whether two source paths are the *same frame*.

    Dedup used to key on the raw ``source_path`` string, but the module contract
    is that frames are matched by their **absolute** path — nothing enforced it.
    So any change of spelling for one physical file defeated dedup and ingested
    it twice (→ double-weighted in the stack): a symlinked subdirectory yielding
    two glob paths to one file within a single scan, or a relative root re-scanned
    from a different cwd. ``os.path.realpath`` normalises both cases (resolves
    symlinks + ``..`` and makes relative paths absolute).

    Crucially this is applied **symmetrically** to the stored and the incoming
    path at lookup time — we do *not* rewrite what's stored — so an already-
    ingested library re-scans clean (``realpath`` is stable/idempotent for an
    unchanged file) rather than re-ingesting every frame. Two genuinely different
    files can never collide (distinct realpaths); at worst an exotic spelling we
    don't normalise still falls back to the old raw-string behaviour (a possible
    duplicate), never a wrong skip.
    """
    return os.path.realpath(str(path))


def _source_fingerprint(src: Path) -> tuple[int, float] | None:
    """A cheap identity fingerprint ``(size, mtime)`` for a source file, or
    ``None`` if it can't be stat'd.

    Stored on the frame row so a later re-scan can tell that a reused source
    path now holds *different* content — an in-place overwrite (a re-export /
    rename collision, or a NAS sync that reuses filenames). This works even when
    ``copy_to_cache`` is off (the webapp default), where there is no cached copy
    to diff against, so the stale-solution refresh below is no longer inert on a
    default install.
    """
    try:
        st = src.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime)


def _cache_stale(cached_path: str | Path, src: Path) -> bool:
    """True if the Stage-1 cache no longer matches its source and should be
    refreshed. A size mismatch means the source grew after it was cached — the
    classic signature of a frame ingested while it was still being copied (its
    cache is truncated). If either file can't be stat'd we conservatively return
    False (leave the existing cache; a later scan retries) rather than churn.
    """
    try:
        return Path(cached_path).stat().st_size != src.stat().st_size
    except OSError:
        return False


def _copy_to_stage1(
    project: Project, cache: CacheManager, src: Path, frame_id: int,
    *, force: bool = False,
) -> Path | None:
    """
    Copy ``src`` into the Stage-1 cache under ``frame_id`` and record the path on
    the frame row. Returns the cached path, or ``None`` if the copy failed (a NAS
    blip): the frame stays usable via ``source_path``, and a later scan retries.

    ``force`` re-copies even when the cached size already matches — needed for an
    in-place *same-size* content swap, which the size-only staleness check can't
    see, so the cache would otherwise keep the previous capture's pixels.
    """
    cached = cache.stage1_path_for(frame_id, src.name)
    try:
        if force or not cached.exists() or cached.stat().st_size != src.stat().st_size:
            shutil.copy2(src, cached)
    except OSError as exc:
        log.warning("could not cache %s: %s", src, exc)
        return None
    project.update_frame(frame_id, cached_path=str(cached))
    return cached


def _refresh_frame_metadata(project: Project, frame_id: int, src: Path) -> None:
    """Re-read a refreshed source's FITS header and drop its stale plate
    solution, so a frame whose *content* changed at a reused path is re-solved
    and re-metadata'd from scratch instead of inheriting the previous capture's
    WCS, timestamp, exposure and gain.

    The Stage-1 cache is refreshed on a size mismatch (see ``_cache_stale``),
    which fires for two cases: a truncated sub whose source finished copying
    (same capture — re-reading the header is idempotent and its ``wcs_json`` is
    already NULL, so clearing is a no-op), *and* a source path overwritten in
    place with a different capture (a re-export/rename collision or a NAS sync
    that reuses filenames). The second case is the one that bites: without this,
    the old WCS is reprojected onto the new pixels and the frame lands at the
    wrong sky position, silently. Header re-read failures are logged and
    tolerated (the old header is kept) — the solution is still cleared so a
    wrong WCS can never be applied."""
    try:
        info = load_header(src)
    except Exception as exc:  # noqa: BLE001 — astropy raises a zoo of exceptions
        log.warning("could not re-read header for refreshed %s: %s", src, exc)
    else:
        project.update_frame(
            frame_id,
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
    project.reset_frame_solution(frame_id)


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
    ``cached_path`` NULL), or the source has since grown past its cached copy (a
    frame ingested mid-copy left a truncated cache), the Stage-1 copy is refreshed
    here instead of the partial sub persisting into QC/stack forever.
    """
    cache.ensure_dirs()
    existing: dict[str, FrameRow] = {
        _dedup_key(f.source_path): f for f in project.iter_frames()
    }

    for src in sources:
        src = Path(src)
        s_str = str(src)
        key = _dedup_key(src)
        prior = existing.get(key)
        if prior is not None:
            # Registered already → skip. But if a NAS blip during an earlier copy
            # left this frame uncached, retry the Stage-1 copy now; otherwise the
            # row is skipped on every future scan and the cache is never populated.
            recovered: Path | None = None
            refreshed = False
            # Has the source's bytes changed under a reused path since we last saw
            # it? A stored fingerprint of None means a pre-fingerprint (upgraded)
            # row or a genuinely fresh one — we backfill it below rather than treat
            # it as a change, so an upgrade doesn't re-solve the whole library.
            fp = _source_fingerprint(src)
            stored_fp = (
                (prior.source_size_bytes, prior.source_mtime)
                if prior.source_size_bytes is not None
                else None
            )
            content_changed = (
                fp is not None and stored_fp is not None and fp != stored_fp
            )
            if copy_to_cache and prior.id is not None:
                if not prior.cached_path:
                    recovered = _copy_to_stage1(project, cache, src, prior.id)
                elif _cache_stale(prior.cached_path, src):
                    # The frame was registered while its source was still being
                    # copied over SMB/NFS (the watcher's stability gate only decides
                    # *when* to fire a batch — the pipeline then re-globs and ingests
                    # the whole incoming dir, so a file still mid-copy can be swept
                    # in). That leaves a *truncated* Stage-1 copy; the source keeps
                    # growing afterwards, but a plain dedup-skip never refreshes the
                    # cache, so the partial sub silently persists into QC/stack. A
                    # size mismatch between the cached copy and the (now-complete)
                    # source is the tell — re-copy so the stack reads the whole
                    # frame, not the truncated one. Byte-identical in the normal
                    # case, so this is a cheap stat compare with no copy.
                    recovered = _copy_to_stage1(project, cache, src, prior.id)
                    if recovered is not None:
                        # The old QC metrics were computed on the truncated data —
                        # reset them so the frame is re-QC'd on the complete cache
                        # (nulling star_count re-offers it to build_qc_arglist), and
                        # flag the refresh so the caller re-QCs this frame's target
                        # in the same run rather than waiting for new frames to land.
                        project.reset_frame_qc(prior.id)
                        # The refreshed cache may be a *different* capture at a
                        # reused source path, not just a completed copy of the
                        # same sub. Re-read the header and drop the stale plate
                        # solution so the new content is re-solved and
                        # re-metadata'd instead of stacking at the old sky
                        # position (idempotent for the truncated→complete case).
                        _refresh_frame_metadata(project, prior.id, src)
                        refreshed = True
            # Cache-independent content-swap recovery. The block above only fires
            # when copy_to_cache is on (the webapp defaults it OFF) and can only
            # see a *size* difference, so a source overwritten in place with a
            # different capture would otherwise keep its stale WCS/header and
            # stack at the wrong sky position. The source fingerprint catches the
            # swap with no cached copy to diff against.
            if content_changed and not refreshed and prior.id is not None:
                # When caching, force-refresh the Stage-1 copy too so QC/solve/
                # stack read the new pixels — a same-size swap slips past the
                # size-only staleness check above and would leave the cache stale.
                if copy_to_cache and prior.cached_path:
                    recovered = _copy_to_stage1(project, cache, src, prior.id,
                                                force=True)
                project.reset_frame_qc(prior.id)
                _refresh_frame_metadata(project, prior.id, src)
                refreshed = True
            # Keep the stored fingerprint current: backfill a NULL (a pre-upgrade
            # row seen again — recorded *without* forcing a re-solve) and record
            # the new baseline after a detected swap. An unchanged frame writes
            # nothing.
            if (
                fp is not None and prior.id is not None
                and (stored_fp is None or content_changed)
            ):
                project.update_frame(
                    prior.id, source_size_bytes=fp[0], source_mtime=fp[1]
                )
            # frame_id stays None on a skip (a registered frame is not "added"),
            # so existing consumers that gate on frame_id don't re-list it.
            yield IngestResult(
                source_path=src, frame_id=None, cached_path=recovered, skipped=True,
                refreshed=refreshed,
            )
            continue

        # Zero-byte files are half-finished copies (or a stalled NAS transfer);
        # skip them cleanly instead of letting astropy raise a confusing error.
        try:
            if src.stat().st_size == 0:
                log.info("skipping empty file %s", src)
                # A 0-byte file is a still-copying / stalled transfer, not a failure:
                # it is retried on the next scan once it has bytes. Record it as a
                # *skip* with a plain-language reason, not an ``error`` (which would
                # inflate the scary "N errors" count a beginner sees for a mid-copy sub).
                yield IngestResult(source_path=src, frame_id=None, cached_path=None,
                                   skipped=True, skip_reason="still copying (empty file)")
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
        ins_fp = _source_fingerprint(src)
        row = FrameRow(
            source_path=s_str,
            source_size_bytes=ins_fp[0] if ins_fp is not None else None,
            source_mtime=ins_fp[1] if ins_fp is not None else None,
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
        existing[key] = row
        yield IngestResult(
            source_path=src, frame_id=frame_id, cached_path=cached, skipped=False
        )
