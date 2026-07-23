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

from seestack.io.project import readable_frame_path
from seestack.solve.astap import ASTAPError, ASTAPSolver, classify_solve_setup_error

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
    ra_hint_deg: float | None = None,
    dec_hint_deg: float | None = None,
    search_radius_deg: float = 30.0,
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
        r = solver.solve(fits_path, ra_hint_deg=ra_hint_deg, dec_hint_deg=dec_hint_deg,
                         radius_deg=search_radius_deg)
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


def build_solve_arglist(
    project, *, use_hint: bool = True,
) -> list[tuple[int, str, str | None, float, float, float | None, float | None, float]]:
    """
    Build ``[(frame_id, path, astap_path, fov_deg, timeout_s, ra_hint_deg,
    dec_hint_deg, search_radius_deg), ...]`` for :func:`solve_one`.

    Skips frames already solved (have a ``wcs_json``). When ``use_hint`` is on
    and a frame carries a telescope-target hint (``ra_hint_deg``/``dec_hint_deg``
    from its FITS header), it's threaded into ASTAP to localise the search.
    """
    astap_path = project.get_meta("astap_path")  # may be None → use auto-find
    fov_deg = float(project.get_meta("astap_fov_deg") or 1.3)
    timeout_s = float(project.get_meta("astap_timeout_s") or 60.0)
    radius_deg = float(project.get_meta("astap_hint_radius_deg") or 30.0)
    out: list[tuple[int, str, str | None, float, float, float | None, float | None, float]] = []
    for f in project.iter_frames():
        if f.id is None:
            continue
        if f.wcs_json:
            continue  # already solved
        path = readable_frame_path(f)
        if not path:
            continue
        ra_hint = f.ra_hint_deg if use_hint else None
        dec_hint = f.dec_hint_deg if use_hint else None
        out.append((f.id, path, astap_path, fov_deg, timeout_s, ra_hint, dec_hint, radius_deg))
    return out


def apply_solve_result_to_db(project, result: SolveResult) -> None:
    """Write a SolveResult back to the project DB."""
    if not result.solved:
        # Don't touch accept/reject — a frame may be unsolved transiently
        # (clouds blocked the catalog match) but be perfectly fine for stacking
        # if it's similar to its neighbours.
        #
        # For a *setup* failure (ASTAP or its star database missing — the same
        # error on every frame, fixed by a one-time setup step), store a stable
        # canonical reason instead of the raw log. The raw ASTAP message is
        # truncated to 120 chars for storage, and the "no star database" line can
        # land past that window — canonicalising here (where the full log is
        # available) lets the Target page reliably show one actionable banner
        # rather than a wall of un-classifiable "Plate-solve failed" chips.
        # Ordinary per-frame failures keep their raw (truncated) message for
        # debugging.
        raw = result.error or "unknown"
        setup = classify_solve_setup_error(raw)
        reason = setup if setup is not None else raw[:120]
        project.update_frame(result.frame_id, reject_reason=f"solve_failed:{reason}")
        return
    fields: dict = dict(
        wcs_json=result.wcs_text,
        ra_center_deg=result.ra_center_deg,
        dec_center_deg=result.dec_center_deg,
        pixscale_arcsec=result.pixscale_arcsec,
        rotation_deg=result.rotation_deg,
    )
    # If this frame previously failed a plate-solve it carries a stale
    # ``solve_failed:`` reject reason (the failure branch above stores one without
    # touching accept). Now that it solves — e.g. the user installed the ASTAP
    # star database that was missing and re-ran solve, so every frame retries and
    # succeeds — clear that reason so it no longer shows as "plate-solve failed"
    # and no longer inflates the Target page's solve-failure banner. Mirrors the
    # QC path's self-heal (``qc/runner.py``): only ever clears a ``solve_failed:``
    # reason; a user / QC / streak reject is left untouched.
    existing = project.get_frame(result.frame_id)
    if existing is not None and (existing.reject_reason or "").startswith("solve_failed:"):
        fields["reject_reason"] = None
    project.update_frame(result.frame_id, **fields)
