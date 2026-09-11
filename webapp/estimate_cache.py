"""Hold a target's stack-sizing **canvas** between requests.

Sizing a stack is two jobs of wildly different cost
(:class:`~seestack.stack.stacker.StackCanvasBasis`): unioning every sub's
footprint into a canvas reads one WCS per sub, and everything after that is
arithmetic. Measured on a 9-panel, 5,477-sub project — the §1 owner's largest —
:func:`~seestack.stack.stacker.estimate_stack_basis` is **1,007 ms** and the two
sizings a ``/stack-estimate`` response carries are microseconds each.

**The canvas depends on ``mosaic_canvas`` alone**, which is a control almost
nobody touches. Every other knob on the Stack form — the drizzle scale, κ, the
min/max count, "Auto outlier removal" — multiplies or reads the *output* of a
canvas it cannot move, and yet each of them is in the query key (they have to
be: they change the peak, or the rejection answer). So a form whose defaults are
already on screen re-pays a whole second of WCS reads to refresh a sentence, on
every nudge, on exactly the target where it costs most. The Target page's
``/rejection-outlook`` pays it once per load for the same reason.

So the basis is memoised here, keyed on ``(project, canvas mode)`` and
**validated against the frames it was built from** rather than trusted for a
while: every lookup takes :meth:`~seestack.io.project.Project.frames_fingerprint`
(129 ms at that scale — ``SELECT *`` over the whole table) and a basis whose
fingerprint no longer matches is thrown away and recomputed. A stale canvas
estimate after a scan is its own bug, and this is the shape that cannot produce
one: the fingerprint covers every column of every frame row, and
``estimate_stack_basis`` reads nothing else — not the ``meta`` table, not the
run records, and not the filesystem (it tests that a frame *has* a path, never
that the file is there). Measured end to end on that project, a hit is
**1,116 ms → 129 ms**, and a target with a handful of subs was never slow
enough for either number to matter.

Deliberately a plain process-local dict, not a shared store: it holds a handful
of small dataclasses, it is rebuilt for free after a restart, and every entry is
re-validated on use, so nothing about it needs to survive anything.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seestack.io.project import Project
    from seestack.stack.stacker import StackCanvasBasis

#: How many ``(project, canvas mode)`` bases are held at once. A basis is six
#: small fields, so this is about bounding the dict rather than memory: a couple
#: of canvas modes for each of a few targets a user is moving between, which is
#: as much locality as a single-user app has. Evicted least-recently-used.
MAX_ENTRIES = 16

_lock = threading.Lock()
_entries: OrderedDict[tuple[str, str], tuple[str, StackCanvasBasis]] = OrderedDict()
_hits = 0
_misses = 0


def canvas_basis(project: Project, mosaic_canvas: str) -> StackCanvasBasis:
    """The canvas half of a stack sizing, from cache when it is still valid.

    Same contract as :func:`~seestack.stack.stacker.estimate_stack_basis`,
    including the ``ValueError`` it raises when the target has nothing solved to
    size — a failure is never cached, so a target that gets its first solve
    answers on the very next request.
    """
    from seestack.stack.stacker import estimate_stack_basis

    global _hits, _misses
    key = (str(project.db_path), str(mosaic_canvas))
    fingerprint = project.frames_fingerprint()
    with _lock:
        held = _entries.get(key)
        if held is not None and held[0] == fingerprint:
            _entries.move_to_end(key)
            _hits += 1
            return held[1]
    # Computed outside the lock: it is the second this whole module exists to
    # avoid, and two requests racing on the same target would simply both do it
    # and store the same answer.
    basis = estimate_stack_basis(project, mosaic_canvas)
    with _lock:
        _entries[key] = (fingerprint, basis)
        _entries.move_to_end(key)
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)
        _misses += 1
    return basis


def stats() -> dict[str, int]:
    """Hit/miss/size counters, for tests and for anyone debugging a slow form."""
    with _lock:
        return {"hits": _hits, "misses": _misses, "entries": len(_entries)}


def clear() -> None:
    """Drop every held basis and reset the counters.

    Correctness never needs this — a changed frame set is caught by the
    fingerprint — so it exists for tests, which want each one to start from a
    known count.
    """
    global _hits, _misses
    with _lock:
        _entries.clear()
        _hits = 0
        _misses = 0
