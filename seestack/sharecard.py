"""A copy-friendly, plain-language blurb to post alongside a shared image.

After the pipeline turns a night's subs into a picture worth showing, a
beginner's very next step is "how do I post this?" — and the answer needs a
short caption. This module builds that one line from data already on the stack
run: the target's name, its total integration, and how many subs went in — e.g.
``"M 42 · 3.2 h · 152 subs"``.

Pure and offline: no I/O, no network, no ``webapp`` imports. The webapp layer
feeds it the run's metadata and surfaces the string next to a "Share image"
button; keeping it here makes it independently testable.
"""

from __future__ import annotations

import math


def _round_half_up(value: float) -> int:
    """Round a non-negative number the way JavaScript's ``Math.round`` does.

    Python's built-in ``round`` is banker's rounding (``round(2.5) == 2``), so a
    duration landing exactly on a half would format differently here than in the
    SPA. Every value this module sees is positive, so ``floor(x + 0.5)`` is the
    whole rule.
    """
    return int(math.floor(value + 0.5))


def format_duration(seconds: float | None) -> str:
    """Integration time in the app's one vocabulary — ``"3.2 h"`` / ``"45 min"``
    / ``"30 s"`` — or ``""`` when there's nothing meaningful to show.

    **This mirrors ``formatIntegration`` in ``frontend/src/format.ts``, and it
    has to.** Both describe the same fact about the same picture, and a beginner
    who reads "3.2 h" on the Target page and then copies a caption saying
    "3h 12m" has no way to know they are the same number — the comment on
    ``Library.tsx``'s own ``expo`` helper spells out that rule for the SPA's
    surfaces, and the caption builders here are simply more of them. The two
    implementations are pinned against one shared table of cases,
    ``tests/fixtures/integration_format.json``, read by both ``pytest`` and
    ``vitest``, so neither can drift without reddening the other's suite.

    The one deliberate difference is the nothing-to-say case: the SPA renders an
    em dash for a stat tile, while a caption must *drop* the clause rather than
    print a placeholder into someone's Instagram post. Hence ``""`` here, and
    the fixture covers positive durations only.
    """
    if seconds is None:
        return ""
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(value) or value <= 0:
        return ""

    # Promote a value that *rounds* up to a full unit rather than printing it in
    # the smaller unit ("60 min" / "60 s"): pick the unit, then re-check that the
    # rounded figure still fits it, else roll into the next unit.
    if value < 60:
        secs = _round_half_up(value)
        if secs < 60:
            return f"{secs} s"
        value = 60.0
    if value < 3600:
        mins = _round_half_up(value / 60)
        if mins < 60:
            return f"{mins} min"
        value = 3600.0
    hours = value / 3600
    if value >= 36000:  # ten hours and up: a tenth of an hour is noise
        return f"{_round_half_up(hours)} h"
    return f"{_round_half_up(hours * 10) / 10:.1f} h"


def share_blurb(
    target_name: str | None,
    n_frames: int | None,
    integration_s: float | None,
    capture_label: str | None = None,
) -> str:
    """A single ``·``-joined caption line from whatever facts are available, e.g.
    ``"M 42 · 15–18 Nov 2024 · 3.2 h · 152 subs"``. Each part is included only
    when it carries real information, so a run missing its integration or sub
    count still yields a tidy line (never a dangling separator or a ``"0 subs"``).

    ``capture_label`` is **when the light was collected**, already formatted —
    :func:`seestack.nightrange.format_night_range` is what makes one, and passing
    an already-rendered string is deliberate so this pure module keeps no date
    logic of its own to drift. Left out (every caller before the app recorded a
    capture window, and every run from before schema 18) the caption is exactly
    what it has always been.

    It must never be a *processing* stamp. A stack's ``timestamp_utc`` is when it
    ran, which on a re-stack of a back catalogue is years from when it was shot —
    the whole class of bug the SPA's ``CaptureLabel`` branded type exists to stop
    on the TypeScript side. It sits second, right after the target: the date is
    the fact a caption is *for*, and a reader wants the object and the night
    before the exposure arithmetic.
    """
    parts: list[str] = []
    name = (target_name or "").strip()
    if name:
        parts.append(name)
    shot = (capture_label or "").strip()
    if shot:
        parts.append(shot)
    dur = format_duration(integration_s)
    if dur:
        parts.append(dur)
    if n_frames and n_frames > 0:
        parts.append(f"{n_frames} sub" if n_frames == 1 else f"{n_frames} subs")
    return " · ".join(parts)
