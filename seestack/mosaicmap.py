"""Where a mosaic is thin — a panel-by-panel depth map.

The app can already tell a mosaic owner **how much** of their goal is left (the
readiness figure scales the goal by panel count, so a 4-panel mosaic with an hour
on each honestly reads "a quarter done"). What it cannot tell them is **where**
the shortfall is, and for the §1 owner — a heavy mosaic user shooting one target
across many nights — that is the actionable half. A mosaic whose *total* looks
healthy can still have one corner at a fifth of the others, and that corner is
grainier than the rest of the picture no matter how good the total is. Today the
only way to see it is to read the frames table and do the geometry by eye.

So: cluster the target's accepted, solved subs into panels, add up each panel's
own integration, and lay the panels out the way the sky actually tiles.

**One definition of "panel", not a second one.** The clustering is
:func:`seestack.stack.pointings.pointing_groups` — the same function, at the same
:data:`~seestack.stack.pointings.PANEL_LINK_DIST_DEG`, that QC grading,
photometric normalization and quality weighting already use to decide "compare
this sub against its own panel". Its soundness gate comes with it: unless at
least two groups each carry a substantial population, this returns ``None`` and
the caller shows nothing at all. A single field, a dithered set too tight to
separate, and an unsolved target therefore behave exactly as they do today.

**Read-only and advisory.** Nothing here rejects, re-weights or restacks
anything; it is a sentence and a small grid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from seestack.stack.pointings import MIN_POINTING_FRAMES, pointing_groups

#: A panel has to carry this many solved subs to count as a panel at all — the
#: same floor the mixed-pointing guard uses for "a substantial pointing", reused
#: rather than re-picked so "panel" means one thing across the app. A handful of
#: strays a degree off the mosaic is not a thirteenth panel.
MIN_PANEL_FRAMES = MIN_POINTING_FRAMES

#: A panel is called out as thin when it holds less than this fraction of the
#: *median* panel's integration. At 0.6 the thin panel's noise is ~1.3× the rest
#: of the picture's — visible in the corner of a finished mosaic, which is the
#: threshold for it being worth a sentence. The median (not the mean) is the
#: yardstick so the thin panel cannot drag its own comparison down.
THIN_FRACTION = 0.6

#: …and only when the shortfall is also worth a night. Two panels at 4 and 7
#: minutes differ by 43 % and by nothing that matters; this stops a brand-new
#: mosaic from being nagged about noise in its first half hour.
THIN_MIN_SHORTFALL_S = 300.0

#: Refuse to lay out a grid bigger than this on a side. A real Seestar mosaic is
#: a handful of panels on a side; anything past this is scattered pointings that
#: happen to have separated, and a 300-row grid is not a picture of anything.
MAX_GRID_SIDE = 24

#: Pointings are folded onto a grid this fine before clustering, because the
#: clustering is O(n²) and this runs on a page the owner opens with thousands of
#: subs behind it (measured: 5,400 subs took 2.2 s unfolded and 0.05 s folded).
#: 0.01° is ~36″ — an order of magnitude below a dither (≲0.1°) and 25× below
#: :data:`~seestack.stack.pointings.PANEL_LINK_DIST_DEG`, so a fold moves a
#: pointing by at most ~0.007° and can only change a link decision for a pair
#: sitting within ~3 % of the link distance. The module's own margin either side
#: is ~2×, so nothing real is at stake; the frame **counts** are exact either
#: way, since the fold carries its size through ``pointing_groups(weights=…)``.
FOLD_GRID_DEG = 0.01


@dataclass(frozen=True)
class MosaicPanel:
    """One panel of the mosaic and how much time has landed on it."""

    row: int              # 0 = top (highest Dec — North up, as the sky is drawn)
    col: int              # 0 = left (highest RA — East left, likewise)
    n_frames: int         # accepted, solved subs on this panel
    exposure_s: float     # their total integration
    ra_deg: float         # panel centre, for the tooltip / future "point here"
    dec_deg: float


@dataclass(frozen=True)
class MosaicDepthMap:
    """The whole map: every panel, the grid it lays out on, and the verdict."""

    panels: list[MosaicPanel]
    rows: int
    cols: int
    median_exposure_s: float
    #: The thinnest panel, **only** when it is materially thinner than the rest
    #: (see :data:`THIN_FRACTION` / :data:`THIN_MIN_SHORTFALL_S`). ``None`` on an
    #: even mosaic — there is nothing to point at, and inventing a "worst" panel
    #: out of a 3 % spread would send someone chasing noise.
    thin: MosaicPanel | None
    #: One plain-language sentence. Always non-empty when a map is returned.
    text: str


def _to_vec(ra_deg: float, dec_deg: float) -> tuple[float, float, float]:
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    cd = math.cos(dec)
    return (cd * math.cos(ra), cd * math.sin(ra), math.sin(dec))


def _direction(summed: tuple[float, float, float]) -> tuple[float, float]:
    """A summed direction vector, normalised back to ``(ra_deg, dec_deg)``.

    Pointings are averaged as unit vectors, so the mean is wrap-safe
    (RA 359°↔1°) and pole-safe by construction — the same reasoning
    ``pointings.py`` gives for working on the sphere rather than on raw
    degrees."""
    x, y, z = summed
    norm = math.hypot(x, y, z)
    if norm <= 0:                       # antipodal cancellation; not reachable
        return (0.0, 0.0)               # for one mosaic, guarded anyway
    x, y, z = x / norm, y / norm, z / norm
    ra = math.degrees(math.atan2(y, x)) % 360.0
    dec = math.degrees(math.asin(max(-1.0, min(1.0, z))))
    return (ra, dec)


def _sep_deg(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    dot = min(1.0, max(-1.0, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))
    return math.degrees(math.acos(dot))


def _wrap180(delta_deg: float) -> float:
    """A RA difference folded into ``(-180, 180]`` so a mosaic straddling 0h
    doesn't lay out 360° wide."""
    return (delta_deg + 180.0) % 360.0 - 180.0


