"""How much darker is the sky at the edge of one of the owner's raw subs than
at its centre — how strong is the S30's own vignetting?

The gate on the Bugs entry "the darker ring just inside the ragged border is
made by the stacker's per-frame sky flatten" (Builder 2026-10-30). On synthetic
subs the mechanism is measured: a 20 % corner fall-off leaves a −24 ADU rim in
every sub's outer pixels, and the canvas border is where only sub edges land.
Whether the owner's ring *is* that rim depends on one number only his raws can
give — the fall-off of a real S30 sub. Under about 3 % it is not his ring.

**Method.** A sample of accepted subs, a few per target spread through its
history, is read raw (read-only; nothing is written) and binned 2×2 so the
Bayer pattern averages out. On each sub it takes robust medians — stars barely
move a median — of the sky in:

* the **centre**: the middle box holding 20 % of the frame;
* the **edge**: the band within 5 % of each side of the frame;
* the four **corners**: 10 % × 10 % boxes;
* rings of normalised radius (centre to corner = 1).

A sky gradient from light pollution lifts one side and drops the other, so it
largely cancels in an all-round edge median; ``side_spread`` (the four sides'
spread relative to the centre) says how much gradient there was to cancel.

The raw ADU carry the camera's pedestal (an offset that is *not* vignetted),
so a raw ratio ``edge / centre`` understates the fall-off. The pedestal is
removed without knowing it: across subs shot under different skies (Moon,
twilight, haze), ``edge = p + s·v_edge`` and ``centre = p + s·v_centre``, so the
**slope** of edge against centre over many subs is ``v_edge / v_centre`` whatever
``p`` is. That slope (a Theil–Sen fit, robust to a few odd subs) is the
headline number; the intercept gives the pedestal it implies.

**Privacy.** Numbers only: per-sub ratios, aggregated into percentiles. No
names, paths, header values or dates.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from seestack.diag import Diagnostic, DiagnosticStopped, iter_sub_refs, sub_path

SUBS_PER_TARGET = 4
MAX_SUBS = 300
#: Normalised radius bins for the radial profile (0 = centre, 1 = corner).
RING_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0)
#: The slope needs skies that differ: below this many subs, or a centre-sky
#: spread (p90/p10) below this ratio, it is reported as ``None``.
MIN_SUBS_FOR_SLOPE = 20
MIN_SKY_SPREAD = 1.2


def _spread(items: list[Any], k: int) -> list[Any]:
    """Up to ``k`` items evenly spread from first to last (deterministic)."""
    n = len(items)
    if n <= k:
        return list(items)
    if k == 1:
        return [items[n // 2]]
    return [items[round(j * (n - 1) / (k - 1))] for j in range(k)]


def measure_frame(raw: np.ndarray) -> dict[str, Any] | None:
    """One raw (Bayer) frame's centre/edge/corner sky, or ``None`` when it is
    too small or flat to say anything."""
    a = np.asarray(raw, dtype=np.float32)
    if a.ndim == 3:            # already colour: average the channels
        a = a.mean(-1)
    h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
    if h < 64 or w < 64:
        return None
    b = a[:h, :w].reshape(h // 2, 2, w // 2, 2).mean((1, 3))
    h, w = b.shape
    if np.isfinite(b).sum() < 0.5 * b.size:
        return None

    def med(x: np.ndarray) -> float:
        x = x[np.isfinite(x)]
        return float(np.median(x)) if x.size else float("nan")

    cy, cx = int(round(h * 0.4472 / 2)), int(round(w * 0.4472 / 2))
    centre = med(b[h // 2 - cy:h // 2 + cy, w // 2 - cx:w // 2 + cx])
    ey, ex = max(1, int(round(h * 0.05))), max(1, int(round(w * 0.05)))
    sides = [med(b[:ey, :]), med(b[-ey:, :]), med(b[:, :ex]), med(b[:, -ex:])]
    band = np.concatenate([b[:ey, :].ravel(), b[-ey:, :].ravel(),
                           b[ey:-ey, :ex].ravel(), b[ey:-ey, -ex:].ravel()])
    edge = med(band)
    ky, kx = max(1, int(round(h * 0.1))), max(1, int(round(w * 0.1)))
    corner = med(np.concatenate([b[:ky, :kx].ravel(), b[:ky, -kx:].ravel(),
                                 b[-ky:, :kx].ravel(), b[-ky:, -kx:].ravel()]))
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot((yy - (h - 1) / 2) / ((h - 1) / 2), (xx - (w - 1) / 2) / ((w - 1) / 2))
    r /= np.sqrt(2.0)
    rings = []
    for lo, hi in zip(RING_EDGES[:-1], RING_EDGES[1:], strict=True):
        sel = (r >= lo) & (r < hi) if hi < 1.0 else (r >= lo)
        rings.append(med(b[sel]))

    if not (np.isfinite(centre) and centre > 0 and np.isfinite(edge)
            and np.isfinite(corner)):
        return None
    return {"centre": centre, "edge": edge, "corner": corner, "rings": rings,
            "side_spread": (max(sides) - min(sides)) / centre}


def _pct(values: list[float]) -> dict[str, float] | None:
    v = np.asarray([x for x in values if np.isfinite(x)], dtype=np.float64)
    if not v.size:
        return None
    p10, p50, p90 = np.percentile(v, [10, 50, 90])
    return {"p10": round(float(p10), 4), "median": round(float(p50), 4),
            "p90": round(float(p90), 4)}


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    """Measure the sampled subs' centre-to-edge sky. Reads raws, writes nothing."""
    from seestack.io.fits_loader import load_seestar_raw

    plan: list[Any] = []
    for entry in library.list_targets():
        try:
            proj = library.open_target(entry.safe_name)
        except Exception:  # noqa: BLE001 — a broken target is skipped
            continue
        try:
            refs = list(iter_sub_refs(proj, accepted_only=True))
        finally:
            proj.close()
        plan.extend(_spread(refs, SUBS_PER_TARGET))
    if len(plan) > MAX_SUBS:
        plan = _spread(plan, MAX_SUBS)

    measured: list[dict[str, Any]] = []
    unreadable = 0
    for i, ref in enumerate(plan):
        if should_stop is not None and should_stop():
            raise DiagnosticStopped("stopped")
        if progress is not None:
            progress("reading subs", i + 1, len(plan))
        path = sub_path(ref)
        try:
            if path is None:
                raise OSError("missing")
            raw, _ = load_seestar_raw(path, debayer=False)
            m = measure_frame(raw)
        except Exception:  # noqa: BLE001 — an unreadable sub is counted, not fatal
            m = None
        if m is None:
            unreadable += 1
        else:
            measured.append(m)

    centre = [m["centre"] for m in measured]

    def ratios(xs: list[float]) -> dict[str, float] | None:
        return _pct([x / c for x, c in zip(xs, centre, strict=True)])

    ring_cols = [[m["rings"][j] for m in measured] for j in range(len(RING_EDGES) - 1)]
    edge_fit = _slope(centre, [m["edge"] for m in measured])
    corner_fit = _slope(centre, [m["corner"] for m in measured])
    return {
        "subs_sampled": len(plan),
        "subs_measured": len(measured),
        "subs_unreadable": unreadable,
        "centre_sky_p90_over_p10": _sky_spread(centre),
        "edge_over_centre_slope": edge_fit,
        "corner_over_centre_slope": corner_fit,
        "ring_edges": list(RING_EDGES),
        "rings_over_centre_slope": [_slope(centre, col) for col in ring_cols],
        "edge_over_centre_raw": ratios([m["edge"] for m in measured]),
        "corner_over_centre_raw": ratios([m["corner"] for m in measured]),
        "side_spread": _pct([m["side_spread"] for m in measured]),
        "how_to_read": (
            "edge_over_centre_slope is the headline: how bright the sky is in the band "
            "within 5 % of each side, as a share of the frame centre's, with the "
            "camera's un-vignetted pedestal removed (the slope of edge against centre "
            "sky over subs shot under different skies; 'low'/'high' are its 95 % "
            "range). 1.0 means no fall-off; 0.80 means the edge sky is 20 % darker. "
            "corner uses the four 10 % boxes, rings run from centre (0) to corner (1). "
            "A slope is null when fewer than 20 subs were measured or the skies were "
            "too alike (centre_sky_p90_over_p10 under 1.2) to separate the pedestal. "
            "The 'raw' ratios include the pedestal and understate the fall-off. "
            "side_spread is how unequal the four sides were (a sky gradient). An "
            "edge slope above about 0.97 means the S30 barely vignettes and the "
            "dark-ring entry's mechanism is not the owner's ring."
        ),
    }


