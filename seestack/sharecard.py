"""A copy-friendly, plain-language blurb to post alongside a shared image.

After the pipeline turns a night's subs into a picture worth showing, a
beginner's very next step is "how do I post this?" — and the answer needs a
short caption. This module builds that one line from data already on the stack
run: the target's name, its total integration, and how many subs went in — e.g.
``"M 42 · 3h 12m · 152 subs"``.

Pure and offline: no I/O, no network, no ``webapp`` imports. The webapp layer
feeds it the run's metadata and surfaces the string next to a "Share image"
button; keeping it here makes it independently testable.
"""

from __future__ import annotations


def format_duration(seconds: float | None) -> str:
    """Compact, human duration for a caption — ``"3h 12m"`` / ``"45m"`` /
    ``"30s"`` — or ``""`` when there's nothing meaningful to show. Rounds to
    whole minutes above a minute (sub-second precision is noise in a caption)."""
    if not seconds or seconds <= 0:
        return ""
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, rem_min = divmod(minutes, 60)
    return f"{hours}h {rem_min:02d}m" if rem_min else f"{hours}h"


def share_blurb(
    target_name: str | None,
    n_frames: int | None,
    integration_s: float | None,
) -> str:
    """A single ``·``-joined caption line from whatever facts are available, e.g.
    ``"M 42 · 3h 12m · 152 subs"``. Each part is included only when it carries
    real information, so a run missing its integration or sub count still yields a
    tidy line (never a dangling separator or a ``"0 subs"``)."""
    parts: list[str] = []
    name = (target_name or "").strip()
    if name:
        parts.append(name)
    dur = format_duration(integration_s)
    if dur:
        parts.append(dur)
    if n_frames and n_frames > 0:
        parts.append(f"{n_frames} sub" if n_frames == 1 else f"{n_frames} subs")
    return " · ".join(parts)
