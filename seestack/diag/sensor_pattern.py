"""Is a colour pattern printed on the sensor, and does it depend on temperature?

Owner report, 2026-10-28: soft brown/blue/purple blotches over the sky of about a
quarter of his pictures, "only when it is cold". A pattern fixed to the sensor
(or to the optics in front of it) survives stacking: random noise falls as √N,
the pattern does not, and an alt-az Seestar puts a target on the same pixels
night after night.

**Method.** Subs of *different* targets share no sky, so averaging them without
aligning cancels stars and nebulae and leaves only what is fixed to the camera.
Each sub is 4×4-binned, its per-channel median removed, scaled by its own sky
noise and clipped (stars out). The subs of one temperature range are split
into two halves drawn from **disjoint sets of targets** — so real sky cannot
repeat between them — and the two halves' large-scale colour maps are compared:

* ``pattern`` — RMS of the halves' mean colour map, in units of one sub's noise;
* ``noise`` — RMS of half their difference (what averaging left of the noise);
* ``repeat_r`` — correlation of the two halves' maps. Near +1: a real pattern.
  Near 0: none.

Then the ranges' maps are correlated with each other: one pattern that only
changes strength reads high; a pattern that changes shape with temperature
reads low.

An earlier, hand-run version of this (2026-11-06) split halves *within* targets,
so in a range with few targets real sky could repeat between them and inflate
``repeat_r``; the disjoint split is what this version fixes.

**Different targets are not always different skies** (version 2). A mosaic and
the single field of the same object are two targets at the same centre
(``"M 31"`` and ``"M 31 (mosaic)"``, :func:`seestack.io.scanner.is_mosaic_target_name`),
and a library also holds neighbours a few degrees apart (the Veil's two arcs)
and one object filed under two names. Version 1 could put such a pair on
opposite halves, and a bright coloured nebula they share would then read as a
pattern fixed to the camera. So targets are first grouped into **skies** — the
same name once a " (mosaic)" suffix is dropped, or centres closer than
:data:`SAME_SKY_DEG` — and it is skies, not targets, that the halves split.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import math
import re

import numpy as np

from seestack.diag import Diagnostic, DiagnosticStopped

#: Sensor-temperature ranges (°C), as reported by the Seestar in each sub.
TEMP_BINS: tuple[tuple[float, float], ...] = (
    (-99.0, 0.0), (0.0, 5.0), (5.0, 10.0), (10.0, 15.0),
    (15.0, 20.0), (20.0, 25.0), (25.0, 99.0),
)
#: Subs read per range (half per side). ~70 × 7 ranges ≈ 500 files at most.
SUBS_PER_BIN = 70
#: A range needs this many distinct targets for the disjoint split to mean much.
MIN_TARGETS = 4
#: Two targets whose centres are closer than this are one sky: an S30 field is
#: 2.1° across and a mosaic a few fields, so this is generous on purpose — a
#: sky wrongly merged costs one target's worth of split; a sky wrongly split
#: can manufacture the very pattern this measures.
SAME_SKY_DEG = 5.0
_BIN = 4          # spatial binning before measuring
_SIGMA = 20.0     # large-scale smoothing, in binned pixels


def _label(lo: float, hi: float) -> str:
    if lo <= -99:
        return f"below {hi:g} C"
    if hi >= 99:
        return f"{lo:g} C and up"
    return f"{lo:g} to {hi:g} C"


def _chroma(img: np.ndarray) -> np.ndarray:
    from scipy.ndimage import gaussian_filter

    return np.stack([gaussian_filter(img[..., 0] - img[..., 1], _SIGMA),
                     gaussian_filter(img[..., 2] - img[..., 1], _SIGMA)], -1)


def _prepared(path: str) -> np.ndarray | None:
    """One sub, binned, sky-removed, in units of its own noise. ``None`` if it
    can't be read. Opens the file read-only and never writes."""
    from seestack.io.fits_loader import load_seestar_raw

    try:
        rgb, _ = load_seestar_raw(path, debayer=True)
    except Exception:  # noqa: BLE001 — an unreadable sub is just skipped
        return None
    h, w = rgb.shape[0] // _BIN * _BIN, rgb.shape[1] // _BIN * _BIN
    if h < 8 * _BIN or w < 8 * _BIN:
        return None
    b = rgb[:h, :w].reshape(h // _BIN, _BIN, w // _BIN, _BIN, 3).mean((1, 3))
    b -= np.median(b.reshape(-1, 3), axis=0)
    lum = b.mean(-1)
    sd = float(np.median(np.abs(lum - np.median(lum)))) * 1.4826
    if not np.isfinite(sd) or sd <= 0:
        return None
    b /= sd
    np.clip(b, -5.0, 5.0, out=b)
    return b.astype(np.float32)


def _frame_path(f: Any) -> str | None:
    for p in (getattr(f, "cached_path", None), getattr(f, "source_path", None)):
        if p and Path(p).exists():
            return p
    return None


def _base_name(name: str) -> str:
    """A target's name with any " (mosaic)" suffix dropped, spacing and case folded."""
    n = re.sub(r"\s*\(mosaic\)\s*$", "", name.strip(), flags=re.I)
    return re.sub(r"[\s_]+", " ", n).strip().lower()


def _unit(ra: float, dec: float) -> tuple[float, float, float]:
    r, d = math.radians(ra), math.radians(dec)
    return (math.cos(d) * math.cos(r), math.cos(d) * math.sin(r), math.sin(d))


def sky_groups(entries: list[Any]) -> dict[str, str]:
    """``safe_name`` → the safe name of the first target of its sky.

    Targets are one sky when their names match once a " (mosaic)" suffix is
    dropped, or their centres are within :data:`SAME_SKY_DEG` — transitively,
    so a chain of overlapping fields is one sky. A target with no recorded
    centre is grouped by name alone."""
    parent = {e.safe_name: e.safe_name for e in entries}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra_, rb = find(a), find(b)
        if ra_ != rb:
            parent[max(ra_, rb)] = min(ra_, rb)

    by_base: dict[str, str] = {}
    centres: list[tuple[str, tuple[float, float, float]]] = []
    cos_max = math.cos(math.radians(SAME_SKY_DEG))
    for e in entries:
        base = _base_name(e.name or e.safe_name)
        if base in by_base:
            union(e.safe_name, by_base[base])
        else:
            by_base[base] = e.safe_name
        ra, dec = e.ra_deg, e.dec_deg
        if ra is None or dec is None or not (np.isfinite(ra) and np.isfinite(dec)):
            continue
        u = _unit(float(ra), float(dec))
        for other, v in centres:
            if u[0] * v[0] + u[1] * v[1] + u[2] * v[2] >= cos_max:
                union(e.safe_name, other)
        centres.append((e.safe_name, u))
    return {k: find(k) for k in parent}


def _measure(by_target: dict[str, list[Any]], rng: np.random.Generator,
             tick, should_stop, sky_of: dict[str, str] | None = None
             ) -> dict[str, Any] | None:
    """Split the targets' *skies* (``sky_of``; each target its own sky when
    absent) into two disjoint halves and compare their colour maps."""
    skies: dict[str, list[str]] = {}
    for t in sorted(by_target):
        skies.setdefault((sky_of or {}).get(t, t), []).append(t)
    if len(skies) < MIN_TARGETS:
        return None
    keys = sorted(skies)
    rng.shuffle(keys)
    sides = ([t for k in keys[0::2] for t in skies[k]],
             [t for k in keys[1::2] for t in skies[k]])
    sums: list[np.ndarray | None] = [None, None]
    used = [0, 0]
    shape = None
    for i, side in enumerate(sides):
        pools = [list(by_target[t]) for t in side]
        picked = 0
        while picked < SUBS_PER_BIN // 2 and any(pools):
            for pool in pools:
                if not pool or picked >= SUBS_PER_BIN // 2:
                    continue
                if should_stop is not None and should_stop():
                    raise DiagnosticStopped("stopped")
                f = pool.pop(int(rng.integers(len(pool))))
                picked += 1
                tick()
                path = _frame_path(f)
                b = _prepared(path) if path else None
                if b is None:
                    continue
                if shape is None:
                    shape = b.shape
                if b.shape != shape:
                    continue
                sums[i] = b if sums[i] is None else sums[i] + b
                used[i] += 1
    if not all(used):
        return None
    a, c = sums[0] / used[0], sums[1] / used[1]
    e = max(1, min(60, a.shape[0] // 6))
    sl = (slice(e, -e), slice(e, -e))
    # A uniform colour cast is not a blotch (and the clip at +5 sigma leaves one
    # behind on every half alike), so each map is measured about its own mean.
    ca, cc, cn = (m[sl] - m[sl].mean(axis=(0, 1)) for m in
                  (_chroma(a), _chroma(c), _chroma((a - c) / 2)))
    mean = (ca + cc) / 2
    pattern = float(np.sqrt((mean ** 2).mean()))
    noise = float(np.sqrt((cn ** 2).mean()))
    r = float(np.corrcoef(ca.ravel(), cc.ravel())[0, 1])
    return {
        "subs": int(sum(used)), "targets": len(by_target), "skies": len(skies),
        "pattern": round(pattern, 4), "noise": round(noise, 4),
        "ratio": round(pattern / noise, 2) if noise > 0 else None,
        "repeat_r": round(r, 3) if np.isfinite(r) else None,
        "_map": mean,
    }


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    """Measure the camera-fixed colour pattern per sensor-temperature range."""
    bins: dict[tuple[float, float], dict[str, list[Any]]] = {b: {} for b in TEMP_BINS}
    every: dict[str, list[Any]] = {}
    nights_by_bin: dict[tuple[float, float], set[str]] = {b: set() for b in TEMP_BINS}
    n_no_temp = 0
    entries = library.list_targets()
    sky_of = sky_groups(entries)
    for entry in entries:
        try:
            proj = library.open_target(entry.safe_name)
        except Exception:  # noqa: BLE001 — a broken target is skipped
            continue
        try:
            for f in proj.iter_frames(accepted_only=True):
                every.setdefault(entry.safe_name, []).append(f)
                t = f.sensor_temp_c
                if t is None or not np.isfinite(t):
                    n_no_temp += 1
                    continue
                for b in TEMP_BINS:
                    if b[0] <= t < b[1]:
                        bins[b].setdefault(entry.safe_name, []).append(f)
                        if f.timestamp_utc:
                            nights_by_bin[b].add(f.timestamp_utc[:10])
                        break
        finally:
            proj.close()

    total = SUBS_PER_BIN * (len(TEMP_BINS) + 1)
    done = [0]

    def tick() -> None:
        done[0] += 1
        if progress is not None:
            progress("reading subs", done[0], total)

    rng = np.random.default_rng(0)
    rows: list[dict[str, Any]] = []
    maps: dict[str, np.ndarray] = {}
    overall = _measure(every, rng, tick, should_stop, sky_of)
    if overall is not None:
        overall.pop("_map")
    for b in TEMP_BINS:
        label = _label(*b)
        m = _measure(bins[b], rng, tick, should_stop, sky_of)
        row: dict[str, Any] = {
            "range": label,
            "subs_available": sum(len(v) for v in bins[b].values()),
            "targets_available": len(bins[b]),
            "skies_available": len({sky_of.get(t, t) for t in bins[b]}),
            "nights": len(nights_by_bin[b]),
        }
        if m is None:
            row["measured"] = False
        else:
            maps[label] = m.pop("_map")
            row.update(measured=True, **m)
        rows.append(row)

    same_shape: list[dict[str, Any]] = []
    labels = list(maps)
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, c = maps[labels[i]], maps[labels[j]]
            if a.shape == c.shape:
                r = float(np.corrcoef(a.ravel(), c.ravel())[0, 1])
                same_shape.append({"a": labels[i], "b": labels[j],
                                   "r": round(r, 3) if np.isfinite(r) else None})
    return {
        "all_temperatures": overall,
        "by_temperature": rows,
        "pattern_shape_between_ranges": same_shape,
        "subs_without_temperature": n_no_temp,
        "targets": len(entries),
        "skies": len(set(sky_of.values())),
        "how_to_read": (
            "pattern and noise are in units of one sub's sky noise; ratio well above 2 "
            "with repeat_r near +1 means a colour pattern fixed to the camera. Halves come "
            "from different skies (a mosaic and its single field, or targets within a few "
            "degrees, count as one sky), so real sky cannot repeat between them. High r between "
            "ranges means one pattern that changes strength; low r means its shape changes."
        ),
    }


def ready(library) -> bool:  # noqa: ANN001
    """Worth running only with subs from at least :data:`MIN_TARGETS` skies —
    below that the two halves cannot come from different skies."""
    live = [e for e in library.list_targets() if (e.n_frames_accepted or 0) > 0]
    return len(set(sky_groups(live).values())) >= MIN_TARGETS


DIAGNOSTIC = Diagnostic(
    name="sensor_pattern_by_temperature",
    version=2,
    question=("Is a colour pattern fixed to the camera, how strong is it at each sensor "
              "temperature, and is it the same pattern at every temperature? (owner's "
              "colour-blotch report, 2026-10-28)"),
    run=run,
    ready=ready,
)
