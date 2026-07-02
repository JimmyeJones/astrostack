"""
Project file (SQLite).

A Seestack project is a directory on local disk containing:

  <project_dir>/
    project.sqlite     ← this module owns this
    cache/
      stage1_raw/
      stage2_aligned/
    output/            ← stack outputs go here

The SQLite database holds one row per frame with all metadata needed to re-stack
without re-running solve / align. That re-stack-with-different-thresholds in seconds
is one of the things DSS doesn't give you.

Schema is intentionally denormalised — one wide ``frames`` table — because
queries are nearly always "give me all frames matching X" and joins would just
add complexity for no win at this scale.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)

SCHEMA_VERSION = 5

SCHEMA_SQL = f"""
PRAGMA user_version = {SCHEMA_VERSION};
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stack_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc   TEXT NOT NULL,
    output_basename TEXT NOT NULL,
    fits_path       TEXT,
    tiff_path       TEXT,
    preview_path    TEXT,
    n_frames_used   INTEGER NOT NULL,
    canvas_h        INTEGER NOT NULL,
    canvas_w        INTEGER NOT NULL,
    coverage_min    INTEGER NOT NULL DEFAULT 0,
    coverage_max    INTEGER NOT NULL DEFAULT 0,
    options_json    TEXT NOT NULL,
    notes           TEXT,
    total_exposure_s REAL,
    transparency_ratio REAL
);

CREATE INDEX IF NOT EXISTS idx_stack_runs_ts ON stack_runs(timestamp_utc);

CREATE TABLE IF NOT EXISTS frames (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- identity / paths
    source_path         TEXT NOT NULL UNIQUE,   -- original NAS path
    cached_path         TEXT,                   -- stage-1 local copy
    aligned_cache_path  TEXT,                   -- stage-2 warped float16 mmap
    -- header
    timestamp_utc       TEXT,                   -- ISO 8601
    exposure_s          REAL,
    gain                REAL,
    sensor_temp_c       REAL,
    width_px            INTEGER,
    height_px           INTEGER,
    bayer_pattern       TEXT,                   -- e.g. 'RGGB'
    -- telescope target hint (from the raw FITS header, used to speed plate-solving)
    ra_hint_deg         REAL,
    dec_hint_deg        REAL,
    -- plate solve
    wcs_json            TEXT,                   -- serialized astropy WCS header
    ra_center_deg       REAL,
    dec_center_deg      REAL,
    pixscale_arcsec     REAL,
    rotation_deg        REAL,
    -- quality metrics (qc module)
    fwhm_px             REAL,
    star_count          INTEGER,
    sky_adu_median      REAL,
    eccentricity_median REAL,
    transparency_score  REAL,
    -- streak detection
    streak_detected     INTEGER NOT NULL DEFAULT 0,  -- 0/1
    streak_count        INTEGER NOT NULL DEFAULT 0,
    -- mosaic grouping (assigned by align stage)
    mosaic_panel_id     INTEGER,
    -- accept / reject
    accept              INTEGER NOT NULL DEFAULT 1,  -- 0/1
    reject_reason       TEXT,                        -- 'auto:fwhm', 'user', etc.
    user_override       INTEGER NOT NULL DEFAULT 0   -- 0/1; 1 means user toggled
);

