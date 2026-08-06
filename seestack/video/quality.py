"""How steady was this capture? — turning per-frame sharpness into advice.

:func:`~seestack.video.lucky.stack_video` already grades every frame of a Moon/
Sun video and throws most of them away. The one decision it leaves the user is
*how many* to keep, and a beginner has no way to answer it: 15 % is right for a
capture taken through turbulent air, 50 % is right for a steady one, and nothing
on the screen says which they had.

This module turns the grading pass's scores — which the stack already computed
and then discarded — into the three things needed to answer that:

  * a small **sharpness curve** (frames sorted sharpest-first) so the shape is
    visible: a cliff means the seeing was jumpy and being picky pays; a flat line
    means the frames are interchangeable and keeping more only cuts noise;
  * the measured **trade-off at each offered setting** — how much sharper than a
    typical frame the kept ones are, and how much noise averaging that many
    removes — so "15 % or 50 %?" becomes two numbers instead of a guess;
  * a **suggested setting**, picked by a stated rule rather than a constant.

Everything here is pure and offline: it reads a list of scores and returns
numbers and one sentence. It never changes a picture — the suggestion is advice
the user applies with a click, so a wrong guess costs one re-stack, not an image.

The sharpness score itself (:func:`~seestack.video.lucky.frame_sharpness`) is on
an arbitrary scale, so only *ratios* of it are used anywhere below.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: How many points the sparkline curve carries. Enough to show a cliff or a
#: plateau at a glance, small enough to sit in a JSON payload for every capture.
CURVE_POINTS = 32

#: The keep percentages the UI actually offers. The suggestion is chosen from
#: these rather than from a continuum, so "use this instead" is one click on the
#: control the user already has.
DEFAULT_CANDIDATES: tuple[float, ...] = (15.0, 30.0, 50.0)

#: How much fine-detail contrast the suggestion may give up to take roughly twice
#: as many frames. 5 % is small next to the ~1.4× noise reduction that doubling
#: the frame count buys, and well under what anyone can see on a lunar disk.
_SHARPNESS_TOLERANCE = 0.95

#: Best-decile-vs-typical *contrast* ratios that separate the three verdicts.
#: Below ``_STEADY`` the frames are effectively interchangeable; above
#: ``_VARIABLE`` the sharpest moments are in a different league from the rest.
#: (≈1.15× and ≈1.5× on the raw score scale, which is contrast squared.)
_STEADY = 1.07
_VARIABLE = 1.22


@dataclass(frozen=True)
class KeepOption:
    """What one keep-% setting would give you, measured on this capture."""

    #: The setting itself, as a percentage of the graded frames.
    percent: float
    #: How many frames it keeps.
    n_frames: int
    #: Fine-detail contrast of the *stack* this setting would produce ÷ that of a
    #: typical single frame. 1.0 means "no sharper than average"; 2.0 means twice
    #: the contrast. See :func:`_kept_contrast` for why it is a mean of √score.
    sharpness_vs_typical: float
    #: √N — roughly how much cleaner than a single frame the average is.
    noise_gain: float


@dataclass(frozen=True)
class SharpnessProfile:
    """The capture's sharpness distribution, and what to do about it."""

    #: Frame scores sorted sharpest-first, rescaled so the best frame is 1.0 and
    #: bucketed down to at most :data:`CURVE_POINTS` points. Ready to draw as a
    #: sparkline; the scale is relative because the raw score has no units.
    curve: tuple[float, ...]
    #: Where the *current* keep setting falls along that curve, 0..1 — so the
    #: drawing can mark "everything left of here was kept".
    cut_fraction: float
    #: The measured trade-off at each offered setting, ascending by percent.
    options: tuple[KeepOption, ...]
    #: The setting this capture's own numbers argue for (one of ``options``).
    suggested_percent: float
    #: ``"steady"`` | ``"mixed"`` | ``"variable"`` — how much the seeing moved.
    spread: str
    #: One plain-language sentence tying the three together.
    summary: str


