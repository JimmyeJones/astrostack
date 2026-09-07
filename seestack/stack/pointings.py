"""Detect a mixed-pointing batch — two+ targets accidentally in one folder.

A Seestar's field of view is ~1.3° across; dithering nudges a pointing by
arc-minutes and a mosaic steps adjacent panels ~1° apart (they overlap), so
*one* target's solved frames — a single pointing, a dithered set, or a
contiguous mosaic — form a chain whose neighbours are all within a couple of
degrees. Two *different* targets accidentally dropped in one incoming folder sit
many degrees apart with nothing bridging the gap. If such a batch is stacked, the
stacker picks one pointing as the reference and silently drops every frame whose
footprint doesn't overlap it (the NALIGNFL count) — so half the night is wasted on
a stack the user only discovers is half-complete afterwards.

This is the pure-geometry mirror of the frontend guard
(``frontend/src/components/target/mixedPointings.ts``), used by the *unattended*
stack chains (watcher auto-stack / one-click "Process target") to refuse a
walk-away stack that would silently combine only one pointing — gated behind the
off-by-default ``mixed_pointing_guard`` setting. We single-linkage-cluster the
solved pointings on the unit sphere at a 3° link distance: a contiguous mosaic
stays one cluster (each panel is <3° from the next), but two well-separated
targets fall into two. Single-linkage keys on the *gap between* groups, not their
total span, so an arbitrarily large but contiguous mosaic never trips it. We only
flag when at least two clusters are each substantial (``≥ MIN_POINTING_FRAMES``),
so a lone mis-solved frame — which the stack's own outlier rejection already
handles — never nags. Working on unit vectors makes it wrap-safe (RA 359°↔1°) and
pole-safe by construction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

LINK_DIST_DEG = 3.0
MIN_POINTING_FRAMES = 5

# Link distance for telling one *mosaic panel* from the next, as opposed to one
# target from another (``LINK_DIST_DEG`` above). The two live at very different
# scales: a dither nudges a pointing by arc-minutes (≲0.1°), while even the
# tightest mosaic steps adjacent panels by roughly half a field of view (~0.5°,
# and commonly several degrees for a framed mosaic). 0.25° sits with a ~2×
# margin on both sides, so a dithered set stays one group and neighbouring
# panels stay apart. Getting it wrong is safe in both directions: too small and
# a dither splits into groups too small to grade (callers fall back to the
# target-wide population, i.e. today's behaviour); too large and the panels
# merge back into one group — also today's behaviour.
PANEL_LINK_DIST_DEG = 0.25

# Pointings are folded onto a grid this fine before the panel clustering, because
# :func:`cluster_pointings` is O(n²) in pure Python and every caller of
# :func:`pointing_groups` hands it one row *per sub* — thousands of them on one
# target, sitting on a handful of panels. 0.01° is ~36″: an order of magnitude
# below a dither (≲0.1°) and 25× below :data:`PANEL_LINK_DIST_DEG`, so a fold
# moves a pointing by at most ~0.007° and can only change a link decision for a
# pair sitting within ~3 % of the link distance — where this module's own margin
# is ~2× on both sides, and where getting it wrong is safe in *both* directions
# (see :data:`PANEL_LINK_DIST_DEG`). Group **sizes** are exact either way: each
# input index still gets its own cell's label, and ``eligible``/``weights`` are
# summed per cell before the gate. Same constant, and the same reasoning, as the
# fold ``seestack.mosaicmap`` shipped for its own copy of this problem.
FOLD_GRID_DEG = 0.01

# Only fold when the link distance is this many fold cells across, so a caller
# that ever asks for a link distance near the grid itself gets the exact
# clustering instead of an approximation that would be the same size as the
# question. Every caller today uses ``PANEL_LINK_DIST_DEG`` (25 cells) or
# ``LINK_DIST_DEG`` (300), so this rail never fires; it exists so a future one
# can't quietly fall off the argument above.
_MIN_FOLD_CELLS_PER_LINK = 10.0


@dataclass(frozen=True)
class MixedPointings:
    """A clearly-bimodal (≥2 well-separated substantial pointings) verdict."""

    pointings: int  # number of substantial (≥MIN_POINTING_FRAMES) well-separated pointings (≥2)
    majority: int  # frames in the largest pointing
    others: int  # frames in the other substantial pointings
    separation_deg: float  # separation between the two largest pointings


def _to_vec(ra_deg: float, dec_deg: float) -> tuple[float, float, float]:
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    cd = math.cos(dec)
    return (cd * math.cos(ra), cd * math.sin(ra), math.sin(dec))


def _sep_deg(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> float:
    dot = min(1.0, max(-1.0, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))
    return math.degrees(math.acos(dot))


def cluster_pointings(
    radecs: list[tuple[float | None, float | None]],
    *,
    link_dist_deg: float = LINK_DIST_DEG,
) -> list[int]:
    """Single-linkage-cluster ``(ra_deg, dec_deg)`` pointings on the unit sphere.

    Returns one cluster label per *input* index — so the caller can map labels
    straight back onto its own rows — using ``-1`` for an entry with a missing
    or non-finite coordinate (an unsolved sub has no pointing to cluster). Two
    pointings within ``link_dist_deg`` of each other share a label; single
    linkage keys on the *gap between* groups rather than their total span, so an
    arbitrarily wide but contiguous chain stays one cluster. Working on unit
    vectors makes it wrap-safe (RA 359°↔1°) and pole-safe by construction.

    O(n²) in the number of solved pointings, the same bound
    :func:`detect_mixed_pointings` has always carried.
    """
    valid = [
        i for i, (ra, dec) in enumerate(radecs)
        if ra is not None and dec is not None
        and math.isfinite(ra) and math.isfinite(dec)
    ]
    labels = [-1] * len(radecs)
    if not valid:
        return labels
    vecs = [_to_vec(radecs[i][0], radecs[i][1]) for i in valid]  # type: ignore[arg-type]
    cos_thresh = math.cos(math.radians(link_dist_deg))

    parent = list(range(len(vecs)))

    def find(i: int) -> int:
        r = i
        while parent[r] != r:
            r = parent[r]
        while parent[i] != r:
            nxt = parent[i]
            parent[i] = r
            i = nxt
        return r

    for i in range(len(vecs)):
        vi = vecs[i]
        for j in range(i + 1, len(vecs)):
            vj = vecs[j]
            if vi[0] * vj[0] + vi[1] * vj[1] + vi[2] * vj[2] >= cos_thresh:
                parent[find(j)] = find(i)

    # Renumber roots to dense 0..n-1 labels in first-appearance order, so the
    # labels are deterministic given the input order (and stable across runs).
    dense: dict[int, int] = {}
    for k, orig in enumerate(valid):
        root = find(k)
        if root not in dense:
            dense[root] = len(dense)
        labels[orig] = dense[root]
    return labels


def fold_pointings(
    radecs: list[tuple[float | None, float | None]],
    *,
    grid_deg: float = FOLD_GRID_DEG,
) -> tuple[list[tuple[float, float]], list[int]]:
    """Fold pointings onto a ``grid_deg`` sky grid: ``(cells, cell_of_index)``.

    ``cells`` is one ``(ra_deg, dec_deg)`` per distinct cell — the **mean** of the
    pointings that landed in it — in first-appearance order, so a caller that
    clusters the cells and maps back gets labels numbered exactly as it would
    have got them unfolded. ``cell_of_index`` maps each input index to its cell,
    or ``-1`` for a missing / non-finite pointing (the same entries
    :func:`cluster_pointings` labels ``-1``).

    Cell keys come from rounding each coordinate, so every member of a cell is
    within one cell of every other and the cell mean is wrap-safe by
    construction: RA 359.999° and 0.001° round to *different* keys, so a cell
    never straddles the 0°/360° seam and the plain mean can never fling one to
    the far side of the sky (the clustering itself is wrap-safe anyway, since it
    works on unit vectors).
    """
    number: dict[tuple[int, int], int] = {}
    sums: list[list[float]] = []            # [ra_sum, dec_sum, n] per cell
    cell_of = [-1] * len(radecs)
    for i, (ra, dec) in enumerate(radecs):
        if ra is None or dec is None:
            continue
        ra_f, dec_f = float(ra), float(dec)
        if not (math.isfinite(ra_f) and math.isfinite(dec_f)):
            continue
        key = (round(ra_f / grid_deg), round(dec_f / grid_deg))
        n = number.get(key)
        if n is None:
            n = len(sums)
            number[key] = n
            sums.append([ra_f, dec_f, 1.0])
        else:
            cell = sums[n]
            cell[0] += ra_f
            cell[1] += dec_f
            cell[2] += 1.0
        cell_of[i] = n
    return [(s[0] / s[2], s[1] / s[2]) for s in sums], cell_of


def _cluster_distinct(
    radecs: list[tuple[float | None, float | None]], link_dist_deg: float,
) -> list[int]:
    """:func:`cluster_pointings`, run over the *distinct* pointings.

    The clustering is O(n²) in pure Python and every caller of
    :func:`pointing_groups` passes one row per sub — measured at **1.14 s** for a
    9-panel, 5,477-sub target, on a path that runs on every scan (the auto-grade
    hook), on two Target-page endpoints, and three more times inside one stack.
    Folding first (see :data:`FOLD_GRID_DEG`) collapses a dithered panel's
    hundreds of subs to a few hundred distinct cells and takes the same target to
    **0.01 s**, with each input index still receiving its own cell's label.

    Falls back to the exact clustering when folding cannot help or would not be
    sound: a link distance near the grid itself, and a set whose pointings are
    already all distinct (where the fold would only add the approximation
    without buying anything).
    """
    if link_dist_deg < _MIN_FOLD_CELLS_PER_LINK * FOLD_GRID_DEG:
        return cluster_pointings(radecs, link_dist_deg=link_dist_deg)
    cells, cell_of = fold_pointings(radecs)
    n_finite = sum(1 for c in cell_of if c >= 0)
    if len(cells) >= n_finite:
        return cluster_pointings(radecs, link_dist_deg=link_dist_deg)
    cell_labels = cluster_pointings(cells, link_dist_deg=link_dist_deg)  # type: ignore[arg-type]
    return [cell_labels[c] if c >= 0 else -1 for c in cell_of]


def pointing_groups(
    radecs: list[tuple[float | None, float | None]],
    *,
    min_members: int,
    eligible: list[bool] | None = None,
    weights: list[int] | None = None,
    link_dist_deg: float = PANEL_LINK_DIST_DEG,
) -> list[int] | None:
    """Per-index **mosaic panel** label, or ``None`` when there is no sound split.

    The shared soundness gate behind every "compare a mosaic's subs against
    their own panel, not against the other panels" decision in the engine — QC
    grading, photometric normalization and quality weighting all need it, and
    all need it to mean *exactly* the same thing.

    Why it exists at all: a mosaic's panels are **different patches of sky**, so
    the position-dependent metrics (star count, sky level, transparency — the
    flux-like ones QC measures) legitimately differ between them. A panel aimed
    at an emptier field really does have fewer, fainter stars, and judging it
    against the whole target's population reads that as cloud or haze.

    Returns a label per *input* index (``-1`` for an unsolved sub, or one in a
    group too small to be a reference), or ``None`` — meaning "no split; use one
    target-wide population, exactly as before" — unless at least **two** groups
    each carry ``min_members`` eligible entries. So a single-pointing target, an
    unsolved target and a mosaic too tightly packed to separate all keep today's
    behaviour, and only a target that genuinely splits gets the per-panel
    treatment. ``eligible`` (default: all) says which entries count toward a
    group's size — a caller that can only use frames carrying a particular
    metric passes that here, so a panel is "substantial" by the population it
    can actually contribute.

    **Cost.** The clustering underneath is O(n²) in pure Python and every caller
    hands this one row *per sub*, so the pointings are folded onto a fine grid
    first and clustered as their **distinct** positions — see
    :func:`_cluster_distinct` for the measurement and :data:`FOLD_GRID_DEG` for
    why a fold cannot move the answer that matters. A group is still substantial
    by the frames it holds: ``eligible`` and ``weights`` are summed per cell
    before the gate, and every input index gets its own cell's label back.

    ``weights`` (default: one each) says how many frames each entry stands for,
    for a caller that has already folded identical pointings together before
    calling — the clustering is O(n²), so a target with thousands of subs on a
    handful of panels is far cheaper to cluster as its distinct pointings. A
    group is still "substantial" by the **frames** it holds, not by the number of
    folded entries, so the gate means exactly the same thing either way; that is
    the point of the parameter, and why it is here rather than in a second
    hand-written copy of this rule.
    """
    labels = _cluster_distinct(radecs, link_dist_deg)
    counts: dict[int, int] = {}
    for i, label in enumerate(labels):
        if label < 0 or (eligible is not None and not eligible[i]):
            continue
        counts[label] = counts.get(label, 0) + (1 if weights is None else int(weights[i]))
    substantial = {label for label, n in counts.items() if n >= max(1, int(min_members))}
    if len(substantial) < 2:
        return None
    return [label if label in substantial else -1 for label in labels]


def detect_mixed_pointings(
    radecs: list[tuple[float | None, float | None]],
    *,
    link_dist_deg: float = LINK_DIST_DEG,
    min_pointing_frames: int = MIN_POINTING_FRAMES,
) -> MixedPointings | None:
    """Cluster ``(ra_deg, dec_deg)`` pointings; return a verdict iff clearly bimodal.

    ``radecs`` is every candidate sub's pointing (the caller passes the
    accepted + solved frames — exactly what the stacker would combine). Entries
    with a ``None`` / non-finite coordinate are ignored. Returns ``None`` unless
    the set splits into two or more substantial, well-separated pointings.

    Like :func:`pointing_groups`, this clusters the **distinct** pointings rather
    than one row per sub (see :data:`FOLD_GRID_DEG`) — the caller hands it a whole
    target's frame list, and the clustering is O(n²) in pure Python: 2.65 s for a
    5,477-sub target, on the pre-flight of every unattended stack once
    ``mixed_pointing_guard`` is on. The margin here is wider still, since
    :data:`LINK_DIST_DEG` is 300 fold cells rather than 25. The **counts** and the
    cluster **centroids** stay exact either way: each cell carries the true number
    of subs behind it and the true sum of their unit vectors, so ``majority``,
    ``others`` and ``separation_deg`` are the numbers the unfolded clustering
    would have reported.
    """
    pts = [
        (ra, dec)
        for (ra, dec) in radecs
        if ra is not None
        and dec is not None
        and math.isfinite(ra)
        and math.isfinite(dec)
    ]
    # Too few to judge a bimodal split robustly (need two substantial groups).
    if len(pts) < 2 * min_pointing_frames:
        return None

    # Fold to the distinct pointings, carrying each cell's true sub count and the
    # true sum of its members' unit vectors — so only the *linking* sees the
    # folded coordinate, while every reported number is computed from the subs.
    cells, cell_of = fold_pointings(pts)  # type: ignore[arg-type]
    sizes = [0] * len(cells)
    cell_vecs: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * len(cells)
    for (ra, dec), c in zip(pts, cell_of, strict=True):
        v = _to_vec(ra, dec)  # type: ignore[arg-type]
        sizes[c] += 1
        s = cell_vecs[c]
        cell_vecs[c] = (s[0] + v[0], s[1] + v[1], s[2] + v[2])

    # Single-linkage clustering via union-find: two pointings within
    # link_dist_deg share a cluster. ``cells`` is finite by construction, so no
    # label comes back -1.
    labels = cluster_pointings(cells, link_dist_deg=link_dist_deg)

    # Collect clusters as (count, summed unit vector) → centroid, keyed by label.
    groups: dict[int, tuple[int, tuple[float, float, float]]] = {}
    for i, label in enumerate(labels):
        count, s = groups.get(label, (0, (0.0, 0.0, 0.0)))
        groups[label] = (
            count + sizes[i],
            (s[0] + cell_vecs[i][0], s[1] + cell_vecs[i][1], s[2] + cell_vecs[i][2]),
        )

    clusters: list[tuple[int, tuple[float, float, float]]] = []
    for count, s in groups.values():
        norm = math.hypot(s[0], s[1], s[2]) or 1.0
        clusters.append((count, (s[0] / norm, s[1] / norm, s[2] / norm)))
    clusters.sort(key=lambda t: t[0], reverse=True)

    # Only a *clearly* bimodal set warns: at least two substantial pointings.
    substantial = [c for c in clusters if c[0] >= min_pointing_frames]
    if len(substantial) < 2:
        return None

    majority = substantial[0][0]
    others = sum(c[0] for c in substantial[1:])
    separation_deg = _sep_deg(substantial[0][1], substantial[1][1])
    return MixedPointings(
        pointings=len(substantial),
        majority=majority,
        others=others,
        separation_deg=separation_deg,
    )