CREATE INDEX IF NOT EXISTS idx_frames_accept ON frames(accept);
CREATE INDEX IF NOT EXISTS idx_frames_panel  ON frames(mosaic_panel_id);
CREATE INDEX IF NOT EXISTS idx_frames_ts     ON frames(timestamp_utc);
"""


@dataclass
class FrameRow:
    """One frame record. Mirrors the ``frames`` table."""

    source_path: str
    id: int | None = None
    cached_path: str | None = None
    aligned_cache_path: str | None = None
    timestamp_utc: str | None = None
    exposure_s: float | None = None
    gain: float | None = None
    sensor_temp_c: float | None = None
    width_px: int | None = None
    height_px: int | None = None
    bayer_pattern: str | None = None
    ra_hint_deg: float | None = None
    dec_hint_deg: float | None = None
    wcs_json: str | None = None
    ra_center_deg: float | None = None
    dec_center_deg: float | None = None
    pixscale_arcsec: float | None = None
    rotation_deg: float | None = None
    fwhm_px: float | None = None
    star_count: int | None = None
    sky_adu_median: float | None = None
    eccentricity_median: float | None = None
    transparency_score: float | None = None
    streak_detected: bool = False
    streak_count: int = 0
    mosaic_panel_id: int | None = None
    accept: bool = True
    reject_reason: str | None = None
    user_override: bool = False


_INSERT_COLS = [
    "source_path", "cached_path", "aligned_cache_path",
    "timestamp_utc", "exposure_s", "gain", "sensor_temp_c",
    "width_px", "height_px", "bayer_pattern",
    "ra_hint_deg", "dec_hint_deg",
    "wcs_json", "ra_center_deg", "dec_center_deg", "pixscale_arcsec", "rotation_deg",
    "fwhm_px", "star_count", "sky_adu_median", "eccentricity_median", "transparency_score",
    "streak_detected", "streak_count",
    "mosaic_panel_id",
    "accept", "reject_reason", "user_override",
]


class Project:
    """Handle to a Seestack project directory and its SQLite database."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.db_path = self.project_dir / "project.sqlite"
        self._conn: sqlite3.Connection | None = None

    # ---- lifecycle ------------------------------------------------------

    @classmethod
    def create(cls, project_dir: Path, name: str) -> "Project":
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "cache").mkdir(exist_ok=True)
        (project_dir / "output").mkdir(exist_ok=True)
        proj = cls(project_dir)
        proj._open()
        proj._init_schema()
        proj.set_meta("name", name)
        proj.set_meta("schema_version", str(SCHEMA_VERSION))
        return proj

    @classmethod
    def open(cls, project_dir: Path) -> "Project":
        proj = cls(project_dir)
        if not proj.db_path.exists():
            raise FileNotFoundError(f"No project database at {proj.db_path}")
        proj._open()
        proj._check_schema()
        return proj

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _open(self) -> None:
        conn = sqlite3.connect(self.db_path, isolation_level=None)  # autocommit
        try:
            conn.row_factory = sqlite3.Row
            # A library scan adds frames to a target's project on a worker thread
            # while the GUI may read the same project. busy_timeout makes a
            # contended connection wait for the lock rather than raising
            # "database is locked" outright.
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            conn.close()
            raise
        self._conn = conn

    def _init_schema(self) -> None:
        assert self._conn is not None
        self._conn.executescript(SCHEMA_SQL)

    def _check_schema(self) -> None:
        assert self._conn is not None
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version < SCHEMA_VERSION:
            self._migrate_schema(from_version=version)
            return
        raise RuntimeError(
            f"Project schema version {version} is newer than this Seestack "
            f"build ({SCHEMA_VERSION}). Upgrade Seestack to open this project."
        )

    def _migrate_schema(self, *, from_version: int) -> None:
        """
        Forward-migrate from any older schema version. We only need to
        *add* tables / columns — we never destroy data.
        """
        assert self._conn is not None
        log.info("Migrating project schema %d → %d", from_version, SCHEMA_VERSION)
        if from_version < 2:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stack_runs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc   TEXT NOT NULL,
                    output_basename TEXT NOT NULL,
                    fits_path       TEXT,
                    tiff_path       TEXT,
                    preview_path    TEXT,
                    n_frames_used   INTEGER NOT NULL,
                    canvas_h        INTEGER NOT NULL,
                    canvas_w        INTEGER NOT NULL,
                    coverage_min    INTEGER NOT NULL DEFAULT 0,
                    coverage_max    INTEGER NOT NULL DEFAULT 0,
                    options_json    TEXT NOT NULL,
                    notes           TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_stack_runs_ts ON stack_runs(timestamp_utc);
                """
            )
        if from_version < 3:
            # Telescope-target hint columns (additive; never destroys data).
            for col in ("ra_hint_deg", "dec_hint_deg"):
                try:
                    self._conn.execute(f"ALTER TABLE frames ADD COLUMN {col} REAL")
                except sqlite3.OperationalError:
                    pass  # already present
        if from_version < 4:
            # Recorded integration time per stack run (additive; older runs stay
            # NULL and fall back to reading EXPTOTAL from their FITS header).
            try:
                self._conn.execute(
                    "ALTER TABLE stack_runs ADD COLUMN total_exposure_s REAL")
            except sqlite3.OperationalError:
                pass  # already present
        if from_version < 5:
            # Recorded transparency verdict per stack run (median transparency of
            # the stacked frames ÷ the target's clear-sky baseline). Additive;
            # older runs stay NULL and simply show no "hazy night" badge.
            try:
                self._conn.execute(
                    "ALTER TABLE stack_runs ADD COLUMN transparency_ratio REAL")
            except sqlite3.OperationalError:
                pass  # already present
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Wrap a batch of writes in a single transaction for speed."""
        assert self._conn is not None
        self._conn.execute("BEGIN")
        try:
            yield self._conn
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # ---- meta -----------------------------------------------------------

    def set_meta(self, key: str, value: str) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO project_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_meta(self, key: str) -> str | None:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT value FROM project_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    # ---- frames ---------------------------------------------------------

    def add_frame(self, frame: FrameRow) -> int:
        """Insert a single frame, returning its new id."""
        assert self._conn is not None
        cols = ", ".join(_INSERT_COLS)
        placeholders = ", ".join("?" for _ in _INSERT_COLS)
        values = [_to_db(getattr(frame, c)) for c in _INSERT_COLS]
        cur = self._conn.execute(
            f"INSERT INTO frames({cols}) VALUES({placeholders})", values
        )
        return cur.lastrowid  # type: ignore[return-value]

    def add_frames(self, frames: list[FrameRow]) -> list[int]:
        """Bulk insert in a single transaction. Faster than add_frame in a loop."""
        ids: list[int] = []
        with self.transaction():
            for f in frames:
                ids.append(self.add_frame(f))
        return ids

    def update_frame(self, frame_id: int, **fields: Any) -> None:
        """Patch a frame in place. Pass column names as kwargs."""
        if not fields:
            return
        assert self._conn is not None
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = [_to_db(v) for v in fields.values()]
        values.append(frame_id)
        self._conn.execute(f"UPDATE frames SET {cols} WHERE id = ?", values)

    def get_frame(self, frame_id: int) -> FrameRow | None:
        assert self._conn is not None
        row = self._conn.execute("SELECT * FROM frames WHERE id = ?", (frame_id,)).fetchone()
        return _row_to_frame(row) if row else None

    def iter_frames(self, accepted_only: bool = False) -> Iterator[FrameRow]:
        assert self._conn is not None
        sql = "SELECT * FROM frames"
        if accepted_only:
            sql += " WHERE accept = 1"
        sql += " ORDER BY id"
        for row in self._conn.execute(sql):
            yield _row_to_frame(row)

    def count(self, accepted_only: bool = False) -> int:
        assert self._conn is not None
        sql = "SELECT COUNT(*) FROM frames"
        if accepted_only:
            sql += " WHERE accept = 1"
        return self._conn.execute(sql).fetchone()[0]

    def median_fwhm(self) -> float | None:
        """Median FWHM (px) across accepted frames that carry a measured value,
        or ``None`` if none do. Used as the physically-motivated default PSF
        width for editor deconvolution — the stacked result's effective star
        size tracks the median of the frames that went into it."""
        assert self._conn is not None
        vals = sorted(
            r[0] for r in self._conn.execute(
                "SELECT fwhm_px FROM frames WHERE accept = 1 AND fwhm_px IS NOT NULL"
            )
        )
        if not vals:
            return None
        n = len(vals)
        mid = n // 2
        return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2

    def reject_reason_counts(self) -> dict[str, int]:
        """Tally rejected frames by ``reject_reason`` (e.g. ``qc:fwhm``,
        ``bulk:streaked``, ``user``). A rejected frame with a NULL reason is
        bucketed under ``"user"`` — that's how a manual reject with no explicit
        reason is recorded elsewhere. Accepted frames are ignored."""
        assert self._conn is not None
        out: dict[str, int] = {}
        for reason, n in self._conn.execute(
            "SELECT COALESCE(reject_reason, 'user') AS r, COUNT(*) "
            "FROM frames WHERE accept = 0 GROUP BY r"
        ):
            out[reason] = n
        return out

    # ---- stack runs ----------------------------------------------------

    def add_stack_run(self, run: StackRunRow) -> int:
        """Record one stack run. Returns its new id."""
        assert self._conn is not None
        cur = self._conn.execute(
            "INSERT INTO stack_runs("
            "  timestamp_utc, output_basename, fits_path, tiff_path, preview_path,"
            "  n_frames_used, canvas_h, canvas_w, coverage_min, coverage_max,"
            "  options_json, notes, total_exposure_s, transparency_ratio"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.timestamp_utc, run.output_basename, run.fits_path,
                run.tiff_path, run.preview_path, run.n_frames_used,
                run.canvas_h, run.canvas_w, run.coverage_min, run.coverage_max,
                run.options_json, run.notes, run.total_exposure_s,
                run.transparency_ratio,
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]

    def iter_stack_runs(self) -> Iterator[StackRunRow]:
        assert self._conn is not None
        for row in self._conn.execute(
            "SELECT * FROM stack_runs ORDER BY timestamp_utc DESC",
        ):
            yield StackRunRow(
                id=row["id"],
                timestamp_utc=row["timestamp_utc"],
                output_basename=row["output_basename"],
                fits_path=row["fits_path"],
                tiff_path=row["tiff_path"],
                preview_path=row["preview_path"],
                n_frames_used=row["n_frames_used"],
                canvas_h=row["canvas_h"],
                canvas_w=row["canvas_w"],
                coverage_min=row["coverage_min"],
                coverage_max=row["coverage_max"],
                options_json=row["options_json"],
                notes=row["notes"],
                total_exposure_s=(
                    row["total_exposure_s"]
                    if "total_exposure_s" in row.keys() else None
                ),
                transparency_ratio=(
                    row["transparency_ratio"]
                    if "transparency_ratio" in row.keys() else None
                ),
            )

    def delete_stack_run(self, run_id: int) -> None:
        assert self._conn is not None
        self._conn.execute("DELETE FROM stack_runs WHERE id = ?", (run_id,))

    def set_stack_run_notes(self, run_id: int, notes: str | None) -> bool:
        """Set (or clear) a run's free-text notes/label. Returns True if a row
        was updated, False if no run with ``run_id`` exists."""
        assert self._conn is not None
        cur = self._conn.execute(
            "UPDATE stack_runs SET notes = ? WHERE id = ?", (notes, run_id))
        return cur.rowcount > 0


