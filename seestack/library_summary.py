"""Pure aggregation for the "Your sky, so far" personal-progress summary.

Rolls a library's registry rows (:class:`~seestack.io.library.TargetEntry`) into
a friendly whole-library tally — total kept integration, subs kept, targets
imaged, first-light date, and the standout targets (longest integration, most
subs kept) — plus an ordered *hero* list of targets that have a finished picture
to show off.

Registry-only by design: it reads only the fields the library keeps stamped on
each target row, so it never opens a per-target ``project.sqlite``. That keeps
the whole summary cheap to compute on every call. Kept pure (no ``webapp``
imports, no filesystem I/O of its own) so it's unit-testable; the webapp layer
supplies the "does this preview file still exist?" predicate and turns the hero
rows into preview URLs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from seestack.io.library import TargetEntry


@dataclass
class SummaryTarget:
    """One target's contribution to the summary (a standout or a hero tile)."""

    safe: str
    name: str
    total_exposure_s: float
    n_frames_accepted: int
    has_preview: bool


@dataclass
class LibrarySummary:
    """The whole-library "Your sky, so far" roll-up.

    Every field is derived from the registry alone. ``longest_target`` /
    ``most_imaged_target`` are ``None`` only when nothing has been imaged yet,
    and ``heroes`` is the exposure-ranked subset of imaged targets that have a
    finished picture to show.
    """

    n_targets_imaged: int
    n_subs_kept: int
    total_integration_s: float
    first_light_utc: str | None
    longest_target: SummaryTarget | None
    most_imaged_target: SummaryTarget | None
    heroes: list[SummaryTarget] = field(default_factory=list)


def _to_summary_target(t: TargetEntry, has_preview: bool) -> SummaryTarget:
    return SummaryTarget(
        safe=t.safe_name,
        name=t.name,
        total_exposure_s=float(t.total_exposure_s or 0.0),
        n_frames_accepted=int(t.n_frames_accepted or 0),
        has_preview=has_preview,
    )


def summarize_library(
    targets: Sequence[TargetEntry],
    *,
    preview_exists: Callable[[str | None], bool] = bool,
    hero_limit: int = 60,
) -> LibrarySummary:
    """Aggregate the registry rows into a :class:`LibrarySummary`.

    A target counts as *imaged* once it has accepted any light (accepted subs or
    accumulated exposure) — the same "has collected some light" gate the
    Dashboard progress card uses, so a freshly-created empty target never shows
    up as one of "your pictures".

    ``preview_exists`` decides whether a target's ``last_stack_preview`` still
    points at a real file (the webapp passes a real ``Path.exists`` check; the
    default treats any non-empty path as present, which is all a unit test
    needs). ``hero_limit`` bounds the hero grid so a huge library returns a sane
    response.
    """
    imaged = [
        t for t in targets
        if (float(t.total_exposure_s or 0.0) > 0.0) or (int(t.n_frames_accepted or 0) > 0)
    ]

    n_subs_kept = sum(int(t.n_frames_accepted or 0) for t in imaged)
    total_integration_s = sum(float(t.total_exposure_s or 0.0) for t in imaged)

    # First light = the earliest target-creation stamp among imaged targets.
    # ``created_utc`` is an ISO-8601 UTC string, so a lexicographic min is a
    # chronological min. Guard against a blank/None stamp on a hand-edited row.
    created_stamps = [t.created_utc for t in imaged if t.created_utc]
    first_light_utc = min(created_stamps) if created_stamps else None

    longest = max(
        imaged, key=lambda t: float(t.total_exposure_s or 0.0), default=None,
    )
    most_imaged = max(
        imaged, key=lambda t: int(t.n_frames_accepted or 0), default=None,
    )

    def with_preview(t: TargetEntry | None) -> SummaryTarget | None:
        if t is None:
            return None
        return _to_summary_target(t, preview_exists(t.last_stack_preview))

    # Heroes: imaged targets that still have a finished picture on disk, ranked
    # by integration (your biggest projects first), capped for a sane response.
    heroes = [
        _to_summary_target(t, True)
        for t in sorted(
            imaged, key=lambda t: float(t.total_exposure_s or 0.0), reverse=True,
        )
        if preview_exists(t.last_stack_preview)
    ][: max(0, hero_limit)]

    return LibrarySummary(
        n_targets_imaged=len(imaged),
        n_subs_kept=n_subs_kept,
        total_integration_s=total_integration_s,
        first_light_utc=first_light_utc,
        longest_target=with_preview(longest),
        most_imaged_target=with_preview(most_imaged),
        heroes=heroes,
    )
