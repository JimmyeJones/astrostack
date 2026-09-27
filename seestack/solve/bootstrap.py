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

**Steps 3–6 have a shortcut when a few subs did solve on their own** (the band
``0 < n_solved < min_frames``, where this still engages): register against one of
*them* and take its real, ASTAP-verified WCS as the reference, instead of
integrating a deep image and solving that. Same registration, same CRPIX
propagation — but no integration, no temp FITS, no second ASTAP call, and none of
that call's risk of failing on the very field that already defeated it per-sub.
The deep-image path stays exactly as it was for the zero-solved case (and for a
target whose solved subs can't be read or don't share the members' shape).

**Field rotation, and why star patterns register these subs now.** Phase
correlation measures a *translation*, and ``skimage``'s never declines: it returns
its best peak whatever the two frames really differ by, with an error of 1.0
either way. The Seestar is alt-az, so a long session turns the field — and a
rotated member was therefore given a confidently wrong place rather than being
left alone. Measured on a synthetic field at 5 arcsec/px: a **4°** member landed
a median 4.2 px (max 10.7 px) from where its stars are, a **8°** one 16 px
(max 24 px) — which on the canvas is a star smeared into an arc. So each member is
now registered by **star-pattern matching** first
(:mod:`seestack.align.starmatch`), which measures the rotation as well as the
shift and *refuses* unless ≥6 stars match at a sub-pixel residual; phase
correlation stays as the fallback for a member too faint to match on, exactly as
before. The deep image is still integrated on the correlation shifts alone — it
is built to be *solvable*, and warping members onto one grid is not what it does.

Safety: this is opt-in (off by default) and additive. A member that doesn't
register confidently is left unsolved (honest — never silently mis-placed), and
a deep image that doesn't solve leaves every sub exactly as it was.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from seestack.align.starmatch import DEFAULT_MAX_ROTATION_DEG, registration_gray
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


# How many already-solved subs to try loading as the registration anchor before
# giving up and integrating a deep image instead. A load is a debayer, so this is
# a work bound, not a quality one — the candidates are tried star-richest first
# and the first one that reads is as good an anchor as the next.
ANCHOR_LOAD_ATTEMPTS = 3


def rescue_would_engage(
    n_solved: int, n_unsolved: int, *, min_frames: int = DEFAULT_MIN_FRAMES,
) -> bool:
    """Would :func:`bootstrap_solve` engage on a target with these counts?

    The engagement gate, as a pure function of two numbers, so a caller can ask
    *before* starting a job — and so the answer it gives a user can never drift
    from the answer the rescue itself gives. :func:`bootstrap_solve` decides with
    this function, it does not re-spell the rule.

    ``n_solved`` is how many of the target's frames carry a WCS (rejected ones
    included — a solved sub is a solved sub whatever its accept flag says, and
    that is the population the deep image competes with). ``n_unsolved`` is how
    many accepted-but-unsolved subs there are to integrate.

    Both halves matter: with ``min_frames`` subs already located there is
    already a real stack's worth and the rescue stands down, and with fewer than
    ``min_frames`` to integrate the deep image would not clear ASTAP's detection
    floor (see the module docstring's measurement).

    Note the caller's ``n_unsolved`` may count subs whose files can't be read
    right now; the rescue checks that itself and declines honestly if too few
    survive. So this is "would it engage", not a promise that it succeeds.
    """
    return n_solved < min_frames and n_unsolved >= min_frames


def rescue_is_worth_offering(
    n_solved: int,
    n_unsolved: int,
    n_tried_and_failed: int,
    *,
    min_frames: int = DEFAULT_MIN_FRAMES,
) -> bool:
    """Should a user be *offered* the rescue on a target with these counts?

    Stricter than :func:`rescue_would_engage`, by one condition: the ordinary
    per-sub solve must already have been tried on at least ``min_frames`` of the
    un-located subs and failed (``n_tried_and_failed`` — accepted subs with no
    WCS carrying a ``solve_failed:`` reason).

    That condition is the difference between "try *harder*" and "try at all". A
    freshly-scanned target on an install with automatic solving off has every sub
    un-located and none of them attempted; the rescue *would* engage there and
    would probably even work — but it would hand each sub a position **propagated**
    from a neighbour when the ordinary solver would have given it its own verified
    one. The first move there is the plate solve, not the rescue, so the button
    stays out of the way until the plate solve has actually been beaten.
    """
    return (
        rescue_would_engage(n_solved, n_unsolved, min_frames=min_frames)
        and n_tried_and_failed >= min_frames
    )


@dataclass
class BootstrapResult:
    """Outcome of a bootstrap attempt (all counts default to a no-op)."""

    engaged: bool = False
    reason: str = ""
    n_members: int = 0
    n_registered: int = 0
    deep_solved: bool = False
    #: True when the burst was registered to an **already-solved** sub and took
    #: its real WCS, instead of integrating a deep image and solving that. The two
    #: are alternatives, so ``deep_solved`` stays False on this path — the deep
    #: image was never built, let alone solved.
    anchored_on_solved_sub: bool = False
    n_propagated: int = 0
    #: How many of ``n_propagated`` were placed by **star-pattern matching**
    #: rather than by a phase-correlation shift. Reported separately because it
    #: is the honest answer to "how was this sub located", and the two answers
    #: rest on different evidence: a similarity fitted to ≥6 identified stars at a
    #: sub-pixel residual, against a correlation peak with no residual at all.
    n_star_matched: int = 0
    propagated_frame_ids: list[int] = field(default_factory=list)

    def as_summary(self) -> dict:
        return {
            "engaged": self.engaged,
            "reason": self.reason,
            "n_members": self.n_members,
            "n_registered": self.n_registered,
            "deep_solved": self.deep_solved,
            "anchored_on_solved_sub": self.anchored_on_solved_sub,
            "n_propagated": self.n_propagated,
            "n_star_matched": self.n_star_matched,
        }


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


def star_match_members(
    grays: list[np.ndarray | None],
    ref_index: int,
    *,
    max_shift_px: float = DEFAULT_MAX_SHIFT_PX,
    max_rotation_deg: float = DEFAULT_MAX_ROTATION_DEG,
) -> list:
    """Match each member's **star pattern** onto the reference's.

    The companion to :func:`register_members`, and the one that can see a
    rotation: it returns a
    :class:`~seestack.align.starmatch.StarTransform` per member — rotation, shift
    and scale together — where the stars matched and passed that module's checks,
    and ``None`` everywhere else (the reference itself, a member that didn't load,
    a field too faint or too sparse to match on). Bounded by the caller's member
    cap, and it loads nothing: these are the frames already in memory for the
    correlation pass.

    ``None`` is not a failure to report, it is "ask phase correlation instead" —
    :func:`propagate_wcs` prefers a transform and falls back to the shift, so a
    member this can't place is exactly as placed as it was before this existed.
    """
    from seestack.align.starmatch import find_star_transform

    out: list = [None] * len(grays)
    ref = grays[ref_index] if 0 <= ref_index < len(grays) else None
    if ref is None:
        return out
    for i, g in enumerate(grays):
        if i == ref_index or g is None:
            continue
        out[i] = find_star_transform(
            ref, g, max_shift_px=max_shift_px, max_rotation_deg=max_rotation_deg,
        )
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


def _wcs_from_star_transform(ref_wcs_text: str, transform, shape) -> str | None:  # noqa: ANN001
    """A member's own WCS from a star-pattern match, or ``None``.

    The match maps this member's pixels onto the reference's, and the reference's
    WCS belongs to that grid — so composing the two *is* this member's solution,
    rotation included. The composition is exact for the linear part of a WCS,
    which is all a similarity of the pixel grid can touch.
    """
    if transform is None:
        return None
    from seestack.io.wcs_io import wcs_text_after_pixel_affine

    matrix, translation = transform.affine()
    h, w = (None, None) if shape is None else (int(shape[0]), int(shape[1]))
    return wcs_text_after_pixel_affine(
        ref_wcs_text, matrix, translation, width=w, height=h,
    )


def propagate_wcs(
    deep_wcs_text: str,
    shifts: list[tuple[float, float] | None],
    ref_index: int,
    *,
    transforms: list | None = None,
    shapes: list | None = None,
    star_placed: list[bool] | None = None,
) -> list[str | None]:
    """Give each member its own WCS from the deep image's solved WCS.

    The deep image shares the reference sub's pixel grid, so ``deep_wcs_text`` is
    the reference sub's WCS. A feature at reference-pixel ``(r, c)`` sits at
    member-pixel ``(r - dr, c - dc)`` for a member registered with shift
    ``(dr, dc)`` (see :func:`_shift_int`), so the member's WCS is the reference's
    with the reference pixel offset: ``CRPIX_member = CRPIX_ref - (dc, dr)`` (the
    CD/scale/rotation are shared). Members with no shift get ``None``.

    ``transforms`` is :func:`star_match_members`' answer, and where it has one
    that member is placed by **it** instead: a shift can only slide the reference
    pixel, so it cannot express the field rotation an alt-az session accumulates,
    while a star match measures the rotation and is refused unless the stars
    themselves agree sub-pixel. ``shapes`` gives ``(h, w)`` per member for the
    ``NAXIS`` of those headers. A member with neither still gets ``None``.

    ``star_placed``, when a list of the same length is passed, is filled with
    which members the star match really placed — not merely which ones *had* one.
    A header this rewrite stands down on (SIP, a legacy ``CROTA``) falls back to
    the shift, and a caller reporting "located by star-pattern matching" has to
    count what happened rather than what was available.
    """
    from seestack.io.wcs_io import wcs_from_text, wcs_to_text

    base = wcs_from_text(deep_wcs_text)
    if base is None:
        return [None] * len(shifts)
    out: list[str | None] = []
    for i, s in enumerate(shifts):
        if i == ref_index:
            out.append(deep_wcs_text)
            continue
        star = _wcs_from_star_transform(
            deep_wcs_text,
            None if transforms is None else transforms[i],
            None if shapes is None else shapes[i],
        )
        if star is not None:
            out.append(star)
            if star_placed is not None and i < len(star_placed):
                star_placed[i] = True
            continue
        if s is None:
            out.append(None)
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


def pick_solved_anchor(frames: list, shape: tuple[int, int]):
    """The best already-solved sub to register this burst against, or ``None``.

    When a *few* subs solved on their own — fewer than ``min_frames``, so the
    bootstrap still engages — one of them is a stronger anchor than a fresh solve
    of the deep image: its WCS is a real ASTAP solution ASTAP has already
    verified, and using it skips building the deep image, writing a temp FITS and
    running the extra solve, along with that solve's own risk of failing on a
    faint field. Everything downstream is unchanged — the same phase-correlation
    shifts, the same CRPIX propagation.

    Candidates are the solved, readable subs in :func:`_order_members` order
    (star-richest, sharpest first — the best correlation target), and the first
    ``ANCHOR_LOAD_ATTEMPTS`` are actually loaded. A candidate is accepted only if
    it carries a **usable** WCS (a truncated sidecar reads back truthy but
    locates nothing) and its pixels are ``shape`` — the members' own shape, since
    a reference of a different size correlates against nothing.

    Returns ``(frame, gray)`` or ``None``, in which case the caller integrates a
    deep image and solves that, exactly as before.
    """
    from seestack.io.wcs_io import wcs_text_is_usable

    candidates = [
        f for f in frames
        if wcs_text_is_usable(f.wcs_json) and readable_frame_path(f) is not None
    ]
    for frame in _order_members(candidates)[:ANCHOR_LOAD_ATTEMPTS]:
        gray = registration_gray(readable_frame_path(frame))
        if gray is not None and gray.shape[:2] == tuple(shape):
            return frame, gray
    return None


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
    star_match: bool = True,
    max_rotation_deg: float = DEFAULT_MAX_ROTATION_DEG,
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

    When one of those few solved subs can serve as the registration reference
    (:func:`pick_solved_anchor`), its own verified WCS is used and **no deep image
    is built or solved** — see the module docstring. ``deep_solver`` is injectable
    for testing and is used only on the deep-image path; production runs ASTAP on
    a temp FITS of the deep image.

    ``star_match`` (on) registers each member by its **star pattern** where that
    succeeds, so a member the session's field rotation has turned is placed by the
    rotation it actually has rather than by a translation that cannot express it —
    see the module docstring for the measurement. It is on inside this already
    opt-in rescue because it is the difference between placing such a member
    correctly and placing it confidently wrong; ``False`` restores the
    correlation-only behaviour, and is what the regression test measures against.
    """
    from seestack.io.wcs_io import wcs_image_center_deg_from_text, wcs_text_is_usable
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

    if not rescue_would_engage(n_solved, len(unsolved), min_frames=min_frames):
        result.reason = ("enough subs already solved" if n_solved >= min_frames
                         else "too few unsolved subs to bootstrap")
        return result

    # Best-first, capped at max_frames — the richest subs make the deepest image.
    members = _order_members(unsolved)[:max_frames]
    paths = [readable_frame_path(f) for f in members]
    grays = [registration_gray(p) if p else None for p in paths]

    valid = [i for i, g in enumerate(grays) if g is not None]
    if len(valid) < min_frames:
        result.reason = "too few readable subs to integrate"
        result.n_members = len(members)
        return result

    # If a few subs *did* solve on their own, register against one of them and use
    # its real WCS rather than solving a deep image: a verified ASTAP solution
    # beats a fresh solve of a synthetic image, and it skips the integration, the
    # temp FITS, the extra ASTAP call and that call's own failure risk. It is
    # prepended as member 0 so the reference is always index 0 on this path;
    # everything below counts only the *unsolved* members, so the engagement
    # gates mean exactly what they meant before.
    anchor = pick_solved_anchor(frames, grays[valid[0]].shape[:2])
    anchored = anchor is not None
    if anchor is not None:
        anchor_frame, anchor_gray = anchor
        members = [anchor_frame, *members]
        paths = [readable_frame_path(anchor_frame), *paths]
        grays = [anchor_gray, *grays]
    first_unsolved = 1 if anchored else 0

    # Reference = the solved anchor if there is one, else the best (first-ordered)
    # sub that actually loaded — it anchors the deep image's WCS, so it should be
    # a star-rich one.
    ref_index = 0 if anchored else valid[0]
    shifts = register_members(grays, ref_index, max_shift_px=max_shift_px)
    # Star-pattern matching, which measures the field rotation a translation
    # cannot. Loads nothing — these frames are already in memory — and is bounded
    # by ``max_frames``, so the cost is one source extraction per member.
    transforms: list = [None] * len(grays)
    if star_match:
        transforms = star_match_members(
            grays, ref_index,
            max_shift_px=max_shift_px, max_rotation_deg=max_rotation_deg,
        )
    registered = [
        i for i, s in enumerate(shifts)
        if (s is not None or transforms[i] is not None)
        and grays[i] is not None and i >= first_unsolved
    ]
    result.n_members = len(members) - first_unsolved
    result.n_registered = len(registered)
    # The deep-image path has to *integrate* ``min_frames`` members, and only the
    # correlation-registered ones are on one pixel grid to integrate — a rotated
    # member would have to be warped, which ``integrate_deep_image`` deliberately
    # does not do. So that path counts shifts only, exactly as it did; the anchored
    # path builds no deep image at all, and there a star-matched member is worth
    # every bit as much as a correlated one.
    integrable = [
        i for i, s in enumerate(shifts)
        if s is not None and grays[i] is not None and i >= first_unsolved
    ]
    if (len(registered) if anchored else len(integrable)) < min_frames:
        result.reason = "too few subs registered to a common frame"
        return result

    if anchored:
        # No deep image is built at all on this path: the anchor's own solution is
        # the reference WCS, and ``propagate_wcs`` offsets CRPIX from it exactly as
        # it would from a solved deep image (both share the reference's pixel grid).
        result.engaged = True
        result.anchored_on_solved_sub = True
        wcs_text = anchor_frame.wcs_json
        pixscale = anchor_frame.pixscale_arcsec
        rotation = anchor_frame.rotation_deg
    else:
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
        # Truthiness is not enough: an empty/truncated ``.wcs`` sidecar reads back as
        # a truthy ``"END"`` blob that parses to a non-``None``, celestial-less WCS
        # (see ``wcs_text_is_usable``). Propagating that would stamp *every* rescued
        # member with a WCS that locates nothing — worse than the honest "didn't
        # solve" here, because a stamped member is never re-offered to the solver.
        if not getattr(solve_res, "solved", False) or not wcs_text_is_usable(wcs_text):
            raw = getattr(solve_res, "error", None) or ""
            setup = classify_solve_setup_error(raw)
            result.reason = setup or "deep image did not solve"
            return result

        result.deep_solved = True
        pixscale = getattr(solve_res, "pixscale_arcsec", None)
        rotation = getattr(solve_res, "rotation_deg", None)

    star_placed = [False] * len(grays)
    member_wcs = propagate_wcs(
        wcs_text, shifts, ref_index,
        transforms=transforms,
        shapes=[None if g is None else g.shape[:2] for g in grays],
        star_placed=star_placed,
    )

    for i, wtext in enumerate(member_wcs):
        if wtext is None or grays[i] is None:
            continue
        if anchored and i == ref_index:
            continue  # the anchor is already solved — never touch a solved sub
        frame = members[i]
        # This member's centre must come from *its own* WCS evaluated at its own
        # centre pixel — not from CRVAL. ``propagate_wcs`` builds each member's
        # solution by keeping the reference's CRVAL/CD and offsetting only CRPIX,
        # so CRVAL is deliberately the *reference* sub's pointing; reading it back
        # as this sub's centre clumped every rescued member at one coordinate,
        # off by its registration shift.
        gh, gw = grays[i].shape[:2]
        centre = wcs_image_center_deg_from_text(wtext, width=gw, height=gh)
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
        if star_placed[i]:
            result.n_star_matched += 1
        result.propagated_frame_ids.append(frame.id)

    how = ("by registering to an already-solved sub" if anchored
           else "via deep-image solve")
    if result.n_star_matched:
        how += f", {result.n_star_matched} of them by star-pattern matching"
    result.reason = f"rescued {result.n_propagated} sub(s) {how}"
    return result
