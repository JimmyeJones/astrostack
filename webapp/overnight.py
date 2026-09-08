"""What the app *did* while nobody was watching — the second half of the
"Last night" card.

The Dashboard's "Last night" recap already answers *what the sky gave me*: how
many subs came in across every target, how many were kept, why the rest were set
aside. It says nothing about what the walk-away pipeline then **did** with them,
which is the other half of the question an owner wakes up with — did it make a
picture, and is anything stuck? Today that answer is scattered: a new stack shows
up as one more unremarked tile in the "Recent stacks" strip (which looks the same
whether it was made overnight or last March), and a target the auto-stack *held*
back is explained only on the Jobs page, a screen a beginner has no reason to
open.

This module folds those two facts into the recap that is already on the screen,
rather than adding a card to a Dashboard the owner has called busy (AGENTS.md §1
— "prefer a consolidation over a new card"):

* :func:`new_pictures_since` — the pictures the app produced since the night's
  first sub landed, one line per target, each with the frame count of that
  target's previous picture so the card can say *deeper than before* rather than
  just *new*.
* :func:`needs_a_look` — the targets the hands-off scan deliberately **held**,
  read from the summary the scan already records: subs whose files were missing
  (``auto_stack_held_unreadable``) and stacks too thin to publish
  (``auto_stack_held_thin``). Both holds are self-clearing — the next scan stacks
  the target the moment the reason goes away — so this reports the newest scan
  only, exactly like ``/api/targets/{safe}/autostack-hold``, and needs no state
  of its own to go stale.

Everything here is pure: it takes rows that another layer has already read and
returns dataclasses, so the aggregation is unit-testable without a library, a job
manager or a request. Stamps are compared with
:func:`seestack.activity_calendar.parse_utc` rather than as strings, because the
app writes UTC in more than one shape (``…Z`` from the job manager, a full
offset from the stacker) and lexicographic order across those two is a lie.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from seestack.activity_calendar import parse_utc


@dataclass(frozen=True)
class NewPicture:
    """One target's newest picture made inside the window."""

    safe: str
    name: str
    run_id: int
    when_utc: str
    n_frames: int
    #: Frames used by that target's newest picture from *before* the window, or
    #: ``None`` when this is its first. Lets the caller say "deeper than before
    #: (120 subs, was 78)" without a second read, and say nothing when there is
    #: nothing to compare against.
    previous_frames: int | None


@dataclass(frozen=True)
class NeedsLook:
    """One target the newest hands-off scan held back, and why."""

    safe: str
    name: str
    #: ``"missing_files"`` — some of its subs had no file on disk, so stacking
    #: now would publish a thinner picture than the one that already stands.
    #: ``"too_thin"`` — too few located subs to make anything but speckle.
    kind: str
    #: Subs the hold could actually have used (readable / located).
    n_frames: int
    #: The other side of the comparison: how many subs were missing
    #: (``missing_files``), or the minimum the setting asks for (``too_thin``).
    n_other: int