def _axis_bins(values: list[float], tol: float) -> list[int]:
    """Bin 1-D coordinates into grid lines, largest value first.

    Single-linkage along the axis: values within ``tol`` of their neighbour share
    a line. Descending, because both axes are drawn descending — North up puts
    the highest Dec at the top, and East left puts the highest RA at the left.

    Returns one bin index per *input* position, so the caller can map straight
    back onto its panels."""
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    bins = [0] * len(values)
    current = 0
    for k, i in enumerate(order):
        if k and (values[order[k - 1]] - values[i]) > tol:
            current += 1
        bins[i] = current
    return bins


def _band(index: int, count: int, low: str, high: str) -> str:
    """The word for one axis position: ``""`` on a single line, else the edge's
    name or "middle"."""
    if count <= 1:
        return ""
    if index == 0:
        return low
    if index == count - 1:
        return high
    return "middle"


def panel_position_words(row: int, col: int, rows: int, cols: int) -> str:
    """"bottom-right" / "left" / "middle" — where a panel sits, in the words a
    beginner would use looking at the picture.

    Deliberately positional rather than "panel 7": the reader is looking at their
    own mosaic, not at our labelling, and "the bottom-right corner is grainy" is
    a sentence they can act on without counting cells."""
    vertical = _band(row, rows, "top", "bottom")
    horizontal = _band(col, cols, "left", "right")
    if vertical and horizontal:
        if vertical == "middle" and horizontal == "middle":
            return "middle"
        return f"{vertical}-{horizontal}"
    return vertical or horizontal or "single"


def _verdict_text(panels: list[MosaicPanel], rows: int, cols: int,
                  median_s: float, thin: MosaicPanel | None) -> str:
    from seestack.sharecard import format_duration

    shape = f"{rows}×{cols}" if rows > 1 and cols > 1 else f"{len(panels)}-panel"
    if thin is not None:
        where = panel_position_words(thin.row, thin.col, rows, cols)
        return (
            f"Your {shape} mosaic is thinnest at the {where}: about "
            f"{format_duration(thin.exposure_s)} there against "
            f"{format_duration(median_s)} on a typical panel. That part of the "
            f"picture will look grainier than the rest until it catches up — "
            f"more time on this mosaic is what evens it out."
        )
    return (
        f"All {len(panels)} panels of your {shape} mosaic have had a similar "
        f"amount of time — around {format_duration(median_s)} each — so no part "
        f"of the picture is being held back."
    )


def _fold_pointings(
    frames: list[tuple[float | None, float | None, float | None]],
) -> list[tuple[float, float, int, float]]:
    """Fold frames onto a :data:`FOLD_GRID_DEG` grid: ``(ra, dec, n, exposure_s)``.

    The clustering below is O(n²) and a target can carry thousands of subs on a
    handful of panels, so it is run over the *distinct* pointings rather than
    over every frame — the counts and the integration are carried through
    exactly, and a folded cell's coordinate is the mean of the frames in it.

    Frames with no pointing (unsolved) are dropped here: they have nowhere to go
    on the map. A frame with no recorded exposure still counts toward its
    panel's frame count; it just adds no time. Output order is deterministic
    (sorted by cell), so the map does not depend on the order the subs arrived.
    """
    cells: dict[tuple[int, int], list[float]] = {}
    for ra, dec, exp in frames:
        if ra is None or dec is None:
            continue
        try:
            ra_f, dec_f = float(ra), float(dec)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(ra_f) and math.isfinite(dec_f)):
            continue
        try:
            seconds = float(exp) if exp is not None else 0.0
        except (TypeError, ValueError):
            seconds = 0.0
        if not math.isfinite(seconds) or seconds < 0.0:
            seconds = 0.0
        key = (round(ra_f / FOLD_GRID_DEG), round(dec_f / FOLD_GRID_DEG))
        cell = cells.get(key)
        if cell is None:
            cells[key] = [ra_f, dec_f, 1.0, seconds]
        else:
            cell[0] += ra_f
            cell[1] += dec_f
            cell[2] += 1.0
            cell[3] += seconds
    return [
        (ra_sum / n, dec_sum / n, int(n), seconds)
        for _, (ra_sum, dec_sum, n, seconds) in sorted(cells.items())
    ]