@dataclass
class StackRunRow:
    """One row of the ``stack_runs`` table."""

    id: int | None
    timestamp_utc: str
    output_basename: str
    fits_path: str | None
    tiff_path: str | None
    preview_path: str | None
    n_frames_used: int
    canvas_h: int
    canvas_w: int
    coverage_min: int
    coverage_max: int
    options_json: str
    notes: str | None = None
    # Effective integration time in seconds (median sub × frames combined).
    # None for runs recorded before this column existed (schema < 4).
    total_exposure_s: float | None = None
    # Median transparency of the stacked frames ÷ this target's clear-sky
    # baseline (< ~0.6 ⇒ shot through haze). None when not computable or for
    # runs recorded before this column existed (schema < 5).
    transparency_ratio: float | None = None


def _to_db(value: Any) -> Any:
    """Convert Python values to sqlite3-friendly forms."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, Path):
        return str(value)
    return value


def _row_to_frame(row: sqlite3.Row) -> FrameRow:
    return FrameRow(
        id=row["id"],
        source_path=row["source_path"],
        cached_path=row["cached_path"],
        aligned_cache_path=row["aligned_cache_path"],
        timestamp_utc=row["timestamp_utc"],
        exposure_s=row["exposure_s"],
        gain=row["gain"],
        sensor_temp_c=row["sensor_temp_c"],
        width_px=row["width_px"],
        height_px=row["height_px"],
        bayer_pattern=row["bayer_pattern"],
        ra_hint_deg=row["ra_hint_deg"],
        dec_hint_deg=row["dec_hint_deg"],
        wcs_json=row["wcs_json"],
        ra_center_deg=row["ra_center_deg"],
        dec_center_deg=row["dec_center_deg"],
        pixscale_arcsec=row["pixscale_arcsec"],
        rotation_deg=row["rotation_deg"],
        fwhm_px=row["fwhm_px"],
        star_count=row["star_count"],
        sky_adu_median=row["sky_adu_median"],
        eccentricity_median=row["eccentricity_median"],
        transparency_score=row["transparency_score"],
        streak_detected=bool(row["streak_detected"]),
        streak_count=row["streak_count"],
        mosaic_panel_id=row["mosaic_panel_id"],
        accept=bool(row["accept"]),
        reject_reason=row["reject_reason"],
        user_override=bool(row["user_override"]),
    )
