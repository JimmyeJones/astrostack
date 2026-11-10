"""Does the Seestar write each mosaic *panel's* pointing into its subs, or the
mosaic's centre?

The gate on the Bugs entry "a mosaic panel whose subs all failed to
plate-solve is missing from the picture, and three whole-target gates call it
a healthy night" (Scout 2026-10-19). Only solved subs stack, so a panel none of
whose subs located simply is not on the canvas — and every check that could say
so divides by the *whole* target, where one panel of nine is a small share. The
fix has to split the un-located subs by panel, and the only pointing an
un-located sub has is the telescope's own hint (``ra_hint_deg`` /
``dec_hint_deg``, read from the sub's header at ingest). **Whether that hint is
the panel's pointing or the mosaic's centre decides the fix's whole design**,
and only the owner's subs can say which.

**Method.** Read the record only — no FITS file is opened. For every target
that is a mosaic (by the folder convention's name, or because its solved centres
split into two or more panels), compare each *solved* sub's hint with the
centre its plate solution found:

* if the hints sit on the sub's own panel (within
  :data:`~seestack.stack.pointings.PANEL_LINK_DIST_DEG`), and themselves split
  into the same number of groups the centres do, the hint is **per panel**;
* if every hint sits on one point near the middle of the panels, it is the
  **mosaic centre**.

It also counts what the fix would find today: groups of hints that hold
un-located subs and no located one — a panel missing from the picture.

**Privacy.** Numbers only. Targets are reported in an anonymous list (largest
first), never by name; distances are *between* two pointings of one sub, never
a position on the sky.
"""
from __future__ import annotations

import math
from statistics import median
from typing import Any

from seestack.diag import Diagnostic, DiagnosticStopped

#: A panel is "substantial" — counted as a panel at all — with this many subs.
#: Below it a cluster is a stray (a mis-solve, a slew frame), not a panel.
MIN_PANEL_SUBS = 5
#: Targets listed one by one in the result (the tallies cover them all).
MAX_LISTED_TARGETS = 60
#: A hint is "on its own panel" within the panel link distance; the hint is
#: called per-panel when at least this share of solved subs' hints are.
PER_PANEL_SHARE = 0.8

_COLUMNS = ("ra_hint_deg", "dec_hint_deg", "ra_center_deg", "dec_center_deg",
            "reject_reason")


def _finite(ra: Any, dec: Any) -> bool:
    try:
        return ra is not None and dec is not None and math.isfinite(float(ra)) \
            and math.isfinite(float(dec))
    except (TypeError, ValueError):
        return False


def _sep(a: tuple[float, float], b: tuple[float, float]) -> float:
    from seestack.stack.pointings import _sep_deg, _to_vec

    return _sep_deg(_to_vec(*a), _to_vec(*b))


def _mean_point(points: list[tuple[float, float]]) -> tuple[float, float]:
    """The unit-vector mean of ``points`` — wrap- and pole-safe."""
    from seestack.stack.pointings import _to_vec

    x = y = z = 0.0
    for p in points:
        v = _to_vec(*p)
        x, y, z = x + v[0], y + v[1], z + v[2]
    r = math.sqrt(x * x + y * y + z * z) or 1.0
    return (math.degrees(math.atan2(y, x)) % 360.0,
            math.degrees(math.asin(max(-1.0, min(1.0, z / r)))))


def _substantial_groups(labels: list[int], min_members: int) -> dict[int, int]:
    counts: dict[int, int] = {}
    for lab in labels:
        if lab >= 0:
            counts[lab] = counts.get(lab, 0) + 1
    return {lab: n for lab, n in counts.items() if n >= min_members}


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(float(x), nd)


