"""One rule for spelling a capture window, in three deliberate styles.

The shared table these read (``tests/fixtures/night_range_format.json``) is also
read by ``frontend/src/format.test.ts`` against the SPA's own
``formatCaptureNights``, so the four surfaces that name a night — the screen, the
baked caption, the exported spreadsheet and the Editor's copyable blurb — cannot
drift into three spellings again without a suite going red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seestack.nightrange import ASCII, DISPLAY, ISO, format_night_range, parse_night

SHARED_CASES = Path(__file__).parent / "fixtures" / "night_range_format.json"


def _cases():
    data = json.loads(SHARED_CASES.read_text())["cases"]
    return [(c[0], c[1], style, expected)
            for c in data for style, expected in c[2].items()]


@pytest.mark.parametrize("start,end,style,expected", _cases())
def test_shared_cases(start, end, style, expected):
    assert format_night_range(start, end, style=style) == expected


def test_every_case_covers_every_style():
    """A case that lists only one style would let the other two drift silently —
    the exact failure the shared table exists to prevent."""
    for start, end, styles in json.loads(SHARED_CASES.read_text())["cases"]:
        assert set(styles) == {DISPLAY, ASCII, ISO}, (start, end)


def test_the_ascii_style_is_the_display_style_with_a_plain_hyphen():
    """The nameplate's font has no en dash — that, and nothing else, is what the
    ASCII style is for. Pinned as a property rather than case by case, so a future
    divergence has to be written on purpose."""
    for start, end, styles in json.loads(SHARED_CASES.read_text())["cases"]:
        assert styles[ASCII] == styles[DISPLAY].replace("–", "-"), (start, end)


def test_a_baked_caption_can_draw_every_character_it_produces():
    """The reason the ASCII style exists at all, stated where it can fail."""
    for _s, _e, styles in json.loads(SHARED_CASES.read_text())["cases"]:
        assert styles[ASCII].isascii()


def test_iso_stays_sortable():
    """Both dates in full, joined by a word: a spreadsheet must not read the cell
    as arithmetic, and a single-night row must parse as a plain date."""
    assert format_night_range("2024-11-15", None, style=ISO) == "2024-11-15"
    span = format_night_range("2024-11-15", "2024-11-18", style=ISO)
    assert "–" not in span and span[4] == "-"  # only the ISO date's own hyphens
    assert span.split(" to ") == ["2024-11-15", "2024-11-18"]


def test_the_dash_is_spaced_only_between_multi_word_sides():
    """The typographic half of the rule, and the half only the SPA used to know:
    "15–18 Nov" must not look like two separate dates, and "28 Oct – 3 Nov" must
    not look like a subtraction."""
    assert format_night_range("2024-11-15", "2024-11-18") == "15–18 Nov 2024"
    assert format_night_range("2024-10-28", "2024-11-03") == "28 Oct – 3 Nov 2024"


def test_display_is_the_default_style():
    assert format_night_range("2024-11-15", "2024-11-18") == \
        format_night_range("2024-11-15", "2024-11-18", style=DISPLAY)


@pytest.mark.parametrize("value", [
    None, "", "   ", "nope", "2024", "2024-11", "2024-13-01", "2024-00-01",
    "2024-11-32", "2024-11-00", "0000-11-15",
])
def test_parse_night_refuses_to_half_read_a_date(value):
    """A date is a fact a beginner pastes into a forum post. A wrong one is worse
    than a missing one, so anything not confidently a date is nothing at all —
    the imaging-log spelling used to take the first ten characters and print
    whatever they were."""
    assert parse_night(value) is None


def test_parse_night_reads_a_timestamp_as_its_date():
    assert parse_night("2024-11-15T22:03:00Z") == (2024, 11, 15)
    assert parse_night("2024-11-15 22:03:00") == (2024, 11, 15)


# --- the three call sites still say what they always said ---------------------

def test_the_nameplate_still_captions_as_before():
    from seestack.nameplate import format_acq_range

    assert format_acq_range("2024-09-11", "2024-09-14") == "11-14 Sep 2024"
    assert format_acq_range("2024-09-11", None) == "11 Sep 2024"
    assert format_acq_range("2024-09-11", "2024-09-11") == "11 Sep 2024"
    assert format_acq_range(None, None) == ""


def test_the_nameplate_now_spaces_a_multi_word_span_too():
    """The one deliberate change of output: the baked caption used to close the
    dash up in every case ("28 Oct-3 Nov 2024"), because it had never learned the
    spacing rule the screen had. It is the same rule now, in ASCII."""
    from seestack.nameplate import format_acq_range

    assert format_acq_range("2024-10-28", "2024-11-03") == "28 Oct - 3 Nov 2024"
    assert format_acq_range("2024-12-28", "2025-01-03") == "28 Dec 2024 - 3 Jan 2025"


def test_the_imaging_log_row_still_parses_as_a_spreadsheet_date():
    from seestack.imaging_log import _format_night_range

    assert _format_night_range("2024-11-15", "2024-11-18") == "2024-11-15 to 2024-11-18"
    assert _format_night_range("2024-11-15", None) == "2024-11-15"
    assert _format_night_range(None, None) == ""
