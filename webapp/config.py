"""Settings model + persistence.

Config lives as a single human-editable JSON file inside the dataset's
``state/`` folder (``$ASTROSTACK_DATA/state/config.json``). Keeping it in the
dataset means it survives container recreation — the whole point of pointing
the container at a TrueNAS dataset.

The layout inside the data root:

    <data_root>/
      incoming/      ← watch this; drop Seestar target folders here
      library/       ← organised per-target projects (the Library root)
      state/         ← config.json + jobs.sqlite (kept out of the library tree)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

CONFIG_FILENAME = "config.json"


def default_data_root() -> str:
    return os.environ.get("ASTROSTACK_DATA", "/data")


def _default_cpu_workers() -> int | None:
    env = os.environ.get("ASTROSTACK_CPU_WORKERS")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return None  # None → engine uses os.cpu_count()


class Settings(BaseModel):
    """All user-tunable configuration. Serialized to ``state/config.json``."""

    data_root: str = Field(default_factory=default_data_root)
    # These default to sub-dirs of data_root when left blank (see resolved_*).
    incoming_dir: str = ""
    library_root: str = ""

    # --- watcher -----------------------------------------------------------
    watcher_enabled: bool = True
    # A file must be size+mtime-stable for this long before it's ingested, so
    # half-copied frames arriving over SMB/NFS are never read mid-write.
    watch_quiet_period_s: int = 30
    # Polling safety net — inotify is unreliable on network mounts.
    watch_poll_interval_s: int = 300

    # --- auto pipeline (configurable per the user's request) ---------------
    copy_to_cache: bool = False
    auto_ingest: bool = True
    auto_qc: bool = True
    auto_solve: bool = True
    auto_stack: bool = False

    # --- plate solving -----------------------------------------------------
    astap_path: str | None = None  # falls back to $SEESTACK_ASTAP_PATH, then PATH
    astap_fov_deg: float = 1.3
    astap_timeout_s: float = 60.0

    # --- compute -----------------------------------------------------------
    cpu_workers: int | None = Field(default_factory=_default_cpu_workers)

    # --- Seestar telescope integration -------------------------------------
    # Monitor (and optionally control) Seestar scopes over the LAN via the
    # unofficial JSON-RPC port 4700. Off by default — it only makes sense when
    # the container can actually reach the scope's network (Station mode).
    seestar_enabled: bool = False
    # Control commands (goto / start / stop / park) are gated separately so
    # monitoring can be on without any risk of disturbing an active session.
    seestar_control_enabled: bool = False
    # CIDR to scan for scopes (e.g. "192.168.1.0/24"). Blank = auto-detect from
    # the container's own interfaces.
    seestar_scan_subnet: str = ""
    # Devices that auto-discovery can't reach can be pinned here by IP.
    seestar_known_ips: list[str] = Field(default_factory=list)
    seestar_scan_interval_s: int = 300
    seestar_poll_interval_s: int = 5

    # --- stacking ----------------------------------------------------------
    # Global default StackOptions (per-target overrides live in project meta).
    default_stack_options: dict[str, Any] = Field(default_factory=dict)

    # ---- resolved paths ---------------------------------------------------

    @property
    def resolved_incoming_dir(self) -> Path:
        return Path(self.incoming_dir) if self.incoming_dir else Path(self.data_root) / "incoming"

    @property
    def resolved_library_root(self) -> Path:
        return Path(self.library_root) if self.library_root else Path(self.data_root) / "library"

    @property
    def state_dir(self) -> Path:
        return Path(self.data_root) / "state"

    @property
    def config_path(self) -> Path:
        return self.state_dir / CONFIG_FILENAME

    @property
    def jobs_db_path(self) -> Path:
        return self.state_dir / "jobs.sqlite"

    def ensure_dirs(self) -> None:
        for d in (
            Path(self.data_root),
            self.resolved_incoming_dir,
            self.resolved_library_root,
            self.state_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


class SettingsStore:
    """Thread-safe load/save wrapper around a single config.json."""

    def __init__(self, data_root: str | None = None) -> None:
        self._lock = RLock()
        root = data_root or default_data_root()
        # Bootstrap: load existing config if present, else defaults.
        cfg_path = Path(root) / "state" / CONFIG_FILENAME
        if cfg_path.exists():
            try:
                self._settings = Settings.model_validate_json(cfg_path.read_text())
                # Honor an explicit data_root override from env on every boot.
                self._settings.data_root = root
            except Exception as exc:  # noqa: BLE001
                log.warning("could not parse %s (%s); using defaults", cfg_path, exc)
                self._settings = Settings(data_root=root)
        else:
            self._settings = Settings(data_root=root)
        self._settings.ensure_dirs()
        self.save()

    def get(self) -> Settings:
        with self._lock:
            return self._settings.model_copy(deep=True)

    def update(self, patch: dict[str, Any]) -> Settings:
        with self._lock:
            merged = self._settings.model_dump()
            merged.update({k: v for k, v in patch.items() if k in Settings.model_fields})
            self._settings = Settings.model_validate(merged)
            self._settings.ensure_dirs()
            self.save()
            return self._settings.model_copy(deep=True)

    def save(self) -> None:
        with self._lock:
            self._settings.state_dir.mkdir(parents=True, exist_ok=True)
            self._settings.config_path.write_text(
                json.dumps(json.loads(self._settings.model_dump_json()), indent=2)
            )
