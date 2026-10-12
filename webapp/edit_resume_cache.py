"""Resume the editor's live preview from the array its sky fits already produced.

:mod:`webapp.edit_fit_cache` (v0.382.2) carries forward every *number* an op
measured, and a number is all it can carry: the three ``background.*`` ops fit a
**spatial model** — a mesh over the whole canvas, a per-coverage-level offset —
and a mesh is not a number. So dragging the saturation slider still re-fitted the
sky from scratch on every debounced frame, twice over (the preview PNG and the
histogram are two requests running the same recipe on the same proxy), and on the
one-click Auto recipe that fit is the largest remaining cost of a render.

**What is cached is the picture at a boundary, not the model.** After the last
enabled additive (``background.*``) op the array is a pure function of the proxy
and of the ops above it — the ops are deterministic and the proxy is the same
file — so when the next render's recipe agrees with this one *op for op up to
that boundary*, resuming from the stored array renders the identical picture and
skips every fit above it. ``apply_recipe`` needs no new parameter to allow that:
the split is made at a point where no stretch has run, so the prefix and the tail
are two ordinary calls whose composition is exactly what the single call does.

**Measured** (2026-10-12, on the bundled mosaic samples through
``build_auto_recipe_for_run`` — ``background.level_coverage`` →
``background.final_gradient`` → colour calibration → stretch → SCNR →
saturation → curves → sharpen → border trim):

| canvas | per render, today | resumed | |
|---|---|---|---|
| 1693×1150 mosaic (the owner's own proxy size) | 5.18 s | **2.81 s** | 1.85× |
| 907×615 mosaic (`--mosaic`) | 1.49 s | 0.73 s | 2.06× |
| 847×575 mosaic at proxy stride 2 (`--big`) | 1.50 s | 0.68 s | 2.21× |
| 480×320 single field | 0.31 s | 0.19 s | 1.64× |

**and ``np.array_equal(cold, resumed, equal_nan=True)`` is ``True`` on all four**
— max absolute difference exactly ``0``, including on the mosaic canvases where
3.6–4.8 % of the pixels are uncovered. That is the point of caching the array
rather than the correction, and it is why this is the shape that shipped.

**Why the array and not the field.** v0.382.2's own note sized the alternative:
record what each additive op *added* (``EditContext.record_field``, built for the
loupe) and replay it. That is how the loupe renders a window and it is right
there — but it is the wrong instrument here, for two reasons it also measured. A
replayed field reconstructs the picture as ``before + float32(after − before)``,
which is **not** ``after``: one float32 rounding, ~4e-7 of full scale, on the one
surface whose whole job is to show what the export will do. And it costs *more*
memory, not less — a mosaic's Auto recipe carries two additive ops, so two
fields, against the one array a boundary needs.

Nothing here is persisted and nothing is user-visible: a miss — a restarted
container, an evicted entry, a changed op above the boundary — is precisely
today's behaviour, so the worst case of this whole module is the render the app
already does.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from seestack.edit.recipe import OpInstance, Recipe
from seestack.edit.registry import get_op
from webapp import edit_fit_cache

#: Total bytes of cached arrays, across every slot. One slot holds one
#: ``(H, W, 3)`` float32 array of the editor's proxy, which
#: ``seestack.edit.proxy.PROXY_MAX_PX`` caps at 1500 px on the long side — 23 MB
#: on the mosaic canvas measured above, 27 MB on the largest square proxy the
#: editor can build. It is a **byte** budget rather than an entry count because
#: bytes are what the owner's RAM-capped NAS actually has, and because the one
#: thing this must never do is trade memory safety for speed (AGENTS.md §3, the
#: OOM history). Two of the largest possible proxies is the ceiling.
MAX_BYTES = 64 * 1024 * 1024

#: How many pictures to remember at once. One is the editor's own shape — a
#: person edits one picture at a time — and two covers stepping back to the
#: previous one without widening the budget above.
MAX_ENTRIES = 2

_lock = threading.Lock()
_store: OrderedDict[tuple, _Entry] = OrderedDict()


@dataclass(frozen=True)
class _Entry:
    fingerprints: tuple
    n_ops: int
    array: np.ndarray
    notes: tuple[tuple[int, str, Any], ...] = ()


@dataclass(frozen=True)
class ResumePoint:
    """An array to render on, and how many enabled ops already went into it."""

    #: The picture at the boundary. A fresh copy per hit (see :func:`resume_for`).
    array: np.ndarray
    #: How many *enabled* ops produced it, i.e. where the tail starts.
    n_ops: int
    #: ``(position in the enabled list, note name, note)`` for the skipped ops,
    #: so ``EditContext.notes_for`` still sees what they recorded — and sees it
    #: in recipe order, which is what lets a reader ask for "the *last* balance
    #: this picture got". Carried by **position** rather than by ``uid`` because
    #: ``recipe_from_dict`` mints a fresh uid for every recipe posted without
    #: one, and a uid-keyed note would then land under a uid nothing matches.
    notes: tuple[tuple[int, str, Any], ...] = ()


def render_key(project_dir: Path | str, run_id: int, fits_path: str | Path | None,
               *, proxy_scale: float, proxy_shape: tuple[int, ...],
               already_display: bool) -> tuple:
    """:func:`webapp.edit_fit_cache.render_key` plus the master file's identity.

    The fit cache can key on the render geometry alone: what it carries is a
    measurement, and the proxy cache (``edit.proxy``) rebuilds on the master's
    ``mtime`` anyway, so the worst a stale entry could do there is hand an op a
    number read off slightly different pixels. An **array** is a different
    promise — a stale one would be a wrong *picture* — so this adds the master's
    ``(mtime_ns, size)``. One ``stat`` per render, and it means the cache cannot
    outlive the pixels it was taken from even if a rewritten master happened to
    come back the same shape at the same scale.
    """
    src: tuple = ()
    if fits_path:
        try:
            st = os.stat(fits_path)
            src = (int(st.st_mtime_ns), int(st.st_size))
        except OSError:  # pragma: no cover — a missing master fails earlier
            src = ()
    return (
        edit_fit_cache.render_key(project_dir, run_id, proxy_scale=proxy_scale,
                                  proxy_shape=proxy_shape,
                                  already_display=already_display),
        src,
    )


def enabled_ops(recipe: Recipe) -> list[OpInstance]:
    """The ops ``apply_recipe`` will actually run, in order.

    The boundary below is a position in *this* list rather than in ``recipe.ops``:
    the pipeline filters disabled ops out before it runs anything, so a
    switched-off op is not a step and must not shift the boundary.
    """
    return [op for op in recipe.ops if op.enabled]


def boundary(ops: list[OpInstance]) -> int:
    """How many leading enabled ops are worth caching past — ``0`` for "don't".

    The boundary sits **after the last additive ``background.*`` op**. Those are
    exactly the ops whose measurement :mod:`webapp.edit_fit_cache` cannot carry,
    which is what makes a render repeat them needlessly, and they are the only
    ops whose cost is a *fit of the whole canvas* rather than a pass over it.

    ``0`` when the recipe has no additive op (there is nothing to save), and
    ``0`` when a stretch sits above the boundary: the pipeline's
    linear→nonlinear contract is per-call state (its local ``stretched`` and
    ``ctx.stage``), so splitting there would let the tail's own fallback stretch
    fire on an already-stretched picture. The frontend cannot build such a recipe
    — ``stageConflicts`` inserts every op on the correct side — but a posted one
    can, and this is the one place that has to care.
    """
    last = 0
    for i, op in enumerate(ops):
        spec = get_op(op.id)
        if spec is not None and spec.additive_field:
            last = i + 1
    if last == 0:
        return 0
    for op in ops[:last]:
        spec = get_op(op.id)
        if spec is not None and spec.is_stretch:
            return 0
    return last


def _prefix_matches(stored: tuple, current: tuple, n: int) -> bool:
    """Do the two recipes agree on their first ``n`` enabled ops?

    Compared on **id and params**, never on ``uid``, for the reason
    :func:`webapp.edit_fit_cache._prefix_uid_map` gives: a uid is bookkeeping
    rather than an input, and a recipe posted without one gets a fresh uid per
    request — matching on it would make the carry a permanent miss. Position for
    position is what pins "the same ops ran on the same pixels".
    """
    if n <= 0 or len(stored) < n or len(current) < n:
        return False
    return all(a[1:] == b[1:]
               for a, b in zip(stored[:n], current[:n], strict=True))


def resume_for(key: tuple, fingerprints: tuple) -> ResumePoint | None:
    """The array this render may start from, or ``None`` for an ordinary render."""
    with _lock:
        entry = _store.get(key)
        if entry is None or not _prefix_matches(
                entry.fingerprints, fingerprints, entry.n_ops):
            return None
        _store.move_to_end(key)
        # The copy is deliberate: the caller renders *onto* this array, and an
        # op is free to write into the one it was handed. A cache the next
        # render corrupts would be worse than no cache, and one copy of a
        # ≤1500 px proxy is milliseconds against the sky fit it saves.
        return ResumePoint(array=entry.array.copy(), n_ops=entry.n_ops,
                           notes=entry.notes)


def notes_onto(point: ResumePoint, ops: list[OpInstance]) -> dict[str, Any]:
    """``point``'s carried notes, re-keyed onto *this* render's op uids.

    ``EditContext.record_note`` keys a note ``"<op uid>:<name>"``, so the uids
    have to be this render's for ``notes_for`` to find them. Positions outside
    the current enabled list are dropped rather than guessed at.
    """
    out: dict[str, Any] = {}
    for pos, name, note in point.notes:
        if 0 <= pos < len(ops):
            out[f"{ops[pos].uid}:{name}"] = note
    return out


def notes_from(op_notes: dict[str, Any], ops: list[OpInstance]) -> tuple:
    """The prefix render's notes, as the position-keyed triples :class:`ResumePoint`
    carries. ``ops`` is the prefix — the enabled ops that produced the array."""
    where = {op.uid: i for i, op in enumerate(ops)}
    out: list[tuple[int, str, Any]] = []
    for key, note in op_notes.items():
        uid, sep, name = key.partition(":")
        if sep and uid in where:
            out.append((where[uid], name, note))
    return tuple(out)


def remember(key: tuple, fingerprints: tuple, *, array: np.ndarray, n_ops: int,
             notes: tuple = ()) -> None:
    """Store the array at the boundary, for the next render of this picture."""
    if n_ops <= 0:
        return
    arr = np.asarray(array)
    if arr.nbytes > MAX_BYTES:
        return
    with _lock:
        _store.pop(key, None)
        _store[key] = _Entry(fingerprints=tuple(fingerprints), n_ops=int(n_ops),
                             array=arr.copy(), notes=tuple(notes))
        while len(_store) > 1 and (len(_store) > MAX_ENTRIES
                                  or _total_bytes() > MAX_BYTES):
            _store.popitem(last=False)


def _total_bytes() -> int:
    return sum(int(e.array.nbytes) for e in _store.values())


def clear() -> None:
    """Forget everything — for tests, and cheap enough to be safe anywhere."""
    with _lock:
        _store.clear()
