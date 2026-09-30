"""What field of view does *this owner's* telescope actually have?

Every "will it fit in one frame?" verdict and every mosaic panel count is a
comparison against a single-frame field, and that field is a property of the
telescope, not a constant. :mod:`seestack.framing` shipped with the **S50's**
77' × 44' baked in (v0.130.0, 2026-07-16) — eight days before the owner confirmed
an **S30**, whose 150 mm objective gives ~128' × 72'. Read as an S50, the owner's
own targets were told to shoot 15 panels of M 31 where 6 do it, and to shoot a
mosaic of the Veil and IC 5070, which fit whole in one of their frames.

The fix is the one ``AGENTS.md`` §1 "Owner facts" prescribes — derive it, never
assume a model — and the data is already in the project DB: the plate solve wrote
``pixscale_arcsec`` on every solved frame, and the frame carries its own pixel
dimensions. So this is a one-row query per target, not a header read, and it is
the *measured* scale rather than a nominal ``FOCALLEN``.

Cached on ``app.state`` because it is asked from the Target page's object card and
from every Tonight-planner row, and it changes only when the owner buys a
different telescope. A library with nothing solved yet answers ``None``, and every
caller then falls back to exactly today's constant — so a fresh install is
unchanged and this can only ever make an answer more correct.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

from seestack.framing import FrameField, frame_field_from_solve
from seestack.io.library import Library
from seestack.io.project import Project

log = logging.getLogger(__name__)

#: How many targets to ask before giving up. The walk exists to skip targets that
#: have nothing solved yet and — since the consensus below — to gather enough
#: answers that one wrong one can be outvoted. The ceiling is unchanged: a library
#: where nothing answers has always opened all eight.
_MAX_TARGETS_PROBED = 8

#: How many *answering* targets :func:`library_frame_field` stops at.
#:
#: Five is still well inside the eight opens the all-failing path has always paid,
#: and it lets the median below survive two wrong answers rather than one. So the
#: common case — a library whose newest targets are all solved — costs five SQLite
#: opens once per process, where it used to cost one, and the worst case is exactly
#: what it was.
_FIELD_CONSENSUS_TARGETS = 5

#: How many answers a consensus needs before it may overrule the newest one.
#: Three is the smallest number at which a median can outvote a single wrong
#: answer; below it :func:`consensus_field` keeps the pre-consensus behaviour.
_FIELD_CONSENSUS_MIN = 3

#: How long to wait before re-probing after a *failed* answer. A successful one is
#: cached for the life of the process (the telescope does not change mid-session);
#: a failure is retried, because "nothing solved yet" becomes "solved" the first
#: time the owner runs QC.
_RETRY_AFTER_S = 300.0


def _field_from_target(lib: Library, entry: Any) -> FrameField | None:
    """The single-frame field of one target's own solved frames, or ``None``.

    Best-effort throughout — a project that won't open, has nothing solved, or
    whose numbers are out of physical range answers ``None`` and the caller falls
    back — because this feeds an advisory sentence and must never be the reason a
    page 500s.
    """
    try:
        proj = Project.open(lib.target_dir(entry))
    except Exception:  # noqa: BLE001 — advisory path, never break a page
        return None
    try:
        geom = proj.solved_frame_geometry()
    except Exception:  # noqa: BLE001
        geom = None
    finally:
        proj.close()
    return None if geom is None else frame_field_from_solve(*geom)


def target_frame_field(lib: Library, entry: Any) -> FrameField | None:
    """The field of the telescope **this target's own frames** came from.

    :func:`library_frame_field` answers for the library as a whole, as the
    consensus of the few targets it probes, on the reasoning that every install
    this app is for has one telescope. That is right for a question asked *about
    the library* (the Tonight planner badges every catalogue row at once), and it
    is a guess when the question is asked **about one target** — which is what the
    "will it fit in one frame?" line and the mosaic panel count on that target's
    own card are. Where the target itself can answer, it should: AGENTS.md §1's
    rule is to derive the field from the frames rather than assume a model, and
    the target's frames are the nearest frames there are.

    ``None`` when this target has nothing solved yet; the caller then falls back
    to the library-wide answer, which is exactly the previous behaviour.
    """
    return _field_from_target(lib, entry)


def consensus_field(fields: Sequence[FrameField]) -> FrameField | None:
    """The field a handful of probed targets agree on, or ``None`` if none did.

    ``fields`` is in probe order — newest activity first — and holds only the
    targets that answered.

    Until this rule existed the library-wide answer was ``fields[0]``: whichever
    target the walk reached first decided the field for every catalogue row the
    Tonight planner and the week plan badge, and :func:`install_frame_field` then
    kept it for the life of the process. The only thing between one bad plate solve
    and that answer was :func:`~seestack.framing.frame_field_from_solve`'s
    3'–1200' sanity band, which a scale wrong by 2x sails straight through —
    :data:`seestack.io.project.GEOMETRY_SAMPLE_FRAMES` is this same argument made
    *within* one target. The owner's library carries 178 rows with an implausible
    solve (observer issue #965) and the engine has a rule for dropping them from a
    stack, so "the first target that looks sensible" was the weakest link left in a
    chain every other link of which is now a median.

    So: **the median of the answers**, taken as one probed target's own field
    rather than as an average of them — a long edge from one telescope beside a
    short edge from another would describe a frame neither had. The element is
    picked the way :meth:`seestack.io.project.Project.solved_frame_geometry` picks
    its triple, ``(n - 1) // 2`` of a stable sort, so the two rules that answer
    "which telescope?" at the two scales cannot drift apart.

    **Below :data:`_FIELD_CONSENSUS_MIN` answers there is nothing to take a
    consensus of, so the previous answer is kept**: one or two targets cannot
    outvote anything, and preferring the smaller of two fields would be a
    behaviour change bought with nothing. That is what makes this one-sided on a
    real install — on a one-telescope library every probed target reports the same
    field and the median *is* ``fields[0]``, so the answer either does not move or
    moves off a wrong number.

    The cost is a *recency* one, written down so nobody has to re-derive it: an
    owner who changes telescope has one recent target on the new optics and
    several older ones on the old, and the median says "old" until the new one is
    the majority. That is the right trade for a *library-wide* default — the
    question is about the library, not about the newest night — and the surface
    where the distinction bites, a target's own card, does not use this: it asks
    :func:`target_frame_field` about its own frames first.
    """
    if not fields:
        return None
    if len(fields) < _FIELD_CONSENSUS_MIN:
        return fields[0]
    # Sorted from a probe-ordered list and stable, so fields that agree keep their
    # newest-first order and the answer is the same on every call.
    ranked = sorted(fields, key=lambda f: f.long_arcmin)
    return ranked[(len(ranked) - 1) // 2]


def library_frame_field(lib: Library) -> FrameField | None:
    """The single-frame field of the telescope this library's frames came from.

    Walks targets newest-activity-first, collecting each one's own answer until
    :data:`_FIELD_CONSENSUS_TARGETS` of them have answered or
    :data:`_MAX_TARGETS_PROBED` have been tried, and returns what
    :func:`consensus_field` makes of them. ``None`` when nothing in the library is
    solved yet, or when every candidate's numbers are out of range — the caller
    then keeps the module default rather than inventing one.

    Best-effort throughout: a target whose project won't open is skipped, never
    raised, because this feeds an advisory sentence and must never be the reason
    a page 500s.
    """
    entries = lib.list_targets()
    entries.sort(key=lambda e: (e.last_activity_utc or ""), reverse=True)
    answers: list[FrameField] = []
    for entry in entries[:_MAX_TARGETS_PROBED]:
        field = _field_from_target(lib, entry)
        if field is not None:
            answers.append(field)
            if len(answers) >= _FIELD_CONSENSUS_TARGETS:
                break
    agreed = consensus_field(answers)
    if agreed is not None and answers and agreed != answers[0]:
        # Worth a line: the newest target the probe reached disagreed with the
        # library, which is either a telescope change part-way through or a solve
        # this library should not be trusting. It happens once per process.
        log.info(
            "frame field: %d probed targets agree on %.1f' x %.1f', "
            "not the newest one's %.1f' x %.1f'",
            len(answers), agreed.long_arcmin, agreed.short_arcmin,
            answers[0].long_arcmin, answers[0].short_arcmin,
        )
    return agreed


def cached_frame_field(app_state: Any) -> tuple[FrameField | None, bool]:
    """``(cached answer, is a fresh probe due?)`` — without touching the library.

    Split out so a caller that would have to *open* the library to probe can
    decide not to bother: `/api/plan/tonight` is polled, and paying a SQLite open
    per request through the whole cooldown window would be a cost for nothing.
    Calling this marks the probe as attempted when it says one is due, so the
    caller must actually perform it (or forfeit its turn — the next request gets
    one).
    """
    cached = getattr(app_state, "frame_field", None)
    if isinstance(cached, FrameField):
        return cached, False
    last_try = getattr(app_state, "frame_field_probed_at", None)
    now = time.monotonic()
    if isinstance(last_try, float) and (now - last_try) < _RETRY_AFTER_S:
        return None, False
    app_state.frame_field_probed_at = now
    return None, True


def install_frame_field(app_state: Any, lib: Library) -> FrameField | None:
    """:func:`library_frame_field`, cached on ``app.state``.

    ``app_state`` is ``request.app.state``. A successful answer is kept for the
    life of the process; a ``None`` is re-probed at most every
    :data:`_RETRY_AFTER_S` seconds, so an install that solves its first frames
    mid-session starts giving honest framing advice without a restart, while a
    library that will never answer is not re-walked on every request.
    """
    cached, due = cached_frame_field(app_state)
    if cached is not None or not due:
        return cached
    try:
        field = library_frame_field(lib)
    except Exception:  # noqa: BLE001 — advisory only
        log.debug("frame-field probe failed", exc_info=True)
        return None
    if field is not None:
        app_state.frame_field = field
    return field
