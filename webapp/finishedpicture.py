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

**The question is about the stored preview's bytes, not about intent**
*(sharpened v0.449.0, after the first version answered a different one)*. Saving
a recipe in the editor writes it to the project DB and re-renders nothing, so a
run carrying somebody's own saved edit is still showing a plain autostretch of
the linear master — and counting that as finished made the chips vanish from the
very cards that most needed them. What makes a preview a picture is that
something *baked* it: an editor export's own tone-mapped pixels, or the
``preview_display_space`` mark an in-place auto-edit writes beside the bytes it
renders.
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
# (There used to be a third hand-spelling here, of the saved recipe's meta
# prefix. v0.449.0 removed the need for it: the answer below is entirely in the
# run's own ``options_json``, so this module no longer reads project meta and no
# longer imports a router.)
_EXPORT_KEYS = ("editor_recipe", "display_space")

#: The mark an *in-place* bake leaves on the run it re-rendered — written by
#: ``pipeline._auto_edit_process_run`` in the same breath as the preview bytes,
#: and read by ``routers.stack._unexported_edit`` for the same purpose: it is the
#: one on-disk fact that says "this preview is a tone-mapped picture, not the
#: autostretch ``_write_preview_png`` writes for a linear master".
_BAKED_PREVIEW_KEY = "preview_display_space"


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
    """True when ``run``'s **stored preview** is a *finished* picture rather than
    the plain autostretch of a linear stack.

    Two shapes count, because the app makes a finished picture two ways:

    * the run **is** an editor export (``options_json`` carrying
      ``editor_recipe``/``display_space``), whose stacked pixels are already
      tone-mapped and whose preview is therefore a picture in its own right; or
    * something **baked** the run's preview through a recipe — which takes
      *both* a recipe with at least one enabled op (an all-disabled one renders
      the linear stack, exactly as the editor would) *and* the
      ``preview_display_space`` mark written beside those bytes by
      ``pipeline._auto_edit_process_run``.

    **That second mark is new here, and its absence was a bug** *(v0.449.0)*.
    The rule used to accept a saved recipe on its own — but ``put_recipe``
    writes the recipe row to the project DB and **nothing else**; no path
    re-renders a preview on Save. So a run carrying somebody's own saved edit is
    still showing ``_write_preview_png``'s plain autostretch of the linear
    master, and counting it as finished made the Library and Gallery chips
    *disappear* the moment a user saved an edit, on a card whose bytes had not
    changed. Exactly backwards: that card is unstretched **and** the user's work
    is invisible on it. The app already said so elsewhere on the same screens —
    ``routers.stack._unexported_edit`` calls this state "the user edited, pressed
    Save, and the stored preview does not show it" — so the two agree now
    instead of contradicting each other about one run.

    Note what is deliberately *not* asked: whether the saved recipe still agrees
    with the baked look. A run we baked and the user has since tweaked is showing
    the look we baked, which is a finished picture. That drift is
    ``_unexported_edit``'s question, not this one.

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

    data: Any = None
    if options_json:
        try:
            data = json.loads(options_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            data = None
    if not isinstance(data, dict):
        data = {}
    if any(data.get(k) for k in _EXPORT_KEYS):
        return True
    # Nothing baked this preview, so whatever the recipe says, the bytes on disk
    # are the plain autostretch of a linear master.
    if not data.get(_BAKED_PREVIEW_KEY):
        return False
    try:
        recipe = recipe_from_json(recipe_json)
    except Exception:  # noqa: BLE001 — a note's count never fails the page
        return False
    return any(op.enabled for op in recipe.ops)
