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

SCHEMA_VERSION = 12

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
    transparency_ratio REAL,
    noise_sigma REAL,
    calstat TEXT,
    is_mosaic INTEGER,
    engine_version TEXT,
    rejection_fraction REAL,
    rejection_mode TEXT,
    preview_stretch REAL,
    preview_black REAL
);

CREATE INDEX IF NOT EXISTS idx_stack_runs_ts ON stack_runs(timestamp_utc);

CREATE TABLE IF NOT EXISTS frames (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- identity / paths
    source_path         TEXT NOT NULL UNIQUE,   -- original NAS path
    cached_path         TEXT,                   -- stage-1 local copy
    aligned_cache_path  TEXT,                   -- stage-2 warped float16 mmap
    -- source fingerprint: detect an in-place content swap at a reused path
    source_size_bytes   INTEGER,                -- source st_size at ingest/refresh
    source_mtime        REAL,                   -- source st_mtime at ingest/refresh
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

# Tables whose columns are reconciled additively on open (see
# ``Project._reconcile_table_columns``). ``project_meta`` is a static key/value
# table, so it's excluded — only the two evolving tables matter.
_RECONCILED_TABLES = ("frames", "stack_runs")


def _authoritative_columns() -> dict[str, list[tuple]]:
    """The columns each reconciled table *should* have, read from the
    authoritative :data:`SCHEMA_SQL` via a throwaway in-memory DB.

    Each entry is ``(name, type, notnull, dflt_value)`` — exactly the fields
    ``ALTER TABLE ADD COLUMN`` needs to re-add a missing column. Computed once
    at import so :meth:`Project._reconcile_table_columns` is a few cheap
    ``PRAGMA`` reads per open, not a schema rebuild."""
    ref = sqlite3.connect(":memory:")
    try:
        ref.executescript(SCHEMA_SQL)
        cols: dict[str, list[tuple]] = {}
        for table in _RECONCILED_TABLES:
            # PRAGMA table_info rows are (cid, name, type, notnull, dflt_value, pk).
            cols[table] = [
                (r[1], r[2], r[3], r[4])
                for r in ref.execute(f"PRAGMA table_info({table})").fetchall()
            ]
        return cols
    finally:
        ref.close()


_EXPECTED_COLUMNS = _authoritative_columns()


@dataclass
class FrameRow:
    """One frame record. Mirrors the ``frames`` table."""

    source_path: str
    id: int | None = None
    cached_path: str | None = None
    aligned_cache_path: str | None = None
    source_size_bytes: int | None = None
    source_mtime: float | None = None
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


def readable_frame_path(frame: "FrameRow") -> str | None:
    """Return the first of a frame's on-disk paths that actually exists.

    A frame carries a Stage-1 ``cached_path`` (a local copy) and the original
    ``source_path``. The cache is disposable: clearing it (the UI's "clear
    cache" button, or a NAS blip) can leave ``cached_path`` pointing at a file
    that no longer exists while the original source is still perfectly
    readable. Prefer the cache when its file is present (it is local/fast), but
    fall back to the source rather than silently dropping the frame from
    QC/solve/stack. Returns ``None`` only when neither path exists on disk.

    This is strictly wider than the old ``cached_path or source_path`` idiom:
    when the cache exists the result is identical (cache tried first); only a
    *missing* cache now falls through to the source instead of failing.
    """
    for path in (frame.cached_path, frame.source_path):
        if path and Path(path).exists():
            return str(path)
    return None


_INSERT_COLS = [
    "source_path", "cached_path", "aligned_cache_path",
    "source_size_bytes", "source_mtime",
    "timestamp_utc", "exposure_s", "gain", "sensor_temp_c",
    "width_px", "height_px", "bayer_pattern",
    "ra_hint_deg", "dec_hint_deg",
    "wcs_json", "ra_center_deg", "dec_center_deg", "pixscale_arcsec", "rotation_deg",
    "fwhm_px", "star_count", "sky_adu_median", "eccentricity_median", "transparency_score",
    "streak_detected", "streak_count",
    "mosaic_panel_id",
    "accept", "reject_reason", "user_override",
]

# Reject reason stamped on the Seestar's own on-device *stacked output* when it
# was ingested into a target as if it were a raw sub (pre-v0.184.9 scans, before
# the folder convention shipped). Additive + reversible — never a delete.
REJECT_REASON_SEESTAR_OUTPUT = "auto:seestar_output"


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
        # If schema-checking/migration raises (a newer on-disk user_version, a
        # corrupt DB, a failing migration), close the connection we just opened
        # before propagating — otherwise the handle leaks. The callers' guarded
        # ``if proj is not None: proj.close()`` never runs on this path because
        # ``open`` never returned the instance.
        try:
            proj._check_schema()
        except Exception:
            proj.close()
            raise
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
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Project schema version {version} is newer than this Seestack "
                f"build ({SCHEMA_VERSION}). Upgrade Seestack to open this project."
            )
        if version < SCHEMA_VERSION:
            self._migrate_schema(from_version=version)
        # Always reconcile columns, even at the current version. The
        # version-specific migration steps only ALTER the columns they knew
        # about, so a project created before a *frames* column was added — but
        # whose ``user_version`` a later build already stamped current — is
        # missing that column with no migration left to run, and every
        # ``_row_to_frame`` read of it raises ``IndexError``. This additive
        # backfill closes that gap for good and self-heals such a DB on open;
        # for an up-to-date project every column already exists, so it's a no-op.
        self._reconcile_table_columns()

    def _reconcile_table_columns(self) -> None:
        """Additively add any column the authoritative :data:`SCHEMA_SQL`
        defines but an on-disk table lacks — never drops, renames or rewrites.

        This makes the schema correct-by-construction against column drift: any
        additive column (past or future) that reached the base schema without a
        matching ``ALTER`` migration is repaired here rather than bricking an
        older project. A current-schema DB matches exactly, so nothing is added.
        """
        assert self._conn is not None
        for table, want in _EXPECTED_COLUMNS.items():
            have = {
                r[1]
                for r in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not have:
                continue  # table absent entirely — handled by the base-schema recreate
            for name, ctype, notnull, dflt in want:
                if name in have:
                    continue
                coldef = f"{name} {ctype}".strip() if ctype else name
                if notnull:
                    coldef += " NOT NULL"
                if dflt is not None:
                    coldef += f" DEFAULT {dflt}"
                try:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
                    log.info("Backfilled missing column %s.%s on open", table, name)
                except sqlite3.OperationalError as exc:
                    # e.g. a NOT NULL column with no default can't be added to a
                    # populated table; never let reconciliation itself fail an open.
                    log.warning("Could not backfill %s.%s: %s", table, name, exc)

    def _migrate_schema(self, *, from_version: int) -> None:
        """
        Forward-migrate from any older schema version. We only need to
        *add* tables / columns — we never destroy data.
        """
        assert self._conn is not None
        log.info("Migrating project schema %d → %d", from_version, SCHEMA_VERSION)
        # A genuine older project always has the base tables (it went through
        # Project.create). But an empty/foreign sqlite opened here can sit at
        # user_version 0 with no `frames` table — the additive ALTERs below would
        # then all silently no-op and stamp the version, leaving a DB that raises
        # "no such table: frames" on first use. Recreate the base schema first
        # (every statement is CREATE … IF NOT EXISTS, so it's a no-op for a real
        # project) so migration never produces a structurally-broken DB.
        has_frames = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='frames'"
        ).fetchone()
        if has_frames is None:
            self._conn.executescript(SCHEMA_SQL)
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
        if from_version < 6:
            # Recorded background-noise σ per stack run (normalized to the image's
            # own signal range so it's comparable across gain/exposure). Additive;
            # older runs stay NULL and simply show no noise readout / clean badge.
            try:
                self._conn.execute(
                    "ALTER TABLE stack_runs ADD COLUMN noise_sigma REAL")
            except sqlite3.OperationalError:
                pass  # already present
        if from_version < 7:
            # Recorded which calibration masters were applied to the lights
            # ("dark+flat", "bias+flat", "flat", …) so a card can show it at a
            # glance without re-reading the FITS. Additive; older runs stay NULL
            # (unknown) and simply show no calibration chip.
            try:
                self._conn.execute(
                    "ALTER TABLE stack_runs ADD COLUMN calstat TEXT")
            except sqlite3.OperationalError:
                pass  # already present
        if from_version < 8:
            # Recorded whether the run used a union/mosaic canvas (the stacker's
            # authoritative decision), so the editor no longer has to infer it
            # from coverage_min/max — which is ~always a range (the reprojection
            # border is uncovered), mislabelling single-field stacks as mosaics.
            # Additive; older runs stay NULL and fall back to a coverage-map check.
            try:
                self._conn.execute(
                    "ALTER TABLE stack_runs ADD COLUMN is_mosaic INTEGER")
            except sqlite3.OperationalError:
                pass  # already present
        if from_version < 9:
            # Recorded the app/engine version that produced each stack, so the
            # History card can show provenance ("made with v0.75.0") and a future
            # "reprocess only targets stacked before version X" filter can skip
            # up-to-date targets instead of restacking the whole library.
            # Additive; older runs stay NULL (version unknown).
            try:
                self._conn.execute(
                    "ALTER TABLE stack_runs ADD COLUMN engine_version TEXT")
            except sqlite3.OperationalError:
                pass  # already present
        if from_version < 10:
            # Recorded the per-pixel outlier-rejection tally per stack run — the
            # fraction of samples the κ-σ / drizzle / min-max pass clipped and
            # which mode ran — so the "How's my stack?" card can name the invisible
            # "we cleaned the satellite/plane trails out" work in plain language
            # without re-reading the FITS header. Additive; older runs stay NULL
            # (unknown) and simply show no clean-up note.
            for col, typ in (("rejection_fraction", "REAL"), ("rejection_mode", "TEXT")):
                try:
                    self._conn.execute(
                        f"ALTER TABLE stack_runs ADD COLUMN {col} {typ}")
                except sqlite3.OperationalError:
                    pass  # already present
        if from_version < 11:
            # Recorded the custom asinh stretch/black a user saved for this run's
            # preview (History "Adjust"), so the "one frame vs your stack" reveal
            # can render its sub half through the *same* tone curve the stored
            # preview used — keeping the two halves honestly comparable. Additive;
            # older runs stay NULL (no custom stretch = the default STF preview).
            for col in ("preview_stretch", "preview_black"):
                try:
                    self._conn.execute(
                        f"ALTER TABLE stack_runs ADD COLUMN {col} REAL")
                except sqlite3.OperationalError:
                    pass  # already present
        if from_version < 12:
            # Recorded the source file's size+mtime fingerprint so a frame whose
            # source path is later overwritten in place with a *different*
            # capture (a re-export/rename collision, or a NAS sync that reuses
            # filenames) is detected and re-solved/re-metadata'd even with
            # copy_to_cache OFF (the webapp default) — where there is no cached
            # copy to diff against. Additive; older rows stay NULL and are
            # backfilled on the first re-scan *without* triggering a re-solve.
            for col, typ in (("source_size_bytes", "INTEGER"), ("source_mtime", "REAL")):
                try:
                    self._conn.execute(
                        f"ALTER TABLE frames ADD COLUMN {col} {typ}")
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

    def delete_meta(self, key: str) -> None:
        """Remove a project-meta key (a no-op if it isn't set)."""
        assert self._conn is not None
        self._conn.execute("DELETE FROM project_meta WHERE key = ?", (key,))

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

    def reset_frame_qc(self, frame_id: int) -> None:
        """Clear a frame's computed QC metrics (and any *auto* accept/reject) so
        the next QC pass re-grades it from scratch.

        Used when a frame's Stage-1 cache was refreshed after ingest (e.g. a
        mid-copy-truncated sub whose source later finished copying): its stored
        metrics were computed on the partial data and must not persist. Nulling
        ``star_count`` also makes ``build_qc_arglist(only_new=True)`` re-offer the
        frame automatically. A user's manual accept/reject (``user_override``) is
        preserved — only auto decisions are reset."""
        existing = self.get_frame(frame_id)
        if existing is None:
            return
        fields: dict[str, Any] = {
            "fwhm_px": None, "star_count": None, "sky_adu_median": None,
            "eccentricity_median": None, "transparency_score": None,
            "streak_detected": False, "streak_count": 0,
        }
        if not existing.user_override:
            fields["accept"] = True
            fields["reject_reason"] = None
        self.update_frame(frame_id, **fields)

    def reset_frame_solution(self, frame_id: int) -> None:
        """Clear a frame's plate solution so it is re-offered to plate-solving.

        Used when a frame's *content* changed after ingest (its source path was
        reused for a **different** capture, so the cached copy was refreshed):
        the stored WCS was solved on the *old* pixels and must never be
        reprojected onto the new ones, or the frame stacks at the wrong sky
        position. Nulling ``wcs_json`` makes ``build_solve_arglist`` re-offer the
        frame automatically. A no-op if the frame was never solved."""
        self.update_frame(
            frame_id,
            wcs_json=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None,
        )

    def reject_seestar_output_frames(self, output_folder: str) -> list[int]:
        """Additively reject already-registered frames that live in the Seestar's
        own on-device *output* folder for this target (the bare ``<T>/`` beside
        the authoritative ``<T>_sub/``), or in a ``*_video/`` capture folder.

        This heals a library first scanned **before** the Seestar folder
        convention shipped (v0.184.9): back then the scanner ingested the
        on-device stacked output as if it were a raw sub, into the very target
        the raw subs now map to. Left in the stack that output is averaged into
        the final image and — being the dither-median frame — is *preferentially*
        picked as the stack reference (which can even flip a plain single field
        into a padded low-res "mosaic"). This moves those frames out of the
        stack/reference pool **without deleting anything**: they are marked
        ``accept=0`` with ``reject_reason=REJECT_REASON_SEESTAR_OUTPUT`` and the
        user can re-accept them.

        ``output_folder`` is the bare target-folder basename (``"<T>"``); a frame
        is treated as output when its source's immediate parent folder matches it
        (case-insensitively) or is a ``*_video`` folder. A frame the user manually
        accepted (``user_override``) is left untouched, and a frame already
        rejected is not re-touched — so a re-scan is idempotent.

        Returns the ids of the frames newly rejected by this call.
        """
        assert self._conn is not None
        base_low = output_folder.strip().lower()
        if not base_low:
            return []
        to_reject: list[int] = []
        for frame in list(self.iter_frames()):
            if frame.id is None or frame.user_override or not frame.accept:
                continue
            parent = Path(frame.source_path).parent.name.lower()
            if parent == base_low or parent.endswith("_video"):
                to_reject.append(frame.id)
        if not to_reject:
            return []
        with self.transaction():
            for fid in to_reject:
                self.update_frame(
                    fid, accept=False,
                    reject_reason=REJECT_REASON_SEESTAR_OUTPUT,
                )
        return to_reject

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

    def count_accepted_unsolved(self) -> int:
        """Count accepted frames that have no plate-solve WCS yet.

        These frames are *not* rejected — they simply never plate-solved (solve
        off, not run yet, or failed/timed-out with ``accept`` left True), so
        ``run_stack`` (which combines only accepted **and** solved frames)
        silently excludes them. Surfacing this count is what lets the
        "why were some frames left out?" breakdown explain a thin stack instead
        of counting these subs as if they made the picture."""
        assert self._conn is not None
        return self._conn.execute(
            "SELECT COUNT(*) FROM frames WHERE accept = 1 AND wcs_json IS NULL"
        ).fetchone()[0]

    def count_accepted_unreadable(self) -> int:
        """Count accepted, still-unsolved frames that couldn't be quality-checked.

        A frame whose FITS couldn't be read during QC (corrupt / truncated / a
        copy still in progress) is stamped a ``qc_error``/``qc_error_final:``
        ``reject_reason`` but left **accepted** (``accept=1``, no metrics), so it
        never solves and ``run_stack`` silently drops it. It is therefore a
        *subset* of :meth:`count_accepted_unsolved`, but its cause is "couldn't be
        read", not "not located in the sky yet" — so the breakdown must attribute
        it to the unreadable bucket (and never nudge a plate-solve on it). The
        ``wcs_json IS NULL`` guard keeps it definitionally within the unsolved set
        (a rare frame that errored in QC yet later solved is not double-counted)."""
        assert self._conn is not None
        return self._conn.execute(
            "SELECT COUNT(*) FROM frames "
            "WHERE accept = 1 AND wcs_json IS NULL "
            "AND reject_reason LIKE 'qc_error%'"
        ).fetchone()[0]

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

    def solve_failure_reason_counts(self) -> dict[str, int]:
        """Tally *unsolved* frames by their ``solve_failed:…`` reason.

        A plate-solve failure is stored with ``reject_reason='solve_failed:…'``
        but the frame is left **accepted** (``accept=1``) — the pixels may be
        fine, they just couldn't be located (see
        :func:`seestack.solve.runner.apply_solve_result_to_db`). So these frames
        are invisible to :meth:`reject_reason_counts` (which tallies only
        ``accept=0``), which is why the plate-solve *setup* banner — the one that
        tells a first-light user to install ASTAP or its star database when
        *every* frame fails identically — never fires from that tally. This
        helper tallies the ``solve_failed:`` reasons regardless of ``accept`` so
        the setup detector can see them. The ``wcs_json IS NULL`` guard excludes
        a frame that later solved cleanly (its stale ``solve_failed`` reason is
        no longer relevant)."""
        assert self._conn is not None
        out: dict[str, int] = {}
        for reason, n in self._conn.execute(
            "SELECT reject_reason AS r, COUNT(*) FROM frames "
            "WHERE wcs_json IS NULL AND reject_reason LIKE 'solve_failed:%' "
            "GROUP BY r"
        ):
            out[reason] = n
        return out

    def frame_night_counts(self) -> dict[str, int]:
        """Tally *all* frames (accepted or rejected) by capture night.

        The key is the UTC date portion (``YYYY-MM-DD``) of ``timestamp_utc``;
        the value is how many frames carry that date. Frames with a NULL/empty
        timestamp are skipped (they contribute no dated growth signal). This
        drives the storage "how many more nights can I keep imaging?" estimate —
        the recent capture cadence in frames/night — so it counts every ingested
        frame, not just the accepted ones, because all of them consume disk."""
        assert self._conn is not None
        out: dict[str, int] = {}
        for night, n in self._conn.execute(
            "SELECT substr(timestamp_utc, 1, 10) AS d, COUNT(*) FROM frames "
            "WHERE timestamp_utc IS NOT NULL AND timestamp_utc <> '' "
            "GROUP BY d"
        ):
            if night:
                out[night] = n
        return out

    # ---- stack runs ----------------------------------------------------

    def add_stack_run(self, run: StackRunRow) -> int:
        """Record one stack run. Returns its new id."""
        assert self._conn is not None
        cur = self._conn.execute(
            "INSERT INTO stack_runs("
            "  timestamp_utc, output_basename, fits_path, tiff_path, preview_path,"
            "  n_frames_used, canvas_h, canvas_w, coverage_min, coverage_max,"
            "  options_json, notes, total_exposure_s, transparency_ratio,"
            "  noise_sigma, calstat, is_mosaic, engine_version,"
            "  rejection_fraction, rejection_mode"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.timestamp_utc, run.output_basename, run.fits_path,
                run.tiff_path, run.preview_path, run.n_frames_used,
                run.canvas_h, run.canvas_w, run.coverage_min, run.coverage_max,
                run.options_json, run.notes, run.total_exposure_s,
                run.transparency_ratio, run.noise_sigma, run.calstat,
                None if run.is_mosaic is None else int(bool(run.is_mosaic)),
                run.engine_version, run.rejection_fraction, run.rejection_mode,
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
                noise_sigma=(
                    row["noise_sigma"]
                    if "noise_sigma" in row.keys() else None
                ),
                calstat=(
                    row["calstat"]
                    if "calstat" in row.keys() else None
                ),
                is_mosaic=(
                    (None if row["is_mosaic"] is None else bool(row["is_mosaic"]))
                    if "is_mosaic" in row.keys() else None
                ),
                engine_version=(
                    row["engine_version"]
                    if "engine_version" in row.keys() else None
                ),
                rejection_fraction=(
                    row["rejection_fraction"]
                    if "rejection_fraction" in row.keys() else None
                ),
                rejection_mode=(
                    row["rejection_mode"]
                    if "rejection_mode" in row.keys() else None
                ),
                preview_stretch=(
                    row["preview_stretch"]
                    if "preview_stretch" in row.keys() else None
                ),
                preview_black=(
                    row["preview_black"]
                    if "preview_black" in row.keys() else None
                ),
            )

    def repoint_stack_runs(self, path_map: dict[str, str]) -> int:
        """Repoint history rows whose output files were moved aside on disk.

        ``path_map`` maps an *old* output path to the path it was archived to
        (see :func:`seestack.stack.output._archive_existing_outputs`). Any run
        whose ``fits_path``/``tiff_path``/``preview_path`` equals an old path is
        updated to its archived location, so after a re-stack (which keeps the
        canonical ``master.*`` names for the *new* image) the previous run's row
        still points at the previous image instead of silently serving the new
        pixels. Returns the number of column values updated. Purely additive to
        history — no run is added, deleted, or content-changed.
        """
        assert self._conn is not None
        if not path_map:
            return 0
        updated = 0
        for col in ("fits_path", "tiff_path", "preview_path"):
            for old, new in path_map.items():
                cur = self._conn.execute(
                    f"UPDATE stack_runs SET {col} = ? WHERE {col} = ?", (new, old))
                updated += cur.rowcount
        return updated

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

    def set_stack_preview_stretch(
        self, run_id: int, stretch: float | None, black: float | None
    ) -> bool:
        """Record the custom asinh stretch/black saved as this run's preview (or
        clear it with ``None``/``None``), so the "one frame vs your stack" reveal
        can render its sub half through the same tone curve. Returns True if a row
        was updated, False if no run with ``run_id`` exists."""
        assert self._conn is not None
        cur = self._conn.execute(
            "UPDATE stack_runs SET preview_stretch = ?, preview_black = ? "
            "WHERE id = ?",
            (stretch, black, run_id))
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
    # Background-noise σ of the stacked image, normalized to its own signal
    # range so it's comparable across gain/exposure (lower = cleaner). None when
    # not computable or for runs recorded before this column existed (schema < 6).
    noise_sigma: float | None = None
    # Which calibration masters were applied to the lights ("dark+flat",
    # "bias+flat", "flat", …), or None when nothing was applied / for runs
    # recorded before this column existed (schema < 7).
    calstat: str | None = None
    # Whether this run used a union/mosaic canvas — the stacker's authoritative
    # decision (True mosaic, False single-field). None for runs recorded before
    # this column existed (schema < 8), where the editor falls back to inspecting
    # the coverage map's distribution rather than the coverage_min/max heuristic.
    is_mosaic: bool | None = None
    # The AstroStack app version that produced this run (``webapp.__version__``
    # at stack time), for provenance and stale-target reprocessing. None for runs
    # recorded before this column existed (schema < 9) or when unset by the caller.
    engine_version: str | None = None
    # Fraction of per-pixel samples the outlier-rejection pass clipped (0–1), and
    # which mode ran ("sigma-clip" | "drizzle-reject" | "min-max-reject"). None
    # when no rejection ran (plain mean), when not computable, or for runs recorded
    # before these columns existed (schema < 10). Lets "How's my stack?" name the
    # trails/cosmic-rays the stack quietly removed — a data-driven fraction only for
    # κ-σ / drizzle (min-max is structural, so its fraction isn't a clean-up figure).
    rejection_fraction: float | None = None
    rejection_mode: str | None = None
    # The custom asinh stretch/black a user saved as this run's preview via the
    # History "Adjust" panel (both in [0, 1]). NULL for runs whose preview is the
    # default export STF autostretch (the common case) or that predate these
    # columns (schema < 11). The "one frame vs your stack" reveal renders its sub
    # half through this same curve so the two halves stay honestly comparable.
    preview_stretch: float | None = None
    preview_black: float | None = None


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
        source_size_bytes=row["source_size_bytes"],
        source_mtime=row["source_mtime"],
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
