"""
Library: a folder containing many Seestack target projects, with a shared
registry.

Why this exists
---------------
A Seestar imaging session leaves you with a folder full of sub-folders —
one per target the telescope observed (``M 42/``, ``Andromeda Mosaic/``,
…) — plus the occasional loose FITS file. A *library* points Seestack at
that folder and turns it into organised, stackable projects:

  <library_root>/
    library.sqlite          ← target registry + campaign totals
    targets/
      M_42/                 ← each one is a regular ``Project``
        project.sqlite
        cache/
        output/
      Andromeda_Mosaic/
        ...
    skymap.png              ← latest all-sky render (optional)

The registry only holds *index* information (target name, RA/Dec, frame
count, total exposure). The source of truth for each target's frames stays
in the per-target ``project.sqlite``, so all the existing GUI / stack code
keeps working unchanged — a Library is just "a folder of Projects you can
list, scan into, and merge".

The registry lets us answer cross-target questions cheaply (total exposure
across the whole campaign) without opening every per-target SQLite. Cached
totals are refreshed after each scan / stack.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from seestack.io.project import Project

log = logging.getLogger(__name__)

LIBRARY_SCHEMA_VERSION = 4
_REGISTRY_FILENAME = "library.sqlite"
_TARGETS_SUBDIR = "targets"

# Name used for the catch-all target that collects loose FITS files found
# directly in a scanned root (i.e. not inside any Seestar sub-folder).
UNSORTED_TARGET_NAME = "Unsorted"

_REGISTRY_SCHEMA_SQL = f"""
PRAGMA user_version = {LIBRARY_SCHEMA_VERSION};
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS library_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT NOT NULL UNIQUE,     -- display name ("M 42")
    safe_name             TEXT NOT NULL UNIQUE,     -- folder name ("M_42")
    ra_deg                REAL,
    dec_deg               REAL,
    created_utc           TEXT NOT NULL,
    last_activity_utc     TEXT,
    n_frames              INTEGER NOT NULL DEFAULT 0,
    n_frames_accepted     INTEGER NOT NULL DEFAULT 0,
    total_exposure_s      REAL NOT NULL DEFAULT 0,
    last_stack_preview    TEXT,                     -- absolute path to latest preview
    notes                 TEXT,
    tags                  TEXT,                      -- JSON array of tag strings
    cover_stack_run_id    INTEGER                    -- pinned "cover" run id (in this target's project.sqlite); NULL = use newest
);