def _kept_contrast(sorted_contrast: np.ndarray, n_keep: int) -> float:
    """Fine-detail contrast of the stack made from the sharpest ``n_keep`` frames.

    ``sorted_contrast`` is √score, sharpest first. Two choices matter here:

    * **√score, not score.** :func:`~seestack.video.lucky.frame_sharpness` is a
      mean-*squared* Laplacian, so it scales as contrast², and only its square
      root is proportional to the fine detail a viewer sees.
    * **The mean, not the median.** The stack is an *average of frames*, so the
      detail it keeps is the average of the frames' — which means a soft frame
      let in by a looser setting genuinely costs you, and the number must show
      that. A median would hide two soft frames behind three sharp ones and
      recommend keeping more than the capture can support.
    """
    n = max(1, min(int(n_keep), sorted_contrast.size))
    return float(np.mean(sorted_contrast[:n]))


def frames_kept(n_graded: int, percent: float) -> int:
    """How many frames a keep percentage takes — the stacker's own rounding.

    Mirrors :func:`~seestack.video.lucky.stack_video` exactly (``ceil``, at least
    one frame) so every number this module reports describes the stack the user
    would actually get.
    """
    if n_graded <= 0:
        return 0
    return max(1, min(n_graded, int(math.ceil(n_graded * float(percent) / 100.0))))


def _curve(sorted_desc: np.ndarray) -> tuple[float, ...]:
    """Sharpest-first scores, normalised to the best frame and bucketed."""
    best = float(sorted_desc[0])
    if not math.isfinite(best) or best <= 0.0:
        # Every frame scored zero (a black or unreadable capture): a flat line is
        # the honest picture, and it keeps the caller free of NaN.
        return tuple(0.0 for _ in range(min(CURVE_POINTS, sorted_desc.size)))
    n = sorted_desc.size
    if n <= CURVE_POINTS:
        return tuple(float(v) / best for v in sorted_desc)
    # Bucket by *mean* rather than by sampling every k-th score: a sampled curve
    # can step straight over the cliff that makes a jumpy capture obvious.
    edges = np.linspace(0, n, CURVE_POINTS + 1).astype(int)
    return tuple(
        float(np.mean(sorted_desc[a:b])) / best
        for a, b in zip(edges[:-1], edges[1:], strict=False) if b > a
    )


