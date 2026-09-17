"""Is the picture a target is *showing* a finished one, or a flat linear stack?

One definition, several surfaces. The app makes a picture in two steps — stack,
then edit — and the second is the one a beginner cannot see the absence of: a
linear master and a finished auto-edit are both a dark-ish rectangle on a card,
and the only difference is that one of them has had its histogram stretched.

Three places now need the same answer and must not each invent it:

* the reprocess-everything dialog, which warns how many finished pictures a
  restack without "also auto-edit" would replace (:mod:`webapp.pipeline`);
* the Library wall's "Not stretched yet" chip (:mod:`webapp.routers.unstretched`);
* and the endpoint behind it, which counts the same targets library-wide.

Modelled on :mod:`webapp.stale_crop` and :mod:`webapp.field_fulls`: a small pure
module the router and the pipeline both read, so no two screens can disagree
about the same target.
"""

from __future__ import annotations

import json
from typing import Any

# The two marks an editor *export* run carries in its own ``options_json``.
# Both are written by the editor's export path and read back by name in several
# places already — ``pipeline._stack_options_from_run_json`` rejects a run
# carrying ``editor_recipe`` as "not a genuine stack", and
# ``routers.editor._run_display_space`` reads ``display_space`` to stop the
# proxy re-stretching an already-tone-mapped run. They are JSON keys on disk
# rather than a constant anyone exports, so this is one more hand-spelling of
# them, not a second definition of anything.
#
# (The saved *recipe's* meta prefix is a real constant, and the function below
# imports it from ``webapp.routers.editor`` rather than re-spelling it. The
# import is inside the function so this module stays importable from anywhere
# without dragging a router in at import time.)
_EXPORT_KEYS = ("editor_recipe", "display_space")


def displayed_picture_run(runs: list[Any], cover_stack_run_id: int | None) -> Any:
    """The run whose preview is this target's **displayed** picture, or ``None``.

    The library-side mirror of ``routers.targets.current_picture_path``, decided
    from run rows already in hand instead of from the filesystem: a pinned cover
    first, then the newest run that has a preview at all. It deliberately does
    *not* stat the preview file — every caller is scanning a whole library, where
    one stat per target on a sleeping NAS is the expensive part, and a stamp
    whose file has gone is a rarer case than the one being counted.

    ``runs`` is newest-first, exactly as ``Project.iter_stack_runs`` yields.
    """
    if cover_stack_run_id is not None:
        pinned = next((r for r in runs
                       if r.id == cover_stack_run_id and r.preview_path), None)
        if pinned is not None:
            return pinned
    return next((r for r in runs if r.preview_path), None)


def run_is_a_finished_picture(proj: Any, run: Any) -> bool:
    """True when ``run``'s preview is a *finished* picture rather than a flat
    linear stack.

    Two shapes count, because the app makes finished pictures two ways:

    * the run carries a **saved editor recipe** with at least one enabled op
      (the one-click Auto look, an unattended auto-edit, or the owner's own
      edit) — read through ``recipe_from_json`` so a recipe whose ops have all
      gone stale reads as "not finished", the same way the editor would render
      it; and
    * the run **is** an editor export (``options_json`` carrying
      ``editor_recipe``/``display_space``), whose stacked pixels are already
      tone-mapped and whose preview is therefore a picture in its own right.

    Best-effort and read-only: an unreadable meta row answers ``False`` rather
    than failing a scan that only drives a note.
    """
    from webapp.routers.editor import RECIPE_META_PREFIX

    try:
        recipe_json = proj.get_meta(f"{RECIPE_META_PREFIX}{run.id}")
    except Exception:  # noqa: BLE001 — a note's count never fails the page
        return False
    return run_is_a_finished_picture_from(
        getattr(run, "options_json", None), recipe_json)


def run_is_a_finished_picture_from(options_json: str | None,
                                  recipe_json: str | None) -> bool:
    """The same answer as :func:`run_is_a_finished_picture`, for a caller that has
    **already read** the run's saved recipe.

    The Gallery list is that caller: it reads every run's recipe row anyway, to
    decide ``unexported_edit``, and it does so once per run of every target — so
    asking the project for the same row a second time would double the reads on
    the one endpoint where they are counted. Split out rather than inlined so the
    two callers share one rule; the ``proj``-taking form above is a two-line
    wrapper over this, which is why there is still only one definition of
    "finished".
    """
    from seestack.edit.recipe import recipe_from_json

    if options_json:
        try:
            data = json.loads(options_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            data = None
        if isinstance(data, dict) and any(data.get(k) for k in _EXPORT_KEYS):
            return True
    try:
        recipe = recipe_from_json(recipe_json)
    except Exception:  # noqa: BLE001 — a note's count never fails the page
        return False
    return any(op.enabled for op in recipe.ops)
