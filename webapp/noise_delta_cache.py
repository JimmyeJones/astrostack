"""A tiny in-process cache for the matched-crop "did it get better?" picture.

:func:`seestack.render.noisedelta.build_noise_delta` is cheap in the crop it
reads and *not* cheap in the two decimated scout views it needs to choose the
crop — those touch every pixel of both masters, exactly like rendering a preview.
The Target page's card asks two questions about one picture (may I show it? and
what may I say about it?), and re-deriving the whole thing per question would
double that cost on the owner's largest mosaics for nothing.

So: hold the last few answers, keyed on the two master paths **and their mtimes**,
so a re-stack that rewrites a master is a miss rather than a stale picture. The
"nothing to show" answer is cached too — it is reached by the same scout loads,
and a target whose masters cannot be compared would otherwise pay for the
discovery on every page view.

Purely an optimisation: dropping the whole module would change no answer, only
how long they take. Nothing here is persisted (see
:mod:`webapp.estimate_cache`, whose shape this follows).
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seestack.render.noisedelta import NoiseDeltaPatch

#: How many composed pictures are held at once. Each is one PNG of two ~320 px
#: squares — a few hundred KB — so this is a couple of MB at worst, sized for the
#: locality a single-user app actually has (the target being looked at, and the
#: one before it).
MAX_ENTRIES = 4

_lock = threading.Lock()
_entries: OrderedDict[tuple, NoiseDeltaPatch | None] = OrderedDict()


def _key(older: str, newer: str, patch_px: int) -> tuple:
    def stamp(p: str) -> tuple:
        try:
            st = Path(p).stat()
            return (int(st.st_mtime_ns), int(st.st_size))
        except OSError:
            return (0, 0)
    return (str(older), stamp(older), str(newer), stamp(newer), int(patch_px))


def noise_delta(older_fits: str, newer_fits: str, *,
                patch_px: int | None = None) -> NoiseDeltaPatch | None:
    """The composed picture for these two masters, from cache when still valid.

    Same contract as :func:`~seestack.render.noisedelta.build_noise_delta`,
    including ``None`` for "there is no honest picture here".
    """
    from seestack.render.noisedelta import PATCH_PX, build_noise_delta

    px = PATCH_PX if patch_px is None else int(patch_px)
    key = _key(older_fits, newer_fits, px)
    with _lock:
        if key in _entries:
            _entries.move_to_end(key)
            return _entries[key]
    # Built outside the lock: it is the second this module exists to avoid, and
    # two requests racing on one target would simply both build it and store the
    # same answer.
    patch = build_noise_delta(older_fits, newer_fits, patch_px=px)
    with _lock:
        _entries[key] = patch
        _entries.move_to_end(key)
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)
    return patch


def clear() -> None:
    """Drop everything held — for tests, and harmless at any time."""
    with _lock:
        _entries.clear()
