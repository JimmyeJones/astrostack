"""Minimal, dependency-free iCalendar (RFC 5545) serialiser.

Turns a plan — "your next good window for M31 is Thu 22:40 → 02:10" — into a
``.ics`` file a beginner's phone/desktop calendar imports with one tap, so the
plan the night-planner computed doesn't evaporate the moment they close the tab.

Deliberately tiny and offline: ``.ics`` is just text, so this needs no calendar
account, no SMTP and no network (all of which would be an outward-facing change
needing owner sign-off). It emits a single ``VCALENDAR`` with one ``VEVENT`` per
window, correctly CRLF-terminated, text-escaped and line-folded, with a
deterministic ``UID`` per (target, start) so re-adding updates the same event in
the user's calendar rather than duplicating it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Product identifier stamped into every calendar (RFC 5545 §3.7.3). Purely
# informational — the importing calendar shows it as the source app.
PRODID = "-//AstroStack//Night planner//EN"


@dataclass(frozen=True)
class IcsEvent:
    """One calendar event: an observing window for a target."""

    uid: str
    start: datetime
    end: datetime
    summary: str
    description: str = ""
    location: str = ""


def _escape_text(value: str) -> str:
    """Escape a TEXT value per RFC 5545 §3.3.11 (backslash first, then the
    structural delimiters, then newlines → the literal ``\\n``)."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fmt_utc(dt: datetime) -> str:
    """Format an aware/naive datetime as a UTC iCal timestamp
    (``YYYYMMDDTHHMMSSZ``). A naive datetime is assumed to already be UTC."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """Fold a content line to ≤75 octets per RFC 5545 §3.1: a continuation
    starts with a single space. Folds on octet (UTF-8) boundaries so multi-byte
    characters are never split across a fold."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks: list[bytes] = []
    # First line: up to 75 octets; each continuation: up to 74 (the leading
    # space counts toward the 75-octet limit).
    limit = 75
    i = 0
    while i < len(raw):
        end = min(i + limit, len(raw))
        # Don't split a UTF-8 multi-byte sequence: back off until `end` is not a
        # continuation byte (0b10xxxxxx), unless we've consumed the whole string.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[i:end])
        i = end
        limit = 74
    return "\r\n ".join(c.decode("utf-8") for c in chunks)


def _prop(name: str, value: str, *, escape: bool = True) -> str:
    text = _escape_text(value) if escape else value
    return _fold(f"{name}:{text}")


def to_ics(events: list[IcsEvent], *, prodid: str = PRODID) -> str:
    """Serialise ``events`` into a single RFC-5545 ``VCALENDAR`` string
    (CRLF-terminated). An empty list still yields a valid, event-less calendar."""
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        _prop("PRODID", prodid),
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for ev in events:
        # DTSTAMP marks when the event data was generated; tie it to the event's
        # own start so the output is deterministic (no wall-clock) and stable
        # across identical re-requests — which keeps the UID-based de-duplication
        # meaningful.
        lines += [
            "BEGIN:VEVENT",
            _prop("UID", ev.uid),
            f"DTSTAMP:{_fmt_utc(ev.start)}",
            f"DTSTART:{_fmt_utc(ev.start)}",
            f"DTEND:{_fmt_utc(ev.end)}",
            _prop("SUMMARY", ev.summary),
        ]
        if ev.description:
            lines.append(_prop("DESCRIPTION", ev.description))
        if ev.location:
            lines.append(_prop("LOCATION", ev.location))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
