"""Which photosites on the owner's sensor are hot or dead, learned from his lights?

Roadmap 1.0, test R5. He has no darks, so the defect repair that already exists
(``seestack.calibrate.defects``, which needs a master dark) never runs, and the
per-frame suppression runs after the debayer has smeared each defect into a
coloured 3×3 blob that walks across the stack. A defect map learned from lights
would fix that — if lights can find defects reliably. This measures whether
they can.

**Method.** Subs of different targets share no sky, so a star lands on a given
photosite only by chance, while a hot photosite is hot in every sub. For each
sampled raw sub (not debayered), each CFA phase is compared with the median of
its same-colour neighbours, in units of that sub's own robust noise; a
photosite more than ``SIGMA`` above (hot) or below (dead) is flagged. Flags
are counted per photosite in two halves drawn from **disjoint sets of targets**.
A photosite flagged in at least ``MIN_SHARE`` of a half's subs is a defect of
that half. Agreement between the halves says whether the map is real.

Read-only; numbers only.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from seestack.diag import Diagnostic, DiagnosticStopped, iter_sub_refs, sub_path

SUBS_PER_HALF = 40
SIGMA = 8.0
MIN_SHARE = 0.5
MIN_TARGETS = 4


_RING = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=bool)


def _flags(raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hot / dead photosites of one raw sub.

    A defect is a *single* photosite: it stands ``SIGMA`` robust-noise units
    away from its same-colour neighbours (the sky it sits on), and its eight
    immediate neighbours — the other colours around it — are not lit with it.
    A star's core fails the second test (its light spreads over every
    neighbour), so stars are not mistaken for hot pixels.
    """
    from scipy.ndimage import maximum_filter, median_filter, minimum_filter

    bg = np.empty_like(raw)
    noise = np.full(raw.shape, np.inf, dtype=np.float32)
    for dy in (0, 1):
        for dx in (0, 1):
            plane = raw[dy::2, dx::2]
            med = median_filter(plane, size=3, mode="nearest")
            resid = plane - med
            mad = float(np.median(np.abs(resid - np.median(resid)))) * 1.4826
            bg[dy::2, dx::2] = med
            if np.isfinite(mad) and mad > 0:
                noise[dy::2, dx::2] = mad
    excess = raw - bg
    nb_max = maximum_filter(raw, footprint=_RING, mode="nearest") - bg
    nb_min = minimum_filter(raw, footprint=_RING, mode="nearest") - bg
    hot = (excess > SIGMA * noise) & (nb_max < excess / 3.0)
    dead = (excess < -SIGMA * noise) & (nb_min > excess / 3.0)
    return hot, dead


def _pools(library) -> dict[str, list[Any]]:  # noqa: ANN001
    pools: dict[str, list[Any]] = {}
    for e in library.list_targets():
        try:
            proj = library.open_target(e.safe_name)
        except Exception:  # noqa: BLE001
            continue
        try:
            refs = list(iter_sub_refs(proj, accepted_only=True))
        finally:
            proj.close()
        if refs:
            pools[e.safe_name] = refs
    return pools


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    from seestack.io.fits_loader import load_seestar_raw

    pools = _pools(library)
    if len(pools) < MIN_TARGETS:
        return {"measured": False, "reason": "needs subs from at least 4 targets"}
    rng = np.random.default_rng(0)
    names = sorted(pools)
    rng.shuffle(names)
    halves = (names[0::2], names[1::2])
    counts: list[dict[str, Any]] = []
    shape = None
    total = 2 * SUBS_PER_HALF
    done = 0
    for side in halves:
        lists = [list(pools[t]) for t in side]
        hot_n = dead_n = None
        used = 0
        attempts = 0
        while used < SUBS_PER_HALF and any(lists) and attempts < 4 * SUBS_PER_HALF:
            for lst in lists:
                if not lst or used >= SUBS_PER_HALF:
                    continue
                if should_stop is not None and should_stop():
                    raise DiagnosticStopped("stopped")
                attempts += 1
                ref = lst.pop(int(rng.integers(len(lst))))
                path = sub_path(ref)
                if not path:
                    continue
                try:
                    raw, _ = load_seestar_raw(path, debayer=False)
                except Exception:  # noqa: BLE001
                    continue
                raw = np.asarray(raw, dtype=np.float32)
                if shape is None:
                    shape = raw.shape
                if raw.shape != shape:
                    continue
                hot, dead = _flags(raw)
                if hot_n is None:
                    hot_n = np.zeros(shape, dtype=np.uint16)
                    dead_n = np.zeros(shape, dtype=np.uint16)
                hot_n += hot
                dead_n += dead
                used += 1
                done += 1
                if progress is not None:
                    progress("reading raw subs", done, total)
        counts.append({"used": used, "hot": hot_n, "dead": dead_n})
    if not all(c["used"] for c in counts):
        return {"measured": False, "reason": "not enough readable subs"}

    def maps(c: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
        need = max(2, int(np.ceil(MIN_SHARE * c["used"])))
        return c["hot"] >= need, c["dead"] >= need

    (ha, da), (hb, db) = maps(counts[0]), maps(counts[1])
    cfa = np.zeros(shape, dtype=np.int8)
    cfa[0::2, 0::2], cfa[0::2, 1::2], cfa[1::2, 0::2], cfa[1::2, 1::2] = 0, 1, 2, 3

    def per_site(mask: np.ndarray) -> list[int]:
        return [int(np.count_nonzero(mask & (cfa == k))) for k in range(4)]

    def jaccard(a: np.ndarray, b: np.ndarray) -> float | None:
        union = np.count_nonzero(a | b)
        return round(np.count_nonzero(a & b) / union, 3) if union else None

    return {
        "measured": True,
        "frame_shape": list(shape),
        "subs_per_half": [counts[0]["used"], counts[1]["used"]],
        "targets": len(pools),
        "sigma": SIGMA, "min_share": MIN_SHARE,
        "hot_per_half": [int(ha.sum()), int(hb.sum())],
        "dead_per_half": [int(da.sum()), int(db.sum())],
        "hot_in_both": int((ha & hb).sum()),
        "dead_in_both": int((da & db).sum()),
        "hot_agreement_jaccard": jaccard(ha, hb),
        "dead_agreement_jaccard": jaccard(da, db),
        "hot_in_both_by_cfa_site_00_01_10_11": per_site(ha & hb),
        "how_to_read": ("halves come from different targets, so stars cannot repeat; a high "
                        "agreement means a defect map learned from lights is reliable"),
    }


DIAGNOSTIC = Diagnostic(
    name="hot_pixel_census",
    version=1,
    question=("Can a hot/dead pixel map be learned reliably from the owner's lights, and how "
              "many defects does his sensor have? (1.0 roadmap R5)"),
    run=run,
    on_demand=True,
    ready=lambda library: sum(1 for e in library.list_targets()
                              if (e.n_frames_accepted or 0) > 0) >= MIN_TARGETS,
)