def mosaic_depth_map(
    frames: list[tuple[float | None, float | None, float | None]],
    *,
    min_panel_frames: int = MIN_PANEL_FRAMES,
) -> MosaicDepthMap | None:
    """The panel-by-panel depth map for one target, or ``None``.

    ``frames`` is ``(ra_center_deg, dec_center_deg, exposure_s)`` for every sub
    the caller would stack — accepted and plate-solved. An unsolved sub has no
    pointing and is ignored by the clustering; a sub with no recorded exposure
    still counts toward its panel's frame count but adds no time.

    ``None`` — meaning "this isn't a mosaic, show nothing" — whenever the shared
    soundness gate says so (fewer than two substantial panels), or when the
    panels don't lay out on a sane grid. Never raises on odd data; the honest
    answer to "is this a mosaic?" for a target with two subs is no.
    """
    folded = _fold_pointings(frames)
    if len(folded) < 2:
        return None
    labels = pointing_groups(
        [(ra, dec) for ra, dec, _, _ in folded],
        min_members=min_panel_frames,
        weights=[n for _, _, n, _ in folded],
    )
    if labels is None:
        return None

    # Gather the panels: frame count, integration, and the direction sum the
    # centroid comes from — each folded pointing weighted by how many subs it
    # stands for, so the centre is what it would have been unfolded.
    counts: dict[int, int] = {}
    exposure: dict[int, float] = {}
    sums: dict[int, tuple[float, float, float]] = {}
    for (ra, dec, n, seconds), label in zip(folded, labels, strict=True):
        if label < 0:                    # in a group too small to be a panel
            continue
        counts[label] = counts.get(label, 0) + n
        exposure[label] = exposure.get(label, 0.0) + seconds
        x, y, z = _to_vec(ra, dec)
        sx, sy, sz = sums.get(label, (0.0, 0.0, 0.0))
        sums[label] = (sx + x * n, sy + y * n, sz + z * n)

    if len(counts) < 2:                  # `pointing_groups` already promises 2+,
        return None                      # belt and braces on an empty eligible set

    order = sorted(counts)
    centres = {label: _direction(sums[label]) for label in order}

    # Grid tolerance: half the closest panel-to-panel separation. Panels on one
    # row share a Dec to well inside that, while the next row is a full step
    # away — so the two never merge, and a slightly scattered pointing still
    # lands on its own line. Single-linkage clustering guarantees the panels are
    # at least PANEL_LINK_DIST_DEG apart, so this is always positive.
    cvecs = {label: _to_vec(*centres[label]) for label in order}
    min_sep = min(
        _sep_deg(cvecs[a], cvecs[b])
        for i, a in enumerate(order) for b in order[i + 1:]
    )
    tol = 0.5 * min_sep

    ra0, dec0 = _direction((
        sum(sums[label][0] for label in order),
        sum(sums[label][1] for label in order),
        sum(sums[label][2] for label in order),
    ))
    cos_dec = math.cos(math.radians(dec0))
    # RA offsets are scaled by cos(dec) so the grid matches how the sky actually
    # tiles rather than stretching sideways near the pole.
    dras = [_wrap180(centres[label][0] - ra0) * cos_dec for label in order]
    ddecs = [centres[label][1] - dec0 for label in order]

    row_of = _axis_bins(ddecs, tol)      # descending Dec → row 0 is North (top)
    col_of = _axis_bins(dras, tol)       # descending RA  → col 0 is East (left)
    rows, cols = max(row_of) + 1, max(col_of) + 1
    if rows > MAX_GRID_SIDE or cols > MAX_GRID_SIDE:
        return None

    panels = [
        MosaicPanel(
            row=row_of[i], col=col_of[i],
            n_frames=counts[label], exposure_s=exposure[label],
            ra_deg=centres[label][0], dec_deg=centres[label][1],
        )
        for i, label in enumerate(order)
    ]
    panels.sort(key=lambda p: (p.row, p.col))

    times = sorted(p.exposure_s for p in panels)
    mid = len(times) // 2
    median_s = times[mid] if len(times) % 2 else 0.5 * (times[mid - 1] + times[mid])

    thinnest = min(panels, key=lambda p: (p.exposure_s, p.row, p.col))
    thin = (
        thinnest
        if median_s > 0.0
        and thinnest.exposure_s < THIN_FRACTION * median_s
        and (median_s - thinnest.exposure_s) >= THIN_MIN_SHORTFALL_S
        else None
    )

    return MosaicDepthMap(
        panels=panels, rows=rows, cols=cols,
        median_exposure_s=median_s, thin=thin,
        text=_verdict_text(panels, rows, cols, median_s, thin),
    )