def measure_target(rows: list[tuple], *, is_mosaic_name: bool) -> dict[str, Any] | None:
    """One target's numbers, or ``None`` when it is not a mosaic at all.

    ``rows`` are ``_COLUMNS`` tuples, one per sub."""
    from seestack.stack.pointings import PANEL_LINK_DIST_DEG, _cluster_distinct

    centres = [(r[2], r[3]) if _finite(r[2], r[3]) else (None, None) for r in rows]
    hints = [(r[0], r[1]) if _finite(r[0], r[1]) else (None, None) for r in rows]
    centre_groups = _substantial_groups(
        _cluster_distinct(centres, PANEL_LINK_DIST_DEG), MIN_PANEL_SUBS)
    if not is_mosaic_name and len(centre_groups) < 2:
        return None

    solved = [i for i, c in enumerate(centres) if c[0] is not None]
    hinted = [i for i, h in enumerate(hints) if h[0] is not None]
    unsolved = [i for i, c in enumerate(centres) if c[0] is None]
    hint_groups = _substantial_groups(
        _cluster_distinct(hints, PANEL_LINK_DIST_DEG), MIN_PANEL_SUBS)

    both = [i for i in solved if hints[i][0] is not None]
    d_own = [_sep(hints[i], centres[i]) for i in both]  # type: ignore[arg-type]
    mosaic_centre = _mean_point([centres[i] for i in solved]) if solved else None  # type: ignore[misc]
    d_hint_mid = ([_sep(hints[i], mosaic_centre) for i in hinted]  # type: ignore[arg-type]
                  if mosaic_centre else [])
    d_centre_mid = ([_sep(centres[i], mosaic_centre) for i in solved]  # type: ignore[arg-type]
                    if mosaic_centre else [])
    share_own = (sum(1 for d in d_own if d <= PANEL_LINK_DIST_DEG) / len(d_own)
                 if d_own else None)

    # Hints of un-located subs that land on no located sub's panel: cluster the
    # un-located subs' hints together with every located centre, and count the
    # groups holding enough un-located subs and no located one.
    pts = [hints[i] for i in unsolved] + [centres[i] for i in solved]
    labels = _cluster_distinct(pts, PANEL_LINK_DIST_DEG)
    n_un = len(unsolved)
    located_labels = {lab for lab in labels[n_un:] if lab >= 0}
    orphan_counts: dict[int, int] = {}
    for lab in labels[:n_un]:
        if lab >= 0 and lab not in located_labels:
            orphan_counts[lab] = orphan_counts.get(lab, 0) + 1
    orphans = {lab: n for lab, n in orphan_counts.items() if n >= MIN_PANEL_SUBS}

    if len(centre_groups) < 2:
        verdict = "cannot_tell"   # no located split to compare the hints against
    elif not both:
        verdict = "no_hints"
    elif share_own is not None and share_own >= PER_PANEL_SHARE and len(hint_groups) >= 2:
        verdict = "per_panel"
    elif len(hint_groups) <= 1 and d_own and median(d_own) > PANEL_LINK_DIST_DEG:
        verdict = "mosaic_centre"
    else:
        verdict = "mixed"

    return {
        "mosaic_by_name": bool(is_mosaic_name),
        "subs": len(rows),
        "located": len(solved),
        "unlocated": len(unsolved),
        "unlocated_solve_failed": sum(
            1 for i in unsolved if str(rows[i][4] or "").startswith("solve_failed:")),
        "with_hint": len(hinted),
        "unlocated_with_hint": sum(1 for i in unsolved if hints[i][0] is not None),
        "located_panels": len(centre_groups),
        "hint_groups": len(hint_groups),
        "median_hint_to_own_centre_deg": _r(median(d_own)) if d_own else None,
        "share_hint_on_own_panel": _r(share_own),
        "median_hint_to_mosaic_middle_deg": _r(median(d_hint_mid)) if d_hint_mid else None,
        "median_centre_to_mosaic_middle_deg": _r(median(d_centre_mid)) if d_centre_mid else None,
        "unlocated_only_hint_groups": len(orphans),
        "subs_in_unlocated_only_hint_groups": sum(orphans.values()),
        "verdict": verdict,
    }


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    """Compare hints with solved centres on every mosaic. Reads the record only."""
    from seestack.io.scanner import is_mosaic_target_name

    entries = library.list_targets()
    measured: list[dict[str, Any]] = []
    single = 0
    for k, entry in enumerate(entries):
        if should_stop is not None and should_stop():
            raise DiagnosticStopped("stopped")
        if progress is not None:
            progress("reading targets", k + 1, len(entries))
        try:
            proj = library.open_target(entry.safe_name)
        except Exception:  # noqa: BLE001 — a broken target is skipped
            continue
        try:
            rows = list(proj.iter_frame_columns(*_COLUMNS))
        except Exception:  # noqa: BLE001
            rows = []
        finally:
            proj.close()
        if not rows:
            continue
        m = measure_target(rows, is_mosaic_name=is_mosaic_target_name(entry.name))
        if m is None:
            single += 1
        else:
            measured.append(m)

    measured.sort(key=lambda m: -m["subs"])
    verdicts: dict[str, int] = {}
    for m in measured:
        verdicts[m["verdict"]] = verdicts.get(m["verdict"], 0) + 1
    return {
        "single_field_targets": single,
        "mosaic_targets": len(measured),
        "verdicts": dict(sorted(verdicts.items())),
        "mosaics_with_an_unlocated_only_hint_group": sum(
            1 for m in measured if m["unlocated_only_hint_groups"] > 0),
        "mosaics": measured[:MAX_LISTED_TARGETS],
        "mosaics_listed": min(len(measured), MAX_LISTED_TARGETS),
        "how_to_read": (
            "One entry per mosaic target, largest first, no names. "
            "located_panels counts the panels the plate-solved centres form; "
            "hint_groups counts the groups the telescope's own pointing hints form. "
            "verdict per_panel: at least 80 % of located subs carry a hint on their own "
            "panel and the hints split too — the hint is the panel's pointing, so "
            "un-located subs can be split by panel. mosaic_centre: the hints form one "
            "group away from the subs' own centres — the hint is the mosaic's middle, "
            "and a per-panel split needs another signal. cannot_tell: fewer than two "
            "located panels. unlocated_only_hint_groups counts groups of at least 5 "
            "un-located subs whose hints sit on no located sub's panel — under "
            "per_panel, a panel missing from the picture today."
        ),
    }


def ready(library) -> bool:  # noqa: ANN001
    """Any target with at least one sub (the mosaic test needs its frames)."""
    return any((e.n_frames or 0) > 0 for e in library.list_targets())


DIAGNOSTIC = Diagnostic(
    name="mosaic_panel_hints",
    version=1,
    question=("Does the Seestar write each mosaic panel's own pointing into its subs, "
              "or the mosaic's centre? (gate on the un-located-panel Bugs entry, "
              "Scout 2026-10-19)"),
    run=run,
    ready=ready,
)
