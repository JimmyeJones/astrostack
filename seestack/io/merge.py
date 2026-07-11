"""
Combine frames from multiple projects of the same target into one.

Use case: you imaged M51 across three nights, each saved as its own project.
You want to stack all of them together for maximum integration time. Rather
than re-ingesting raws, point at the existing project DBs and have Seestack
copy their frame rows (with WCS, QC metrics, etc.) into a destination project.

What gets merged:
  - Frame DB rows from every source project. Skipped silently if a frame's
    source path is already in the destination (no duplicate ingest).
  - Stage-1 cached files (the local copies of the raws) when available, so
    the destination project doesn't need to re-read the NAS.

What does NOT get merged:
  - Stage-2 caches (aligned data — invalidated when the destination's
    reference frame changes anyway).
  - Stack runs / project meta — those stay per-source.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from seestack.core.cache import CacheManager
from seestack.io.project import FrameRow, Project

log = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Per-source-project outcome."""

    source_project: str
    n_added: int
    n_skipped_duplicate: int
    n_skipped_missing_file: int


def merge_projects(
    destination: Project,
    source_dirs: Iterable[str | Path],
    *,
    copy_cached_files: bool = True,
) -> Iterator[MergeResult]:
    """
    Pull every frame from each source project into ``destination``.

    Yields one ``MergeResult`` per source so the caller can show progress.
    """
    dest_cache = CacheManager(destination.project_dir)
    dest_cache.ensure_dirs()
    existing_sources = {f.source_path for f in destination.iter_frames()}

    for src_dir in source_dirs:
        src_path = Path(src_dir)
        if not (src_path / "project.sqlite").exists():
            log.warning("skipping %s: not a Seestack project", src_path)
            yield MergeResult(str(src_path), 0, 0, 0)
            continue
        src_project = Project.open(src_path)
        try:
            added = 0
            dup = 0
            missing = 0
            with destination.transaction():
                for frame in src_project.iter_frames():
                    if frame.source_path in existing_sources:
                        dup += 1
                        continue
                    # Copy the row sans id; let the destination assign a new one.
                    new_row = _frame_without_id(frame)
                    new_id = destination.add_frame(new_row)
                    existing_sources.add(frame.source_path)
                    added += 1
                    # Copy the cached file if available.
                    if copy_cached_files and frame.cached_path:
                        old_cache = Path(frame.cached_path)
                        if old_cache.exists():
                            new_cache = dest_cache.stage1_path_for(new_id, old_cache.name)
                            try:
                                if not new_cache.exists() or new_cache.stat().st_size != old_cache.stat().st_size:
                                    shutil.copy2(old_cache, new_cache)
                                destination.update_frame(new_id, cached_path=str(new_cache))
                            except OSError as exc:
                                log.warning("cache copy failed: %s", exc)
                        else:
                            missing += 1
            yield MergeResult(str(src_path), added, dup, missing)
        finally:
            src_project.close()


def _frame_without_id(frame: FrameRow) -> FrameRow:
    """Shallow copy without the id (destination assigns a new one)."""
    return FrameRow(
        source_path=frame.source_path,
        cached_path=None,  # we rewrite this after insert if we copy the cache
        aligned_cache_path=None,  # stage 2 not merged
        timestamp_utc=frame.timestamp_utc,
        exposure_s=frame.exposure_s,
        gain=frame.gain,
        sensor_temp_c=frame.sensor_temp_c,
        width_px=frame.width_px,
        height_px=frame.height_px,
        bayer_pattern=frame.bayer_pattern,
        # Telescope-target pointing hints (header-derived, not path-specific like
        # the deliberately-reset caches) — kept so a frame merged *before* it's
        # plate-solved still gets a localized ASTAP search around the mount's
        # pointing instead of a slow, failure-prone blind all-sky solve.
        ra_hint_deg=frame.ra_hint_deg,
        dec_hint_deg=frame.dec_hint_deg,
        wcs_json=frame.wcs_json,
        ra_center_deg=frame.ra_center_deg,
        dec_center_deg=frame.dec_center_deg,
        pixscale_arcsec=frame.pixscale_arcsec,
        rotation_deg=frame.rotation_deg,
        fwhm_px=frame.fwhm_px,
        star_count=frame.star_count,
        sky_adu_median=frame.sky_adu_median,
        eccentricity_median=frame.eccentricity_median,
        transparency_score=frame.transparency_score,
        streak_detected=frame.streak_detected,
        streak_count=frame.streak_count,
        mosaic_panel_id=frame.mosaic_panel_id,
        accept=frame.accept,
        reject_reason=frame.reject_reason,
        user_override=frame.user_override,
    )
