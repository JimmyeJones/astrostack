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
from seestack.solve.astap import (
    SOLVE_FAILED_TIMEOUT,
    ASTAPError,
    ASTAPSolver,
    classify_solve_setup_error,
    is_solve_timeout_error,
)

log = logging.getLogger(__name__)

# A Seestar holds one pointing for a whole target, so once *any* sub has solved
# we know where the scope is aimed to well within a degree. When we offer that
# solved centre as the fallback hint for a still-unsolved sub, search a *tight*
# radius around it (far narrower than the 30° blind default) — a smaller,
# correct search region is exactly what turns an ASTAP timeout/failure on a
# star-poor field into a solve, and 5° leaves generous slack for any real
# field drift while still dramatically localising the search.
SIBLING_HINT_RADIUS_DEG = 5.0


def _fov_deg_for_frame(fits_path: str, fallback_fov_deg: float) -> float:
    """The FOV (degrees) to hand ASTAP for this frame.

    Prefer the value derived from the frame's own FITS header (focal length +
    pixel size + dimensions), which is correct for *any* Seestar model with no
    user config; fall back to the caller-supplied FOV (the configured Settings
    value, else the 1.3° default) when the header lacks the fields. ASTAP's
    quad-matching does not forgive a badly-wrong FOV, so getting this right
    per-frame is the single highest-yield fix for an S30 owner (true FOV ≈ 2.1°)
    whose subs would otherwise all be solved at the wrong 1.3° scale.

    Best-effort: any read/parse problem degrades silently to the fallback.
    """
    try:
        from seestack.io.fits_loader import fov_deg_from_header, load_header

        derived = fov_deg_from_header(load_header(fits_path))
    except Exception:  # noqa: BLE001 — a header read must never sink a solve
        derived = None
    return derived if derived is not None else fallback_fov_deg


