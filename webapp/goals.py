"""The user's per-target integration goal — one definition, read by every screen.

A goal ("I want 12 h on M 31") is a gentle suggestion, never a gate: nothing
here blocks stacking. But it is read by *four* surfaces — the Target page's "Is
it enough yet?" card, the Dashboard's "Target progress" overview, the Tonight
planner's already-targeted rows, and the goal endpoints themselves — and every
one of them must answer with the same number, or the app contradicts itself
about the same picture.

It lives in the existing key/value ``project_meta`` table, so storing it needed
no schema migration: an old project simply has the key absent and falls back to
the per-object-type default. Keep it that way — this module only reads and
validates, and the parse deliberately treats a stale or hand-edited value as
*unset* rather than raising, so a garbled project can never 500 a card.
"""

from __future__ import annotations

# Project-meta key holding the goal (total accepted-sub exposure, seconds).
GOAL_META_KEY = "integration_goal_s"

# Sanity bounds so a fat-fingered value can't poison the readiness card: 1 minute
# to 1000 hours. The bound only guards against nonsense, not against an ambitious
# deep-integration target.
MIN_GOAL_S = 60.0
MAX_GOAL_S = 1000.0 * 3600.0


def read_goal_s(proj) -> float | None:  # noqa: ANN001 — any open Project
    """The target's stored integration goal in seconds, or ``None`` when unset.

    Tolerates a stale/garbage value (treated as unset) so a hand-edited project
    can never 500 a screen that merely wants to *show* the goal.
    """
    raw = proj.get_meta(GOAL_META_KEY)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not (val > 0) or val != val:  # non-positive or NaN → unset
        return None
    return val
