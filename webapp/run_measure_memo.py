"""Remember the editor's per-run *measurements* of a picture that cannot change.

The "How did Auto do?" chips answer every tap with a request that asks the run's
coarse archetype (:func:`webapp.routers.editor.classify_run_measured`), and the
run-scoped preferences read the chip row re-fetches straight afterwards asks it
again together with Auto's measured knobs
(:func:`webapp.routers.editor._run_taste_context`). Both are pure functions of the
run's own files — the master (which the proxy is cut from), its coverage siblings
and the stored ``is_mosaic`` flag — and none of those moves between two taps. Yet
each request re-read the proxy, re-measured the well-covered rectangle and
re-classified the picture from scratch.

**Measured** on the ``--dithered`` dogfood sample (a 1212×784 canvas, smaller
than the owner's 1693×1150 mosaics): the tap's POST took **2.3–3.2 s** and the
re-read **4.4 s**, so a tap sat in silence for seconds before its "Thanks — Auto
will lean that way for you" appeared, and the dogfood's own drive read
"NOTHING SAID". With the answers remembered the first read pays once, when the
editor opens, and every tap after it is a dictionary lookup.

**The key is the whole safety rule.** It carries every input the measurement
reads: the run's identity, its master path, the stored mosaic flag, and the
``(mtime_ns, size)`` of the master and both coverage siblings — so a re-stack, a
re-written sibling or a back-filled flag is a different key and measures afresh,
exactly as :mod:`seestack.edit.proxy` keys the proxy on the master's mtime. A miss
(a restarted container, an evicted entry, a changed file) is precisely the
behaviour before this module existed. A computation that raises is never stored,
so a transient read failure is retried on the next request rather than
remembered. Values are copied in and out, so a caller can never edit the memo.
Nothing here is persisted and nothing is user-visible.
"""

from __future__ import annotations

import copy
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from seestack.edit.proxy import coverage_path_for, frame_coverage_path_for

# Each entry is a small dict of floats and a label — never an image — so the
# store is kilobytes. Two kinds per run, and a person edits one or two runs at a
# time; 32 bounds a long-running container comfortably above that.
MAX_ENTRIES = 32

_lock = threading.Lock()
_store: OrderedDict[tuple, Any] = OrderedDict()
MISS = object()


def _stat_sig(path: Path) -> tuple[int, int] | None:
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def run_key(kind: str, project_dir: str | Path, run) -> tuple:
    """Everything a per-run measurement of the picture depends on."""
    fits_path = str(run.fits_path)
    return (
        kind,
        str(project_dir),
        int(run.id),
        fits_path,
        getattr(run, "is_mosaic", None),
        _stat_sig(Path(fits_path)),
        _stat_sig(coverage_path_for(fits_path)),
        _stat_sig(frame_coverage_path_for(fits_path)),
    )


def key_for(kind: str, project_dir: str | Path, run) -> tuple | None:
    """:func:`run_key`, or ``None`` when it can't be built. Take the key **before**
    measuring: a file that changes mid-measurement then files the answer under the
    old files' key, where nothing will ever look it up again."""
    try:
        return run_key(kind, project_dir, run)
    except Exception:  # noqa: BLE001 — a key that can't be built is a miss
        return None


def lookup(key: tuple | None) -> Any:
    """The remembered value for ``key``, or :data:`MISS`. Never raises."""
    if key is None:
        return MISS
    with _lock:
        if key not in _store:
            return MISS
        _store.move_to_end(key)
        return copy.deepcopy(_store[key])


def store(key: tuple | None, value: Any) -> None:
    """Remember ``value`` under ``key``. Never raises."""
    if key is None:
        return
    try:
        value = copy.deepcopy(value)
    except Exception:  # noqa: BLE001 — a memo that can't be written is a miss
        return
    with _lock:
        _store[key] = value
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)


def clear() -> None:
    with _lock:
        _store.clear()
