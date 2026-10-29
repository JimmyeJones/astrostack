"""Which pictures has nobody ever edited — and can be finished with Auto in one go?

The owner's ⭐ entry of 2026-10-28: "about 25 % of my images" came out with a
ragged, colour-confetti border, and every one of them was a picture he had never
edited — the plain autostretch of a linear master. Asked what he wanted, he chose
**both** halves of the fix: new stacks finish themselves when his own
``auto_edit_on_autostack`` switch says so (his to flip, never ours), and for the
pictures he already has, *one* plain-language action that finishes every one he
never touched.

That is a deliberate, owner-requested widening of
:mod:`webapp.routers.unstretched`'s "it names; it never acts", and it is kept just
as narrow as he asked. A target is finished only when its **displayed** picture
(:func:`webapp.finishedpicture.displayed_picture_run`):

* is not already a finished picture
  (:func:`webapp.finishedpicture.run_is_a_finished_picture`); and
* has **no saved recipe at all** — no look anyone saved, whether or not it was
  ever rendered.

Everything else that is flat is left alone and *named*:

* a saved edit that was never exported → ``"has_edit"``: Auto would replace it;
* a cover **he** pinned → ``"cover_pinned"``: he chose that picture as it is (a
  pin the *app* placed is not a choice — :mod:`seestack.coverpin`);
* this target's own auto-edit preference is off → ``"auto_edit_off"``.

Read-only; the job that acts on it is
:func:`webapp.pipeline.submit_finish_unedited_pictures`, and the write itself is
:func:`webapp.pipeline._auto_edit_process_run` — which independently refuses to
write over a recipe it did not bake. Reversible from the editor's Reset, and
earlier results stay in History.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from webapp.finishedpicture import displayed_picture_run, run_is_a_finished_picture

log = logging.getLogger(__name__)

FINISH = "finish"
HAS_EDIT = "has_edit"
COVER_PINNED = "cover_pinned"
AUTO_EDIT_OFF = "auto_edit_off"


@dataclass(frozen=True)
class FinishVerdict:
    safe_name: str
    name: str
    verdict: str          # one of the constants above
    run_id: int | None    # the displayed run a finish would bake, when FINISH


def finish_verdict(proj: Any, entry: Any) -> FinishVerdict | None:
    """This target's answer, or ``None`` when its displayed picture is already
    finished (or it has no picture at all) — i.e. it is not an unedited one."""
    from seestack.coverpin import app_pin_reason
    from webapp.auto_edit_pref import read_auto_edit_pref
    from webapp.routers.editor import RECIPE_META_PREFIX

    runs = list(proj.iter_stack_runs())            # newest first
    shown = displayed_picture_run(runs, entry.cover_stack_run_id)
    if shown is None or run_is_a_finished_picture(proj, shown):
        return None

    def verdict(v: str, run_id: int | None = None) -> FinishVerdict:
        return FinishVerdict(entry.safe_name, entry.name, v, run_id)

    # Any saved recipe at all is somebody's look — even one whose ops are all
    # disabled, or one this app baked and the preview has since lost. Auto
    # would write over it, so it is named rather than finished.
    if proj.get_meta(f"{RECIPE_META_PREFIX}{shown.id}"):
        return verdict(HAS_EDIT)
    if (entry.cover_stack_run_id is not None
            and app_pin_reason(proj, entry.cover_stack_run_id) is None):
        return verdict(COVER_PINNED)
    if read_auto_edit_pref(proj) is False:
        return verdict(AUTO_EDIT_OFF)
    return verdict(FINISH, shown.id)


def scan_finish_unedited(lib: Any) -> list[FinishVerdict]:
    """Every unedited displayed picture in the library with its verdict.
    Fail-soft per target: one unreadable project is logged and skipped, never
    fails the scan."""
    out: list[FinishVerdict] = []
    for entry in lib.list_targets():
        try:
            proj = lib.open_target(entry.safe_name)
        except Exception:  # noqa: BLE001
            log.warning("finish scan: cannot open %s", entry.safe_name, exc_info=True)
            continue
        try:
            v = finish_verdict(proj, entry)
        except Exception:  # noqa: BLE001
            log.warning("finish scan: %s failed", entry.safe_name, exc_info=True)
            v = None
        finally:
            proj.close()
        if v is not None:
            out.append(v)
    out.sort(key=lambda v: v.name)
    return out
