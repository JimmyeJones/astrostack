"""
Plate solving driver.

The actual solving lives in ``solve.astap`` (which wraps the ASTAP CLI). This
module provides:

  - A picklable ``solve_one`` entry point safe to call from a worker process.
  - ``SolveResult`` — a pure dataclass that crosses the process boundary.
  - ``apply_solve_result_to_db`` — writes WCS + center coords back to the DB.

Why a separate module? ``ASTAPSolver`` opens a subprocess and reads file paths
each time it's used; that's fine inside a worker but you don't want to ship
the live solver instance through pickle. The runner constructs a fresh solver
inside each worker and returns only plain data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from seestack.solve.astap import ASTAPError, ASTAPSolver

log = logging.getLogger(__name__)


@dataclass
class SolveResult:
    """Pickleable solve outcome."""

    frame_id: int
    fits_path: str
    solved: bool
    wcs_text: str | None
    ra_center_deg: float | None
    dec_center_deg: float | None
    pixscale_arcsec: float | None
    rotation_deg: float | None
    error: str | None


def solve_one(
    frame_id: int,
    fits_path: str,
    astap_path: str | None = None,
    fov_deg: float = 1.3,
    timeout_s: float = 60.0,
) -> SolveResult:
    """
    Plate-solve one frame. Picklable, safe to call from ``ProcessPoolExecutor``.

    ASTAP writes its sidecar files (``.wcs``, ``.ini``) next to the FITS file,
    so we read those after the solve completes and serialize the WCS as text
    for storage in the project DB.
    """
    from seestack.io.wcs_io import wcs_text_from_sidecar

    try:
        solver = ASTAPSolver(astap_path=astap_path, fov_deg=fov_deg, timeout_s=timeout_s)
    except ASTAPError as exc:
        return SolveResult(
            frame_id=frame_id, fits_path=fits_path, solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None,
            error=str(exc),
        )

    try:
        r = solver.solve(fits_path)
    except Exception as exc:  # noqa: BLE001
        return SolveResult(
            frame_id=frame_id, fits_path=fits_path, solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    wcs_text = wcs_text_from_sidecar(r.wcs_sidecar_path) if r.wcs_sidecar_path else None
    return SolveResult(
        frame_id=frame_id, fits_path=fits_path,
        solved=r.solved,
        wcs_text=wcs_text,
        ra_center_deg=r.ra_center_deg,
        dec_center_deg=r.dec_center_deg,
        pixscale_arcsec=r.pixscale_arcsec,
        rotation_deg=r.rotation_deg,
        error=None if r.solved else (r.log_tail or "").strip()[-500:] or "no solution",
    )


def build_solve_arglist(project) -> list[tuple[int, str, str | None, float, float]]:
    """
    Build ``[(frame_id, path, astap_path, fov_deg, timeout_s), ...]``.

    Skips frames that have already been solved (already have a ``wcs_json``)
    so a re-run only touches the still-unsolved ones.
    """
    out: list[tuple[int, str, str | None, float, float]] = []
    astap_path = project.get_meta("astap_path")  # may be None → use auto-find
    fov_deg = float(project.get_meta("astap_fov_deg") or 1.3)
    timeout_s = float(project.get_meta("astap_timeout_s") or 60.0)
    for f in project.iter_frames():
        if f.id is None:
            continue
        if f.wcs_json:
            continue  # already solved
        path = f.cached_path or f.source_path
        if not path or not Path(path).exists():
            continue
        out.append((f.id, str(path), astap_path, fov_deg, timeout_s))
    return out


def apply_solve_result_to_db(project, result: SolveResult) -> None:
    """Write a SolveResult back to the project DB."""
    if not result.solved:
        # Don't touch accept/reject — a frame may be unsolved transiently
        # (clouds blocked the catalog match) but be perfectly fine for stacking
        # if it's similar to its neighbours.
        project.update_frame(result.frame_id, reject_reason=f"solve_failed:{(result.error or 'unknown')[:120]}")
        return
    project.update_frame(
        result.frame_id,
        wcs_json=result.wcs_text,
        ra_center_deg=result.ra_center_deg,
        dec_center_deg=result.dec_center_deg,
        pixscale_arcsec=result.pixscale_arcsec,
        rotation_deg=result.rotation_deg,
    )
