""""You've shot more of this than the picture has in it."

``GET /api/new-subs-waiting`` answers, for the whole library at once: *which
targets have accepted, plate-solved subs their newest stack does not contain?* —
i.e. whose current picture is no longer made of all the light they own.

**Why it needs its own endpoint.** The per-target version of this note has
shipped since v0.90.0 (``countNewSubsSinceStack`` on the Target page), and it is
the right shape for someone who is already looking at the picture that is out of
date. But the owner this app is for shoots **many targets across many nights
with auto-stack off** (AGENTS.md §1), so after a night's capture the one thing
they cannot find out is *which* targets to open — the only surface that knows is
the one you have to visit per target to reach. That is the same gap
``/api/gallery/unexported-edits`` was built to close for saved-but-unexported
edits, and this is its sibling for un-stacked light.

**One bar, and the picture on the wall is the one measured.** A sub counts
only if a re-stack would actually combine it — accepted **and** solved — and the
run it is measured against is the genuine stack behind the target's **displayed**
picture: the pinned cover if there is one, else the newest run with a preview,
resolved through an editor export to the stack it was rendered from (an export
or a channel combine does not reset the clock, via the shared
:func:`webapp.run_options.run_has_reusable_options` the Target page's
``reusable`` flag already comes from). It used to be the newest genuine run
regardless of what was shown, and after a Combine that is a one-night stack
carried in with its own timestamp — so the deep target the Combine existed to
make deeper was the one target this note could never name
(:func:`new_light_since_picture`). That same run also says whether "solved" is part of the bar at all:
see :func:`webapp.run_options.run_places_unsolved_subs`.

**The Target page asks the same question of one target, through the same rule**
(``GET /api/targets/{safe}/new-light``, :func:`get_target_new_light`). It used to
spell the rule itself, in TypeScript — *"accepted + solved frames captured after
the newest ``reusable`` run"* — and that is two readings away from this one: the
clock instead of membership, and the newest genuine run instead of the picture on
the wall. On a Combined target both diverge at once (the newest genuine run is the
carried one-night stack; the picture is the merge's pin), so this endpoint named
the target on the Dashboard while the target's own page said nothing. One
function, so the roll-up and the line beside the picture cannot disagree.

**What stays deliberately separate is the *reason*, not the number.** The sibling
card (``GET …/restored-subs``, :mod:`seestack.restorednudge`) says *"some of your
subs came back after this picture was made"*, which is the shape
:func:`seestack.solve.runner.reconcile_bad_solve_frames` creates by design and the
one a capture-time test structurally cannot see. Beside one picture that reason is
worth saying, so the page gives that card the slot whenever a restoration is the
*whole* of the shortfall, and uses this wider number when there is more missing
than came back — naming only the restorations would then understate what a
re-stack folds in. A test pins the roll-up against both of the Target page's own
numbers.

**It offers; it never acts.** Re-stacking is hours of CPU on a NAS, so this
endpoint is read-only and there is no batch button *here*: each named target
links to its own Stack form, where the estimate and the settings live, and the
one library-wide offer the note carries is a **link** to Settings → Maintenance,
where the confirm dialog and the counts are.

**One definition, four surfaces now.** :func:`new_light_since_picture` is the
rule; since v0.492.0 the "Bring my pictures up to date" reprocess scope
(``new_light_only``) and the counts its dialog quotes ask it too, and the Target
page's own note asks it through :func:`get_target_new_light` — so the note that
names the targets, the line beside the picture and the batch that restacks them
cannot be about different targets.

Deliberately cheap: per target, one ``stack_runs`` read (a target's run rows are
a few dozen at most; the owner's whole library holds under a thousand), and —
only for a target that has a picture — a single indexed ``COUNT``
(:meth:`seestack.io.project.Project.count_light_missing_from_run`). A target
that has never been stacked costs the first read alone and is skipped: this note
is about a picture that has fallen behind, and "you have never stacked this" is a
different sentence that other surfaces already say.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps
from webapp.finishedpicture import displayed_picture_run
from webapp.run_options import (
    derived_from_run_id,
    run_has_reusable_options,
    run_places_unsolved_subs,
)

router = APIRouter(tags=["new-subs"])

#: How many targets the response names. The count is exact; this only bounds the
#: list, which exists so a single target can be linked directly.
NEW_SUBS_WAITING_MAX = 12


class NewSubsWaitingItem(BaseModel):
    safe: str
    target_name: str
    #: The genuine stack run behind the displayed picture — the picture that has
    #: fallen behind.
    run_id: int | None = None
    stacked_utc: str = ""
    #: How many subs that picture combined, so the note can say what the
    #: re-stack would grow from as well as by.
    n_frames_used: int = 0
    #: Accepted + solved subs this picture does not contain — captured after
    #: ``stacked_utc``, or set aside while it was made and since put back.
    n_new_subs: int = 0


class NewLightOut(BaseModel):
    """The one-target reading of the same question, for the Target page's own
    *"your picture doesn't include everything you've shot"* note.

    Exactly :func:`new_light_since_picture`'s answer, which is the point: the
    Dashboard note, "Bring my pictures up to date" and the line beside the
    picture itself now ask one function, so the library-wide roll-up can never
    name a target whose own page says there is nothing waiting. That is the bug
    this exists to close — the page counted by *capture time* against the *newest
    reusable* run, and on a Combined target with the merge's pin neither half of
    that is the picture on the wall.

    Shaped like the sibling nudges the same page draws (``RestoredSubsOut``,
    ``RestackGainOut``): the run measured, what it was made of, and the number.
    """

    #: The genuine stack run behind the displayed picture — the one measured.
    run_id: int
    #: When that run stacked, so the note can date the picture it names.
    timestamp_utc: str
    #: How many subs it combined, i.e. what a re-stack would grow *from*.
    n_frames_used: int
    #: Accepted + located subs that picture does not contain.
    n_new_subs: int


class NewSubsWaitingResponse(BaseModel):
    #: How many targets have new light waiting (exact, even when the list is
    #: truncated to :data:`NEW_SUBS_WAITING_MAX`).
    count: int = 0
    #: Their new subs summed, so one sentence can carry the whole library's
    #: backlog without naming every target.
    total_new_subs: int = 0
    items: list[NewSubsWaitingItem] = []


def picture_measured_for_new_light(runs, cover_stack_run_id=None):  # noqa: ANN001
    """The genuine stack run a target's **displayed** picture is made of, or
    ``None`` when the target has no genuine stack at all.

    ``runs`` is the target's stack runs **newest first**. The displayed picture
    is :func:`webapp.finishedpicture.displayed_picture_run`'s answer — the pinned
    cover, else the newest run with a preview — and it is resolved to a *stack*:

    * a genuine run is itself;
    * an editor export is the run it was rendered from (``derived_from``), or,
      for an export recorded before that field existed, the newest genuine run
      not newer than it — an export re-renders pixels an earlier stack
      combined, and never folds in a sub;
    * a target with no preview at all (a run whose preview was pruned, a
      never-previewed batch) falls back to the newest genuine run, which is the
      answer every caller had before the displayed picture was consulted.

    Why the displayed picture and not the newest genuine run: after a Combine
    the newest genuine run is the one-night stack carried in, with its own
    (recent) timestamp and a subset of the target's subs, while the picture the
    merge pinned to keep on the wall is the older, deeper one. Measuring the
    newest run answered "0 missing" for the one target a Combine exists to
    deepen. The same reading was wrong for any pinned cover: the note is about
    the picture the owner is looking at, so that is the one measured.
    """
    runs = list(runs)
    shown = displayed_picture_run(runs, cover_stack_run_id)
    if shown is None:
        return next((r for r in runs
                     if run_has_reusable_options(r.options_json)), None)
    if run_has_reusable_options(shown.options_json):
        return shown
    origin = derived_from_run_id(shown.options_json)
    if origin is not None:
        source = next((r for r in runs
                       if r.id == origin and run_has_reusable_options(r.options_json)),
                      None)
        if source is not None:
            return source
    older = runs[runs.index(shown) + 1:]
    return next((r for r in older if run_has_reusable_options(r.options_json)), None)


def new_light_since_picture(proj, runs, cover_stack_run_id=None):  # noqa: ANN001
    """``(the picture that has fallen behind, how many subs it is missing)``.

    **This is the one definition of "this target has new light."** It is a named
    function rather than three lines inlined below because three surfaces now ask
    it: this note, the "Bring my pictures up to date" reprocess scope
    (:func:`webapp.pipeline.submit_reprocess_all`), and the counts that scope's
    confirm dialog quotes (:func:`webapp.pipeline.reprocess_status`). A second
    spelling of the rule is exactly how two of them would end up naming different
    targets — the drift ``webapp/run_options.py`` was created to undo.

    **"New light" means light this picture does not contain, not light shot since
    it was made** — the two diverge, and the narrower reading made this note and
    the batch it scopes blind to a whole class of shortfall.
    :meth:`~seestack.io.project.Project.count_light_missing_from_stack` owns the
    rule: a sub the app set aside by itself and has since put back (a streak that
    turned out to be a tracked object, a grade re-run on a bigger population, a
    file that reappeared, a wrong-scale plate solve given its one retry) was shot
    on the very night the picture is made of, so a capture-time test cannot see
    it — and it is missing from that picture just the same. The per-target card
    that says so (:mod:`seestack.restorednudge`, ``GET …/restored-subs``) has said
    since it was written that this nudge "cannot see this case at all"; now it
    can, which is what lets the one library-wide offer reach those targets instead
    of sending the owner through them one at a time.

    **The run measured is the one behind the displayed picture**
    (:func:`picture_measured_for_new_light`), and **"missing" is membership
    where the run recorded which subs it was offered**
    (:meth:`~seestack.io.project.Project.count_light_missing_from_run`), the
    capture-time rule only where it did not. Both halves exist for the same
    shape: a Combine carries a one-night stack into the deep target with its own
    recent timestamp, the merge pins the deep target's own picture so the wall
    keeps showing it, and every sub of the other night was shot *before* that
    picture and never restored — so measured by the newest run and by the clock,
    the one target the Combine existed to deepen answered "nothing missing", the
    Dashboard note stayed silent, and "Bring my pictures up to date" skipped it.
    A carried night, a set-aside night and a pinned older cover are the same
    failure with different names, and they are the cases the tests pin.

    ``runs`` is the target's stack runs **newest first**; ``cover_stack_run_id``
    is the target's pinned cover, if any (the registry row's own value — pass it
    when you have it, so the picture measured is the one shown). ``(None, 0)``
    when there is no genuine stack at all — "you have never stacked this" is a
    different sentence other surfaces already say, and there is nothing to
    count "after".

    **The "and solved" half of the bar has one exception, and the run itself says
    whether it applies.** Since v0.482.0 the stacker can place a sub *no plate
    solve could locate*, by matching its star patterns to the reference — that is
    what ``StackOptions.star_match_unsolved`` is for, on a faint or star-poor field
    where ASTAP fails on most subs and the picture is the handful that happened to
    solve. It is off by default and hand-set, so for the owner's runs the solved
    bar is exactly right; on an install that turns it on, a target whose whole
    shortfall is un-located subs read as **nothing waiting** and this note could
    never name it. So the bar is taken from the run being measured against
    (:func:`webapp.run_options.run_places_unsolved_subs`) — the run a reprocess
    reuses the settings of, i.e. the settings the re-stack would in fact use.
    """
    runs = list(runs)
    if cover_stack_run_id is not None:
        from seestack.coverpin import PIN_REASON_KEPT_FINISHED, app_pin_reason

        # A pin the bulk restack placed to keep a hand-finished picture on the
        # wall while the deeper run went into History. The owner has not chosen
        # that picture over the deeper one — the app kept it for him — so the
        # light to measure is what the deeper, newest picture is missing:
        # otherwise every batch would re-name the target, restack it again, keep
        # the picture again, and never stop. The cover nudge on the Target page
        # is what offers him the deeper run.
        if app_pin_reason(proj, cover_stack_run_id) == PIN_REASON_KEPT_FINISHED:
            cover_stack_run_id = None
    run = picture_measured_for_new_light(runs, cover_stack_run_id)
    if run is None:
        return None, 0
    return run, proj.count_light_missing_from_run(
        run, include_unsolved=run_places_unsolved_subs(run.options_json))


def scan_new_subs_waiting(lib) -> list[NewSubsWaitingItem]:  # noqa: ANN001
    """Every target whose newest genuine stack is missing accepted, solved subs
    the target already has — most waiting first.

    A broken project DB is skipped exactly as the other cross-target reads skip
    it, so one corrupt target cannot cost the whole answer.
    """
    from seestack.io.project import Project

    found: list[NewSubsWaitingItem] = []
    for t in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            run, n_new = new_light_since_picture(
                proj, proj.iter_stack_runs(),
                getattr(t, "cover_stack_run_id", None))
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


@router.get("/api/targets/{safe}/new-light", response_model=NewLightOut | None)
def get_target_new_light(safe: str, request: Request) -> NewLightOut | None:
    """**"Your picture doesn't include everything you've shot."** One target.

    The per-target half of this module, and the reason it lives here rather than
    beside the Target page's other nudges in :mod:`webapp.routers.targets`:
    :func:`new_light_since_picture` is *the* definition of "this target has new
    light", and a second spelling of it is exactly how two surfaces end up
    answering one question differently. The page used to spell it itself, in
    TypeScript, as "accepted + solved frames captured after the newest
    ``reusable`` run" — so a Combined target, whose newest genuine run is the
    carried one-night stack and whose picture is the merge's pin, was named by
    the Dashboard while its own page said nothing.

    ``null`` when there is nothing to say: no genuine stack to measure against
    (*"you have never stacked this"* is another surface's sentence), or a picture
    that already contains every sub the target has — which is the common case.
    Read-only; it never starts a stack. Cheap by the same accounting as the
    library-wide scan, for one target: one ``stack_runs`` read and one indexed
    ``COUNT``.
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        entry = lib.find_target(safe)
        run, n_new = new_light_since_picture(
            proj, proj.iter_stack_runs(),
            getattr(entry, "cover_stack_run_id", None))
    finally:
        proj.close()
        lib.close()
    if run is None or n_new <= 0 or run.id is None:
        return None
    return NewLightOut(
        run_id=run.id,
        timestamp_utc=run.timestamp_utc,
        n_frames_used=run.n_frames_used or 0,
        n_new_subs=n_new,
    )