def _sky_spread(centre: list[float]) -> float | None:
    v = np.asarray(centre, dtype=np.float64)
    if v.size < 2:
        return None
    p10, p90 = np.percentile(v, [10, 90])
    return round(float(p90 / p10), 4) if p10 > 0 else None


def _slope(x: list[float], y: list[float]) -> dict[str, float] | None:
    """Theil–Sen slope of ``y`` on ``x`` with its 95 % range and the pedestal
    the line implies, or ``None`` when the skies cannot separate the two."""
    from scipy.stats import theilslopes

    xs = np.asarray(x, dtype=np.float64)
    ys = np.asarray(y, dtype=np.float64)
    ok = np.isfinite(xs) & np.isfinite(ys)
    xs, ys = xs[ok], ys[ok]
    spread = _sky_spread(list(xs))
    if xs.size < MIN_SUBS_FOR_SLOPE or spread is None or spread < MIN_SKY_SPREAD:
        return None
    slope, intercept, low, high = theilslopes(ys, xs, 0.95)
    out = {"slope": round(float(slope), 4), "low": round(float(low), 4),
           "high": round(float(high), 4)}
    if abs(1.0 - slope) > 1e-3:
        # y = p + v·(x − p)  ⇒  intercept = p·(1 − v)
        out["pedestal_over_median_centre"] = round(
            float(intercept / (1.0 - slope) / np.median(xs)), 4)
    return out


def ready(library) -> bool:  # noqa: ANN001
    """Any target with an accepted sub."""
    return any((e.n_frames_accepted or 0) > 0 for e in library.list_targets())


DIAGNOSTIC = Diagnostic(
    name="sky_falloff",
    version=1,
    question=("How much darker is the sky at the edge and corners of a raw S30 sub than "
              "at its centre? (gate on the dark-ring Bugs entry, Builder 2026-10-30)"),
    run=run,
    ready=ready,
)
