"""Reading an op's best-effort outcome note back off a finished render.

``EditContext.op_notes`` is the channel an op uses to hand the *caller* a small,
JSON-safe fact about what it actually did — which white-balance path ran, on how
many stars, and whether the decimated preview landed somewhere the full-res
export will not. Nothing in the engine reads it; two surfaces in the webapp do
(the editor's live histogram payload and the walk-away auto-edit's History
stamp), and this module is the one place that turns "every instance's note" into
the single read-out those two show, so they cannot describe one render
differently.

A recipe is a **list**, and nothing stops it carrying the same op twice — the
editor's Add menu has no duplicate guard, so two ``tone.color_calibrate`` ops is
a couple of clicks. Notes are therefore keyed per *instance* (see
:meth:`seestack.edit.registry.EditContext.record_note`), exactly as ``fitted``
and ``field_deltas`` already are, and a reader has to say what it means when
there is more than one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

#: The one op that records a note today. Named here rather than spelled at each
#: reader, so the writer and the two readers cannot drift onto different strings.
COLOR_CAL_OP = "tone.color_calibrate"


def merge_color_cal(notes: Sequence[Any]) -> dict[str, Any] | None:
    """One colour-calibration read-out for a whole render, or ``None``.

    ``notes`` is every enabled ``tone.color_calibrate`` instance's note, in the
    order they ran (:meth:`~seestack.edit.registry.EditContext.notes_for`). The
    two fields answer different questions, so they are merged differently:

    * **Which balance the picture ended up with** — ``mode_used`` /
      ``n_stars_used`` / ``notes`` come from the **last** instance that reported
      a mode. A second calibration is applied on top of the first, so the last
      one is the balance the saved picture actually carries.
    * **Whether the preview's colour is the export's** — ``proxy_fallback`` is
      **any** instance's. It is a parity warning, and the preview diverges from
      the export if *any* step of the chain diverged; taking the last one's
      silently drops the warning when an earlier instance is the one that fell
      back. That is the same rule the histogram payload's sibling warning
      (``star_reduce_preview_overstates``) already applies across every
      ``stars.reduce`` op in the recipe.

    Bit-for-bit today's answer on the single-instance recipe every surface
    actually renders (including the one-click Auto recipe): one note in, the same
    dict out, with ``proxy_fallback`` recomputed from that same note.
    """
    dicts: list[Mapping[str, Any]] = [n for n in notes if isinstance(n, Mapping)]
    base: Mapping[str, Any] | None = None
    for note in dicts:
        if note.get("mode_used"):
            base = note
    if base is None:
        return None
    merged = dict(base)
    merged["proxy_fallback"] = any(bool(n.get("proxy_fallback")) for n in dicts)
    return merged
