"""One signature-keyed cache for the per-target roll-ups, shared by every
endpoint that has to open each project's SQLite to answer.

Several read-only screens ask the same expensive question — *for every target in
the library, what has the owner actually collected?* — and answering it means
opening each target's project DB. The cheap half is a key/value meta read (the
user's integration goal, well under a millisecond); the expensive half is the
per-night pace, which scans three columns of every dated frame. Measured on a
synthetic 40-target library with 1500 frames each: opening + the goal read costs
**0.6 ms a target**, and adding the pace scan takes it to **5.4 ms a target**
(24 ms → 217 ms for the library). That is fine once a minute and wasteful on
every render, and it grows with both the target count and the frame count.

So the answer is cached on ``app.state`` under a caller-chosen key, invalidated
by a **signature** over the library registry — each target's activity stamp,
accepted-frame count and newest picture — plus a short TTL. The signature catches
anything a scan or a stack changed; the TTL backstops the edits it can't see
(setting a goal doesn't bump ``last_activity_utc``), so a just-changed goal still
shows within a minute.

This started as a bespoke cache inside ``routers/stats.py`` for
``/api/library-progress``; the Tonight planner needs exactly the same treatment
for exactly the same reason, so the pattern lives here rather than being
copy-pasted a second time (the copy-paste failure mode this project has been
bitten by before — see ``webapp/goals.py``).

Purely an in-process performance cache: it is never a source of truth, it holds
only data re-derivable from disk, and losing it costs one recomputation.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterable
from typing import Any

# How long a cached roll-up stays fresh without a registry change. Short enough
# that an edit the signature can't see (a goal change) surfaces promptly.
DEFAULT_TTL_S = 60.0


def registry_signature(targets: Iterable[Any]) -> tuple:
    """A cheap, order-stable fingerprint of the library registry.

    Keys on each target's identity, last activity, accepted-frame count and
    newest picture — the registry columns that move whenever a scan, an ingest,
    a stack or a frame accept/reject changes what a per-target roll-up would say.

    The newest picture is in there because the first three genuinely miss a
    stack. ``last_activity_utc`` is written at **one-second** granularity
    (``seestack.io.library._utc_iso``), and a re-stack of frames already in the
    library moves neither the accepted-frame count nor — if it lands inside the
    same second as the previous registry write — the stamp. The roll-up would
    then keep answering from the *previous* picture for a whole TTL, which for
    the Tonight planner means telling someone to nudge a scope they have already
    moved (the exact thing ``newest_picture_nudge`` exists to avoid). A stack
    always writes a new preview path, so this column moves when a new picture
    lands and nothing else does. Tolerates a target object without the attribute.
    """
    return tuple(sorted(
        (t.safe_name, t.last_activity_utc or "", int(t.n_frames_accepted or 0),
         str(getattr(t, "last_stack_preview", None) or ""))
        for t in targets
    ))


def _attr(key: str) -> str:
    return f"_registry_cache_{key}"


def cached_for_registry[T](app: Any, key: str, sig: tuple, build: Callable[[], T],
                           *, ttl_s: float = DEFAULT_TTL_S) -> T:
    """Return ``build()``'s result for ``sig``, reusing a fresh cached one.

    ``key`` namespaces the entry on ``app.state`` so different roll-ups never
    collide. A cached entry is reused only when its signature matches *and* it is
    younger than ``ttl_s``; otherwise ``build`` runs and its result is stored.
    Failures aren't cached — an exception in ``build`` propagates and leaves any
    previous entry alone, so a transient error can't pin a stale answer.
    """
    attr = _attr(key)
    now = time.monotonic()
    entry = getattr(app.state, attr, None)
    if entry and entry["sig"] == sig and (now - entry["at"]) < ttl_s:
        return entry["data"]
    data = build()
    setattr(app.state, attr, {"sig": sig, "at": now, "data": data})
    return data


# Every roll-up that folds in a value the registry signature can't see. Setting an
# integration goal writes project meta without touching ``last_activity_utc``, so
# without this the user would set a goal and watch two screens keep quoting the
# old one for up to a minute — the TTL is a backstop, not an answer.
GOAL_DEPENDENT_KEYS = ("library_progress", "plan_library_targets")


def invalidate_registry_cache(app: Any, *keys: str) -> None:
    """Drop cached roll-ups so the next request rebuilds them.

    Call this after a write the registry signature can't see. Given no ``keys``,
    every goal-dependent roll-up is dropped. Never raises: a missing entry is
    simply nothing to drop — and the two exceptions that means are both caught,
    because Starlette's ``State`` deletes out of a dict and raises ``KeyError``
    where a plain object would raise ``AttributeError``.
    """
    for key in (keys or GOAL_DEPENDENT_KEYS):
        with contextlib.suppress(AttributeError, KeyError):
            delattr(app.state, _attr(key))