def fallback_solve_hint(solved_frames) -> tuple[float, float] | None:
    """Robust median sky centre (RA, Dec in degrees) of the already-solved frames.

    A Seestar points at one target for the whole session, so the centre of the
    subs that *did* plate-solve is a far tighter, more reliable search hint for
    the target's still-unsolved subs than a missing/loose FITS-header hint. Only
    a *search-localisation* aid — ASTAP still verifies the star pattern, so a
    hint that's slightly off can never create a false solution, it just widens
    (or fails) the search as today. RA-wrap-safe for a target near RA=0h (reuses
    the shared :func:`circular_median_ra_deg`). Returns ``None`` when no frame
    carries a usable solved centre.
    """
    import numpy as np

    from seestack.coords import circular_median_ra_deg

    pairs = [
        (f.ra_center_deg, f.dec_center_deg)
        for f in solved_frames
        if getattr(f, "ra_center_deg", None) is not None
        and getattr(f, "dec_center_deg", None) is not None
    ]
    if not pairs:
        return None
    ras = [ra for ra, _ in pairs]
    decs = [dec for _, dec in pairs]
    return (circular_median_ra_deg(ras), float(np.median(decs)))


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

    # Derive the true FOV from this frame's header when possible (S30 ≈ 2.1°,
    # S50 ≈ 1.27°), falling back to the passed-through Settings/default FOV.
    effective_fov_deg = _fov_deg_for_frame(fits_path, fov_deg)

    try:
        solver = ASTAPSolver(astap_path=astap_path, fov_deg=effective_fov_deg, timeout_s=timeout_s)
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
    ra_center = r.ra_center_deg
    dec_center = r.dec_center_deg
    # ASTAP can solve (returncode 0 + a valid ``.wcs`` sidecar) yet leave the centre
    # None when its ``.ini`` sidecar is missing or unparseable — the centre is only
    # read from the ``.ini``. The same coordinates live in the ``.wcs`` sidecar's
    # reference point (CRPIX is the image centre, so CRVAL1/CRVAL2 are the centre),
    # so recover them from the WCS instead of persisting a solved-but-centreless
    # frame. Without a centre the frame stacks but is silently barred from being the
    # reference frame and from seeding sibling plate-solve hints, and is never
    # re-offered to fill it in.
    if r.solved and wcs_text is not None and (ra_center is None or dec_center is None):
        from seestack.io.wcs_io import wcs_center_deg_from_text

        centre = wcs_center_deg_from_text(wcs_text)
        if centre is not None:
            ra_center, dec_center = centre
    return SolveResult(
        frame_id=frame_id, fits_path=fits_path,
        solved=r.solved,
        wcs_text=wcs_text,
        ra_center_deg=ra_center,
        dec_center_deg=dec_center,
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
    from its FITS header), it's threaded into ASTAP to localise the search. When
    a frame has *no* usable header hint but a sibling sub on the same target has
    already solved, its solved centre (:func:`fallback_solve_hint`) is offered
    instead, with a tight :data:`SIBLING_HINT_RADIUS_DEG` search radius — this
    only *fills in* a hint where there wasn't a better one, so a frame that
    already carried a header hint (or ``use_hint=False``) is untouched.
    """
    astap_path = project.get_meta("astap_path")  # may be None → use auto-find
    fov_deg = float(project.get_meta("astap_fov_deg") or 1.3)
    timeout_s = float(project.get_meta("astap_timeout_s") or 60.0)
    radius_deg = float(project.get_meta("astap_hint_radius_deg") or 30.0)

    # A Seestar holds one pointing per target, so once any sub has solved its
    # centre is a far tighter hint for the rest. Collect the solved centres in a
    # single pass and derive one robust fallback hint (suppressed when the caller
    # asked for a fully blind solve). Cap the sibling radius at the configured
    # blind radius so a user who deliberately tightened it is never widened.
    frames = [f for f in project.iter_frames() if f.id is not None]
    fallback = fallback_solve_hint([f for f in frames if f.wcs_json]) if use_hint else None
    sibling_radius = min(radius_deg, SIBLING_HINT_RADIUS_DEG)

    out: list[tuple[int, str, str | None, float, float, float | None, float | None, float]] = []
    for f in frames:
        if f.wcs_json:
            continue  # already solved
        # A deliberately-rejected frame can never enter the stack (``run_stack``
        # combines only accepted **and** solved frames), so re-plate-solving it on
        # every scan is pure wasted ASTAP time — a real drag on a long night with
        # many soft/cloudy subs the user (or QC/streak/auto-grade) dropped. Skip
        # those. But keep offering a frame whose *only* mark against it is a prior
        # ``solve_failed:`` reason: those are the genuine retry candidates once the
        # star database is installed (``apply_solve_result_to_db`` clears the reason
        # on success), and skipping them would strand a first-light user's whole
        # library as un-solvable. Accepted-unsolved frames are offered as before.
        if f.accept is False and not (f.reject_reason or "").startswith("solve_failed:"):
            continue
        path = readable_frame_path(f)
        if not path:
            continue
        ra_hint = f.ra_hint_deg if use_hint else None
        dec_hint = f.dec_hint_deg if use_hint else None
        radius = radius_deg
        # No usable header hint (both coords) but a sibling solved → borrow its
        # centre and search tight around it instead of a loose blind sweep.
        if fallback is not None and (ra_hint is None or dec_hint is None):
            ra_hint, dec_hint = fallback
            radius = sibling_radius
        out.append((f.id, path, astap_path, fov_deg, timeout_s, ra_hint, dec_hint, radius))
    return out


def _store_solve_failed_reason(project, frame_id, reason: str) -> None:
    """Stamp a ``solve_failed:<reason>`` reject reason **without clobbering a real
    prior reason.**

    ``build_solve_arglist`` gates only on ``wcs_json`` (not ``accept``), so a frame
    already carrying a concrete reason — ``user`` / ``qc:`` / ``qc_error``(``_final``)
    / ``auto:streak`` / ``auto:grade:`` / ``bulk:`` — is still offered to plate-solve,
    and a solve *outcome* on it is irrelevant (it's already out of the stack, or its
    QC state is terminal). Mirror the success branch's self-heal contract in reverse:
    only stamp ``solve_failed:`` when the frame carries no reason, or already carries a
    ``solve_failed:`` reason (a re-failed solve just refreshes its message), or is
    still accepted *and* not carrying a ``qc_error`` state.

    The ``qc_error`` carve-out matters: a frame that failed QC (``qc_error:``
    retryable / ``qc_error_final:`` terminal) keeps ``accept`` True
    (``apply_qc_result_to_db`` sets only ``reject_reason``), so the bare ``accepted``
    term would clobber that reason. That defeats the QC terminal-skip state machine —
    ``build_qc_arglist(only_new=True)`` skips only ``qc_error_final`` frames, so a
    clobbered-to-``solve_failed`` frame is re-QC'd every scan forever (and can never
    re-reach ``qc_error_final``, since the next QC failure sees a non-``qc_error``
    prior). Overwriting an ``auto:grade:`` reason additionally breaks the cumulative
    25% auto-grade cap. A prior reason is a real state, so preserve it.
    """
    existing = project.get_frame(frame_id)
    prior = (existing.reject_reason or "") if existing is not None else ""
    accepted = existing.accept if existing is not None else True
    if (not prior
            or prior.startswith("solve_failed:")
            or (accepted and not prior.startswith("qc_error"))):
        project.update_frame(frame_id, reject_reason=f"solve_failed:{reason}")


def apply_solve_result_to_db(project, result: SolveResult) -> None:
    """Write a SolveResult back to the project DB."""
    from seestack.io.wcs_io import wcs_text_is_usable

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
        # The same canonicalisation applies to the *other* fixable failure: every
        # rung of the ladder ran out of time. That one has an obvious next step
        # ("give the solver longer"), but only if the Target page can tell it
        # apart from an ordinary "no catalog match" — and the raw log tail that
        # would otherwise be stored is per-frame text that no tally can group.
        raw = result.error or "unknown"
        setup = classify_solve_setup_error(raw)
        if setup is not None:
            reason = setup
        elif is_solve_timeout_error(raw):
            reason = SOLVE_FAILED_TIMEOUT
        else:
            reason = raw[:120]
        # Preserve a real prior reason (see ``_store_solve_failed_reason``).
        _store_solve_failed_reason(project, result.frame_id, reason)
        return
    if not wcs_text_is_usable(result.wcs_text):
        # ASTAP reported success (returncode 0 + a ``.wcs`` sidecar) but no usable
        # WCS could be extracted from it — a malformed/partial sidecar, or the
        # ``.ini`` parse raised so the centre coords came back None. Persisting
        # this as "solved with wcs_json=None" is a silent trap: ``run_stack``
        # treats a None WCS as unsolved (the frame never stacks), while
        # ``build_solve_arglist`` skips only frames with a *truthy* ``wcs_json``,
        # so the frame is re-offered and re-solved on every scan forever — wasted
        # ASTAP time on a frame that can never contribute. Record an explicit,
        # honest failure so it stops being re-offered and the reject-summary can
        # surface it, mirroring the failure branch above (``accept`` untouched —
        # the pixels may be fine, they just couldn't be located). Use the shared
        # preserve-guard so this branch, like the ``not result.solved`` one, never
        # clobbers a ``qc_error`` / concrete prior reason (a qc_error frame stays
        # ``accept=True`` and is re-offered to solve; a "solved-but-unreadable"
        # result on it must not overwrite its QC state — see
        # ``_store_solve_failed_reason``).
        #
        # The gate is *usability*, not ``is None``: ``wcs_text_from_sidecar``
        # happily returns header text for an empty/truncated ``.wcs`` (a
        # returncode-0 solve whose sidecar write was cut short), and that blob is
        # truthy, so an ``is None`` check let it through — the frame was stored
        # "solved" with a celestial-less ``wcs_json`` and a null centre, which
        # ``build_solve_arglist`` then skips forever (truthy ``wcs_json``) while
        # align feeds the useless WCS to reprojection. A genuine ASTAP solve
        # always ends with a celestial reference point, so requiring one rejects
        # exactly the garbage case and leaves every real solve untouched.
        _store_solve_failed_reason(
            project, result.frame_id, "unreadable plate solution"
        )
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
