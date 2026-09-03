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
