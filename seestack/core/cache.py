"""
Cache manager for the two-stage NAS-aware cache.

A Seestack project keeps its caches in ``<project_dir>/cache/``:

- ``stage1_raw/`` — copies of the original Seestar ``.fit`` raws pulled from the NAS.
  Stage 1 exists so every downstream pass reads from local SSD instead of the NAS.

- ``stage2_aligned/`` — warped, debayered, float16 mmap files. Pass-2 sigma-clipping
  re-streams these instead of re-warping. ~2× the size of stage 1 but huge time
  savings for the second pass.

The two stages can be cleared independently from the GUI.

This module just owns the layout and accounting. Actual fetching/warping happens in
the io and align modules.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

STAGE1_DIRNAME = "stage1_raw"
STAGE2_DIRNAME = "stage2_aligned"


@dataclass
class CacheStats:
    """Disk usage for one cache stage."""

    path: Path
    file_count: int
    bytes_total: int

    @property
    def gb(self) -> float:
        return self.bytes_total / 1024**3


class CacheManager:
    """Owns the on-disk layout for a project's caches."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.cache_root = self.project_dir / "cache"
        self.stage1 = self.cache_root / STAGE1_DIRNAME
        self.stage2 = self.cache_root / STAGE2_DIRNAME

    def ensure_dirs(self) -> None:
        self.stage1.mkdir(parents=True, exist_ok=True)
        self.stage2.mkdir(parents=True, exist_ok=True)

    def stage1_path_for(self, frame_id: int, original_name: str) -> Path:
        """Deterministic local path for a stage-1 cached raw."""
        suffix = Path(original_name).suffix or ".fit"
        return self.stage1 / f"frame_{frame_id:06d}{suffix}"

    def stage2_path_for(self, frame_id: int) -> Path:
        """Deterministic local path for a stage-2 aligned float16 mmap."""
        return self.stage2 / f"frame_{frame_id:06d}.f16.mmap"

    def stats(self, stage: str) -> CacheStats:
        """Disk usage for ``stage1`` or ``stage2``."""
        path = {"stage1": self.stage1, "stage2": self.stage2}[stage]
        if not path.exists():
            return CacheStats(path=path, file_count=0, bytes_total=0)
        files = list(path.iterdir())
        total = 0
        for f in files:
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError as exc:  # file vanished/permission — don't crash the report
                log.warning("could not stat %s: %s", f, exc)
        return CacheStats(path=path, file_count=len(files), bytes_total=total)

    def clear(self, stage: str) -> None:
        """Delete the contents of one cache stage. Project DB is untouched."""
        path = {"stage1": self.stage1, "stage2": self.stage2}[stage]
        if path.exists():
            log.info("clearing cache stage %s at %s", stage, path)
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
