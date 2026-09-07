"""Carry one live-preview render's *measurements* forward to the next one.

Every editor render runs the whole recipe from the top — that is the live
preview's contract and it is not negotiable. But several ops don't only
transform pixels: they **measure the whole image first** and derive a number
from it (the stretch's per-channel robust median and σ, the tone curve's
derived control points, "Neutralize background"'s sky medians, and — by far the
dominant cost — colour calibration's star detection and white-balance solve).
Dragging one slider therefore re-solves a star field that cannot have changed,
on every debounced frame, twice over (the preview PNG and the histogram are two
requests running the same recipe on the same proxy).

``EditContext.fit`` already exists for exactly this problem — the loupe measures
on the whole picture and hands the fits to the window render — but nothing was
carrying them between two renders of the *same* picture. This module is that
carry, and nothing more.

**Measured** on a 1500×1000 proxy carrying the one-click Auto recipe
(gradient removal → colour calibration → stretch → SCNR → saturation → curves →
sharpen): **4.1 s a render before, 2.35 s with the unchanged ops' fits carried
forward — 1.75×**, with **bit-identical** output (the carried numbers *are* the
numbers the render would have measured).

**The safety rule is the whole design.** A fit may be reused only when that op's
own params *and its input* are unchanged, so only the **longest common prefix**
of the previous render's enabled ops is ever offered: the first op whose id or
params differ ends the prefix, and it and everything after it measure for
themselves exactly as before. Every op in a matching prefix received a
bit-identical array (the ops are deterministic and the proxy is the same file),
so its measurement is bit-identical too.

Nothing here is persisted and nothing is user-visible: a miss — a restarted
container, an evicted entry, a changed first op — is precisely today's
behaviour, so the worst case of this whole module is the render the app already
does.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from seestack.edit.recipe import Recipe

# How many (target, run, proxy-geometry) slots to remember. Each holds a handful
# of small fitted values — three or four per recipe on the Auto pipeline, each a
# tuple of floats or a small solve — never an image, so the whole store is
# kilobytes. Eight is comfortably more than the one target a person edits at a
# time while still bounding a long-running container.
MAX_ENTRIES = 8

_lock = threading.Lock()
# key -> (op fingerprints that produced them, fitted values)
_store: OrderedDict[tuple, tuple[tuple, dict[str, Any]]] = OrderedDict()


def render_key(
    project_dir: Path | str,
    run_id: int,
    *,
    proxy_scale: float,
    proxy_shape: tuple[int, ...],
    already_display: bool,
) -> tuple:
    """Everything besides the recipe that decides what an op measures.

    A fit is only interchangeable between two renders of the **same pixels at the
    same scale**: ``proxy_scale`` sizes every pixel-scaled measurement
    (``EditContext.scaled_px`` — the colour solve's detection FWHM is derived from
    it), and ``already_display`` decides whether the pipeline's own fallback
    stretch runs at all. A windowed/loupe render never shares a key with the
    whole-picture preview because its scale (and origin) differ.
    """
    return (
        str(project_dir),
        int(run_id),
        round(float(proxy_scale), 6),
        tuple(int(v) for v in tuple(proxy_shape)[:2]),
        bool(already_display),
    )


def op_fingerprints(recipe: Recipe) -> tuple[tuple[str, str, str], ...]:
    """The *enabled* ops in order, as ``(uid, id, params)`` triples.

    Disabled ops are excluded because :func:`seestack.edit.pipeline.apply_recipe`
    filters them out before it runs anything — editing a switched-off op changes
    no pixel, so it must not invalidate the prefix. Params are compared as sorted
    JSON so key order can't read as a change; an unserialisable value falls back
    to ``repr``, which is conservative (it can only ever *miss*).
    """
    out: list[tuple[str, str, str]] = []
    for op in recipe.ops:
        if not op.enabled:
            continue
        try:
            params = json.dumps(op.params, sort_keys=True, default=str)
        except (TypeError, ValueError):  # pragma: no cover — defensive
            params = repr(op.params)
        out.append((str(op.uid), str(op.id), params))
    return tuple(out)


def _prefix_uid_map(
    stored: tuple[tuple[str, str, str], ...],
    current: tuple[tuple[str, str, str], ...],
) -> dict[str, str]:
    """``stored uid -> this render's uid`` for the leading ops the two agree on.

    The comparison deliberately ignores the **uid** and matches on position, op
    id and params, because a uid is bookkeeping and not an input: what an op
    measures is decided by the array it is handed, its own params and the render
    geometry, all three of which a position-for-position match pins. That also
    makes the carry work for a client that mints a fresh uid per request
    (``recipe_from_dict`` does exactly that for a recipe posted without one),
    which is otherwise a permanent miss.
    """
    out: dict[str, str] = {}
    # Not strict: the two recipes legitimately differ in length (an op added or
    # removed), and the shorter one simply ends the prefix.
    for a, b in zip(stored, current, strict=False):
        if a[1:] != b[1:]:
            break
        out[a[0]] = b[0]
    return out


def frozen_fits_for(key: tuple, fingerprints: tuple) -> dict[str, Any] | None:
    """The fits safe to reuse for this render, or ``None`` when there are none.

    ``None`` — not an empty dict — because that is what ``EditContext`` treats as
    "no caller supplied any", i.e. today's behaviour.
    """
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        _store.move_to_end(key)
        stored_fps, fitted = entry
    uid_map = _prefix_uid_map(stored_fps, fingerprints)
    if not uid_map:
        return None
    # ``EditContext`` keys a fit as "<op uid>:<name>" (see ``_fit_key``), so the
    # carried values are re-keyed onto *this* render's uids. A fit recorded with
    # no op uid — impossible from the pipeline, which always sets one — simply
    # never matches, which is the safe direction.
    out: dict[str, Any] = {}
    for k, v in fitted.items():
        stored_uid, sep, name = k.partition(":")
        if not sep:
            continue
        mapped = uid_map.get(stored_uid)
        if mapped is not None:
            out[f"{mapped}:{name}"] = v
    return out or None


def remember(key: tuple, fingerprints: tuple, fitted: dict[str, Any]) -> None:
    """Store what this render measured, for the next render of the same picture.

    A render that itself ran on carried fits re-records them (``EditContext.fit``
    records the frozen value as well as a fresh one), so the stored set stays
    complete rather than thinning out over a session.
    """
    if not fitted:
        return
    with _lock:
        _store[key] = (fingerprints, dict(fitted))
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)


def clear() -> None:
    """Forget everything — for tests, and cheap enough to be safe anywhere."""
    with _lock:
        _store.clear()
