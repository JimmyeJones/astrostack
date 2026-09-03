"""One rule for spelling **when a picture was shot**, in three deliberate styles.

The app has three places that render a stack's capture window — the screen, the
caption baked onto a shared JPEG, and the imaging-log spreadsheet — and each one
used to carry its own implementation of the same idea. All three read the *same
two ISO dates off the same run*, so a beginner who compares the picture on screen
with the caption they copied and the row they exported saw three renderings of one
night: ``15–18 Nov 2024``, ``15-18 Nov 2024`` and ``2024-11-15 to 2024-11-18``.

**Two of those three differences are right and survive here as styles**, because
they are forced by where the text lands:

* :data:`ASCII` — the bundled nameplate font has no en dash (see
  :mod:`seestack.nameplate`'s header, whose test pins that every character a
  caption can produce has a real glyph), so a baked caption uses a plain ``-``.
* :data:`ISO` — the imaging log is a **spreadsheet cell**, where ``2024-11-15 –
  2024-11-18`` reads as arithmetic and a plain date should stay sortable and
  parseable, so that style spells the join ``to`` and keeps both dates in full.

What was *not* deliberate is that only the on-screen one knew the rest of the
rule: that the shared parts of a span are written once, that the dash is spaced
only when the two sides are multi-word (``15–18 Nov`` but ``28 Oct – 3 Nov``), and
that a window recorded end-first still reads forwards. Those live here now, once.

The fourth renderer is the SPA's own ``formatCaptureNights``
(``frontend/src/format.ts``), which cannot import Python. It is held to the
:data:`DISPLAY` style by a shared case table — ``tests/fixtures/night_range_format.json``,
read by both ``pytest`` and ``vitest`` — exactly as
``tests/fixtures/integration_format.json`` already holds the two integration
formatters together. A change to either side that isn't a change to the other
reddens a suite.
"""

from __future__ import annotations

from typing import Literal

#: On screen and in a copyable caption: an en dash, month names abbreviated.
DISPLAY = "display"
#: A baked nameplate: identical, but with an ASCII hyphen for the font's sake.
ASCII = "ascii"
#: A spreadsheet cell: two full ISO dates joined by the word "to".
ISO = "iso"

Style = Literal["display", "ascii", "iso"]

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def parse_night(value: str | None) -> tuple[int, int, int] | None:
    """``"2024-11-15"`` / ``"2024-11-15T22:03:00Z"`` → ``(2024, 11, 15)``.

    Best-effort and strict about it: anything that isn't confidently a date
    returns ``None`` rather than a half-parsed guess, because every caller here
    drops the clause instead of printing a placeholder. A date is a fact a
    beginner pastes into a forum post — a wrong one is worse than a missing one.
    """
    if not value:
        return None
    head = str(value).strip().replace("T", " ").split(" ", 1)[0]
    bits = head.split("-")
    if len(bits) < 3:
        return None
    try:
        year, month, day = int(bits[0]), int(bits[1]), int(bits[2])
    except (TypeError, ValueError):
        return None
    if year <= 0 or not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    return year, month, day


def _one(night: tuple[int, int, int], style: Style) -> str:
    year, month, day = night
    if style == ISO:
        return f"{year:04d}-{month:02d}-{day:02d}"
    return f"{day} {_MONTHS[month - 1]} {year}"


def format_night_range(start: str | None, end: str | None = None, *,
                       style: Style = DISPLAY) -> str:
    """The night a stack's subs were shot on, or the span they cover.

    ``("2024-11-15", "2024-11-18")`` gives ``"15–18 Nov 2024"`` (:data:`DISPLAY`),
    ``"15-18 Nov 2024"`` (:data:`ASCII`) or ``"2024-11-15 to 2024-11-18"``
    (:data:`ISO`). A single night — or an end that is missing, unparseable or the
    same day — degrades to that one date. Nothing datable at all gives ``""``.
    """
    a = parse_night(start) or parse_night(end)
    b = parse_night(end) or parse_night(start)
    if a is None or b is None:
        return ""
    # A window recorded (or hand-edited) end-first still describes a real range;
    # name it in the order a reader expects rather than printing it backwards.
    first, last = (a, b) if a <= b else (b, a)
    last_label = _one(last, style)
    if first == last:
        return last_label
    if style == ISO:
        return f"{_one(first, style)} to {last_label}"

    dash = "-" if style == ASCII else "–"
    if first[0] != last[0]:                       # different years
        return f"{_one(first, style)} {dash} {last_label}"
    if first[1] != last[1]:                       # same year, different months
        return f"{first[2]} {_MONTHS[first[1] - 1]} {dash} {last_label}"
    # Same month: the dash joins two bare numbers, so it is *unspaced* — spacing
    # it there ("15 – 18 Nov") reads as two separate dates, and closing it up in
    # the multi-word cases ("28 Oct-3 Nov") reads as a subtraction. This is the
    # part of the rule the two Python renderers never had.
    return f"{first[2]}{dash}{last_label}"
