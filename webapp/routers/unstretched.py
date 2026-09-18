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

**And it answers a second question about the same card: is that picture deep
enough?** *(v0.450.0.)* A different question from stretch — a stretch is a
decision, a depth is a fact about the light — and the one the Library wall was
*least* able to answer, because the only number on the card is the target's
total frame count. On a mosaic that total is the flattering one this app has now
corrected in five other places: 900 subs over a 12×8 raster is about nine on
each patch of sky, and thirty over a 3×3 is three. The Gallery card of the very
same run already turns its frame badge orange
(``frontend/src/components/target/thinStack.ts``); the wall said nothing at all,
so a picture that is one sub deep everywhere — the owner's "gibberish" case —
sat there looking like any other. The threshold is
:mod:`webapp.thinpicture`, a guarded hand-mirror of that module's, and the two
numbers the sentence needs travel on the wire so the chip's hint and the
Gallery's tooltip are one string written once.

Both halves ride one scan because they are read by one wall, on one visit:
a second endpoint would open every project a second time.

Cheap on a healthy library: per target, the run rows it already has, one
``LIMIT 1`` frame row for the native sub shape, and at most one project-meta
read. A target with no stacked picture at all is named by neither half — there
is nothing to stretch and nothing to be thin, and "get some more subs" is a
different sentence that the Target page already says.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps
from webapp.finishedpicture import displayed_picture_run, run_is_a_finished_picture

router = APIRouter(tags=["unstretched"])

#: How many targets each of the response's two lists names. Both counts are
#: exact; this only bounds the lists, which exist so the wall can chip the
#: individual cards. Generous next to the dashboard notes' three, because every
#: item here is one card's badge rather than a name in a sentence — and the owner
#: had 44 unstretched at once.
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


class ThinPictureItem(BaseModel):
    """One target whose *displayed* picture is only a few subs deep on any one
    patch of sky — the other thing a Library card could not say about itself."""

    safe: str
    target_name: str
    run_id: int
    #: The run's combined frame count and how many single-frame field-fulls of
    #: sky its canvas covers. Both, rather than the quotient, because the wall
    #: asks ``thinStackWarning`` for its sentence and that function names *both*
    #: figures on a mosaic ("your 30 subs are spread across about 9 fields of
    #: sky, so a typical part …"). Serving only the depth would make the wall write a
    #: second sentence about a picture the Gallery already has one for.
    n_frames_used: int = 0
    #: ``None`` on a single field and whenever the shape can't be measured — the
    #: same "no scaling" answer every other consumer of this figure reads.
    field_fulls: float | None = None


class UnstretchedResponse(BaseModel):
    #: How many targets are showing an unstretched picture (exact, even when the
    #: list is truncated).
    count: int = 0
    items: list[UnstretchedItem] = []
    #: How many targets are showing a thin picture (exact, even when the list is
    #: truncated). Additive with a ``0``/``[]`` default, so an older frontend
    #: ignores them and an older backend that omits them reads as "nothing to
    #: chip" — which is exactly the wall's behaviour before v0.450.0.
    thin_count: int = 0
    thin: list[ThinPictureItem] = []


def scan_wall_chips(lib) -> tuple[list[UnstretchedItem], list[ThinPictureItem]]:  # noqa: ANN001
    """What each target's *displayed* picture needs said about it, by name:
    ``(unstretched, thin)``.

    Only the displayed run is judged — the one every wall surface shows. An
    older run left unedited under a finished newer one is not something anyone
    is looking at, and naming it would be noise. A broken project DB is skipped
    exactly as the other cross-target reads skip it, so one corrupt target
    cannot cost the whole answer.

    **The two lists are not exclusive and neither is a subset of the other.**
    Stretch is a decision somebody has or hasn't made; depth is a fact about the
    light. A finished picture can be one sub deep — that is precisely the case
    worth naming, because it is the one that *looks* like a picture — and an
    unstretched one can be two hundred deep. So the depth is measured on every
    target that has a picture at all, including the ones this scan has already
    decided are finished.
    """
    from seestack.io.project import Project
    from webapp.derived_light import stacking_field_fulls
    from webapp.field_fulls import native_frame_shape
    from webapp.routers.editor import (
        AUTO_EDIT_BAKED_LOOK_PREFIX,
        EXPORTED_RECIPE_META_PREFIX,
        RECIPE_META_PREFIX,
    )
    from webapp.routers.stack import _unexported_edit
    from webapp.thinpicture import picture_is_thin

    found: list[UnstretchedItem] = []
    thin: list[ThinPictureItem] = []
    for t in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            runs = list(proj.iter_stack_runs())  # newest first
            shown = displayed_picture_run(
                runs, getattr(t, "cover_stack_run_id", None))
            if shown is None:
                continue  # no picture yet — nothing to stretch, nothing to be thin
            # Depth first, because it is asked of *every* target with a picture.
            # ``stacking_field_fulls`` rather than the run's own canvas: a
            # finished picture is a crop (the editor seeds Auto, Auto trims), and
            # measuring a crop against itself reads it as deeper than its pixels
            # are — the direction that tells a beginner to stop shooting.
            #
            # The raw attribute goes to the decision, never a ``or 0`` of it: a
            # count that is absent is not a count of nothing, and a chip that
            # appeared because a number was *missing* would accuse a whole wall
            # — the same rule the rest of this endpoint's fields follow. The
            # schema says ``NOT NULL``, so this is the belt to that braces.
            n_used_raw = getattr(shown, "n_frames_used", None)
            fulls = stacking_field_fulls(
                shown, {r.id: r for r in runs}, native_frame_shape(proj))
            is_thin = picture_is_thin(n_used_raw, fulls)
            n_used = int(n_used_raw or 0)
            unstretched = not run_is_a_finished_picture(proj, shown)
            unexported = False
            if unstretched:
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
        if unstretched:
            found.append(UnstretchedItem(
                safe=t.safe_name, target_name=t.name, run_id=shown.id,
                unexported_edit=unexported))
        if is_thin:
            thin.append(ThinPictureItem(
                safe=t.safe_name, target_name=t.name, run_id=shown.id,
                n_frames_used=n_used, field_fulls=fulls))
    # By name, so the order is stable between polls and between the wall's own
    # sort orders — these lists are looked up by `safe`, never read top-down.
    found.sort(key=lambda it: it.target_name)
    thin.sort(key=lambda it: it.target_name)
    return found, thin


def scan_unstretched(lib) -> list[UnstretchedItem]:  # noqa: ANN001
    """Just the unstretched half of :func:`scan_wall_chips`, for a caller that
    only wants that question."""
    return scan_wall_chips(lib)[0]


@router.get("/api/unstretched-pictures", response_model=UnstretchedResponse)
def get_unstretched(request: Request) -> UnstretchedResponse:
    """Targets whose displayed picture is still a flat linear stack, and targets
    whose displayed picture is only a few subs deep."""
    lib = deps.open_library(request)
    try:
        found, thin = scan_wall_chips(lib)
    finally:
        lib.close()
    return UnstretchedResponse(
        count=len(found), items=found[:UNSTRETCHED_MAX],
        thin_count=len(thin), thin=thin[:UNSTRETCHED_MAX])
