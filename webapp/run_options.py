"""One answer to "what settings did this stack run use?".

A ``stack_runs`` row carries its settings as ``options_json``, and three
surfaces ask the same two questions of it: the Gallery card and the History /
Target run listings ask *"can I offer «reuse these settings»?"*, and
``GET …/stack-runs/{id}/options`` — the endpoint that button calls — asks
*"is there anything to hand back?"*.

Those three used to be three hand-written copies of the same rule, and they did
not agree: two read a run with no recorded options as reusable and one did not,
so a listing could offer a button the endpoint refused (or withhold one it would
have served). That is the same "one fact, several spellings" drift
``webapp/library_hygiene.py`` and ``seestack.io.scanner.junk_output_frame_cap``
were each created to undo. This module is that fix for run options: the parse
and the verdict live here, and the three sites call them.
"""

from __future__ import annotations

import json
import math
from typing import Any


def parse_run_options(options_json: str | None) -> dict[str, Any]:
    """A run's recorded settings as a dict — ``{}`` when there are none.

    Empty, absent, unparseable, and "valid JSON that isn't an object" all read
    as ``{}``: the run recorded no usable settings, which is one state however
    it came about. Callers that need to tell "no settings" from "some settings"
    ask :func:`run_has_reusable_options`, not the truthiness of this."""
    if not options_json:
        return {}
    try:
        parsed = json.loads(options_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def run_has_reusable_options(options_json: str | None) -> bool:
    """True when this run's settings can pre-fill the Stack form.

    False in three cases, and the third is the one the old hand-mirrored copies
    disagreed about:

    * an **editor-recipe** run — the picture an editor export wrote, whose
      ``options_json`` is the recipe, not stack knobs;
    * a **channel-combine** run, for the same reason;
    * a run that recorded **no settings at all** (empty, unparseable, or not an
      object). Pre-filling a form from nothing is a button that appears to
      promise something and then does nothing, so the honest answer is not to
      offer it — and it is the answer the endpoint behind the button gives.
    """
    options = parse_run_options(options_json)
    if not options:
        return False
    return "editor_recipe" not in options and "channel_combine" not in options


def derived_from_run_id(options_json: str | None) -> int | None:
    """The stack run this row was **rendered from**, or ``None`` for a stack.

    An editor export writes ``derived_from`` into its options
    (``webapp.pipeline._apply_editor_to_run``): the picture is a re-render of
    pixels another run already combined, on the same light, over the same nights.
    Anything that asks *"is this row a second copy of a stack I have already
    described?"* asks this.

    The rule is the one ``frontend/src/routes/History.tsx``'s ``derivedFromNote``
    has applied since the two rows first appeared on that page side by side, and
    it is spelled the same way here so the two cannot drift: ``options`` is
    whatever JSON the run stored, so a value that is not a finite number is no
    answer, and a row pointing at *itself* is nonsense rather than a loop. An
    ordinary stack, a channel combine, and every run recorded before the field
    existed all read as ``None`` — i.e. "a stack in its own right", which is what
    they are.
    """
    raw = parse_run_options(options_json).get("derived_from")
    # `bool` is an `int` in Python; `True` is not a run id.
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if not math.isfinite(raw):
        return None
    return int(raw)


def run_places_unsolved_subs(options_json: str | None) -> bool:
    """True when this run stacked with ``star_match_unsolved`` on — i.e. when a
    sub **no plate solve could place** is still light a re-stack would fold in.

    Everything that asks *"how much light is this picture missing?"* has to answer
    *"missing light a re-stack could actually use"*, and the bar for that is
    normally accepted **and** solved
    (:meth:`seestack.io.project.Project.count_light_missing_from_stack`,
    :meth:`~seestack.io.project.Project.restored_frame_windows`). Since v0.482.0
    that bar has one exception: with ``StackOptions.star_match_unsolved`` on, the
    stacker places un-located subs by matching their star patterns to the
    reference (``seestack.stack.stacker._star_matched_unsolved_frames``) — which
    is the *point* of the option, because on a faint or star-poor field ASTAP
    fails on most subs and the solved ones are a handful. On such an install a
    target whose whole shortfall is unsolved subs reads as **nothing waiting**,
    and the one library-wide offer never names it.

    **Gated on the option, never on a threshold.** The star-match path is capped
    at ``stacker.STAR_MATCH_MAX_UNSOLVED`` per run and refuses any sub whose stars
    do not clearly match, so the exact number a re-stack rescues is not knowable
    from the ``frames`` table. Modelling that cap here would be a second, worse
    copy of the stacker's own rule; asking "is this install even trying?" is one
    bit that the run itself recorded.

    Read off **the run being measured against**, which is the run a reprocess
    reuses the settings of (``webapp.pipeline._last_stack_options_for_target``),
    so the question "what would stacking this again fold in?" is answered with the
    settings it would in fact be stacked with.

    Strictly ``is True``: the option defaults ``False``, and a run that recorded
    no settings, a non-boolean, or nothing at all reads as off. That keeps the
    error on the side the bug already errs on — the offer says *less* than it
    could, which for an offer is the safe direction to be wrong in.
    """
    return parse_run_options(options_json).get("star_match_unsolved") is True
