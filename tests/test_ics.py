"""Unit tests for the dependency-free iCalendar serialiser (``webapp/ics.py``)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from webapp.ics import IcsEvent, to_ics


def _event(**over) -> IcsEvent:
    base = dict(
        uid="M_42-20260115T224000Z@astrostack",
        start=datetime(2026, 1, 15, 22, 40, 0, tzinfo=timezone.utc),
        end=datetime(2026, 1, 16, 2, 10, 0, tzinfo=timezone.utc),
        summary="Image M42",
        description="M42 climbs to 61°. Bring the Seestar out.",
        location="51.5000, -0.1300",
    )
    base.update(over)
    return IcsEvent(**base)


def test_wraps_a_valid_vcalendar_with_one_vevent():
    out = to_ics([_event()])
    assert out.startswith("BEGIN:VCALENDAR\r\n")
    assert out.rstrip("\r\n").endswith("END:VCALENDAR")
    assert out.count("BEGIN:VEVENT") == 1
    assert out.count("END:VEVENT") == 1
    assert "VERSION:2.0\r\n" in out
    assert "PRODID:" in out


def test_utc_timestamps_are_ical_z_format():
    out = to_ics([_event()])
    assert "DTSTART:20260115T224000Z" in out
    assert "DTEND:20260116T021000Z" in out
    # DTSTAMP is required and pinned to the start for deterministic output.
    assert "DTSTAMP:20260115T224000Z" in out


def test_aware_non_utc_start_is_converted_to_utc():
    from datetime import timedelta

    tz = timezone(timedelta(hours=2))
    out = to_ics([_event(start=datetime(2026, 1, 16, 0, 40, 0, tzinfo=tz))])
    # 00:40 at +02:00 is 22:40 UTC the previous day.
    assert "DTSTART:20260115T224000Z" in out


def test_naive_start_is_assumed_utc():
    out = to_ics([_event(start=datetime(2026, 1, 15, 22, 40, 0))])
    assert "DTSTART:20260115T224000Z" in out


def test_text_values_are_escaped():
    ev = _event(summary="M42; the Orion Nebula, bright",
                description="Line one\nLine two\\back")
    out = to_ics([ev])
    assert "SUMMARY:M42\\; the Orion Nebula\\, bright" in out
    # Newline → literal \n, backslash doubled.
    assert "Line one\\nLine two\\\\back" in out


def test_uid_is_present_and_carried_through():
    out = to_ics([_event(uid="target-x@astrostack")])
    assert "UID:target-x@astrostack" in out


def test_optional_fields_are_omitted_when_empty():
    out = to_ics([_event(description="", location="")])
    assert "DESCRIPTION" not in out
    assert "LOCATION" not in out
    # The required fields are still there.
    assert "SUMMARY:Image M42" in out


def test_multiple_events_each_get_their_own_vevent():
    out = to_ics([
        _event(uid="a@astrostack"),
        _event(uid="b@astrostack",
               start=datetime(2026, 1, 16, 22, 40, tzinfo=timezone.utc),
               end=datetime(2026, 1, 17, 2, 10, tzinfo=timezone.utc)),
    ])
    assert out.count("BEGIN:VEVENT") == 2
    assert "UID:a@astrostack" in out and "UID:b@astrostack" in out


def test_empty_event_list_is_a_valid_event_less_calendar():
    out = to_ics([])
    assert "BEGIN:VCALENDAR" in out and "END:VCALENDAR" in out
    assert "VEVENT" not in out


def test_long_lines_are_folded_to_75_octets():
    ev = _event(description="x" * 200)
    out = to_ics([ev])
    for line in out.split("\r\n"):
        # A folded continuation begins with a single space; every physical line
        # must fit in 75 octets (RFC 5545 §3.1).
        assert len(line.encode("utf-8")) <= 75, line
    # Unfolding (CRLF + leading space → nothing) restores the 200 x's.
    unfolded = out.replace("\r\n ", "")
    assert "DESCRIPTION:" + "x" * 200 in unfolded


def test_multibyte_chars_are_not_split_across_a_fold():
    # A run of degree signs (2 octets each in UTF-8) must fold on char boundaries.
    ev = _event(description="61° " * 40)
    out = to_ics([ev])
    for line in out.split("\r\n"):
        # Each physical line must still be decodable on its own (no split byte).
        line.encode("utf-8").decode("utf-8")  # would raise if a fold split a char
        assert len(line.encode("utf-8")) <= 75


def test_output_is_crlf_terminated():
    out = to_ics([_event()])
    assert out.endswith("\r\n")
    # No bare LF that isn't part of a CRLF.
    assert "\n" not in out.replace("\r\n", "")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
