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
from typing import Any

from seestack.framing import FrameField, frame_field_from_solve
from seestack.io.library import Library
from seestack.io.project import Project

log = logging.getLogger(__name__)

#: How many targets to ask before giving up. The answer is the same for all of
#: them on a one-telescope install (which is every install this app is for), so
#: the walk exists only to skip targets that have nothing solved yet.
_MAX_TARGETS_PROBED = 8

#: How long to wait before re-probing after a *failed* answer. A successful one is
#: cached for the life of the process (the telescope does not change mid-session);
#: a failure is retried, because "nothing solved yet" becomes "solved" the first
#: time the owner runs QC.
_RETRY_AFTER_S = 300.0


def library_frame_field(lib: Library) -> FrameField | None:
    """The single-frame field of the telescope this library's frames came from.

    Walks targets newest-activity-first and returns the first solved frame
    geometry that yields a physically-sensible field. ``None`` when nothing in
    the library is solved yet, or when every candidate's numbers are out of
    range — the caller then keeps the module default rather than inventing one.

    Best-effort throughout: a target whose project won't open is skipped, never
    raised, because this feeds an advisory sentence and must never be the reason
    a page 500s.
    """
    entries = lib.list_targets()
    entries.sort(key=lambda e: (e.last_activity_utc or ""), reverse=True)
    for entry in entries[:_MAX_TARGETS_PROBED]:
        try:
            proj = Project.open(lib.target_dir(entry))
        except Exception:  # noqa: BLE001 — advisory path, never break a page
            continue
        try:
            geom = proj.solved_frame_geometry()
        except Exception:  # noqa: BLE001
            geom = None
        finally:
            proj.close()
        if geom is None:
            continue
        field = frame_field_from_solve(*geom)
        if field is not None:
            return field
    return None


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