CREATE INDEX IF NOT EXISTS idx_targets_radec ON targets(ra_deg, dec_deg);
"""

# The ``targets`` registry is the one evolving table (``library_meta`` is a
# static key/value store), so it's the only one whose columns are reconciled
# additively on open — see ``Library._ensure_columns``.
_TARGETS_TABLE = "targets"


def _authoritative_target_columns() -> list[tuple]:
    """The columns the ``targets`` table *should* have, read from the
    authoritative :data:`_REGISTRY_SCHEMA_SQL` via a throwaway in-memory DB.

    Each entry is ``(name, type, notnull, dflt_value)`` — exactly the fields
    ``ALTER TABLE ADD COLUMN`` needs to re-add a missing column. Computed once
    at import so the per-open reconciliation is a couple of cheap ``PRAGMA``
    reads, not a schema rebuild. Mirrors ``project.py``'s
    ``_authoritative_columns`` so the library gets the same generic column
    self-heal a per-target project already has."""
    ref = sqlite3.connect(":memory:")
    try:
        ref.executescript(_REGISTRY_SCHEMA_SQL)
        # PRAGMA table_info rows are (cid, name, type, notnull, dflt_value, pk).
        return [
            (r[1], r[2], r[3], r[4])
            for r in ref.execute(f"PRAGMA table_info({_TARGETS_TABLE})").fetchall()
        ]
    finally:
        ref.close()


_EXPECTED_TARGET_COLUMNS = _authoritative_target_columns()


@dataclass
class TargetEntry:
    """Registry row for one target."""

    id: int
    name: str
    safe_name: str
    ra_deg: float | None
    dec_deg: float | None
    created_utc: str
    last_activity_utc: str | None
    n_frames: int
    n_frames_accepted: int
    total_exposure_s: float
    last_stack_preview: str | None
    notes: str | None
    tags: list[str] = field(default_factory=list)
    # Run id (in this target's ``project.sqlite``) the user pinned as the target's
    # showcase "cover" image. ``None`` means "show the newest stack" (the default).
    cover_stack_run_id: int | None = None


def make_safe_name(name: str) -> str:
    """
    Turn a target name like ``"M 42"`` or ``"NGC 7000 / North America"`` into
    a filesystem-safe folder name. We deliberately preserve case (so 'M31'
    and 'm31' don't collapse to the same folder) but replace anything that
    would confuse Windows / git / shells.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    cleaned = cleaned.strip("._-")
    if not cleaned:
        cleaned = "target"
    return cleaned[:64]  # keep folder names sane


class Library:
    """A folder of Seestack target projects with a shared registry."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.registry_path = self.root / _REGISTRY_FILENAME
        self.targets_dir = self.root / _TARGETS_SUBDIR
        self._conn: sqlite3.Connection | None = None

    # ---- lifecycle -----------------------------------------------------

    @classmethod
    def create(cls, root: Path) -> "Library":
        """Create a fresh library at ``root``. Idempotent."""
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        (root / _TARGETS_SUBDIR).mkdir(exist_ok=True)
        lib = cls(root)
        lib._open()
        lib._init_schema()
        return lib

    @classmethod
    def open(cls, root: Path) -> "Library":
        """Open an existing library. Creates the registry if it's missing
        (forward-compat for users who manually moved per-target projects
        into a library folder), adopting any projects already present."""
        root = Path(root)
        lib = cls(root)
        if not lib.registry_path.exists():
            lib.targets_dir.mkdir(parents=True, exist_ok=True)
            lib._open()
            # Close the fresh connection if adopting/initialising raises, rather
            # than leak it (the classmethod never returned the instance, so no
            # caller can close it).
            try:
                lib._init_schema()
                lib._adopt_existing_projects()
            except Exception:
                lib.close()
                raise
            return lib
        lib._open()
        # Same guard for the existing-registry path: a newer-version or corrupt
        # registry makes _check_schema raise, and the connection must be closed.
        try:
            lib._check_schema()
        except Exception:
            lib.close()
            raise
        return lib

    @classmethod
    def open_or_create(cls, root: Path) -> "Library":
        root = Path(root)
        if (root / _REGISTRY_FILENAME).exists():
            return cls.open(root)
        return cls.create(root)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _open(self) -> None:
        conn = sqlite3.connect(self.registry_path, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            # A background scan worker and the GUI hold separate connections to
            # this registry. busy_timeout makes a contended connection wait for
            # the lock instead of immediately raising "database is locked".
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            conn.close()
            raise
        self._conn = conn

    def _init_schema(self) -> None:
        assert self._conn is not None
        self._conn.executescript(_REGISTRY_SCHEMA_SQL)
        self._set_meta("schema_version", str(LIBRARY_SCHEMA_VERSION))
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Additively add any column the authoritative registry schema defines
        but an on-disk ``targets`` table lacks — never drops, renames or
        rewrites. ``CREATE TABLE IF NOT EXISTS`` never adds columns, so a
        version-stamped-but-incomplete registry (an additive column, past or
        future, that reached the base schema without a matching ALTER migration)
        is repaired here rather than bricking an old library on
        ``list_targets``. This is the same belt-and-braces self-heal
        ``Project._reconcile_table_columns`` already has. A current-schema
        registry matches exactly, so nothing is added."""
        assert self._conn is not None
        have = {
            r["name"]
            for r in self._conn.execute(f"PRAGMA table_info({_TARGETS_TABLE})")
        }
        if not have:
            return  # table absent entirely — handled by the base-schema recreate
        for name, ctype, notnull, dflt in _EXPECTED_TARGET_COLUMNS:
            if name in have:
                continue
            coldef = f"{name} {ctype}".strip() if ctype else name
            if notnull:
                coldef += " NOT NULL"
            if dflt is not None:
                coldef += f" DEFAULT {dflt}"
            try:
                self._conn.execute(
                    f"ALTER TABLE {_TARGETS_TABLE} ADD COLUMN {coldef}"
                )
                log.info("Backfilled missing column %s.%s on open", _TARGETS_TABLE, name)
            except sqlite3.OperationalError as exc:
                # e.g. a NOT NULL column with no default can't be added to a
                # populated table; never let reconciliation itself fail an open.
                log.warning("Could not backfill %s.%s: %s", _TARGETS_TABLE, name, exc)

    def _check_schema(self) -> None:
        assert self._conn is not None
        v = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if v == LIBRARY_SCHEMA_VERSION:
            self._ensure_columns()
            return
        if v < LIBRARY_SCHEMA_VERSION:
            # Older library (possibly created by a pre-scan build that still
            # had watch_config / routing_log tables). The schema only ever
            # *adds*; the new code simply ignores any leftover tables. Just
            # re-run the (idempotent) schema and stamp the new version.
            self._init_schema()
            return
        raise RuntimeError(
            f"Library schema version {v} is newer than this Seestack build "
            f"({LIBRARY_SCHEMA_VERSION}). Upgrade to open this library."
        )

    def _adopt_existing_projects(self) -> None:
        """
        If the library is being created on top of a folder that already
        contains target sub-projects, register each one. Best-effort:
        anything that doesn't open as a valid Project is silently skipped.
        """
        if not self.targets_dir.exists():
            return
        for sub in sorted(self.targets_dir.iterdir()):
            if not sub.is_dir() or not (sub / "project.sqlite").exists():
                continue
            try:
                proj = Project.open(sub)
            except Exception as exc:  # noqa: BLE001
                log.warning("skipping non-Project folder %s: %s", sub, exc)
                continue
            try:
                name = proj.get_meta("name") or sub.name
                ra, dec = _median_radec(proj)
                self._upsert_target(name=name, safe_name=sub.name,
                                    ra_deg=ra, dec_deg=dec)
                self._refresh_target_stats_locked(sub.name, proj)
            finally:
                proj.close()

    # ---- meta ----------------------------------------------------------

    def _set_meta(self, key: str, value: str) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO library_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_meta(self, key: str) -> str | None:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT value FROM library_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        """Public meta setter — used to remember e.g. the last scanned root."""
        self._set_meta(key, value)

    # ---- targets -------------------------------------------------------

    def create_target(
        self, name: str, *, ra_deg: float | None = None,
        dec_deg: float | None = None, notes: str | None = None,
    ) -> tuple[TargetEntry, Project]:
        """
        Create a new target sub-project. Returns (registry entry, open Project).
        The caller is responsible for closing the Project.
        """
        safe = make_safe_name(name)
        proj_dir = self.targets_dir / safe
        if proj_dir.exists() and (proj_dir / "project.sqlite").exists():
            raise FileExistsError(f"target '{safe}' already exists")
        proj = Project.create(proj_dir, name=name)
        entry = self._upsert_target(name=name, safe_name=safe,
                                    ra_deg=ra_deg, dec_deg=dec_deg, notes=notes)
        return entry, proj

    def open_or_create_target(
        self, name: str, *, notes: str | None = None,
    ) -> tuple[TargetEntry, Project]:
        """
        Return (entry, open Project) for ``name``, creating it if needed.

        This is what the folder scanner uses: re-scanning a library is
        idempotent because an already-existing target is simply re-opened
        and added to, never duplicated.
        """
        safe = make_safe_name(name)
        proj_dir = self.targets_dir / safe
        if proj_dir.exists() and (proj_dir / "project.sqlite").exists():
            proj = Project.open(proj_dir)
            entry = self.find_target(safe)
            if entry is None:
                # Folder exists but isn't registered yet — register it.
                entry = self._upsert_target(name=name, safe_name=safe, notes=notes)
            return entry, proj
        return self.create_target(name, notes=notes)

    def open_target(self, name_or_safe: str) -> Project:
        """Open a target's Project by display name or by safe folder name."""
        entry = self.find_target(name_or_safe)
        if entry is None:
            raise FileNotFoundError(f"no target '{name_or_safe}' in library")
        return Project.open(self.targets_dir / entry.safe_name)

    def find_target(self, name_or_safe: str) -> TargetEntry | None:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM targets WHERE name = ? OR safe_name = ?",
            (name_or_safe, name_or_safe),
        ).fetchone()
        return _row_to_target(row) if row else None

    def update_target(self, name_or_safe: str, *, notes: str | None = None,
                      tags: list[str] | None = None) -> TargetEntry | None:
        """Patch user-editable target metadata (notes / tags). Only the
        arguments explicitly passed are changed; ``None`` means "leave as is".
        Returns the refreshed entry, or ``None`` if the target is unknown."""
        assert self._conn is not None
        entry = self.find_target(name_or_safe)
        if entry is None:
            return None
        sets: list[str] = []
        params: list[object] = []
        if notes is not None:
            sets.append("notes = ?")
            params.append(notes)
        if tags is not None:
            cleaned = [str(t).strip() for t in tags if str(t).strip()]
            # De-duplicate while preserving order.
            seen: set[str] = set()
            unique = [t for t in cleaned if not (t in seen or seen.add(t))]
            sets.append("tags = ?")
            params.append(json.dumps(unique))
        if sets:
            params.append(entry.id)
            self._conn.execute(
                f"UPDATE targets SET {', '.join(sets)} WHERE id = ?", params
            )
        return self.find_target(name_or_safe)

    def set_target_cover(self, name_or_safe: str,
                         cover_stack_run_id: int | None) -> TargetEntry | None:
        """Pin (or clear) the target's showcase "cover" run.

        ``cover_stack_run_id`` is a run id in this target's own
        ``project.sqlite``; the tile/card then shows that run's preview instead
        of the newest stack. ``None`` clears the pin (back to "newest"). The
        caller is responsible for validating the id exists; a dangling id simply
        falls back to the newest preview at render time, so it's never fatal.
        Returns the refreshed entry, or ``None`` if the target is unknown."""
        assert self._conn is not None
        entry = self.find_target(name_or_safe)
        if entry is None:
            return None
        self._conn.execute(
            "UPDATE targets SET cover_stack_run_id = ? WHERE id = ?",
            (cover_stack_run_id, entry.id),
        )
        return self.find_target(name_or_safe)

    def list_targets(self) -> list[TargetEntry]:
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM targets ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [_row_to_target(r) for r in rows]

    def iter_targets(self) -> Iterator[TargetEntry]:
        for entry in self.list_targets():
            yield entry

    def target_dir(self, entry: TargetEntry) -> Path:
        """The on-disk folder for ``entry``."""
        return self.targets_dir / entry.safe_name

    def delete_target(self, name_or_safe: str, *, remove_files: bool = False) -> bool:
        """Remove a target from the registry. Files are kept unless
        ``remove_files`` is True (an explicit, destructive choice).

        Returns True if a target was found and deleted, False if
        ``name_or_safe`` didn't match anything."""
        assert self._conn is not None
        entry = self.find_target(name_or_safe)
        if entry is None:
            return False
        self._conn.execute("DELETE FROM targets WHERE id = ?", (entry.id,))
        if remove_files:
            import shutil
            shutil.rmtree(self.targets_dir / entry.safe_name, ignore_errors=True)
        return True

    def find_target_within(self, ra_deg: float, dec_deg: float,
                           radius_deg: float) -> TargetEntry | None:
        """
        Return the registered target whose center is within ``radius_deg``
        of the given coordinates (closest match if there are several).
        Used by the "merge by sky position" helper. None if nothing matches.
        """
        candidates = [t for t in self.list_targets()
                      if t.ra_deg is not None and t.dec_deg is not None]
        if not candidates:
            return None
        best: TargetEntry | None = None
        best_sep = radius_deg
        for t in candidates:
            sep = _angular_separation_deg(
                ra_deg, dec_deg, float(t.ra_deg), float(t.dec_deg),
            )
            if sep <= best_sep:
                best_sep = sep
                best = t
        return best

    def _upsert_target(self, *, name: str, safe_name: str,
                       ra_deg: float | None = None, dec_deg: float | None = None,
                       notes: str | None = None) -> TargetEntry:
        assert self._conn is not None
        now = _utc_iso()
        self._conn.execute(
            "INSERT INTO targets(name, safe_name, ra_deg, dec_deg, created_utc, notes) "
            "VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(safe_name) DO UPDATE SET "
            "  ra_deg = COALESCE(excluded.ra_deg, ra_deg),"
            "  dec_deg = COALESCE(excluded.dec_deg, dec_deg),"
            "  notes = COALESCE(excluded.notes, notes)",
            (name, safe_name, ra_deg, dec_deg, now, notes),
        )
        row = self._conn.execute(
            "SELECT * FROM targets WHERE safe_name = ?", (safe_name,),
        ).fetchone()
        return _row_to_target(row)

    # ---- merging -------------------------------------------------------

    def merge_targets(self, into_name_or_safe: str,
                      source_names_or_safes: list[str]) -> int:
        """
        Merge one or more targets into ``into_name_or_safe``.

        Every frame from each source target's project is copied into the
        destination project (cached files included, duplicates skipped via
        source_path), then the source target is removed from the registry
        and its folder deleted.

        Returns the number of frames added to the destination. Use this for
        the "I have two folders that are really the same target" case the
        one-folder-per-target scan can't know about.
        """
        from seestack.io.merge import merge_projects

        dest = self.find_target(into_name_or_safe)
        if dest is None:
            raise FileNotFoundError(f"no target '{into_name_or_safe}' in library")

        source_dirs: list[Path] = []
        source_entries: list[TargetEntry] = []
        for s in source_names_or_safes:
            se = self.find_target(s)
            if se is None or se.id == dest.id:
                continue
            source_entries.append(se)
            source_dirs.append(self.target_dir(se))
        if not source_dirs:
            return 0

        dest_proj = Project.open(self.target_dir(dest))
        total_added = 0
        try:
            for result in merge_projects(dest_proj, source_dirs):
                total_added += result.n_added
        finally:
            dest_proj.close()

        # Remove the now-merged source targets (registry + folder).
        for se in source_entries:
            self.delete_target(se.safe_name, remove_files=True)

        self.refresh_target_stats(dest.safe_name)
        return total_added

    # ---- stats ---------------------------------------------------------

    def refresh_target_stats(self, name_or_safe: str) -> TargetEntry | None:
        """
        Re-read frame counts, total exposure, and latest preview from the
        target's per-project database. Call this after a scan or a stack.
        Returns the refreshed entry (or None if not found).
        """
        entry = self.find_target(name_or_safe)
        if entry is None:
            return None
        proj_dir = self.targets_dir / entry.safe_name
        if not (proj_dir / "project.sqlite").exists():
            return entry
        try:
            proj = Project.open(proj_dir)
        except Exception as exc:  # noqa: BLE001
            log.warning("can't refresh stats for %s: %s", entry.safe_name, exc)
            return entry
        try:
            self._refresh_target_stats_locked(entry.safe_name, proj)
        finally:
            proj.close()
        return self.find_target(entry.safe_name)

    def _refresh_target_stats_locked(self, safe_name: str, proj: Project) -> None:
        """Inner refresh — caller already has the Project open."""
        assert self._conn is not None
        n_total = proj.count(accepted_only=False)
        n_accept = proj.count(accepted_only=True)
        total_exp = 0.0
        ra_med, dec_med = _median_radec(proj)
        for f in proj.iter_frames(accepted_only=True):
            if f.exposure_s is not None and f.exposure_s > 0:
                total_exp += float(f.exposure_s)
        last_preview: str | None = None
        try:
            for run in proj.iter_stack_runs():
                if run.preview_path:
                    p = Path(run.preview_path)
                    last_preview = str(p) if p.is_absolute() else str(
                        self.targets_dir / safe_name / p
                    )
                    break
        except Exception:  # noqa: BLE001
            pass

        self._conn.execute(
            "UPDATE targets SET "
            "  n_frames = ?,"
            "  n_frames_accepted = ?,"
            "  total_exposure_s = ?,"
            "  last_activity_utc = ?,"
            "  last_stack_preview = COALESCE(?, last_stack_preview),"
            "  ra_deg = COALESCE(?, ra_deg),"
            "  dec_deg = COALESCE(?, dec_deg) "
            "WHERE safe_name = ?",
            (n_total, n_accept, total_exp, _utc_iso(), last_preview,
             ra_med, dec_med, safe_name),
        )

    def campaign_stats(self) -> dict:
        """Aggregate stats across the whole library."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT COUNT(*) AS n_targets, "
            "       COALESCE(SUM(n_frames), 0) AS n_frames, "
            "       COALESCE(SUM(n_frames_accepted), 0) AS n_accepted, "
            "       COALESCE(SUM(total_exposure_s), 0) AS total_exposure_s "
            "FROM targets"
        ).fetchone()
        return {
            "n_targets": int(row["n_targets"] or 0),
            "n_frames": int(row["n_frames"] or 0),
            "n_frames_accepted": int(row["n_accepted"] or 0),
            "total_exposure_s": float(row["total_exposure_s"] or 0.0),
        }


# ---- helpers -----------------------------------------------------------

def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _row_to_target(row: sqlite3.Row) -> TargetEntry:
    return TargetEntry(
        id=row["id"],
        name=row["name"],
        safe_name=row["safe_name"],
        ra_deg=row["ra_deg"],
        dec_deg=row["dec_deg"],
        created_utc=row["created_utc"],
        last_activity_utc=row["last_activity_utc"],
        n_frames=row["n_frames"],
        n_frames_accepted=row["n_frames_accepted"],
        total_exposure_s=row["total_exposure_s"],
        last_stack_preview=row["last_stack_preview"],
        notes=row["notes"],
        tags=_parse_tags(row["tags"] if "tags" in row.keys() else None),
        cover_stack_run_id=(
            row["cover_stack_run_id"]
            if "cover_stack_run_id" in row.keys() else None
        ),
    )


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [str(t) for t in val] if isinstance(val, list) else []


def _median_radec(proj: Project) -> tuple[float | None, float | None]:
    """Median RA/Dec across accepted, plate-solved frames. None/None if no
    solved frames are present yet."""
    ras: list[float] = []
    decs: list[float] = []
    for f in proj.iter_frames(accepted_only=True):
        if f.ra_center_deg is None or f.dec_center_deg is None:
            continue
        ras.append(float(f.ra_center_deg))
        decs.append(float(f.dec_center_deg))
    if not ras:
        return None, None
    import numpy as np

    from seestack.coords import circular_median_ra_deg

    # RA wraps at 0°/360°: a target imaged near RA=0h has frames straddling the
    # boundary (some ~359.9°, some ~0.1°), and a plain median would land ~180° away
    # (a 50/50 split of 359.9°/0.1° medians to 180.0° — the opposite side of the
    # sky), placing the target's catalog position wrong for the sky-map plot and
    # find_target_within matching. circular_median_ra_deg unwraps into a continuous
    # range before the median (shared with compute_mosaic_canvas / pick_reference_frame),
    # then folds back to [0, 360). A no-op when nothing straddles the wrap.
    return circular_median_ra_deg(ras), float(np.median(decs))


def _angular_separation_deg(ra1: float, dec1: float,
                             ra2: float, dec2: float) -> float:
    """Great-circle distance in degrees between two RA/Dec pairs (haversine —
    robust at the poles and across RA=0)."""
    import math
    phi1, phi2 = math.radians(dec1), math.radians(dec2)
    dphi = math.radians(dec2 - dec1)
    dlam = math.radians(ra2 - ra1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    c = 2 * math.asin(min(1.0, math.sqrt(a)))
    return math.degrees(c)


# ---------------------------------------------------------------------------
# "Same object? Combine these into one deep picture" — the Seestar app writes a
# NEW folder per night, so a beginner who shoots M 31 across three clear nights
# ends up with three *separate* AstroStack targets — each a shallow stack —
# instead of one deep one, and never realises their subs are being split. Manual
# merge already exists (``merge_targets`` here + the webapp ``/merge`` endpoint);
# this pure helper *detects* the split so a friendly nudge can offer the one-click
# fix. It groups targets whose plate-solved centres sit within a tight tolerance
# (same sky object), so the deep image "just happens". Read-only and offline.
# ---------------------------------------------------------------------------

# How close two targets' plate-solved centres must be to be judged the *same*
# object. The Seestar S50's field of view is ~1.27°, and it re-centres on the
# same catalogued target each night to within a couple of arcminutes, so a small
# tolerance captures "same object, different nights" comfortably. It is kept well
# below the separation of genuinely distinct-but-close neighbours a beginner might
# shoot (M 31↔M 32 ≈ 0.4°, M 31↔M 110 ≈ 0.6°), so those are never fused. 0.1° =
# 6 arcmin.
SAME_OBJECT_TOL_DEG = 0.1


class _LocatableTarget(Protocol):
    """The minimal shape :func:`find_same_object_target_groups` reads — any
    target-like row with a plate-solved centre and integration figures. Kept a
    Protocol so the helper stays pure and unit-testable with a lightweight stub,
    not a full :class:`TargetEntry`."""

    safe_name: str
    name: str
    ra_deg: float | None
    dec_deg: float | None
    n_frames_accepted: int
    total_exposure_s: float


@dataclass
class SameObjectGroup:
    """A cluster of ≥2 targets whose centres agree to within the tolerance — i.e.
    the same sky object split across separate folders/nights. ``members`` are the
    original target objects, ordered deepest-integration first (so the natural
    "merge into" is ``members[0]`` — it keeps the most history/identity)."""

    members: list  # the caller's own target rows (see _LocatableTarget), deepest first
    center_ra_deg: float
    center_dec_deg: float
    max_sep_deg: float  # widest pairwise separation in the group (confidence cue)


def find_same_object_target_groups(
    targets: Sequence[_LocatableTarget], *, tol_deg: float = SAME_OBJECT_TOL_DEG,
) -> list[SameObjectGroup]:
    """Group targets that point at the *same sky object* (centres within
    ``tol_deg``), so a nudge can offer to merge each group into one deep stack.

    Pure and offline: it only reads each target's ``ra_deg``/``dec_deg`` (skips
    targets with no plate-solved centre) and its integration figures for
    ordering. Clusters by single-linkage over the wrap/pole-safe haversine
    separation (union-find); singletons are dropped, so the result is only the
    genuine "same object in more than one folder" cases. Groups are returned
    with the most-integrated group first, and each group's members
    deepest-integration first. Returns ``[]`` when nothing clusters."""
    located = [
        t for t in targets
        if t.ra_deg is not None and t.dec_deg is not None
    ]
    n = len(located)
    if n < 2:
        return []

    # Union-find: join any two located targets whose centres are within tol.
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # path halving
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if _angular_separation_deg(
                float(located[i].ra_deg), float(located[i].dec_deg),
                float(located[j].ra_deg), float(located[j].dec_deg),
            ) <= tol_deg:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    groups: list[SameObjectGroup] = []
    for idxs in clusters.values():
        if len(idxs) < 2:
            continue
        members = [located[i] for i in idxs]
        # Deepest integration first, so the default "merge into" keeps the most
        # data; ties break on accepted count then name for a stable order.
        members.sort(
            key=lambda t: (t.total_exposure_s or 0.0, t.n_frames_accepted or 0, t.name),
            reverse=True,
        )
        # Widest pairwise separation in the cluster — an honest confidence cue the
        # UI can show ("all within N′") and a guard the caller could tighten on.
        max_sep = 0.0
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                sep = _angular_separation_deg(
                    float(members[a].ra_deg), float(members[a].dec_deg),
                    float(members[b].ra_deg), float(members[b].dec_deg),
                )
                max_sep = max(max_sep, sep)
        groups.append(SameObjectGroup(
            members=members,
            center_ra_deg=float(members[0].ra_deg),
            center_dec_deg=float(members[0].dec_deg),
            max_sep_deg=max_sep,
        ))

    # Most-integrated group first, so the highest-value merge leads the nudge.
    groups.sort(
        key=lambda g: sum(m.total_exposure_s or 0.0 for m in g.members),
        reverse=True,
    )
    return groups
