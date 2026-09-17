""""This picture hasn't been stretched yet."

``GET /api/unstretched-pictures`` answers, for the whole library at once: *which
targets are showing a flat linear stack rather than a finished picture?*

**Why a beginner can't see this for themselves.** A stack straight out of the
stacker is *linear*: almost all of its information sits in the bottom few percent
of the range, so on screen it is a dark rectangle with a few stars. The finished
version of the very same data — the one-click Auto look — is the same rectangle
with its histogram stretched. On a Library card at 160 px both are "a dark-ish
square", and nothing on any wall surface says which one you are looking at. So
the owner's own question — *why do some of my pictures look flat?* — had no
answer anywhere in the app, and the honest answer ("that one is still linear,
open it and press Auto") is one the app can work out for itself.

That is not hypothetical. Observer issue
`#903 <https://github.com/JimmyeJones/astrostack/issues/903>`_ found 44 of the
owner's targets in exactly this state at once, after a reprocess-everything run
whose "also auto-edit" switch was off: every restack is saved as a new result and
the newest result is the picture every wall shows, so a finished target silently
went back to its linear master. v0.447.2 stopped that happening *silently*; this
is the standing answer for the state itself, whatever produced it — a target
stacked by hand and never edited, an import that auto-stacked with auto-editing
off, or a restack like that one.

**One definition, two surfaces.** "Finished" means exactly what the reprocess
dialog's warning means — :func:`webapp.finishedpicture.run_is_a_finished_picture`
on the run :func:`~webapp.finishedpicture.displayed_picture_run` picks, the same
functions :func:`webapp.pipeline.reprocess_status` counts with — so the chip and
the dialog can never name different targets. A test pins that.

**And "finished" is about the stored bytes, not about a saved recipe**
*(v0.449.0)*. Saving an edit in the editor writes the recipe and re-renders
nothing, so the card keeps showing the linear autostretch — and the chip used to
*withdraw* at that moment, from the one card where the user's work is invisible
as well as unstretched. It now asks whether something baked the preview, which is
the same fact ``routers.stack._unexported_edit`` reads, so the two stop
contradicting each other about one run.

**It names; it never acts.** Whether a picture is worth finishing is the owner's
call (a linear master is the honest data, and some people export exactly that),
so nothing here writes a recipe and there is no "fix them all" button: the chip
sits on the card, and the one-click Auto is where it has always been, in that
target's own editor.

Cheap on a healthy library: per target, the run rows it already has plus at most
one project-meta read. A target with no stacked picture at all is not named —
there is nothing to stretch yet, and "get some more subs" is a different
sentence that the Target page already says.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps
from webapp.finishedpicture import displayed_picture_run, run_is_a_finished_picture

router = APIRouter(tags=["unstretched"])

#: How many targets the response lists. The count is exact; this only bounds the
#: list, which exists so the wall can chip the individual cards. Generous next to
#: the dashboard notes' three, because every item here is one card's badge rather
#: than a name in a sentence — and the owner had 44 at once.
UNSTRETCHED_MAX = 200


class UnstretchedItem(BaseModel):
    safe: str
    target_name: str
    #: The run whose linear preview is the picture being shown, so a caller can
    #: link straight to it in the editor.
    run_id: int
    #: True when that run carries an edit its owner **saved and never exported**,
    #: so this card is unstretched *and* their work is invisible on it. The two
    #: states want opposite advice — the chip's standing hint says "press Auto",
    #: which is the one thing somebody who already has a saved edit should not be
    #: told, because Auto replaces it. Same `routers.stack._unexported_edit`
    #: decision History, the Gallery and the Target hero use, so a fourth surface
    #: does not invent a fourth opinion. Additive, `False` default — which is what
    #: every ordinary unstretched card is, and what an older frontend reads.
    unexported_edit: bool = False


class UnstretchedResponse(BaseModel):
    #: How many targets are showing an unstretched picture (exact, even when the
    #: list is truncated).
    count: int = 0
    items: list[UnstretchedItem] = []


def scan_unstretched(lib) -> list[UnstretchedItem]:  # noqa: ANN001
    """Every target whose *displayed* picture is a flat linear stack, by name.

    Only the displayed run is judged — the one every wall surface shows. An
    older run left unedited under a finished newer one is not something anyone
    is looking at, and naming it would be noise. A broken project DB is skipped
    exactly as the other cross-target reads skip it, so one corrupt target
    cannot cost the whole answer.
    """
    from seestack.io.project import Project

    from webapp.routers.editor import (
        AUTO_EDIT_BAKED_LOOK_PREFIX,
        EXPORTED_RECIPE_META_PREFIX,
        RECIPE_META_PREFIX,
    )
    from webapp.routers.stack import _unexported_edit

    found: list[UnstretchedItem] = []
    for t in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            runs = list(proj.iter_stack_runs())  # newest first
            shown = displayed_picture_run(
                runs, getattr(t, "cover_stack_run_id", None))
            if shown is None:
                continue  # no picture yet — nothing to stretch
            if run_is_a_finished_picture(proj, shown):
                continue
            # Only now, on the cards that are getting a chip anyway: which
            # *kind* of unstretched is this? Three keyed meta reads on the one
            # run being shown — not per run, and never on a library whose
            # pictures are all finished.
            unexported = _unexported_edit(
                shown.options_json,
                proj.get_meta(f"{RECIPE_META_PREFIX}{shown.id}"),
                proj.get_meta(f"{EXPORTED_RECIPE_META_PREFIX}{shown.id}"),
                proj.get_meta(f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{shown.id}"),
            )
        except Exception:  # noqa: BLE001 — one broken project must not 500 a wall
            continue
        finally:
            if proj is not None:
                proj.close()
        found.append(UnstretchedItem(
            safe=t.safe_name, target_name=t.name, run_id=shown.id,
            unexported_edit=unexported))
    # By name, so the order is stable between polls and between the wall's own
    # sort orders — this list is looked up by `safe`, never read top-down.
    found.sort(key=lambda it: it.target_name)
    return found


@router.get("/api/unstretched-pictures", response_model=UnstretchedResponse)
def get_unstretched(request: Request) -> UnstretchedResponse:
    """Targets whose displayed picture is still a flat linear stack."""
    lib = deps.open_library(request)
    try:
        found = scan_unstretched(lib)
    finally:
        lib.close()
    return UnstretchedResponse(count=len(found), items=found[:UNSTRETCHED_MAX])
