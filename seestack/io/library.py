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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from seestack.io.project import Project

log = logging.getLogger(__name__)

LIBRARY_SCHEMA_VERSION = 3
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
    tags                  TEXT                       -- JSON array of tag strings
);

CREATE INDEX IF NOT EXISTS idx_targets_radec ON targets(ra_deg, dec_deg);
"""


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
            lib._init_schema()
            lib._adopt_existing_projects()
            return lib
        lib._open()
        lib._check_schema()
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
        self._conn = sqlite3.connect(self.registry_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # A background scan worker and the GUI hold separate connections to
        # this registry. busy_timeout makes a contended connection wait for
        # the lock instead of immediately raising "database is locked".
        self._conn.execute("PRAGMA busy_timeout = 5000")

    def _init_schema(self) -> None:
        assert self._conn is not None
        self._conn.executescript(_REGISTRY_SCHEMA_SQL)
        self._set_meta("schema_version", str(LIBRARY_SCHEMA_VERSION))
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Add columns introduced by later schema versions to an existing
        ``targets`` table. ``CREATE TABLE IF NOT EXISTS`` never adds columns,
        so each additive column needs an explicit, idempotent ALTER."""
        assert self._conn is not None
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(targets)")}
        if "tags" not in cols:
            self._conn.execute("ALTER TABLE targets ADD COLUMN tags TEXT")

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

    def delete_target(self, name_or_safe: str, *, remove_files: bool = False) -> None:
        """Remove a target from the registry. Files are kept unless
        ``remove_files`` is True (an explicit, destructive choice)."""
        assert self._conn is not None
        entry = self.find_target(name_or_safe)
        if entry is None:
            return
        self._conn.execute("DELETE FROM targets WHERE id = ?", (entry.id,))
        if remove_files:
            import shutil
            shutil.rmtree(self.targets_dir / entry.safe_name, ignore_errors=True)

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
    return float(np.median(ras)), float(np.median(decs))


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
