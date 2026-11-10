"""How much does a sub registered in two targets inflate the Dashboard's
headline today?

The gate on the Bugs LEAD "the Dashboard's whole-library headline
(``/api/stats``) and 'Your sky, so far' count a sub registered in two targets
(#878) twice" (Scout 2026-10-18). Both read
:meth:`seestack.io.library.Library.campaign_stats`-shaped sums of the
``targets`` registry's per-target columns, and each column is stamped from that
target's *own* record — so a twin target holding a row for the same
``source_path`` makes both count the sub. Fixing that cheaply is real design
work (the registry sum opens no project, and ``/api/stats`` is polled every
~10 s), and the lead says to measure first: if the owner has already run
**Combine into ``<T> (mosaic)``** on his pairs, the overcount is gone and the
entry closes with the measurement.

**Method.** Read the record only — no FITS file is opened. Take the registry's
own sums (what the Dashboard shows), then open every target and union its subs
by ``source_path`` under the same rules :meth:`Library._refresh_target_stats_locked`
uses (``n_frames`` = every row, ``n_frames_accepted`` = accepted rows,
exposure = accepted rows with a positive ``exposure_s``), counting each sub
once. A sub is "accepted" library-wide if any target accepted it, and its
exposure is counted once, from the first target that accepted it. The sum of
the per-target counts read *now* is reported too, so a stale registry column is
not mistaken for a duplicate.

Memory: one 8-byte digest and one small int per distinct sub — a few MB at the
owner's scale, never a ``FrameRow``.

**Privacy.** Numbers only. Pairs of targets that share subs are listed
anonymously (largest overlap first) with whether each side is named as a
mosaic; no target name, no path.
"""
from __future__ import annotations

import hashlib
from typing import Any

from seestack.diag import Diagnostic, DiagnosticStopped

#: Pairs of targets listed one by one in the result (the tallies cover them all).
MAX_LISTED_PAIRS = 40

_COLUMNS = ("source_path", "accept", "exposure_s")


def _key(source_path: str) -> bytes:
    return hashlib.blake2b(source_path.encode("utf-8", "surrogateescape"),
                           digest_size=8).digest()


def _hours(seconds: float) -> float:
    return round(seconds / 3600.0, 2)


def _ratio(a: float, b: float) -> float | None:
    return round(a / b, 3) if b > 0 else None


def _totals(n: int, acc: int, exp_s: float) -> dict[str, Any]:
    return {"n_frames": int(n), "n_frames_accepted": int(acc),
            "total_exposure_h": _hours(exp_s)}


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    """Registry sums against the distinct-sub truth. Reads the record only."""
    from seestack.io.scanner import is_mosaic_target_name

    registry_sums = library.campaign_stats()
    entries = library.list_targets()

    # digest -> first target index * 2 + (1 if accepted somewhere so far)
    first: dict[bytes, int] = {}
    # digest -> how many targets hold it, only for subs held by two or more
    holders: dict[bytes, int] = {}
    pairs: dict[tuple[int, int], int] = {}
    is_mosaic: list[bool] = []
    per_target_subs: list[int] = []
    rec_n = rec_acc = 0
    rec_exp = 0.0
    d_acc = 0
    d_exp = 0.0
    unreadable = 0

    for idx, entry in enumerate(entries):
        if should_stop is not None and should_stop():
            raise DiagnosticStopped("stopped")
        if progress is not None:
            progress("reading targets", idx + 1, len(entries))
        is_mosaic.append(bool(is_mosaic_target_name(entry.name)))
        per_target_subs.append(0)
        try:
            proj = library.open_target(entry.safe_name)
        except Exception:  # noqa: BLE001 — a broken target is skipped and counted
            unreadable += 1
            continue
        try:
            rows = proj.iter_frame_columns(*_COLUMNS)
            for source_path, accept, exposure_s in rows:
                if not source_path:
                    continue
                per_target_subs[idx] += 1
                accepted = bool(accept)
                exp = (float(exposure_s) if accepted and exposure_s is not None
                       and float(exposure_s) > 0 else 0.0)
                rec_n += 1
                if accepted:
                    rec_acc += 1
                    rec_exp += exp
                k = _key(str(source_path))
                seen = first.get(k)
                if seen is None:
                    first[k] = idx * 2 + (1 if accepted else 0)
                    if accepted:
                        d_acc += 1
                        d_exp += exp
                    continue
                other, was_accepted = divmod(seen, 2)
                if other == idx:
                    continue  # source_path is UNIQUE per project; belt and braces
                holders[k] = holders.get(k, 1) + 1
                pair = (other, idx)
                pairs[pair] = pairs.get(pair, 0) + 1
                if accepted and not was_accepted:
                    first[k] = other * 2 + 1
                    d_acc += 1
                    d_exp += exp
        except Exception:  # noqa: BLE001 — a half-read target still counts what it gave
            unreadable += 1
        finally:
            proj.close()

    d_n = len(first)
    reg_n = int(registry_sums.get("n_frames", 0))
    reg_acc = int(registry_sums.get("n_frames_accepted", 0))
    reg_exp = float(registry_sums.get("total_exposure_s", 0.0))

    sharing = sorted(pairs.items(), key=lambda kv: -kv[1])
    listed = [{
        "shared_subs": n,
        "subs_in_first": per_target_subs[a],
        "subs_in_second": per_target_subs[b],
        "first_is_mosaic_name": is_mosaic[a],
        "second_is_mosaic_name": is_mosaic[b],
    } for (a, b), n in sharing[:MAX_LISTED_PAIRS]]
    targets_sharing = {t for pair in pairs for t in pair}

    return {
        "targets": len(entries),
        "unreadable_targets": unreadable,
        "registry": _totals(reg_n, reg_acc, reg_exp),
        "record_sum": _totals(rec_n, rec_acc, rec_exp),
        "distinct": _totals(d_n, d_acc, d_exp),
        "overcount": {
            "n_frames": _ratio(reg_n, d_n),
            "n_frames_accepted": _ratio(reg_acc, d_acc),
            "total_exposure": _ratio(reg_exp, d_exp),
        },
        "subs_in_two_or_more_targets": len(holders),
        "subs_in_three_or_more_targets": sum(1 for n in holders.values() if n >= 3),
        "targets_sharing_subs": len(targets_sharing),
        "sharing_pairs": len(pairs),
        "pairs": listed,
        "pairs_listed": len(listed),
        "how_to_read": (
            "registry is what the Dashboard headline and the library summary add up "
            "today (per-target columns summed); distinct counts each sub once by its "
            "source file, under the same accepted/exposure rules; record_sum is the "
            "per-target counts read now, so registry minus record_sum is staleness, "
            "and record_sum minus distinct is double registration. overcount is "
            "registry over distinct: 1.0 means the headline is honest and the Bugs "
            "LEAD closes; above it, the headline is inflated by that factor. pairs "
            "lists pairs of targets that hold the same subs (a sub in three targets "
            "pairs with the first that holds it), largest overlap first, no names."
        ),
    }


def ready(library) -> bool:  # noqa: ANN001
    """Two or more targets with subs — one target cannot share with another."""
    return sum(1 for e in library.list_targets() if (e.n_frames or 0) > 0) >= 2


DIAGNOSTIC = Diagnostic(
    name="twin_target_overcount",
    version=1,
    question=("How much do subs registered in two targets inflate the Dashboard's "
              "frame count and integration hours today? (gate on the #878 headline "
              "Bugs LEAD, Scout 2026-10-18)"),
    run=run,
    ready=ready,
)
