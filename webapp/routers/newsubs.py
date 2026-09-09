""""You've shot more of this since the picture was made."

``GET /api/new-subs-waiting`` answers, for the whole library at once: *which
targets have accepted, plate-solved subs that arrived after their newest stack
ran?* — i.e. whose current picture is no longer made of all the light they own.

**Why it needs its own endpoint.** The per-target version of this note has
shipped since v0.90.0 (``countNewSubsSinceStack`` on the Target page), and it is
the right shape for someone who is already looking at the picture that is out of
date. But the owner this app is for shoots **many targets across many nights
with auto-stack off** (AGENTS.md §1), so after a night's capture the one thing
they cannot find out is *which* targets to open — the only surface that knows is
the one you have to visit per target to reach. That is the same gap
``/api/gallery/unexported-edits`` was built to close for saved-but-unexported
edits, and this is its sibling for un-stacked light.

**One definition, two surfaces.** "New" means exactly what the Target page's
nudge means — accepted **and** solved, captured after the newest *genuine* stack
run (an editor export or a channel combine does not reset the clock, via the
shared :func:`webapp.run_options.run_has_reusable_options` the Target page's
``reusable`` flag already comes from). So the Dashboard and the Target page can
never name different numbers for one target; a test pins that.

**It offers; it never acts.** Re-stacking is hours of CPU on a NAS, so this is
read-only and there is no batch button here: each named target links to its own
Stack form, where the estimate and the settings live.

Deliberately cheap: per target, one ``stack_runs`` read that stops at the newest
genuine row, and — only for a target that has one — a single indexed ``COUNT``
(:meth:`seestack.io.project.Project.count_accepted_solved_after`). A target that
has never been stacked costs the first read alone and is skipped: this note is
about a picture that has fallen behind, and "you have never stacked this" is a
different sentence that other surfaces already say.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps
from webapp.run_options import run_has_reusable_options

router = APIRouter(tags=["new-subs"])

#: How many targets the response names. The count is exact; this only bounds the
#: list, which exists so a single target can be linked directly.
NEW_SUBS_WAITING_MAX = 12


class NewSubsWaitingItem(BaseModel):
    safe: str
    target_name: str
    #: The newest genuine stack run — the picture that has fallen behind.
    run_id: int | None = None
    stacked_utc: str = ""
    #: How many subs that picture combined, so the note can say what the
    #: re-stack would grow from as well as by.
    n_frames_used: int = 0
    #: Accepted + solved subs captured after ``stacked_utc``.
    n_new_subs: int = 0


class NewSubsWaitingResponse(BaseModel):
    #: How many targets have new light waiting (exact, even when the list is
    #: truncated to :data:`NEW_SUBS_WAITING_MAX`).
    count: int = 0
    #: Their new subs summed, so one sentence can carry the whole library's
    #: backlog without naming every target.
    total_new_subs: int = 0
    items: list[NewSubsWaitingItem] = []


def scan_new_subs_waiting(lib) -> list[NewSubsWaitingItem]:  # noqa: ANN001
    """Every target whose newest genuine stack predates subs it has since
    accepted and solved — most waiting first.

    A broken project DB is skipped exactly as the other cross-target reads skip
    it, so one corrupt target cannot cost the whole answer.
    """
    from seestack.io.project import Project

    found: list[NewSubsWaitingItem] = []
    for t in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            # Newest first, so this normally stops on the first row. A target
            # whose newest runs are all editor exports walks past them, which is
            # the point: an export is a re-render of an existing picture and
            # never folds in a sub.
            run = next(
                (r for r in proj.iter_stack_runs()
                 if run_has_reusable_options(r.options_json)),
                None,
            )
            # Never stacked at all → not this note's sentence (see the module
            # docstring), and nothing to count "after".
            n_new = (proj.count_accepted_solved_after(run.timestamp_utc)
                     if run is not None else 0)
        except Exception:  # noqa: BLE001 — one broken project must not 500 the note
            continue
        finally:
            if proj is not None:
                proj.close()
        if run is None or n_new <= 0:
            continue
        found.append(NewSubsWaitingItem(
            safe=t.safe_name,
            target_name=t.name,
            run_id=run.id,
            stacked_utc=run.timestamp_utc,
            n_frames_used=run.n_frames_used or 0,
            n_new_subs=n_new,
        ))
    # Most waiting first — the target where a re-stack buys the most — with the
    # name as a tiebreak so the order is stable between polls.
    found.sort(key=lambda it: (-it.n_new_subs, it.target_name))
    return found


@router.get("/api/new-subs-waiting", response_model=NewSubsWaitingResponse)
def get_new_subs_waiting(request: Request) -> NewSubsWaitingResponse:
    """Targets whose picture no longer includes every sub they have."""
    lib = deps.open_library(request)
    try:
        found = scan_new_subs_waiting(lib)
    finally:
        lib.close()
    return NewSubsWaitingResponse(
        count=len(found),
        total_new_subs=sum(it.n_new_subs for it in found),
        items=found[:NEW_SUBS_WAITING_MAX],
    )
