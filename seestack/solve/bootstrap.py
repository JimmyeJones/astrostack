"""
Stack-then-solve bootstrap — rescue a faint field that won't plate-solve per-sub.

On a faint / sparse-star field a single 10 s Seestar sub simply lacks the SNR to
show ASTAP enough stars, so it fails to plate-solve and ``run_stack`` drops it
(it combines only accepted **and** solved frames). The result is a "stack" of the
handful of subs that happened to solve — often one — i.e. the owner's reported
single-frame colour speckle.

Mature tools (Siril's global registration, N.I.N.A.'s blind-solve after a rough
stack) get around this by **integrating first to raise SNR, then solving the deep
image**. That is exactly what this module does, and it was *measured* to work:
with the real ASTAP CLI + the bundled d05 database, at a faintness where a single
sub detects 0–2 stars (below ASTAP's ≥3-star abort — un-solvable) a plain mean of
8–16 subs detects 6–12 stars — comfortably solvable — and the gain survives a few
pixels of uncompensated inter-sub drift (see ``docs/IMPROVEMENTS.md``).

The flow (all pure/testable except the one ASTAP call, which is injected):

  1. Gather the target's **accepted-but-unsolved** subs.
  2. Guard: only engage when the per-sub solve left too few solved to make a real
     stack yet there are enough unsolved subs to integrate a deep image.
  3. Load + debayer + luminance-flatten each member for registration.
  4. Register every member to a chosen reference sub with phase correlation
     (integer-pixel shift — enough per the jitter measurement), skipping any that
     can't be located confidently within a bounded shift.
  5. Mean the registered members onto the reference grid → a higher-SNR deep image.
  6. Plate-solve **that** deep image once.
  7. The deep image shares the reference sub's pixel grid, so its solved WCS *is*
     the reference sub's WCS. Propagate it to every member by offsetting the
     reference pixel (CRPIX) by the member's measured shift — giving each member a
     per-sub WCS so the whole burst can finally stack.

Safety: this is opt-in (off by default) and additive. A member that doesn't
register confidently is left unsolved (honest — never silently mis-placed), and
a deep image that doesn't solve leaves every sub exactly as it was.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from seestack.io.project import readable_frame_path

log = logging.getLogger(__name__)

# Default number of accepted-unsolved subs to integrate for the deep image. The
# audit measured a plain mean of 8–16 subs is enough to lift a faint field over
# ASTAP's detection floor; 8 is the minimum that reliably solved.
DEFAULT_MIN_FRAMES = 8
DEFAULT_MAX_FRAMES = 16

# A member whose measured registration shift exceeds this (pixels) is treated as
# a bad correlation lock (noise, a passing cloud, a genuinely different pointing)
# and left unsolved rather than propagated to a wrong place. A Seestar holds one
# pointing per target with only small dither/drift, so a real member never needs
# a large shift; this bounds the "silent mis-placement" risk the idea flagged.
DEFAULT_MAX_SHIFT_PX = 200.0


@dataclass
class BootstrapResult:
    """Outcome of a bootstrap attempt (all counts default to a no-op)."""

    engaged: bool = False
    reason: str = ""
    n_members: int = 0
    n_registered: int = 0
    deep_solved: bool = False
    n_propagated: int = 0
    propagated_frame_ids: list[int] = field(default_factory=list)

    def as_summary(self) -> dict:
        return {
            "engaged": self.engaged,
            "reason": self.reason,
            "n_members": self.n_members,
            "n_registered": self.n_registered,
            "deep_solved": self.deep_solved,
            "n_propagated": self.n_propagated,
        }


def _registration_gray(path: str) -> np.ndarray | None:
    """Load a sub as a background-flattened luminance image for star registration.

    Debayer to RGB, average to a single luminance plane, then subtract a robust
    sky level and clip negatives so phase correlation locks onto the *stars*
    rather than the (frame-varying) sky pedestal or the Bayer checkerboard.
    Returns ``None`` on any read/decode problem — a member we can't read is just
    skipped, never fatal.
    """
    try:
        from seestack.io.fits_loader import load_seestar_raw

        rgb, _info = load_seestar_raw(path, debayer=True, out_dtype=np.float32)
    except Exception as exc:  # noqa: BLE001 — a bad sub must never sink the batch
        log.debug("bootstrap: could not load %s: %s", path, exc)
        return None
    gray = np.asarray(rgb, dtype=np.float32)
    if gray.ndim == 3:
        gray = gray.mean(axis=2)
    if gray.ndim != 2 or gray.size == 0:
        return None
    # Robust sky subtraction: the median is a stable pedestal estimate on a
    # star-sparse field. Clip negatives so only star flux drives the correlation.
    sky = float(np.nanmedian(gray))
    flat = gray - sky
    np.clip(flat, 0.0, None, out=flat)
    # A frame that came back all-NaN or flat (no signal) can't register.
    if not np.isfinite(flat).any() or float(np.nanmax(flat)) <= 0.0:
        return None
    return np.nan_to_num(flat, nan=0.0, posinf=0.0, neginf=0.0)


def _phase_shift(reference: np.ndarray, moving: np.ndarray) -> tuple[float, float] | None:
    """Integer-ish (row, col) shift to align ``moving`` onto ``reference``.

    Wraps :func:`skimage.registration.phase_cross_correlation` with the same
    ``(reference, moving)`` convention it uses: the returned shift is what
    ``scipy.ndimage.shift(moving, shift)`` would apply to register ``moving`` to
    ``reference``. Returns ``None`` if the correlation can't be computed.
    """
    try:
        from skimage.registration import phase_cross_correlation

        shift, _error, _phase = phase_cross_correlation(
            reference, moving, upsample_factor=1,
        )
    except Exception as exc:  # noqa: BLE001 — a bad correlation just skips the member
        log.debug("bootstrap: phase correlation failed: %s", exc)
        return None
    return (float(shift[0]), float(shift[1]))


def register_members(
    grays: list[np.ndarray | None],
    ref_index: int,
    *,
    max_shift_px: float = DEFAULT_MAX_SHIFT_PX,
) -> list[tuple[float, float] | None]:
    """Measure each member's ``(row, col)`` shift onto the reference.

    ``grays[ref_index]`` is the reference (its own shift is ``(0.0, 0.0)``). A
    member that can't be correlated, or whose shift exceeds ``max_shift_px`` in
    either axis (a bad lock or a genuinely different pointing), returns ``None``
    and will not be integrated or propagated to — it stays honestly unsolved.
    """
    ref = grays[ref_index]
    out: list[tuple[float, float] | None] = []
    for i, g in enumerate(grays):
        if i == ref_index:
            out.append((0.0, 0.0))
            continue
        if g is None or ref is None or g.shape != ref.shape:
            out.append(None)
            continue
        shift = _phase_shift(ref, g)
        if shift is None or abs(shift[0]) > max_shift_px or abs(shift[1]) > max_shift_px:
            out.append(None)
            continue
        out.append(shift)
    return out


def _shift_int(img: np.ndarray, dr: int, dc: int) -> np.ndarray:
    """Integer shift with NaN fill: ``out[r, c] = img[r - dr, c - dc]``.

    Matches :func:`scipy.ndimage.shift` translation semantics (a positive ``dr``
    moves content *down*), so a member's registration shift can be applied
    directly. Pixels shifted in from outside the frame are NaN (no coverage).
    """
    h, w = img.shape
    out = np.full_like(img, np.nan)
    r0d, r1d = max(0, dr), min(h, h + dr)
    c0d, c1d = max(0, dc), min(w, w + dc)
    r0s, r1s = max(0, -dr), min(h, h - dr)
    c0s, c1s = max(0, -dc), min(w, w - dc)
    if r1d > r0d and c1d > c0d:
        out[r0d:r1d, c0d:c1d] = img[r0s:r1s, c0s:c1s]
    return out


def integrate_deep_image(
    grays: list[np.ndarray | None],
    shifts: list[tuple[float, float] | None],
    ref_index: int,
) -> np.ndarray:
    """Mean the confidently-registered members onto the reference grid.

    Each member is integer-shifted onto the reference's pixels and the stack is
    averaged NaN-aware (over covered pixels only), so the deep image has the
    reference sub's shape/grid and a higher SNR — the star signal adds while the
    per-frame sky noise averages down. Members whose shift is ``None`` are
    excluded. Any pixel covered by no member is left as the sky floor (0.0).
    """
    ref = grays[ref_index]
    if ref is None:
        raise ValueError("reference gray image is None")
    stack: list[np.ndarray] = []
    for g, s in zip(grays, shifts, strict=True):
        if g is None or s is None or g.shape != ref.shape:
            continue
        stack.append(_shift_int(g, int(round(s[0])), int(round(s[1]))))
    if not stack:
        raise ValueError("no registered members to integrate")
    arr = np.stack(stack, axis=0)
    with np.errstate(invalid="ignore"):
        deep = np.nanmean(arr, axis=0)
    return np.nan_to_num(deep, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


def propagate_wcs(
    deep_wcs_text: str,
    shifts: list[tuple[float, float] | None],
    ref_index: int,
) -> list[str | None]:
    """Give each member its own WCS from the deep image's solved WCS.

    The deep image shares the reference sub's pixel grid, so ``deep_wcs_text`` is
    the reference sub's WCS. A feature at reference-pixel ``(r, c)`` sits at
    member-pixel ``(r - dr, c - dc)`` for a member registered with shift
    ``(dr, dc)`` (see :func:`_shift_int`), so the member's WCS is the reference's
    with the reference pixel offset: ``CRPIX_member = CRPIX_ref - (dc, dr)`` (the
    CD/scale/rotation are shared). Members with no shift get ``None``.
    """
    from seestack.io.wcs_io import wcs_from_text, wcs_to_text

    base = wcs_from_text(deep_wcs_text)
    if base is None:
        return [None] * len(shifts)
    out: list[str | None] = []
    for i, s in enumerate(shifts):
        if s is None:
            out.append(None)
            continue
        if i == ref_index:
            out.append(deep_wcs_text)
            continue
        dr, dc = s
        w = base.deepcopy()
        # CRPIX is (x, y) = (col, row); offset by -(dc, dr).
        w.wcs.crpix = [base.wcs.crpix[0] - dc, base.wcs.crpix[1] - dr]
        out.append(wcs_to_text(w))
    return out


def _order_members(frames: list) -> list:
    """Order candidate subs best-first for integration.

    Prefer the star-richest, sharpest subs (they carry the most signal into the
    deep image) using whatever QC metrics are present; a sub with no QC metrics
    sorts after graded ones but is still eligible. Stable and deterministic.
    """
    def key(f):
        stars = f.star_count if f.star_count is not None else -1
        # Lower FWHM (sharper) is better; unknown sorts worst.
        fwhm = f.fwhm_px if f.fwhm_px is not None else 1e9
        return (-stars, fwhm)

    return sorted(frames, key=key)


def _default_deep_solver(
    deep: np.ndarray,
    *,
    astap_path: str | None,
    fov_deg: float,
    timeout_s: float,
    ra_hint_deg: float | None,
    dec_hint_deg: float | None,
):
    """Write the deep image to a temp FITS and plate-solve it once with ASTAP.

    Returns the :class:`~seestack.solve.runner.SolveResult`. Isolated behind a
    parameter so the pure bootstrap logic is fully testable without ASTAP.
    """
    import tempfile
    from pathlib import Path

    from astropy.io import fits

    from seestack.solve.runner import solve_one

    with tempfile.TemporaryDirectory(prefix="astrostack-bootstrap-") as td:
        deep_path = Path(td) / "deep.fits"
        fits.PrimaryHDU(data=np.asarray(deep, dtype=np.float32)).writeto(
            deep_path, overwrite=True,
        )
        # The deep image carries no optics headers, so solve_one falls back to the
        # FOV we pass — the reference sub's true (header-derived) FOV.
        return solve_one(
            frame_id=-1,
            fits_path=str(deep_path),
            astap_path=astap_path,
            fov_deg=fov_deg,
            timeout_s=timeout_s,
            ra_hint_deg=ra_hint_deg,
            dec_hint_deg=dec_hint_deg,
        )


def bootstrap_solve(
    project,
    *,
    astap_path: str | None = None,
    fov_deg: float = 1.3,
    timeout_s: float = 60.0,
    min_frames: int = DEFAULT_MIN_FRAMES,
    max_frames: int = DEFAULT_MAX_FRAMES,
    max_shift_px: float = DEFAULT_MAX_SHIFT_PX,
    deep_solver=None,
) -> BootstrapResult:
    """Attempt to rescue a target's un-plate-solvable faint subs.

    Engages only when the ordinary per-sub solve left **fewer than
    ``min_frames`` subs solved** (so there isn't already a real stack's worth)
    yet there are **at least ``min_frames`` accepted-but-unsolved subs** to
    integrate. On success, writes a propagated ``wcs_json`` (and centre) to each
    rescued member so they can finally stack. Never deletes, never touches an
    already-solved or deliberately-rejected sub, and skips any member it can't
    register confidently. Returns a :class:`BootstrapResult`.

    ``deep_solver`` is injectable for testing; production uses ASTAP on a temp
    FITS of the deep image.
    """
    from seestack.io.wcs_io import wcs_center_deg_from_text, wcs_text_is_usable
    from seestack.solve.astap import classify_solve_setup_error
    from seestack.solve.runner import _fov_deg_for_frame

    result = BootstrapResult()

    frames = [f for f in project.iter_frames() if f.id is not None]
    n_solved = sum(1 for f in frames if f.wcs_json)
    unsolved = [
        f for f in frames
        if not f.wcs_json
        and f.accept is not False
        and readable_frame_path(f) is not None
    ]

    if n_solved >= min_frames:
        result.reason = "enough subs already solved"
        return result
    if len(unsolved) < min_frames:
        result.reason = "too few unsolved subs to bootstrap"
        return result

    # Best-first, capped at max_frames — the richest subs make the deepest image.
    members = _order_members(unsolved)[:max_frames]
    paths = [readable_frame_path(f) for f in members]
    grays = [_registration_gray(p) if p else None for p in paths]

    valid = [i for i, g in enumerate(grays) if g is not None]
    if len(valid) < min_frames:
        result.reason = "too few readable subs to integrate"
        result.n_members = len(members)
        return result

    # Reference = the best (first-ordered) sub that actually loaded — it anchors
    # the deep image's WCS, so it should be a star-rich one.
    ref_index = valid[0]
    shifts = register_members(grays, ref_index, max_shift_px=max_shift_px)
    registered = [i for i, s in enumerate(shifts) if s is not None and grays[i] is not None]
    result.n_members = len(members)
    result.n_registered = len(registered)
    if len(registered) < min_frames:
        result.reason = "too few subs registered to a common frame"
        return result

    deep = integrate_deep_image(grays, shifts, ref_index)

    ref_frame = members[ref_index]
    ref_fov = _fov_deg_for_frame(paths[ref_index], fov_deg)
    ra_hint = ref_frame.ra_hint_deg
    dec_hint = ref_frame.dec_hint_deg

    solver = deep_solver if deep_solver is not None else _default_deep_solver
    try:
        solve_res = solver(
            deep,
            astap_path=astap_path,
            fov_deg=ref_fov,
            timeout_s=timeout_s,
            ra_hint_deg=ra_hint,
            dec_hint_deg=dec_hint,
        )
    except Exception as exc:  # noqa: BLE001 — a solve crash must not sink the scan
        log.warning("bootstrap deep solve raised: %s", exc)
        result.engaged = True
        result.reason = "deep-image solve error"
        return result

    result.engaged = True
    wcs_text = getattr(solve_res, "wcs_text", None)
    # Truthiness is not enough: an empty/truncated ``.wcs`` sidecar reads back as a
    # truthy ``"END"`` blob that parses to a non-``None``, celestial-less WCS (see
    # ``wcs_text_is_usable``). Propagating that would stamp *every* rescued member
    # with a WCS that locates nothing — worse than the honest "didn't solve" here,
    # because a stamped member is never re-offered to the solver again.
    if not getattr(solve_res, "solved", False) or not wcs_text_is_usable(wcs_text):
        raw = getattr(solve_res, "error", None) or ""
        setup = classify_solve_setup_error(raw)
        result.reason = setup or "deep image did not solve"
        return result

    result.deep_solved = True
    pixscale = getattr(solve_res, "pixscale_arcsec", None)
    rotation = getattr(solve_res, "rotation_deg", None)
    member_wcs = propagate_wcs(wcs_text, shifts, ref_index)

    for i, wtext in enumerate(member_wcs):
        if wtext is None or grays[i] is None:
            continue
        frame = members[i]
        centre = wcs_center_deg_from_text(wtext)
        ra_c, dec_c = centre if centre is not None else (None, None)
        fields: dict = dict(
            wcs_json=wtext,
            ra_center_deg=ra_c,
            dec_center_deg=dec_c,
            pixscale_arcsec=pixscale,
            rotation_deg=rotation,
        )
        # A member that carried a stale ``solve_failed:`` reason is now located —
        # clear it (mirrors ``apply_solve_result_to_db``'s self-heal); never touch
        # a user/QC/streak/grade reject reason.
        if (frame.reject_reason or "").startswith("solve_failed:"):
            fields["reject_reason"] = None
        project.update_frame(frame.id, **fields)
        result.n_propagated += 1
        result.propagated_frame_ids.append(frame.id)

    result.reason = f"rescued {result.n_propagated} sub(s) via deep-image solve"
    return result
