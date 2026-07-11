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

    vecs = [_to_vec(ra, dec) for (ra, dec) in pts]
    cos_thresh = math.cos(math.radians(link_dist_deg))

    # Single-linkage clustering via union-find: two frames within link_dist_deg
    # (dot ≥ cos(threshold)) share a cluster. O(n²), bounded by the frame-list cap.
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

    # Collect clusters as (count, summed unit vector) → centroid, keyed by root.
    groups: dict[int, tuple[int, tuple[float, float, float]]] = {}
    for i in range(len(vecs)):
        root = find(i)
        count, s = groups.get(root, (0, (0.0, 0.0, 0.0)))
        groups[root] = (
            count + 1,
            (s[0] + vecs[i][0], s[1] + vecs[i][1], s[2] + vecs[i][2]),
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
