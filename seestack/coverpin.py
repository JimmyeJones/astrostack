"""Who pinned this target's cover — the owner, or the app on his behalf?

A target's **cover** (``TargetEntry.cover_stack_run_id``) is the picture every
wall surface shows in place of the newest run. It has one column and two
authors: the owner, through "Set as cover" in History, and the app itself, in
two places that both exist to keep a finished picture on the wall —

* a **Combine** pins the destination's own displayed picture, because the
  carried one-night stack is usually the *newest* run and would otherwise take
  its place (:meth:`seestack.io.library.Library.merge_targets_result`);
* a **bulk restack** pins a picture the owner finished *by hand* before the
  fresh, unedited run lands as the newest one
  (``webapp.pipeline.submit_reprocess_all``) — observer issue #903's shape,
  where exactly such a batch flattened 44 of his pictures.

The trouble with a pin the app placed is that it is *permanent* in a column that
does not say who placed it: the next deeper run the app makes for that target
is never displayed, and the "new light waiting" note keeps naming a target whose
deeper picture already exists. An owner's pin must be respected forever (he
chose the picture); an app's pin must **advance** when the reason for it is
gone. So the app records its own pins here, in the target's ``project_meta``,
beside the pin — a record, never a second cover column, so §9's "the existing
column's meaning is untouched" holds: the registry still reads
``cover_stack_run_id`` exactly as it always did, and an older build that has
never heard of this key simply keeps the pin.

The record is **only** valid while it names the run that is actually pinned.
The moment the owner pins something else, or clears the pin, the stored run id
and the registry's disagree and :func:`app_pin_reason` answers ``None`` — the
pin is his. No write is needed on the owner's side, which is what makes this
safe against every path that sets a cover, including ones written later.

Engine module (no ``webapp`` imports, AGENTS.md §6) so the library's merge can
write it and the web layer can read it.
"""

from __future__ import annotations

import json
from typing import Any

#: ``project_meta`` key: ``{"run_id": <int>, "reason": <str>}``.
APP_COVER_PIN_META_KEY = "cover_pinned_by_app"

#: A Combine pinned the destination's own picture over the carried, newer one.
PIN_REASON_MERGE = "merge"
#: A bulk restack pinned a hand-finished picture so its fresh run would not
#: replace it on the wall.
PIN_REASON_KEPT_FINISHED = "kept_finished"


def mark_app_pin(proj: Any, run_id: int, reason: str) -> None:
    """Record that the app pinned ``run_id`` as this target's cover, and why."""
    proj.set_meta(APP_COVER_PIN_META_KEY,
                  json.dumps({"run_id": int(run_id), "reason": str(reason)}))


def clear_app_pin(proj: Any) -> None:
    """Forget the app's record — called when the app itself lifts its pin."""
    proj.delete_meta(APP_COVER_PIN_META_KEY)


def app_pin_reason(proj: Any, cover_stack_run_id: int | None) -> str | None:
    """Why the app pinned the cover ``cover_stack_run_id``, or ``None`` when the
    pin is the owner's (or there is no pin).

    ``None`` is the *safe* answer and every doubt resolves to it: no pin, no
    record, an unreadable record, or a record naming a different run than the
    one pinned — that last one is how an owner's later "Set as cover" silently
    retires the app's record without any code having to notice.
    """
    if cover_stack_run_id is None:
        return None
    try:
        raw = proj.get_meta(APP_COVER_PIN_META_KEY)
    except Exception:  # noqa: BLE001 — a note's read never fails its caller
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    run_id = data.get("run_id")
    if isinstance(run_id, bool) or not isinstance(run_id, int):
        return None
    if run_id != int(cover_stack_run_id):
        return None
    reason = data.get("reason")
    return str(reason) if reason else None
