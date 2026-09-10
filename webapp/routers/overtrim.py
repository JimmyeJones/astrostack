""""Some of your pictures were trimmed too far by an older version."

``GET /api/over-trimmed-pictures`` answers, for the whole library at once: *which
targets' saved edits still carry a crop the D1 border-trim bugs got wrong?*

**Why it needs its own endpoint.** The per-run verdict
(``…/editor/crop-health``) is the right shape for someone already looking at the
picture — but a saved recipe is replayed on the **Library card, the hero image,
the thumbnail and the share sheet**, not only in the editor, and the owner
processed many mosaics on the affected builds. So the one thing he cannot find
out is *which* targets to re-seed, and the only surface that knew was the one he
had to open per target to reach. That is the gap ``/api/new-subs-waiting`` and
``/api/gallery/unexported-edits`` were both built to close for their own
sentences; this is the third, and it is modelled on the first deliberately, down
to the "one definition, two surfaces" rule below.

**One definition, two surfaces.** "Trimmed too far" means exactly what the
editor's note means — :func:`webapp.routers.editor.crop_health_for_run`, the same
function, on the same saved recipe — so the Dashboard and the editor can never
name different pictures. A test pins that.

**It offers; it never acts.** A small crop may be the owner's own framing
(:mod:`webapp.stale_crop`), so nothing here rewrites a recipe: each named target
links to its own editor, where the one-click re-seed lives and where he can see
the picture before and after.

Deliberately cheap on a healthy library: per target, the newest run's saved
recipe is read from the project DB, and a run with no enabled ``geometry.crop``
answers before any coverage FITS is opened. Only a target that actually carries a
crop costs a strided coverage read.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps

router = APIRouter(tags=["over-trimmed"])

#: How many targets the response names. The count is exact; this only bounds the
#: list, which exists so a single target can be linked directly.
OVER_TRIMMED_MAX = 12


class OverTrimmedItem(BaseModel):
    safe: str
    target_name: str
    #: The run whose saved recipe carries the bad crop.
    run_id: int
    #: Share of the canvas that recipe keeps (0..1) — the sliver.
    stored_keep_fraction: float | None = None
    #: Share the current border rule would keep, so the note can say what
    #: re-seeding buys back.
    suggested_keep_fraction: float | None = None


class OverTrimmedResponse(BaseModel):
    #: How many targets are affected (exact, even when the list is truncated).
    count: int = 0
    items: list[OverTrimmedItem] = []


def scan_over_trimmed(lib) -> list[OverTrimmedItem]:  # noqa: ANN001
    """Every target whose newest edited picture still carries an older build's
    over-trim — worst (smallest surviving sliver) first.

    Only the **newest** run per target is judged: that is the picture every other
    surface shows, and offering to re-seed a superseded run's recipe would be
    noise. A broken project DB is skipped exactly as the other cross-target reads
    skip it, so one corrupt target cannot cost the whole answer."""
    from seestack.io.project import Project
    from webapp.routers.editor import crop_health_for_run

    found: list[OverTrimmedItem] = []
    for t in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            run = next(iter(proj.iter_stack_runs()), None)  # newest first
            if run is None:
                continue
            health = crop_health_for_run(proj, run)
        except Exception:  # noqa: BLE001 — one broken project must not 500 the note
            continue
        finally:
            if proj is not None:
                proj.close()
        if not health.stale:
            continue
        found.append(OverTrimmedItem(
            safe=t.safe_name,
            target_name=t.name,
            run_id=run.id,
            stored_keep_fraction=health.stored_keep_fraction,
            suggested_keep_fraction=health.suggested_keep_fraction,
        ))
    # Worst first — the picture that lost the most — with the name as a tiebreak
    # so the order is stable between polls.
    found.sort(key=lambda it: (it.stored_keep_fraction if it.stored_keep_fraction
                               is not None else 1.0, it.target_name))
    return found


@router.get("/api/over-trimmed-pictures", response_model=OverTrimmedResponse)
def get_over_trimmed(request: Request) -> OverTrimmedResponse:
    """Targets whose saved edit still carries an older version's over-trim."""
    lib = deps.open_library(request)
    try:
        found = scan_over_trimmed(lib)
    finally:
        lib.close()
    return OverTrimmedResponse(count=len(found), items=found[:OVER_TRIMMED_MAX])
