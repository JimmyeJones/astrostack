"""Which targets lost a picture the app had finished — and can be given it back?

Observer issue `#903 <https://github.com/JimmyeJones/astrostack/issues/903>`_:
a "reprocess everything" run with its auto-edit switch off recorded each
restack as a new run, the newest run is the picture every wall shows, and so
44 of the owner's targets went from a finished Auto picture to a flat linear
master at once. v0.447.2 made that loud, v0.448.1 stopped a *future* batch doing
it (:func:`webapp.pipeline._picture_is_auto_finished`), and v0.448.0's "Not
stretched yet" chip names the state — but nothing put the pictures back.

The owner asked for exactly that on 2026-09-26, as a one-off repair. It is the
v0.448.1 rule applied after the fact, and deliberately just as narrow:

* the target's **displayed** picture
  (:func:`webapp.finishedpicture.displayed_picture_run`) is *not* finished; and
* the newest **older** run that *is* a finished picture was finished **by the
  app** — it carries the ``editor_auto_baked_look`` stamp an unattended
  auto-edit writes.

Then re-applying Auto to the displayed run is "re-do what this picture already
had", not a new opinion about it. Everything else is left alone and *named*:

* the older finished picture is somebody's own edit (a saved recipe with no
  stamp, or an editor export) → ``"by_hand"``: Auto's look is no evidence of
  what they wanted, so the owner redoes those himself;
* nothing was ever finished → ``"never_finished"``: a linear master may be
  deliberate (``webapp.routers.unstretched`` "names; it never acts");
* a cover is pinned → ``"cover_pinned"``: somebody chose the picture;
* this target's own auto-edit preference is off → ``"auto_edit_off"``.

Read-only; the job that acts on it is :func:`webapp.pipeline.submit_refinish_pictures`,
and the write itself is :func:`webapp.pipeline._auto_edit_process_run`, which
independently refuses to write over a recipe it did not bake.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from webapp.finishedpicture import displayed_picture_run, run_is_a_finished_picture

log = logging.getLogger(__name__)

REFINISH = "refinish"
BY_HAND = "by_hand"
NEVER_FINISHED = "never_finished"
COVER_PINNED = "cover_pinned"
AUTO_EDIT_OFF = "auto_edit_off"


@dataclass(frozen=True)
class RefinishVerdict:
    safe_name: str
    name: str
    verdict: str          # one of the constants above
    run_id: int | None    # the displayed run a refinish would bake, when REFINISH


def refinish_verdict(proj: Any, entry: Any) -> RefinishVerdict | None:
    """This target's answer, or ``None`` when its displayed picture is already
    finished (or it has no picture at all) — i.e. it is not one of the flat ones."""
    from webapp.auto_edit_pref import read_auto_edit_pref
    from webapp.routers.editor import AUTO_EDIT_BAKED_LOOK_PREFIX

    runs = list(proj.iter_stack_runs())            # newest first
    shown = displayed_picture_run(runs, entry.cover_stack_run_id)
    if shown is None or run_is_a_finished_picture(proj, shown):
        return None

    def verdict(v: str, run_id: int | None = None) -> RefinishVerdict:
        return RefinishVerdict(entry.safe_name, entry.name, v, run_id)

    if entry.cover_stack_run_id is not None:
        return verdict(COVER_PINNED)
    older = runs[runs.index(shown) + 1:]
    prior = next((r for r in older
                  if r.preview_path and run_is_a_finished_picture(proj, r)), None)
    if prior is None:
        return verdict(NEVER_FINISHED)
    if not proj.get_meta(f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{prior.id}"):
        return verdict(BY_HAND)
    if read_auto_edit_pref(proj) is False:
        return verdict(AUTO_EDIT_OFF)
    return verdict(REFINISH, shown.id)


def scan_refinish(lib: Any) -> list[RefinishVerdict]:
    """Every flat target in the library with its verdict. Fail-soft per target:
    one unreadable project is logged and skipped, never fails the scan."""
    out: list[RefinishVerdict] = []
    for entry in lib.list_targets():
        try:
            proj = lib.open_target(entry.safe_name)
        except Exception:  # noqa: BLE001
            log.warning("refinish scan: cannot open %s", entry.safe_name, exc_info=True)
            continue
        try:
            v = refinish_verdict(proj, entry)
        except Exception:  # noqa: BLE001
            log.warning("refinish scan: %s failed", entry.safe_name, exc_info=True)
            v = None
        finally:
            proj.close()
        if v is not None:
            out.append(v)
    return out
