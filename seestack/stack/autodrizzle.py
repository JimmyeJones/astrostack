"""Should an unattended stack drizzle itself? — "Auto, when worth it".

The owner noticed his finished pictures come out at the sensor's own resolution
and asked whether drizzle is ever used. It never was: ``StackOptions.drizzle``
defaults off and no unattended path ever set it, so the only way to get a
super-resolved picture was to tick a box on the Stack form before every run.
Asked what he wanted instead, he chose **"Auto, when worth it"** — which is the
one answer that needs a definition of *worth it*, and this module is it.

Drizzle buys resolution back from an undersampled sensor by depositing each
sub's pixels onto a finer grid, and it only works when **lots of sub-pixel-shifted
samples land on every output pixel**: see :mod:`seestack.stack.drizzle_path`'s
own recommendation ("use drizzle when lots of dithered subs land on each output
pixel — typically 200+"). Below that the finer grid is filled by too few samples
and the result comes back slower, noisier and gappier than the ordinary
weighted-mean path. So "worth it" is two measurements and a budget:

1. **Depth per output pixel** ≥ :data:`AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL`.
   Counted *per output pixel*, never as the target's frame total — on a mosaic
   the subs are spread across the raster, so a 3×3 raster 900 subs deep in total
   has ~100 on any pixel, and a bar counted in frames says yes on exactly the
   canvas drizzle handles worst. This is the same per-pixel count
   ``webapp.routers.stack._pixel_depth`` and ``frontend/src/samplesPerPixel.ts``
   compute for the Stack form's own drizzle caution — canvas area ÷ frame
   footprint — and :func:`samples_per_output_pixel` is this module's copy of that
   arithmetic, guarded against drift by ``tests/test_auto_drizzle_mirror.py``.
2. **The subs actually moved sub-pixel between frames**
   (:func:`dither_spread_px` ≥ :data:`AUTO_DRIZZLE_MIN_DITHER_PX` on **both**
   axes). Without sub-pixel variety every sample on an output pixel carries the
   same phase, and drizzle adds a grid rather than detail.
3. **The ×1.5 canvas fits the memory budget together with its two-pass
   rejection** — an unattended drizzle without outlier rejection keeps every
   satellite, so the pair is priced as one. The scale steps down towards
   :data:`AUTO_DRIZZLE_MIN_SCALE` and below that the answer is simply "no".

**What saying yes costs, measured** (2026-10-12, ``scripts/measure_drizzle_cost.py``;
four real ``run_stack`` runs over the same 1920×1080 subs at 12 / 24 / 36 frames
on a 4-vCPU container). Per-sub slope over that span: plain reproject +
weighted mean **0.78 s**, drizzle ×1.0 single-pass 1.97 s, drizzle ×1.5
single-pass 2.23 s, and what this module actually asks for — ×1.5 with two-pass
rejection — **5.68 s**. So an automatic drizzle costs about **×7 a plain sub**:
~×2.9 for drizzle plus the bigger canvas, and a further ~×2.5 for the second
pass, which makes ``drizzle_path``'s "two-pass rejection roughly doubles that
again" right and a little understated. The whole-run ratio reads lower (×5.2 at
12 subs, ×6.4 at 36) only because both paths share the same fixed start-up cost.

The **ratio** is the transferable half — the seconds belong to that container,
and ``seestack.stacktime.estimate_from_runs`` already measures the owner's own
seconds-per-sub per ``stack_cost_class`` from his finished runs. Multiplying the
two is uncomfortable at his scale: on a target of 5,477 subs ×7 turns about an
hour of stacking into most of a day's, and his deepest is 35,894. Nothing here
refuses on those grounds, deliberately — a time gate is a *new* refusal on the
on-by-default hot path and the owner's own call, so it is filed for him rather
than guessed at. What this note exists to prevent is the next reader assuming
the cost is a few percent.

Nothing here reads a setting or touches I/O: the decision is a pure function of
numbers the stacker already has in hand, so the run that makes it, the header
card that records it and the sentence History reads can never describe three
different decisions. It is only ever *asked* on a run that expressed no drizzle
choice of its own (``StackOptions.auto_drizzle``, which only the unattended
chains set) — an explicit ``drizzle`` in the owner's global or per-target saved
defaults always wins, on **or** off.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

log = logging.getLogger(__name__)

#: Samples **on one output pixel** below which an automatic drizzle is the wrong
#: call. The engine's own recommendation (``drizzle_path``'s module docstring)
#: is "typically 200+", and this is that recommendation rather than
#: ``DRIZZLE_MIN_SAMPLES_PER_PIXEL`` (100), which is the *warn* bar — the depth
#: below which recommending drizzle is actively bad advice. The two are
#: deliberately different numbers: one is "don't nag a user who asked for it",
#: this one is "don't turn it on for a user who didn't".
AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL = 200

#: Per-axis spread of the subs' sub-pixel phases, in output pixels, below which
#: the set is read as undithered. A perfectly undithered set scores 0.0 and a
#: uniformly dithered one ~0.289 (the standard deviation of a uniform
#: distribution over one pixel, 1/√12), so 0.2 sits between "every sample shares
#: a phase" and "the phases fill the pixel" with room on both sides. Plate-solve
#: noise alone is a few tenths of a pixel, so this is a guard against the
#: pathological case (a set that never moved at all) rather than a fine judgement
#: of dither quality — which is the only thing it can honestly be, since the
#: phases are measured *through* the solve.
AUTO_DRIZZLE_MIN_DITHER_PX = 0.2

#: What an automatic drizzle asks for, and the floor it will step down to rather
#: than give up. ×1.5 is the scale the Stack form's own drizzle probe uses, and
#: ×2 is deliberately not offered: it quadruples the canvas on a target whose
#: canvas is the one thing a walk-away box has least of.
AUTO_DRIZZLE_SCALE = 1.5
AUTO_DRIZZLE_MIN_SCALE = 1.2
#: The grain the step-down walks on, matching ``_largest_drizzle_scale_within_budget``'s
#: own default so the two can't land between each other's stops.
AUTO_DRIZZLE_SCALE_STEP = 0.1

#: Why the decision went the way it did. Stable codes: they are stamped into the
#: output FITS header (``ADRZWHY``) and read back by
#: ``frontend/src/routes/History.tsx`` to build the sentence, so a code is part
#: of the file format and only ever gets *added* to.
REASON_DEEP_AND_DITHERED = "deep_and_dithered"
REASON_TOO_FEW_SAMPLES = "too_few_samples"
REASON_TOO_LITTLE_DITHER = "too_little_dither"
REASON_DITHER_UNKNOWN = "dither_unknown"
REASON_NO_ROOM_IN_BUDGET = "no_room_in_budget"

AUTO_DRIZZLE_REASONS = (
    REASON_DEEP_AND_DITHERED,
    REASON_TOO_FEW_SAMPLES,
    REASON_TOO_LITTLE_DITHER,
    REASON_DITHER_UNKNOWN,
    REASON_NO_ROOM_IN_BUDGET,
)

#: Per-sub cost of each drizzle cost class, as a multiple of a plain reproject +
#: weighted mean — the transferable half of the 2026-10-12 measurement in the
#: module docstring (``scripts/measure_drizzle_cost.py``: 0.78 s plain, 2.23 s
#: drizzle ×1.5 single-pass, 5.68 s drizzle ×1.5 with two-pass rejection, over
#: the same 1920×1080 subs at 12/24/36 frames).
#:
#: Keyed on ``seestack.stacktime.stack_cost_class``, which is what separates
#: runs the owner's own seconds-per-sub may be read across — so the ratio and
#: the measured rate it multiplies are talking about the same two jobs. The
#: numbers are for ×1.5; the automatic path may step down to ×1.2, where the
#: canvas is ~36 % smaller than ×1.5's, so a stepped-down run comes in *under*
#: its estimate. That direction is the safe one for a sentence beginning
#: "about", and splitting the ratio by scale would be inventing two more numbers
#: from one measurement.
DRIZZLE_COST_RATIO = {
    "drizzle": 2.9,
    "drizzle+reject": 7.3,
}


@dataclass(frozen=True)
class DitherSpread:
    """How far the subs' sub-pixel phases spread, per axis, in output pixels.

    ``panels`` is how many pointing groups the measurement was taken *within* —
    1 for a pooled single-field measurement, N for a mosaic measured panel by
    panel. It is load-bearing rather than decorative: pooling a mosaic's phases
    would read a raster of perfectly undithered panels as beautifully dithered,
    because each panel sits at its own arbitrary sub-pixel offset from the canvas
    grid while no *pixel* ever sees more than one of them. So a mosaic is
    measured per panel and ``x``/``y`` carry the **worst** panel's spread.
    """

    x: float
    y: float
    n: int
    panels: int

    @property
    def worst(self) -> float:
        """The axis that moved least — the one the bar is really about."""
        return min(self.x, self.y)


@dataclass(frozen=True)
class AutoDrizzleDecision:
    """What the automatic drizzle decided, and everything it decided it from.

    Carried out of the engine twice over: into the run's own FITS header (so the
    finished picture explains its size long after the job log has rolled) and
    into the ``StackOptions`` the run records, so a Gallery chip reading the
    stored options and this card can never disagree about whether the picture was
    drizzled.
    """

    #: Turn drizzle on for this run?
    drizzle: bool
    #: At what super-resolution scale — ``None`` whenever ``drizzle`` is False.
    scale: float | None
    #: One of :data:`AUTO_DRIZZLE_REASONS`.
    reason: str
    #: Subs on one output pixel, rounded down — the number the decision turned
    #: on, and the one the owner is shown.
    samples_per_pixel: int
    #: The bar ``samples_per_pixel`` was judged against. Carried rather than
    #: re-read from the module constant so the run's own header card cannot
    #: quote a different bar from the one that decided it.
    bar: int
    #: The worst axis's phase spread in output pixels; ``None`` when unmeasured
    #: (which happens when the depth bar already answered the question, since the
    #: dither measurement is the expensive half and is not taken when it cannot
    #: change the answer).
    dither_px: float | None
    #: How many pointing groups the dither was measured within (see
    #: :class:`DitherSpread`); ``None`` when no dither measurement was taken.
    panels: int | None


@dataclass(frozen=True)
class AutoDrizzleRun:
    """A yes from :func:`decide_auto_drizzle`, plus what it costs to price it.

    The owner asked to be **told how long an automatic drizzle will take** and
    then left alone — not refused, and not gated on a threshold (sign-off item
    19, answered 2026-10-13). Nothing in the engine can say that sentence: the
    seconds come from his own finished runs, which live in the project DB the
    webapp reads, and the surface is a running job's row. So the engine hands
    the decision *out* — ``run_stack(on_auto_drizzle=…)`` is called once, with
    this, at the moment the run commits to drizzling — and the webapp prices it
    (:mod:`webapp.drizzletime`).

    It carries the two cost classes rather than the options blobs because the
    engine is the only place that knows them without re-deriving the rule:
    ``cost_class`` is what this run will be recorded as and what its rate should
    be read from, and ``plain_cost_class`` is what the very same run would have
    been had the automatic drizzle said no — which is the comparison the owner's
    sentence makes ("a plain stack would take about 2 h"). Deriving either from
    a mapping afterwards would be a second, quietly different resolution of
    ``auto_reject`` and the ``drizzle_reject`` affordability check, which is the
    shape of mistake this project keeps finding.
    """

    #: The decision itself — always one with ``drizzle`` True.
    decision: AutoDrizzleDecision
    #: Subs this run will actually combine.
    n_frames: int
    #: The **pre-drizzle** stacking canvas in pixels, for comparing against the
    #: canvases the owner's past runs were measured on.
    canvas_px: int
    #: ``stack_cost_class`` of the options that will run (``"drizzle"`` or
    #: ``"drizzle+reject"``, the latter only once the second pass is known to be
    #: affordable).
    cost_class: str
    #: ``stack_cost_class`` of what this run would have been without the
    #: automatic drizzle.
    plain_cost_class: str


def samples_per_output_pixel(
    n_frames: int,
    *,
    dst_shape: tuple[int, int],
    ref_shape: tuple[int, int],
) -> float | None:
    """How many subs land on **one pixel** of a ``dst_shape`` canvas — the
    per-pixel depth, not the target's frame total.

    Canvas area ÷ one frame's footprint, which is the same arithmetic
    ``webapp.field_fulls.field_fulls_of_sky`` does for the four surfaces that
    already answer "how deep is a pixel of this run?", and which
    ``webapp.routers.stack._pixel_depth`` divides the frame count by for the
    Stack form's own drizzle caution. ``dst_shape`` is the **pre-drizzle**
    stacking canvas, so no drizzle-scale correction applies: the super-resolved
    grid re-samples the same sky, and a sub that covered a patch still covers it.

    ``None`` when the canvas is no bigger than one frame — a single field, or a
    mosaic forced onto the reference canvas — where the honest answer is simply
    ``n_frames`` and the caller should use that rather than an area ratio of
    ~1.0 computed from a bounding box. ``None`` too on a degenerate shape, which
    is the only other thing a caller can safely be told.

    It is a **bounding box**, so an under-covered corner counts as sky and the
    ratio reads a little deep. The direction matters and is accepted
    deliberately: the corners of a union canvas are the thinnest part of the
    picture, and this number is about a *typical* pixel — the same reading, and
    the same measured justification, as ``_pixel_depth``'s (observer issue #901,
    where the thinnest-cluster alternative came out ~0.10× the real depth on 12
    of 17 of the owner's mosaics).
    """
    if n_frames <= 0:
        return None
    dh, dw = (float(dst_shape[0]), float(dst_shape[1]))
    fh, fw = (float(ref_shape[0]), float(ref_shape[1]))
    if min(dh, dw, fh, fw) <= 0:
        return None
    fulls = (dh * dw) / (fh * fw)
    if not math.isfinite(fulls) or fulls <= 1.0:
        return None
    return float(n_frames) / fulls


def _circular_spread(phases: Sequence[float]) -> float:
    """Standard deviation of sub-pixel phases, measured *around the circle*.

    A phase is a position inside one pixel, so it wraps: 0.98 and 0.02 are two
    hundredths of a pixel apart, not 0.96. A plain standard deviation reads that
    pair as a spread of ~0.48 — nearly the uniform value — and would call a set
    that never moved "well dithered" purely because the solve jitters across a
    pixel boundary. So the phases are centred on their **circular** mean first
    and wrapped into ``[-0.5, 0.5)`` before the ordinary deviation is taken.

    0.0 for identical phases; ~0.289 (1/√12) for phases filling the pixel, which
    is the same scale a plain deviation would report — so the number stays
    readable as "pixels", which is what :data:`AUTO_DRIZZLE_MIN_DITHER_PX` is in.
    """
    vals = [float(p) % 1.0 for p in phases if math.isfinite(p)]
    if len(vals) < 2:
        return 0.0
    two_pi = 2.0 * math.pi
    cs = sum(math.cos(two_pi * v) for v in vals) / len(vals)
    sn = sum(math.sin(two_pi * v) for v in vals) / len(vals)
    centre = math.atan2(sn, cs) / two_pi
    acc = 0.0
    for v in vals:
        d = (v - centre + 0.5) % 1.0 - 0.5
        acc += d * d
    return math.sqrt(acc / len(vals))


def dither_spread_px(
    phases_xy: Sequence[tuple[float, float]],
    *,
    labels: Sequence[int] | None = None,
    min_members: int = 2,
) -> DitherSpread | None:
    """Per-axis sub-pixel phase spread of ``phases_xy``, in output pixels.

    ``phases_xy`` is one ``(x, y)`` canvas-pixel position per sub — the whole
    coordinate, not its fractional part; the wrap-safe fraction is taken here so
    callers cannot take it two ways. ``labels`` optionally gives each sub its
    mosaic panel (``-1`` for "no panel"), in which case the spread is measured
    **within** each substantial panel and the worst panel's figure is returned —
    see :class:`DitherSpread` for why pooling a mosaic is the wrong measurement.

    ``None`` when nothing could be measured: fewer than two subs anywhere, or a
    labelled set in which no panel has ``min_members``.
    """
    if labels is None:
        pts = [(x, y) for x, y in phases_xy
               if math.isfinite(x) and math.isfinite(y)]
        if len(pts) < 2:
            return None
        return DitherSpread(
            x=_circular_spread([p[0] for p in pts]),
            y=_circular_spread([p[1] for p in pts]),
            n=len(pts), panels=1,
        )
    groups: dict[int, list[tuple[float, float]]] = {}
    for (x, y), label in zip(phases_xy, labels, strict=True):
        if label < 0 or not (math.isfinite(x) and math.isfinite(y)):
            continue
        groups.setdefault(int(label), []).append((x, y))
    usable = {k: v for k, v in groups.items() if len(v) >= max(2, int(min_members))}
    if not usable:
        return None
    worst_x = min(_circular_spread([p[0] for p in v]) for v in usable.values())
    worst_y = min(_circular_spread([p[1] for p in v]) for v in usable.values())
    return DitherSpread(
        x=worst_x, y=worst_y,
        n=sum(len(v) for v in usable.values()), panels=len(usable),
    )


def decide_auto_drizzle(
    *,
    n_frames: int,
    ref_shape: tuple[int, int],
    dst_shape: tuple[int, int],
    measure_dither: Callable[[], DitherSpread | None],
    fits_budget: Callable[[float], bool] | None = None,
    min_samples_per_pixel: int | None = None,
) -> AutoDrizzleDecision:
    """"Auto, when worth it", as one pure decision — see the module docstring.

    ``measure_dither()`` returns :func:`dither_spread_px`'s verdict, or ``None``
    for "could not be measured", which is a **refusal**: drizzle without
    sub-pixel variety adds a grid instead of detail, so an unmeasurable set is
    not drizzled rather than drizzled on the assumption that it moved. It is a
    *callable* rather than a value because it is the expensive half — a WCS read
    per sub, plus the panel clustering on a mosaic — and the depth bar below
    answers most runs on arithmetic alone. Not calling it is therefore part of
    the contract, not an optimisation detail, and
    ``tests/test_auto_drizzle.py`` pins it.

    ``fits_budget(scale)`` answers "would a drizzle at this scale, with its
    two-pass rejection, fit the memory budget?" — supplied by the caller because
    pricing a canvas is the stacker's own arithmetic and this module must not
    import it. ``None`` means "don't ask", for a caller that has already decided
    the budget is not its question (the pure tests).
    """
    bar = (AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL if min_samples_per_pixel is None
           else int(min_samples_per_pixel))
    per_pixel = samples_per_output_pixel(
        n_frames, dst_shape=dst_shape, ref_shape=ref_shape)
    depth = float(n_frames) if per_pixel is None else per_pixel
    samples = int(depth) if depth > 0 else 0
    if samples < bar:
        return AutoDrizzleDecision(
            drizzle=False, scale=None, reason=REASON_TOO_FEW_SAMPLES,
            samples_per_pixel=samples, bar=bar, dither_px=None, panels=None)
    dither = measure_dither()
    if dither is None:
        return AutoDrizzleDecision(
            drizzle=False, scale=None, reason=REASON_DITHER_UNKNOWN,
            samples_per_pixel=samples, bar=bar, dither_px=None, panels=None)
    if dither.worst < AUTO_DRIZZLE_MIN_DITHER_PX:
        return AutoDrizzleDecision(
            drizzle=False, scale=None, reason=REASON_TOO_LITTLE_DITHER,
            samples_per_pixel=samples, bar=bar,
            dither_px=round(dither.worst, 4), panels=dither.panels)
    scale = _largest_scale_that_fits(fits_budget)
    if scale is None:
        return AutoDrizzleDecision(
            drizzle=False, scale=None, reason=REASON_NO_ROOM_IN_BUDGET,
            samples_per_pixel=samples, bar=bar,
            dither_px=round(dither.worst, 4), panels=dither.panels)
    return AutoDrizzleDecision(
        drizzle=True, scale=scale, reason=REASON_DEEP_AND_DITHERED,
        samples_per_pixel=samples, bar=bar,
        dither_px=round(dither.worst, 4), panels=dither.panels)


def _largest_scale_that_fits(
    fits_budget: Callable[[float], bool] | None,
) -> float | None:
    """The biggest offered scale the budget can hold, or ``None`` for none of them.

    Walks :data:`AUTO_DRIZZLE_SCALE` down to :data:`AUTO_DRIZZLE_MIN_SCALE` in
    :data:`AUTO_DRIZZLE_SCALE_STEP` stops and stops at the first that fits.
    Below the floor the answer is "don't drizzle" rather than "drizzle a little":
    at ×1.2 the extra resolution is already marginal and the run would be paying
    the whole drizzle cost — a slower pass per sub, twice over for the rejection
    — for it.
    """
    if fits_budget is None:
        return float(AUTO_DRIZZLE_SCALE)
    scale = float(AUTO_DRIZZLE_SCALE)
    floor = float(AUTO_DRIZZLE_MIN_SCALE)
    while scale >= floor - 1e-9:
        if fits_budget(round(scale, 4)):
            return round(scale, 4)
        scale -= float(AUTO_DRIZZLE_SCALE_STEP)
    return None


#: Subs a mosaic panel must hold before its own phase spread is believed. A
#: handful of phases is not a distribution — the sample deviation of five
#: uniform draws scatters by a third of its own value — and the depth bar above
#: has already established that a qualifying canvas is 200 samples deep per
#: pixel, so every panel that contributes to that depth clears this by an order
#: of magnitude. It exists for the stragglers: the half-shot panel at the edge of
#: a raster the owner is still building, which must not be allowed to answer for
#: the whole canvas.
AUTO_DRIZZLE_PANEL_MIN_FRAMES = 10


def canvas_pixel_positions(
    frames: Sequence[object],
    *,
    canvas_wcs_text: str | None,
) -> list[tuple[float, float]]:
    """Each sub's own centre, in **canvas pixel** coordinates — one entry per
    frame, ``(nan, nan)`` for a sub whose position can't be read.

    The fractional part of these is the sub-pixel *phase* drizzle cares about:
    where this sub's grid sits inside one output pixel. Taken from each frame's
    **own WCS** (``wcs_image_center_deg_from_text``, so a solution that offsets
    CRPIX rather than CRVAL — which is what
    ``seestack.solve.bootstrap.propagate_wcs`` writes for a star-matched sub — is
    read at its true centre) and projected through the canvas WCS the stack is
    about to reproject onto, in one vectorised call.

    One WCS parse per sub, which is the same cost
    :func:`~seestack.stack.mosaic.compute_mosaic_canvas` already pays once —
    about a second on the owner's largest target, against a stack measured in
    minutes, and only on a run that is actually asking the auto-drizzle question.

    **What this measures and what it does not.** A frame's centre position fixes
    its grid's phase only up to the frame's own rotation: two subs an hour apart
    on an alt-az mount have slightly rotated grids, so their phases differ
    across the field rather than uniformly. The spread of the centres is still
    the standard reading of "did the subs move sub-pixel between frames", and
    rotation can only ever *add* phase variety — so this is the conservative
    direction for a bar whose job is to catch a set that never moved at all.
    """
    from seestack.io.wcs_io import wcs_from_text, wcs_image_center_deg_from_text

    out: list[tuple[float, float]] = [(float("nan"), float("nan"))] * len(frames)
    canvas = wcs_from_text(canvas_wcs_text)
    if canvas is None:
        return out
    try:
        cel = canvas.celestial
        if not cel.has_celestial:
            return out
    except Exception as exc:  # noqa: BLE001 — a degenerate canvas WCS measures nothing
        log.warning("Auto-drizzle: canvas WCS unusable (%s)", exc)
        return out
    idx: list[int] = []
    radec: list[list[float]] = []
    for i, f in enumerate(frames):
        w = getattr(f, "width_px", None)
        h = getattr(f, "height_px", None)
        text = getattr(f, "wcs_json", None)
        if not text or not w or not h:
            continue
        centre = wcs_image_center_deg_from_text(text, width=int(w), height=int(h))
        if centre is None:
            continue
        idx.append(i)
        radec.append([centre[0], centre[1]])
    if not idx:
        return out
    try:
        xy = cel.all_world2pix(radec, 0)
    except Exception as exc:  # noqa: BLE001 — an unprojectable sub measures nothing
        log.warning("Auto-drizzle: could not project sub centres (%s)", exc)
        return out
    for i, (x, y) in zip(idx, xy, strict=True):
        out[i] = (float(x), float(y))
    return out
