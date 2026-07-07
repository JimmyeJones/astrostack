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
from typing import Any, Literal

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
    # Bounded so a typo (e.g. 0) can't defeat the half-written-file guard,
    # and an absurd value can't stall ingestion for days.
    watch_quiet_period_s: int = Field(default=30, ge=1, le=3600)
    # Polling safety net — inotify is unreliable on network mounts.
    watch_poll_interval_s: int = Field(default=300, ge=2, le=86400)

    # --- auto pipeline (configurable per the user's request) ---------------
    copy_to_cache: bool = False
    auto_ingest: bool = True
    auto_qc: bool = True
    auto_solve: bool = True
    auto_stack: bool = False
    # After a successful background auto-stack, also auto-edit the fresh master
    # into a finished picture (persist the one-click Auto recipe as the run's
    # editor recipe + re-render its thumbnail through it), the same chain the
    # one-click "Process target" and "Reprocess everything" runs use. Off by
    # default (it seeds an editor recipe on every unattended stack); when on, the
    # "drop subs in, walk away, come back to a great image" path returns a
    # finished picture instead of a flat linear master. Best-effort per target —
    # a failed auto-edit never sinks the stack. Requires ``auto_stack``.
    auto_edit_on_autostack: bool = False
    # QC auto-rejects a whole frame when it detects a satellite/plane streak,
    # discarding ~99% good pixels with it. With this on, streaked frames are
    # *flagged* but kept accepted, so a stack with per-pixel rejection
    # (sigma-clip or drizzle rejection) can remove the streak while keeping the
    # frame's good signal. Off by default (the streak is fully rejected) since it
    # only pays off when rejection is enabled at stack time.
    keep_streaked_frames: bool = False
    # Auto-grade: after QC, statistically grade each target's accepted frames
    # (robust outliers on FWHM / stars / sky / eccentricity / transparency) and
    # reject the clearly-bad ones with a plain-language reason. Off by default —
    # the Target page's "Auto-grade" preview covers the manual workflow; this
    # setting makes it hands-off. Frames the user graded are never touched.
    auto_grade_frames: bool = False
    auto_grade_sensitivity: Literal["conservative", "balanced", "aggressive"] = "balanced"

    # --- plate solving -----------------------------------------------------
    astap_path: str | None = None  # falls back to $SEESTACK_ASTAP_PATH, then PATH
    astap_fov_deg: float = Field(default=1.3, ge=0.1, le=20.0)
    # A too-low timeout (e.g. 0) would make every solve attempt fail instantly.
    astap_timeout_s: float = Field(default=60.0, ge=5.0, le=1800.0)
    # Use the telescope target RA/Dec from each frame's FITS header as a
    # plate-solve search hint (localises ASTAP's search; speeds up solving).
    astap_use_solve_hints: bool = True

    # --- compute -----------------------------------------------------------
    # ge=1: a zero/negative worker count would crash the thread/process pool.
    cpu_workers: int | None = Field(default_factory=_default_cpu_workers, ge=1)

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
    seestar_scan_interval_s: int = Field(default=300, ge=30, le=86400)
    seestar_poll_interval_s: int = Field(default=5, ge=1, le=3600)

    # --- stacking ----------------------------------------------------------
    # Global default StackOptions (per-target overrides live in project meta).
    default_stack_options: dict[str, Any] = Field(default_factory=dict)
    # Working-memory cap for a single stack, in GB. None = auto (~70% of
    # available RAM). The ASTROSTACK_MAX_STACK_GB env var, when set, still wins
    # over this (a deployment-level override). Bounds keep a fat-fingered value
    # from either OOM-ing the box or refusing every stack.
    max_stack_memory_gb: float | None = Field(default=None, ge=0.5, le=1024.0)

    # --- jobs --------------------------------------------------------------
    # How many finished jobs the in-memory map keeps (and, at ~10×, how many
    # rows jobs.sqlite retains) before old history is pruned. Higher keeps more
    # of the Jobs/Logs history at the cost of a slightly larger DB; the default
    # matches the long-standing hard-coded cap so an existing install is
    # unchanged. Bounds keep a fat-fingered value from either losing all history
    # or letting the DB grow without bound.
    job_history_limit: int = Field(default=200, ge=10, le=100000)

    # --- access control ----------------------------------------------------
    # Optional HTTP Basic auth. Empty hash = disabled (the app is open). Managed
    # only via /api/auth/password — never set these through the settings PUT.
    auth_username: str = "admin"
    auth_password_hash: str = ""
    auth_salt: str = ""

    # Numeric ranges are enforced by the per-field ``Field(ge=, le=)`` bounds
    # above (a bad value 422s on the settings PUT; see routers/settings.py).

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


def _load_resilient(text: str, root: str) -> "Settings":
    """Load settings from JSON, tolerating a few bad fields on upgrade.

    A single out-of-range or malformed value must never wipe every other
    setting (the app persists user config here, and field bounds can tighten
    between versions). We validate, and if that fails we drop only the offending
    fields — which then fall back to their defaults — and retry, rather than
    discarding the whole file.
    """
    try:
        return Settings.model_validate_json(text)
    except Exception:  # noqa: BLE001
        pass
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        log.warning("config.json is not valid JSON; using defaults")
        return Settings(data_root=root)
    if not isinstance(raw, dict):
        return Settings(data_root=root)
    from pydantic import ValidationError

    for _ in range(len(raw) + 1):
        try:
            return Settings.model_validate(raw)
        except ValidationError as exc:
            bad = {e["loc"][0] for e in exc.errors() if e.get("loc")}
            if not bad or not (bad & raw.keys()):
                break
            for k in bad:
                raw.pop(k, None)  # drop the bad field → it reverts to default
            log.warning("config.json: reset invalid field(s) %s to defaults", sorted(bad))
    return Settings(data_root=root)


class SettingsStore:
    """Thread-safe load/save wrapper around a single config.json."""

    def __init__(self, data_root: str | None = None) -> None:
        self._lock = RLock()
        root = data_root or default_data_root()
        # Bootstrap: load existing config if present, else defaults.
        cfg_path = Path(root) / "state" / CONFIG_FILENAME
        if cfg_path.exists():
            self._settings = _load_resilient(cfg_path.read_text(), root)
        else:
            self._settings = Settings(data_root=root)
        # Honor an explicit data_root override from env on every boot.
        self._settings.data_root = root
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
            path = self._settings.config_path
            payload = json.dumps(json.loads(self._settings.model_dump_json()), indent=2)
            # Atomic write: a crash mid-write must not corrupt config.json (which
            # would silently revert all settings to defaults on next boot).
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(payload)
            os.replace(tmp, path)