def new_pictures_since(
    runs: Iterable[Any], since_utc: str | None,
) -> list[NewPicture]:
    """The pictures made since ``since_utc``, newest first, one per target.

    ``runs`` is any iterable of stack-run rows carrying ``safe``,
    ``target_name``, ``run_id``, ``timestamp_utc``, ``n_frames_used`` and
    ``is_genuine`` — i.e. the roll-up the Dashboard already builds
    (:class:`webapp.routers.stats.RecentStack`), in any order.

    **One line per target, not one per run.** A walk-away night that re-stacked
    the same target twice (a scan that fired, then a second scan after more subs
    landed) produced *one* new picture as far as the owner is concerned — the
    latest one — and a card that listed both would read as though the app had
    thrashed. Non-genuine runs (editor exports, channel combines) are skipped
    for the same reason: exporting a finished edit is not the app making a new
    picture overnight, and counting it would double every target the auto-edit
    also touched.

    ``previous_frames`` is the frame count of that target's newest genuine run
    from *before* the window — the picture this one replaced — so the caller can
    tell "deeper than before" from "first picture" without re-reading anything.
    """
    since = parse_utc(since_utc) if since_utc else None
    if since is None:
        return []
    newest: dict[str, tuple[Any, Any]] = {}   # safe -> (when, row) inside window
    previous: dict[str, tuple[Any, int]] = {}  # safe -> (when, frames) before it
    for row in runs:
        if not getattr(row, "is_genuine", True):
            continue
        when = parse_utc(getattr(row, "timestamp_utc", "") or "")
        if when is None:
            continue
        safe = row.safe
        if when >= since:
            best = newest.get(safe)
            if best is None or when > best[0]:
                newest[safe] = (when, row)
        else:
            prev = previous.get(safe)
            if prev is None or when > prev[0]:
                previous[safe] = (when, int(row.n_frames_used or 0))
    out = [
        NewPicture(
            safe=safe,
            name=getattr(row, "target_name", safe) or safe,
            run_id=int(row.run_id),
            when_utc=row.timestamp_utc,
            n_frames=int(row.n_frames_used or 0),
            previous_frames=(previous[safe][1] if safe in previous else None),
        )
        for safe, (_when, row) in newest.items()
    ]
    out.sort(key=lambda p: p.when_utc, reverse=True)
    return out


def newest_scan_summary(jobs: Sequence[Any]) -> dict | None:
    """The result summary of the most recent *finished* hands-off scan, or None.

    ``jobs`` is the job manager's own newest-first listing. Only the newest
    finished ``pipeline`` job counts: both holds below are self-clearing, so a
    hold the next scan resolved is history, not news — the same discipline
    ``/api/targets/{safe}/autostack-hold`` already applies (a scan that reported
    no hold ends the search rather than falling through to an older one that
    did).
    """
    for job in jobs:
        if getattr(job, "kind", None) != "pipeline" or getattr(job, "state", None) != "done":
            continue
        result = getattr(job, "result", None)
        return result if isinstance(result, dict) else {}
    return None


def needs_a_look(
    summary: dict | None,
    name_for: Callable[[str], str] | None = None,
) -> list[NeedsLook]:
    """Targets the newest scan held back, missing-files first.

    ``summary`` is that scan's result dict (see :func:`newest_scan_summary`);
    ``name_for`` maps a target's safe name to its display name, falling back to
    the safe name for a target that has since been removed.

    Missing files lead because they are the one kind the app cannot resolve on
    its own: a too-thin hold clears itself the moment more subs solve, whereas
    an unreadable sub means a storage problem the owner has to go and look at
    (AGENTS.md §1, the walk-away degradation family). A target that somehow
    appears under both is reported once, as the missing-files hold.
    """
    if not isinstance(summary, dict):
        return []
    named = name_for or (lambda safe: safe)
    out: list[NeedsLook] = []
    seen: set[str] = set()
    for entry in _entries(summary.get("auto_stack_held_unreadable")):
        safe = entry.get("target")
        if not isinstance(safe, str) or safe in seen:
            continue
        seen.add(safe)
        out.append(NeedsLook(
            safe=safe, name=named(safe) or safe, kind="missing_files",
            n_frames=_count(entry.get("readable")),
            n_other=_count(entry.get("unreadable")),
        ))
    for entry in _entries(summary.get("auto_stack_held_thin")):
        safe = entry.get("target")
        if not isinstance(safe, str) or safe in seen:
            continue
        seen.add(safe)
        out.append(NeedsLook(
            safe=safe, name=named(safe) or safe, kind="too_thin",
            n_frames=_count(entry.get("frames")),
            n_other=_count(entry.get("min")),
        ))
    return out


def _entries(value: Any) -> list[dict]:
    """The dict rows of a summary list, tolerating an absent or odd value — a
    job record is JSON the app wrote, but it is also *history*, so a shape an
    older build wrote must degrade to "nothing to say" rather than a 500."""
    if not isinstance(value, list):
        return []
    return [e for e in value if isinstance(e, dict)]


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