def _spread_of(sorted_contrast: np.ndarray) -> tuple[str, float]:
    """``(verdict, best-decile ÷ typical)`` for the capture's contrast range.

    The top decile rather than the single best frame, so one freakishly good (or
    one hot-pixel-flecked) frame can't decide the verdict for the whole capture.
    """
    typical = float(np.median(sorted_contrast))
    if not math.isfinite(typical) or typical <= 0.0:
        return "steady", 1.0
    decile = _kept_contrast(sorted_contrast, max(1, sorted_contrast.size // 10))
    ratio = decile / typical
    if not math.isfinite(ratio) or ratio <= 0.0:
        return "steady", 1.0
    if ratio < _STEADY:
        return "steady", ratio
    if ratio < _VARIABLE:
        return "mixed", ratio
    return "variable", ratio


def _suggest(options: tuple[KeepOption, ...]) -> float:
    """The most frames you can keep without giving up meaningful sharpness.

    Averaging more frames always cuts noise, so the only reason to be picky is
    the contrast it costs. Take the strictest setting's stack contrast as the
    benchmark and pick the *largest* setting still within
    :data:`_SHARPNESS_TOLERANCE` of it. On a steady capture every setting ties,
    so the loosest wins and the user gets the cleanest picture; on a jumpy one
    the looser settings fall away and the strictest is returned.
    """
    if not options:
        return DEFAULT_CANDIDATES[1]
    benchmark = options[0].sharpness_vs_typical
    if not math.isfinite(benchmark) or benchmark <= 0.0:
        return options[0].percent
    best = options[0].percent
    for opt in options:
        if opt.sharpness_vs_typical >= _SHARPNESS_TOLERANCE * benchmark:
            best = opt.percent
    return best


def _summary(spread: str, current: KeepOption | None, suggested: KeepOption) -> str:
    """One sentence a beginner can act on, built from the measured numbers."""
    if spread == "steady":
        head = ("The air was steady for this capture — the sharpest frames are "
                "barely better than the rest")
    elif spread == "variable":
        head = ("The seeing jumped around a lot — the best moments are far crisper "
                "than a typical frame")
    else:
        head = "The seeing varied a fair bit during this capture"

    if current is not None and abs(current.percent - suggested.percent) < 1e-6:
        return (
            f"{head}. Keeping {current.percent:.0f}% used {current.n_frames} frames "
            f"({current.sharpness_vs_typical:.1f}× a typical frame's sharpness, about "
            f"{current.noise_gain:.0f}× cleaner than one frame) — a good choice here."
        )
    tail = (
        f"keeping {suggested.percent:.0f}% would use {suggested.n_frames} frames "
        f"({suggested.sharpness_vs_typical:.1f}× a typical frame's sharpness, about "
        f"{suggested.noise_gain:.0f}× cleaner than one frame)"
    )
    if current is None:
        return f"{head}, so {tail}."
    if suggested.percent > current.percent:
        return (
            f"{head}, so you can afford to keep more: {tail}, against "
            f"{current.n_frames} at {current.percent:.0f}%."
        )
    return (
        f"{head}, so being pickier pays: {tail}, against "
        f"{current.n_frames} at {current.percent:.0f}%."
    )


def sharpness_profile(
    scores,
    keep_percent: float | None = None,
    *,
    candidates: tuple[float, ...] = DEFAULT_CANDIDATES,
) -> SharpnessProfile | None:
    """Describe a capture's sharpness distribution and recommend a keep setting.

    ``scores`` is the grading pass's per-frame sharpness list (any order;
    non-finite entries are dropped). ``keep_percent`` is the setting the user
    actually stacked with, used to mark the curve and to phrase the advice
    relative to what they already did — pass ``None`` before a stack exists.

    Returns ``None`` when there is nothing to say: fewer than two usable scores,
    or a capture whose frames all scored zero. Callers treat ``None`` as "hide
    the panel" rather than showing an empty chart.
    """
    arr = np.asarray(list(scores), dtype=np.float64)
    arr = arr[np.isfinite(arr) & (arr >= 0.0)]
    if arr.size < 2:
        return None
    sorted_desc = np.sort(arr)[::-1]
    # Work in contrast (√score) from here on — see :func:`_kept_contrast`.
    sorted_contrast = np.sqrt(sorted_desc)
    typical = float(np.median(sorted_contrast))
    if not math.isfinite(typical) or typical <= 0.0:
        return None

    n = int(sorted_desc.size)
    opts = tuple(
        KeepOption(
            percent=float(p),
            n_frames=frames_kept(n, p),
            sharpness_vs_typical=_kept_contrast(sorted_contrast, frames_kept(n, p)) / typical,
            noise_gain=math.sqrt(max(1, frames_kept(n, p))),
        )
        for p in sorted(candidates)
    )
    suggested_percent = _suggest(opts)
    suggested = next(o for o in opts if o.percent == suggested_percent)

    current: KeepOption | None = None
    if keep_percent is not None and math.isfinite(float(keep_percent)):
        n_cur = frames_kept(n, float(keep_percent))
        current = KeepOption(
            percent=float(keep_percent),
            n_frames=n_cur,
            sharpness_vs_typical=_kept_contrast(sorted_contrast, n_cur) / typical,
            noise_gain=math.sqrt(max(1, n_cur)),
        )

    spread, _ratio = _spread_of(sorted_contrast)
    return SharpnessProfile(
        curve=_curve(sorted_desc),
        cut_fraction=(current.n_frames / n) if current is not None else 0.0,
        options=opts,
        suggested_percent=suggested_percent,
        spread=spread,
        summary=_summary(spread, current, suggested),
    )
