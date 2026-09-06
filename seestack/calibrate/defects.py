"""
Sensor defect map — find the pixels that are *broken*, and only fix those.

The always-on per-frame ``suppress_hot_cold_pixels`` filter is a blind 3×3
local-median outlier test on the **debayered** frame. It can't tell a real star
peak from a hot pixel, and by the time it runs a single hot CFA site has already
been smeared into a 3×3 halo by the bilinear debayer — so at best it knocks the
defect down to halo level, and at worst it clips a star core.

A master dark knows better. A hot pixel is bright in *every* dark and a dead one
is stuck low in every dark, independent of where the scope was pointed — so the
master dark the calibrate path already builds is a map of exactly which
photosites are broken. Correcting **only** those, in the **raw Bayer domain**
before debayer, erases the defect while it is still a single pixel and can never
touch a star. One-frame transients (cosmic rays, satellite trails) are left to
the multi-frame κ-σ / min-max rejection, which *can* tell a persistent star from
a single-frame spike.

Two pieces, both pure:

* :func:`find_sensor_defects` — a boolean mask of hot/dead photosites, measured
  per **CFA phase** against a local median so a dark-current gradient or amp
  glow reads as sky, not as thousands of defects.
* :class:`DefectMap` — the mask plus the precomputed same-phase neighbour
  gather that :meth:`DefectMap.repair` uses to replace each broken pixel with
  the median of its working neighbours. The gather is built **once** (masters
  are loaded once per stack) so the per-frame cost is proportional to the number
  of *defects*, not to the frame — a few thousand floats, not a canvas copy.

Both are conservative by construction: a set of candidates too large to be
credible as sensor defects (see ``max_fraction``) is refused wholesale rather
than applied, because a threshold that has latched onto structure would repair
the image into mush.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

# Deviation from the local same-phase median, in robust sigmas, before a pixel
# counts as a sensor defect. Deliberately high: a false positive costs a real
# photosite's data on *every* sub, so the bar is "unmistakably broken", not
# "unusual". Hot pixels in a stacked master sit tens of sigma out.
DEFECT_SIGMA = 12.0

# Side (in same-phase samples) of the local-median window the residual is
# measured against: 5 → a 5×5 phase window = 10×10 raw px, wide enough that a
# small cluster of adjacent defects can't define its own baseline and narrow
# enough to follow amp glow.
_LOCAL_WINDOW = 5

# Side (in same-phase samples) of the window a *no-data* sample is filled from
# before the local median is taken. Wider than ``_LOCAL_WINDOW`` so a small hole
# still reaches real data all round it, and a mean rather than a median so a
# partly-filled window degrades smoothly. See ``_local_fill``.
_FILL_WINDOW = 9

# Refuse the whole map above this fraction of the sensor. Real Seestar sensors
# carry defects in the 1e-5..1e-3 range; a percent-scale answer means the
# threshold latched onto structure (a badly-built master, a light frame passed
# in by mistake), and repairing that many pixels would do more harm than the
# defects ever did.
MAX_DEFECT_FRACTION = 0.02

# The eight same-CFA-phase neighbours of a pixel on a 2×2 mosaic.
_PHASE_NEIGHBOURS = tuple(
    (dy, dx)
    for dy in (-2, 0, 2)
    for dx in (-2, 0, 2)
    if not (dy == 0 and dx == 0)
)


def _local_fill(plane: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """A stand-in value for every sample of ``plane`` the master says nothing
    about: the mean of the *valid* samples around it.

    The no-data samples have to hold *something* before ``median_filter`` runs,
    and what they hold matters twice over. Filling them with the whole plane's
    median — which is what this did until v0.369.4 — puts a value from the
    middle of the frame into a corner that may be sitting under amp glow or a
    dark-current gradient, i.e. exactly the structure ``_LOCAL_WINDOW`` exists
    to follow. That spike then (a) reads as a defect at the filled sample itself
    and (b) drags the local median of the *real* pixels beside it, so a hole big
    enough to cover part of a 5×5 window flags a rosette of perfectly good
    photosites around it. A locally-derived fill is flat against its own
    surroundings, so it does neither.

    Falls back to the plane's own median where a sample has no valid neighbour
    within the window at all (a hole wider than ``_FILL_WINDOW``), which is the
    degenerate case the old behaviour was — and those samples still can't be
    flagged, because the caller masks them out afterwards.
    """
    from scipy.ndimage import uniform_filter

    vals = np.where(valid, plane, 0.0).astype(np.float32, copy=False)
    weight = valid.astype(np.float32)
    num = uniform_filter(vals, size=_FILL_WINDOW, mode="reflect")
    den = uniform_filter(weight, size=_FILL_WINDOW, mode="reflect")
    kept = plane[valid]
    fallback = float(np.median(kept)) if kept.size else 0.0
    with np.errstate(invalid="ignore", divide="ignore"):
        local_mean = num / den
    return np.where(den > 0, local_mean, fallback).astype(np.float32, copy=False)


def _robust_scale(residual: np.ndarray) -> float:
    """MAD of ``residual`` about zero, scaled to a Gaussian sigma.

    About zero (not about the median) because ``residual`` is already a
    deviation from the local median, so its centre is zero by construction and
    re-centring on a median dragged by the defects themselves would widen the
    scale exactly where it must not.
    """
    finite = residual[np.isfinite(residual)]
    if finite.size == 0:
        return 0.0
    return float(np.median(np.abs(finite)) * 1.4826)


def _candidate_mask(
    arr: np.ndarray,
    sigma: float,
    exclude: np.ndarray | None,
) -> np.ndarray:
    """The per-phase outlier mask, *before* the ``max_fraction`` ceiling.

    Split out of :func:`find_sensor_defects` so :func:`census_sensor_defects`
    can report how many candidates there were on a master the ceiling refuses —
    the one number that tells a user "this map was declined" apart from "this
    sensor is clean", which the refusal itself deliberately conflates for a
    *repair* caller (see :func:`find_sensor_defects`).
    """
    mask = np.zeros(arr.shape, dtype=bool)
    if sigma <= 0:
        return mask
    if exclude is not None:
        exclude = np.asarray(exclude, dtype=bool)
        if exclude.shape != arr.shape:
            exclude = None

    from scipy.ndimage import median_filter

    for py in (0, 1):
        for px in (0, 1):
            plane = np.asarray(arr[py::2, px::2], dtype=np.float32)
            if plane.size == 0:
                continue
            # A plane thinner than the window still works — ``median_filter``
            # reflects at the edge — but a 1-sample plane has no neighbourhood
            # to be an outlier against, so skip it rather than flag everything.
            if min(plane.shape) < 2:
                continue
            # "No data" is the union of the caller's ``exclude`` map and any
            # sample that is non-finite in its own right: a master says nothing
            # about the sensor at either, so neither may define a baseline, skew
            # the scale, or be flagged.
            valid = np.isfinite(plane)
            if exclude is not None:
                valid &= ~exclude[py::2, px::2]
            all_valid = bool(valid.all())
            if not all_valid:
                plane = np.where(valid, plane, _local_fill(plane, valid))
            local = median_filter(plane, size=_LOCAL_WINDOW, mode="reflect")
            residual = plane - local
            # Measured over the samples the master actually knows about: a fill
            # is a stand-in, not a measurement, and letting it into the MAD moves
            # the threshold every real photosite is judged against.
            scale = _robust_scale(residual if all_valid else residual[valid])
            tol = sigma * scale
            # ``scale == 0`` means the plane is *exactly* its own local median
            # everywhere the noise reaches — a synthetic or heavily quantised
            # master. Then any strict deviation is the outlier, which is the
            # same degradation ``masters._sigma_clip_mean`` makes for the same
            # reason: a zero scale must not be read as "no outliers here".
            flagged = np.abs(residual) > tol
            if not all_valid:
                # The docstring's promise, enforced rather than assumed: a
                # no-data sample can never be flagged, whatever the fill made
                # its residual look like.
                flagged &= valid
            mask[py::2, px::2] = flagged

    return mask


def _over_ceiling(n: int, n_pixels: int, max_fraction: float) -> bool:
    """Is a candidate count too large to be credible as sensor defects?"""
    return bool(n) and n > max_fraction * n_pixels


def find_sensor_defects(
    master: np.ndarray,
    *,
    sigma: float = DEFECT_SIGMA,
    max_fraction: float = MAX_DEFECT_FRACTION,
    exclude: np.ndarray | None = None,
) -> np.ndarray:
    """Boolean mask of hot / dead photosites in a master dark (or bias).

    ``master`` is the raw 2-D Bayer mosaic of a master frame. Each of the four
    CFA phases is measured **separately** against its own local median, so the
    mosaic's own pattern is never read as structure and the four planes each get
    a scale matched to their own noise.

    A pixel is a defect when it sits more than ``sigma`` robust sigmas above
    (hot) or below (dead / stuck-low) the local median of its own phase. The
    test is two-sided on purpose: dark subtraction already removes a hot pixel's
    *mean* level but leaves its excess noise, and it does nothing at all for a
    photosite stuck at a constant — both are pixels whose value carries no sky.

    ``exclude`` marks pixels the master carries **no information** about — the
    caller's "this master pixel was non-finite before sanitizing" map. A master
    with no data at a pixel says nothing about whether the *sensor* is broken
    there, and its sanitized 0 would otherwise read as stuck-low and get the
    light frame's perfectly good sample overwritten from its neighbours. Those
    pixels are neutralised before measuring and can never be flagged.

    Returns an all-``False`` mask (never raises) when the master isn't a usable
    2-D frame, when nothing clears the threshold, or when *too much* does — see
    ``max_fraction``. Callers can therefore treat "no map" and "an empty map"
    identically.
    """
    arr = np.asarray(master)
    if arr.ndim != 2 or arr.size == 0:
        return np.zeros(arr.shape, dtype=bool)

    mask = _candidate_mask(arr, sigma, exclude)
    n = int(np.count_nonzero(mask))
    if _over_ceiling(n, arr.size, max_fraction):
        log.warning(
            "Sensor defect map: %d candidate pixels is %.2f%% of the sensor "
            "(over the %.2f%% ceiling) — refusing the map rather than repairing "
            "structure as if it were broken photosites",
            n, 100.0 * n / arr.size, 100.0 * max_fraction,
        )
        return np.zeros(arr.shape, dtype=bool)
    return mask


@dataclass(frozen=True)
class DefectCensus:
    """How many photosites a master says are broken — the *reporting* answer.

    :func:`find_sensor_defects` deliberately collapses "nothing is broken" and
    "too much read as broken to trust" into the same empty mask, because a
    *repair* caller does the same thing in both cases: nothing. A person reading
    the master's row wants them apart — one means a healthy sensor and the other
    means the repair will not run and why — so this carries the candidate count
    alongside ``refused``.

    ``measurable`` is false when the master isn't a usable 2-D frame at all
    (nothing was measured, as opposed to measured and found clean).
    """

    n_defects: int = 0
    n_pixels: int = 0
    refused: bool = False
    measurable: bool = False

    @property
    def fraction(self) -> float:
        """Share of the sensor flagged, in [0, 1]; 0.0 when nothing was measured."""
        return self.n_defects / self.n_pixels if self.n_pixels else 0.0


def census_sensor_defects(
    master: np.ndarray | None,
    *,
    sigma: float = DEFECT_SIGMA,
    max_fraction: float = MAX_DEFECT_FRACTION,
    exclude: np.ndarray | None = None,
) -> DefectCensus:
    """Count the broken photosites in a master, without building a repair map.

    Same measurement as :func:`find_sensor_defects`, reported rather than
    applied: this is what a screen shows about a master the user is looking at,
    so it must never raise and must distinguish a refused map from a clean
    sensor. Never allocates the neighbour gather — a census is asked for a
    master that may never be stacked with.
    """
    if master is None:
        return DefectCensus()
    arr = np.asarray(master)
    if arr.ndim != 2 or arr.size == 0:
        return DefectCensus()
    mask = _candidate_mask(arr, sigma, exclude)
    n = int(np.count_nonzero(mask))
    return DefectCensus(
        n_defects=n,
        n_pixels=int(arr.size),
        refused=_over_ceiling(n, arr.size, max_fraction),
        measurable=True,
    )


# ``eq=False`` because every field is a numpy array: the generated ``__eq__``
# would return an array (ambiguous truth) and the frozen ``__hash__`` would raise.
# Identity comparison is all any caller wants of a map.
@dataclass(frozen=True, eq=False)
class DefectMap:
    """A sensor defect mask plus the neighbour gather that repairs it.

    Build with :meth:`from_mask` (or :func:`build_defect_map`) once per stack;
    :meth:`repair` is then the per-frame hot path and touches only the defective
    pixels. ``None`` is the right value for "no map" — this class is never
    constructed empty by :func:`build_defect_map`.
    """

    mask: np.ndarray
    # (N,) raw-frame coordinates of the defective pixels.
    ys: np.ndarray
    xs: np.ndarray
    # (8, N) coordinates of each defect's same-phase neighbours, clipped into
    # the frame, with ``valid`` False wherever the neighbour was clipped (it
    # would otherwise duplicate an edge sample) or is itself defective.
    nbr_ys: np.ndarray
    nbr_xs: np.ndarray
    nbr_valid: np.ndarray
    n_defects: int = field(default=0)

    @property
    def shape(self) -> tuple[int, ...]:
        return self.mask.shape

    @classmethod
    def from_mask(cls, mask: np.ndarray) -> DefectMap | None:
        """Precompute the neighbour gather for ``mask``, or ``None`` if empty."""
        mask = np.asarray(mask, dtype=bool)
        if mask.ndim != 2 or not mask.any():
            return None
        h, w = mask.shape
        ys, xs = np.nonzero(mask)
        nbr_ys = np.empty((len(_PHASE_NEIGHBOURS), ys.size), dtype=np.intp)
        nbr_xs = np.empty_like(nbr_ys)
        nbr_valid = np.empty(nbr_ys.shape, dtype=bool)
        for i, (dy, dx) in enumerate(_PHASE_NEIGHBOURS):
            ny, nx = ys + dy, xs + dx
            inside = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
            # Clip only so the gather is in-bounds; ``inside`` is what decides
            # whether the sample counts, so an edge defect medians over the
            # neighbours it really has instead of a duplicated one.
            cy = np.clip(ny, 0, h - 1)
            cx = np.clip(nx, 0, w - 1)
            nbr_ys[i] = cy
            nbr_xs[i] = cx
            # A neighbour that is itself broken carries no sky either.
            nbr_valid[i] = inside & ~mask[cy, cx]
        return cls(
            mask=mask, ys=ys, xs=xs,
            nbr_ys=nbr_ys, nbr_xs=nbr_xs, nbr_valid=nbr_valid,
            n_defects=int(ys.size),
        )

    def repair(self, frame: np.ndarray) -> int:
        """Replace each defective pixel of ``frame`` **in place**, returning how
        many were actually repaired.

        ``frame`` must be the raw 2-D mosaic the map was measured on (a shape
        mismatch is a no-op returning 0 — the same defensive posture
        ``apply_raw`` takes for a mismatched master). Each defect takes the
        median of its working same-phase neighbours, so the replacement is a
        genuine same-colour estimate rather than an average across the CFA.

        A defect with no usable neighbour at all (an isolated frame corner, or a
        cluster large enough to swallow its own surroundings) is **left
        untouched** rather than filled with a guess — a value the map can't
        stand behind is worse than the broken one, which the blind per-frame
        filter downstream will still see.
        """
        if frame.ndim != 2 or frame.shape != self.mask.shape or self.n_defects == 0:
            return 0
        # Gather first, cast after: casting the *frame* would copy the whole
        # mosaic on a non-float32 input, where the gather is only (8, N_defects).
        vals = frame[self.nbr_ys, self.nbr_xs].astype(np.float32, copy=False)
        vals = np.where(self.nbr_valid & np.isfinite(vals), vals, np.nan)
        # An all-NaN column (no usable neighbour) warns; it is the documented
        # "leave it alone" case, handled by the finite test below.
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.filterwarnings("ignore", r"All-NaN.*", RuntimeWarning)
            repaired = np.nanmedian(vals, axis=0)
        ok = np.isfinite(repaired)
        if not ok.any():
            return 0
        frame[self.ys[ok], self.xs[ok]] = repaired[ok].astype(frame.dtype, copy=False)
        return int(np.count_nonzero(ok))


def build_defect_map(
    master: np.ndarray | None,
    *,
    sigma: float = DEFECT_SIGMA,
    max_fraction: float = MAX_DEFECT_FRACTION,
    exclude: np.ndarray | None = None,
) -> DefectMap | None:
    """:func:`find_sensor_defects` + :meth:`DefectMap.from_mask`, or ``None``.

    ``None`` in (no master) gives ``None`` out, as does a master with no
    credible defects — so a caller can hold the result and simply test it.
    """
    if master is None:
        return None
    mask = find_sensor_defects(
        master, sigma=sigma, max_fraction=max_fraction, exclude=exclude)
    return DefectMap.from_mask(mask)
