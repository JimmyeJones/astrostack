"""Which mosaic of the same object does the library already hold?

A single-field picture of something bigger than one frame gets told, twice on its
Target page, to "shoot it in mosaic mode next session" — by the framing note and by
the coaching line above it. For a heavy mosaic user that advice is usually already
taken: the Seestar writes mosaic subs into a separate ``<T>_mosaic_sub/`` folder, the
convention turns that into its own ``"<T> (mosaic)"`` target, and the two are kept
apart on purpose (their canvases differ). So the page was prescribing a session he
has already shot, and never pointed at the picture that session made.

This answers the one question those two surfaces need: *is there a mosaic of this
object in the library, and which one?* Read-only, registry-only (no project is
opened), and silent whenever the answer is not plain.
"""

from __future__ import annotations

from collections.abc import Sequence

from seestack.io.library import SAME_OBJECT_TOL_DEG, TargetEntry, _angular_separation_deg
from seestack.io.scanner import is_mosaic_target_name, mosaic_target_name


def find_mosaic_companion(
    entry: TargetEntry, targets: Sequence[TargetEntry],
) -> TargetEntry | None:
    """The mosaic target that pictures the same object as single-field ``entry``.

    ``None`` when ``entry`` is itself a mosaic (it has no "shoot it in mosaic
    mode" advice to answer), and when no mosaic qualifies. A candidate must be a
    mosaic by the convention's name (:func:`is_mosaic_target_name`), hold at least
    one accepted sub, and not be a flagged mixed-drop leftover. It is the same
    object when either

    * its name is exactly the one the convention gives this field's mosaic
      (``"M 42"`` → ``"M 42 (mosaic)"``) — the Seestar's own folder pair; or
    * both have a plate-solved centre within :data:`SAME_OBJECT_TOL_DEG` — the
      tolerance the merge nudge already trusts for "same object", which covers a
      pair one of whose names the owner has since edited.

    The name match wins outright; among several positional matches the deepest
    (most integration) is the one to keep building, which is the order the merge
    nudge uses too.
    """
    if is_mosaic_target_name(entry.name):
        return None
    candidates = [
        t for t in targets
        if t.safe_name != entry.safe_name
        and is_mosaic_target_name(t.name)
        and (t.n_frames_accepted or 0) > 0
        and not t.legacy_mixed_drop
    ]
    if not candidates:
        return None
    wanted = mosaic_target_name(entry.name.strip()).lower()
    for t in candidates:
        if t.name.strip().lower() == wanted:
            return t
    if entry.ra_deg is None or entry.dec_deg is None:
        return None
    near = [
        t for t in candidates
        if t.ra_deg is not None and t.dec_deg is not None
        and _angular_separation_deg(
            float(entry.ra_deg), float(entry.dec_deg),
            float(t.ra_deg), float(t.dec_deg),
        ) <= SAME_OBJECT_TOL_DEG
    ]
    if not near:
        return None
    near.sort(
        key=lambda t: (t.total_exposure_s or 0.0, t.n_frames_accepted or 0, t.name),
        reverse=True,
    )
    return near[0]
