"""
ASTAP plate-solver wrapper.

ASTAP (https://www.hnsky.org/astap.htm) is a free, fast, local plate solver. It runs
as a command-line executable that reads a FITS file, computes the WCS, and writes
results either back into the FITS header or into a sidecar ``.wcs`` / ``.ini`` file.

Why ASTAP and not astrometry.net? On Windows it's a single ``astap.exe`` install
plus a star database. astrometry.net's Windows story is rough, and the online
solver is slow and rate-limited. ASTAP solves a Seestar frame in roughly a second.

This module is a thin wrapper that:

1. Locates the ``astap.exe`` binary (PATH, common install dirs, or user-set).
2. Runs the solver on a FITS file with sensible defaults for Seestar (~1° FOV).
3. Parses the resulting ``.wcs`` sidecar into an astropy WCS object.

It is a stub for M1 — the full implementation lands in M3 along with parallel
running, retries, and progress reporting.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class ASTAPError(RuntimeError):
    """Raised when ASTAP fails to solve or its output cannot be parsed."""


@dataclass
class ASTAPResult:
    """Outcome of a single solve."""

    fits_path: Path
    wcs_sidecar_path: Path | None
    ra_center_deg: float | None
    dec_center_deg: float | None
    pixscale_arcsec: float | None
    rotation_deg: float | None
    solved: bool
    log_tail: str = ""


# Common ASTAP install locations on Windows.
_DEFAULT_WINDOWS_PATHS = (
    r"C:\Program Files\astap\astap.exe",
    r"C:\Program Files (x86)\astap\astap.exe",
    r"C:\astap\astap.exe",
    r"C:\Users\Public\astap\astap.exe",
    # ASTAP's installer also offers per-user install paths; check %LOCALAPPDATA%.
)


def find_astap(user_path: str | os.PathLike[str] | None = None) -> Path | None:
    """
    Locate astap.exe. Order:
      1. Explicit user path (e.g. from project settings).
      2. ``SEESTACK_ASTAP_PATH`` environment variable.
      3. ``astap`` on PATH.
      4. Common Windows install directories.
      5. ``%LOCALAPPDATA%\\Programs\\astap\\astap.exe``.
    """
    if user_path:
        p = Path(user_path)
        return p if p.exists() else None
    env_path = os.environ.get("SEESTACK_ASTAP_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
    on_path = shutil.which("astap")
    if on_path:
        return Path(on_path)
    for cand in _DEFAULT_WINDOWS_PATHS:
        if Path(cand).exists():
            return Path(cand)
    # Per-user Programs install (some ASTAP versions put it here).
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        cand = Path(local_app) / "Programs" / "astap" / "astap.exe"
        if cand.exists():
            return cand
    return None


def find_star_db_dir(astap_path: str | os.PathLike[str] | None = None) -> Path | None:
    """
    Locate the directory holding ASTAP's star database.

    ASTAP databases come in two band formats: the older ``.290`` files (G/H/V/W
    series, e.g. g05, h18) and the newer ``.1476`` files (D series, e.g. d05,
    d50). Either works; we look for both.

    ASTAP normally finds its database automatically when it lives next to the
    executable (the Windows install layout). In other layouts — notably the
    Docker image, where the binary and the database live in ``/opt/astap`` but
    ASTAP is invoked with a different working directory — auto-detection can miss
    it, and *every* solve then fails with "no star database found". We pass the
    directory explicitly via ASTAP's ``-d`` flag when we can find one.

    Order: ``SEESTACK_ASTAP_DATA`` env var → the executable's own directory.
    Returns ``None`` if no database files are found (then we omit ``-d`` and let
    ASTAP search on its own, preserving the old behaviour).
    """
    candidates: list[Path] = []
    env_dir = os.environ.get("SEESTACK_ASTAP_DATA")
    if env_dir:
        candidates.append(Path(env_dir))
    if astap_path:
        candidates.append(Path(astap_path).resolve().parent)
    for d in candidates:
        try:
            if d.is_dir() and (any(d.glob("*.290")) or any(d.glob("*.1476"))):
                return d
        except OSError:
            continue
    return None


class ASTAPSolver:
    """Run ASTAP on FITS files. Configure once, solve many."""

    # Adaptive solve ladder. Each frame is tried with progressively stronger
    # noise suppression until one attempt solves. Clean frames solve on the
    # first (cheap) attempt; only noisy frames pay for the extra tries.
    #
    # ``downsample`` maps to ASTAP's ``-z`` (bin NxN before detecting stars):
    # binning collapses single-pixel hot/read noise that would otherwise be
    # mistaken for stars, while real stars survive with higher SNR. ``max_stars``
    # maps to ``-s`` (cap on detected stars used for matching) — fewer, brighter
    # stars means less chance of matching against noise.
    _SOLVE_LADDER: tuple[dict[str, int | None], ...] = (
        {"downsample": None},                  # ASTAP default (auto)
        {"downsample": 2},                     # bin 2x — suppress noise
        {"downsample": 4, "max_stars": 200},   # bin 4x, brightest stars only
    )

    def __init__(
        self,
        astap_path: str | os.PathLike[str] | None = None,
        fov_deg: float = 1.3,
        search_radius_deg: float = 30.0,
        timeout_s: float = 60.0,
    ) -> None:
        path = find_astap(astap_path)
        if path is None:
            raise ASTAPError(
                "astap.exe not found. Install ASTAP from https://www.hnsky.org/astap.htm "
                "and either add it to PATH or set the path in Settings."
            )
        self.astap_path = path
        # Where the star database (*.290) lives. None → let ASTAP search itself.
        self.db_dir = find_star_db_dir(path)
        # Seestar S50 has ~1.27° FOV; S30 is wider. 1.3° is a safe default and
        # ASTAP just uses it as a starting hint, so a small mismatch is fine.
        self.fov_deg = fov_deg
        self.search_radius_deg = search_radius_deg
        self.timeout_s = timeout_s

    def solve(self, fits_path: str | os.PathLike[str]) -> ASTAPResult:
        """Solve one FITS file, escalating noise suppression on failure.

        Tries each rung of :attr:`_SOLVE_LADDER` in turn and returns the first
        attempt that solves. If none solve, returns the last failed result with
        a log that records every attempt. A fatal error (e.g. no star database)
        stops the ladder immediately — retrying can't help.
        """
        fits_path = Path(fits_path)
        if not fits_path.exists():
            raise FileNotFoundError(fits_path)

        attempts_log: list[str] = []
        last: ASTAPResult | None = None
        for i, params in enumerate(self._SOLVE_LADDER):
            result = self._solve_once(
                fits_path,
                downsample=params.get("downsample"),
                max_stars=params.get("max_stars"),
            )
            last = result
            if result.solved:
                if i > 0:
                    log.info("solved %s on attempt %d (%s)", fits_path.name, i + 1, params)
                return result
            attempts_log.append(f"[attempt {i + 1} {params}] {result.log_tail.strip()[-300:]}")
            if _is_fatal_solve_error(result.log_tail):
                break  # no database / unreadable file — more tries won't help

        if last is not None:
            last.log_tail = "\n".join(attempts_log)[-2000:]
            return last
        # Defensive: ladder was empty (shouldn't happen).
        raise ASTAPError("no solve attempts were configured")

    def _solve_once(
        self,
        fits_path: Path,
        *,
        downsample: int | None = None,
        max_stars: int | None = None,
    ) -> ASTAPResult:
        """One ASTAP invocation with a specific detection configuration."""
        # ASTAP CLI flags:
        #   -f <file>       FITS file to solve
        #   -fov <deg>      approximate FOV
        #   -r   <deg>      search radius
        #   -z   <0-4>      downsample (bin) before star detection; suppresses noise
        #   -s   <N>        max number of detected stars to use for matching
        #   -wcs            write a .wcs sidecar
        #   -update         also update FITS header (we DON'T want this — keep raws untouched)
        cmd = [
            str(self.astap_path),
            "-f", str(fits_path),
            "-fov", f"{self.fov_deg}",
            "-r", f"{self.search_radius_deg}",
            "-wcs",
        ]
        if downsample is not None:
            cmd += ["-z", str(downsample)]
        if max_stars is not None:
            cmd += ["-s", str(max_stars)]
        # Point ASTAP at the star database explicitly when we know where it is,
        # so solving doesn't depend on the working directory / auto-detection.
        if self.db_dir is not None:
            cmd += ["-d", str(self.db_dir)]
        log.debug("astap cmd: %s", cmd)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ASTAPError(f"ASTAP timed out after {self.timeout_s}s on {fits_path}") from exc

        log_tail = (proc.stdout + proc.stderr)[-2000:]
        wcs_sidecar = fits_path.with_suffix(".wcs")
        ini_sidecar = fits_path.with_suffix(".ini")
        solved = proc.returncode == 0 and wcs_sidecar.exists()

        ra = dec = pix = rot = None
        if solved:
            try:
                ra, dec, pix, rot = _parse_astap_ini(ini_sidecar)
            except Exception as exc:  # noqa: BLE001 — ini format varies
                log.warning("could not parse astap ini for %s: %s", fits_path, exc)

        return ASTAPResult(
            fits_path=fits_path,
            wcs_sidecar_path=wcs_sidecar if solved else None,
            ra_center_deg=ra,
            dec_center_deg=dec,
            pixscale_arcsec=pix,
            rotation_deg=rot,
            solved=solved,
            log_tail=log_tail,
        )


def _is_fatal_solve_error(log_tail: str) -> bool:
    """True if the failure is unrecoverable (retrying with other params is futile)."""
    low = log_tail.lower()
    return any(
        sig in low
        for sig in ("no star database", "star database not found", "could not open", "error reading")
    )


def _parse_astap_ini(ini_path: Path) -> tuple[float, float, float, float]:
    """
    Pull (ra_deg, dec_deg, pixscale_arcsec, rotation_deg) from an ASTAP .ini.

    ASTAP writes a flat key=value file. Keys we care about:
      CRVAL1   — RA center, degrees
      CRVAL2   — Dec center, degrees
      CDELT2   — pixel scale, degrees/pixel (we convert to arcsec)
      CROTA2   — rotation, degrees
    """
    if not ini_path.exists():
        raise ASTAPError(f"no .ini sidecar at {ini_path}")
    values: dict[str, float] = {}
    for line in ini_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        try:
            values[k.strip().upper()] = float(v.strip())
        except ValueError:
            continue
    ra = values["CRVAL1"]
    dec = values["CRVAL2"]
    pixscale_arcsec = abs(values["CDELT2"]) * 3600.0
    rotation = values.get("CROTA2", 0.0)
    return ra, dec, pixscale_arcsec, rotation
