"""Your year under the stars — a calendar-year recap of a season of imaging.

The app already has both ends of the time axis and nothing in the middle. A
*night* has :mod:`seestack.session_recap` ("Last night", the by-breakfast
poster); the *whole hobby* has "Your sky, so far" and
:mod:`seestack.recap`'s share poster. Neither answers the question a beginner
actually asks in January: **"what did last year look like?"** — the milestone
they want to look back on and post.

This module folds the nights the activity calendar already computes into one
calendar year and asks the six things a person would want to be told:

  * how many **nights** they were out,
  * how much **light** they collected,
  * how many **targets** they pointed at,
  * which targets they saw for the **first time** that year ("first light"),
  * their **longest single night**,
  * and their **sharpest** night.

Everything is derived from :class:`seestack.activity_calendar.NightActivity`
rows, so a night's numbers mean exactly what they mean on the Dashboard heatmap
and the "best night" card — one definition, one voice. Pure, offline and
deterministic: no clock, no network, no ``webapp`` imports, nothing written.

Honest rather than complete: a figure the data can't support is left out
(``None``/empty) instead of guessed, and a year with no nights simply says so.

The year is also *shareable*: :func:`year_caption` writes the copy-paste blurb
and :func:`draw_year_poster` renders the square picture to post beside it — the
latter by feeding this module's facts into :func:`seestack.recap.draw_poster`,
the same renderer the all-time "your sky, so far" poster uses, so the two can
never drift apart in look.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from seestack.activity_calendar import NightActivity, sharpest_night
from seestack.sharecard import format_duration

#: How many first-light names the "first light" line spells out before it falls
#: back to "and N more". Three is what reads as a sentence rather than a list,
#: matching :data:`seestack.recap._MAX_OTHER_NAMES`.
_MAX_FIRST_LIGHT_NAMES = 3

#: How many nights a year needs before "your longest night" is worth naming.
#: On a one-night year the longest night is *the* night wearing a rosette —
#: exactly the reasoning behind
#: :data:`seestack.activity_calendar.SHARPEST_MIN_NIGHTS`, and deliberately the
#: same number so the two standouts appear and disappear together.
LONGEST_MIN_NIGHTS = 2


def _year_of(night: NightActivity) -> int | None:
    """The calendar year of a night's ISO date, or ``None`` if it can't be read.

    A single malformed row must never sink a recap, so this is forgiving in the
    same way :func:`seestack.activity_calendar.parse_utc` is."""
    try:
        return date.fromisoformat(night.date).year
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class YearRecap:
    """One calendar year of imaging, as facts.

    ``has_anything`` is the caller's cue: false means the year had no imaged
    nights at all, and the page should offer the years that *do* have data
    rather than a wall of zeros.
    """

    year: int
    has_anything: bool = False
    n_nights: int = 0
    total_exposure_s: float = 0.0
    n_frames: int = 0
    n_targets: int = 0
    #: Every target imaged that year, by name, sorted.
    target_names: tuple[str, ...] = ()
    #: Targets whose *first ever* imaged night falls in this year, in the order
    #: they were first shot — the year's "first light" moments.
    first_light_names: tuple[str, ...] = ()
    #: The year's longest single night by capture time, or ``None`` (see
    #: :data:`LONGEST_MIN_NIGHTS`).
    longest_night: NightActivity | None = None
    #: The year's sharpest night, by the app's one definition
    #: (:func:`seestack.activity_calendar.sharpest_night`), or ``None``.
    sharpest_night: NightActivity | None = None
    #: The year's imaged nights, date-ascending.
    nights: tuple[NightActivity, ...] = ()
    #: Every year the library has an imaged night in, ascending — so a page can
    #: offer "2024 · 2025 · 2026" without a second pass over the library.
    years_with_data: tuple[int, ...] = ()


def first_night_by_target(nights: list[NightActivity]) -> dict[str, date]:
    """Each target's earliest imaged night, over *every* night given.

    This is what makes "first light this year" honest: a target counts as new
    only if the whole library has never seen it before, so the caller must pass
    the library's complete night list, not one year's slice.
    """
    out: dict[str, date] = {}
    for n in nights:
        try:
            d = date.fromisoformat(n.date)
        except (TypeError, ValueError):
            continue
        for name in n.targets:
            if not name:
                continue
            prev = out.get(name)
            if prev is None or d < prev:
                out[name] = d
    return out


def longest_night(nights: list[NightActivity]) -> NightActivity | None:
    """The night with the most capture time, or ``None``.

    Silent rather than wrong, on the same two conditions the sharpest-night
    answer uses: at least :data:`LONGEST_MIN_NIGHTS` nights to compare, and a
    winner that actually collected some light. Ties break on the earlier date,
    so the answer is deterministic.
    """
    ranked = [n for n in nights if n.exposure_s > 0]
    if len(ranked) < LONGEST_MIN_NIGHTS:
        return None
    # ``min`` on a negated exposure gives the longest night, and leaves the date
    # ascending so a tie resolves to the earlier one.
    return min(ranked, key=lambda n: (-n.exposure_s, n.date))


def years_with_data(nights: list[NightActivity]) -> tuple[int, ...]:
    """Every calendar year with at least one imaged night, ascending."""
    return tuple(sorted({y for n in nights if (y := _year_of(n)) is not None}))


def build_year_recap(nights: list[NightActivity], *, year: int) -> YearRecap:
    """Fold the library's complete night list into one calendar year's recap.

    ``nights`` must be *every* night the library knows about (the unclipped
    output of :func:`seestack.activity_calendar.nights_from`), because two of
    the facts — first light, and which years to offer — are only answerable
    against the whole history.
    """
    year = int(year)
    all_years = years_with_data(nights)
    mine = [n for n in nights if _year_of(n) == year]
    if not mine:
        return YearRecap(year=year, years_with_data=all_years)

    firsts = first_night_by_target(nights)
    new_this_year = sorted(
        (name for name, d in firsts.items() if d.year == year),
        key=lambda name: (firsts[name], name),
    )
    names = sorted({name for n in mine for name in n.targets if name})
    return YearRecap(
        year=year,
        has_anything=True,
        n_nights=len(mine),
        total_exposure_s=round(sum(n.exposure_s for n in mine), 3),
        n_frames=sum(n.n_frames for n in mine),
        n_targets=len(names),
        target_names=tuple(names),
        first_light_names=tuple(new_this_year),
        longest_night=longest_night(mine),
        sharpest_night=sharpest_night(mine),
        nights=tuple(mine),
        years_with_data=all_years,
    )


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one}" if n == 1 else f"{n:,} {many}"


def year_headline(recap: YearRecap) -> str:
    """The one plain-language sentence the page leads with, e.g.

    ``"You were out under the stars on 31 nights in 2026 and collected 52.4 h
    of light on 9 targets."``

    Built from whatever is known and phrased as a person would say it, with each
    clause dropped when its figure is missing — so it never prints a zero or a
    dangling "and". Returns ``""`` for a year with nothing in it; that year's
    empty state is the caller's to write.
    """
    if not recap.has_anything or recap.n_nights <= 0:
        return ""
    sentence = (
        f"You were out under the stars on "
        f"{_plural(recap.n_nights, 'night', 'nights')} in {recap.year}"
    )
    dur = format_duration(recap.total_exposure_s)
    targets = (
        _plural(recap.n_targets, "target", "targets") if recap.n_targets > 0 else ""
    )
    if dur and targets:
        sentence += f" and collected {dur} of light on {targets}"
    elif dur:
        sentence += f" and collected {dur} of light"
    elif targets:
        sentence += f" and pointed at {targets}"
    return sentence + "."


def year_first_light_line(recap: YearRecap) -> str:
    """The "what you met for the first time" line, or ``""``.

    Spells out up to :data:`_MAX_FIRST_LIGHT_NAMES` names and counts the rest,
    the same way :func:`seestack.recap.recap_other_targets_line` does — the
    names are the part a person actually reads, and a list of forty is a table,
    not a sentence."""
    names = list(recap.first_light_names)
    if not names:
        return ""
    shown = names[:_MAX_FIRST_LIGHT_NAMES]
    rest = len(names) - len(shown)
    if rest:
        return "First light: " + ", ".join(shown) + f" and {rest:,} more"
    if len(shown) == 1:
        return f"First light: {shown[0]}"
    return "First light: " + ", ".join(shown[:-1]) + f" and {shown[-1]}"


def year_stats(recap: YearRecap) -> list[tuple[str, str]]:
    """The headline ``(value, label)`` pairs, biggest first.

    A zero or missing figure is dropped rather than printed — "0 targets" reads
    as a bug, not as a beginning — so an empty list is the caller's cue that
    there is nothing to celebrate yet.
    """
    out: list[tuple[str, str]] = []
    dur = format_duration(recap.total_exposure_s)
    if dur:
        out.append((dur, "of light collected"))
    if recap.n_nights > 0:
        out.append((f"{recap.n_nights:,}",
                    "night out" if recap.n_nights == 1 else "nights out"))
    if recap.n_targets > 0:
        out.append((f"{recap.n_targets:,}",
                    "target imaged" if recap.n_targets == 1 else "targets imaged"))
    if recap.first_light_names:
        n = len(recap.first_light_names)
        out.append((f"{n:,}", "first light" if n == 1 else "first lights"))
    if recap.n_frames > 0:
        out.append((f"{recap.n_frames:,}",
                    "sub kept" if recap.n_frames == 1 else "subs kept"))
    return out


def year_caption(recap: YearRecap) -> str:
    """The copy-paste blurb to post beside the year poster, e.g.

    ``"2026 under the stars · 31 nights out · 52.4 h of light · 9 targets ·
    first light: M 31, M 42 and 3 more"``

    Built from whatever is known, in the order a person would say it, with each
    part omitted when its figure is missing — the same voice (and the same
    middle-dot separator) as :func:`seestack.recap.recap_caption`, so a beginner
    who posts both in one week doesn't meet two different products. Returns
    ``""`` for a year with nothing in it.
    """
    if not recap.has_anything or recap.n_nights <= 0:
        return ""
    parts = [f"{recap.year} under the stars",
             _plural(recap.n_nights, "night", "nights") + " out"]
    dur = format_duration(recap.total_exposure_s)
    if dur:
        parts.append(f"{dur} of light")
    if recap.n_targets > 0:
        parts.append(_plural(recap.n_targets, "target", "targets"))
    # …and what you met for the first time. Lower case here (mid-sentence) where
    # the poster's own line is capitalised — exactly how `recap_caption` folds in
    # its "also shot" line.
    firsts = year_first_light_line(recap)
    if firsts:
        parts.append(firsts[0].lower() + firsts[1:])
    return " · ".join(parts)


def _night_date(night: NightActivity | None) -> str:
    """A night's date as a person writes it (``"12 Jan 2026"``), or ``""``."""
    from seestack.nameplate import format_acq_date

    return format_acq_date(night.date) if night is not None else ""


def year_longest_night_line(recap: YearRecap) -> str:
    """The poster's "longest night" line, or ``""`` when the year has none.

    Uses a **middle dot** rather than an em dash for the same reason
    :func:`seestack.recap.recap_top_project_line` does: Pillow's built-in font
    has no U+2014 glyph, and a tofu box on a poster is the one character the
    user is about to post publicly.
    """
    night = recap.longest_night
    when, dur = _night_date(night), format_duration(
        night.exposure_s if night is not None else None)
    if not when or not dur:
        return ""
    return f"Longest night: {when} · {dur}"


def year_sharpest_night_line(recap: YearRecap) -> str:
    """The poster's "sharpest night" footnote, or ``""``.

    Star size in pixels — the unit the Frames table, the Nights card and the
    year page all quote — so a beginner meets one number rather than three.
    """
    night = recap.sharpest_night
    when = _night_date(night)
    fwhm = night.median_fwhm_px if night is not None else None
    if not when or fwhm is None or not (fwhm > 0):
        return ""
    return f"Sharpest night: {when} · {fwhm:.1f} px stars"


def year_poster_title(recap: YearRecap) -> str:
    """The poster's headline, e.g. ``"My 2026 under the stars"``."""
    return f"My {recap.year} under the stars"


def draw_year_poster(recap: YearRecap, hero=None, *, size: int | None = None):  # noqa: ANN001
    """Render the year as one square, social-ready ``PIL.Image``.

    Deliberately a *second facts source into the same renderer* rather than a
    second poster: :func:`seestack.recap.draw_poster` owns the layout, so the
    year poster and the all-time one can never drift apart in look.

    ``hero`` is the user's own picture for the backdrop — the caller decides
    which, since only it knows the library; without one the poster falls back to
    the plain deep-space background.
    """
    from seestack.recap import POSTER_SIZE, draw_poster

    return draw_poster(
        title=year_poster_title(recap),
        stats=year_stats(recap),
        lines=(
            year_longest_night_line(recap),
            year_first_light_line(recap),
            year_sharpest_night_line(recap),
        ),
        hero=hero,
        size=POSTER_SIZE if size is None else size,
    )


def years_by_target(nights: list[NightActivity]) -> dict[str, tuple[int, ...]]:
    """Each target's imaged calendar years, ascending, over every night given.

    This is what lets a year page caption its best picture *honestly*: a target's
    newest stack is the pixels the thumbnail shows, and those pixels only belong
    to one year if the target was never imaged in another.
    """
    out: dict[str, set[int]] = {}
    for n in nights:
        year = _year_of(n)
        if year is None:
            continue
        for name in n.targets:
            if name:
                out.setdefault(name, set()).add(year)
    return {name: tuple(sorted(years)) for name, years in out.items()}


def year_hero_note(year: int, target_years: tuple[int, ...] | None) -> str:
    """The honest caveat under a year's best picture, or ``""`` when none is
    needed.

    A hero's preview is its **newest** stack, which may have been made from
    nights either side of the year — so unless the target was imaged in this
    year and no other, the page has to say so rather than implying the pixels
    are the year's. An unknown span is treated as "might span", because a
    silent overclaim is the failure mode worth avoiding.
    """
    years = tuple(target_years or ())
    if years == (int(year),):
        return ""
    return ("Your newest picture of it — it may include light from other "
            "years too.")


# Kept as a module-level name so a caller can present the same empty state the
# tests pin, rather than each surface inventing its own wording.
def year_empty_message(recap: YearRecap) -> str:
    """What to say about a year with no imaged nights — kindly, and with a way
    forward when other years do have data."""
    if recap.has_anything:
        return ""
    others = [y for y in recap.years_with_data if y != recap.year]
    if not others:
        return (
            f"No nights recorded in {recap.year} yet. Once you've captured and "
            "kept some frames, your year will appear here."
        )
    if len(others) == 1:
        return f"Nothing from {recap.year} — but {others[0]} has your nights in it."
    listed = ", ".join(str(y) for y in others[:-1])
    return (
        f"Nothing from {recap.year} — but {listed} and {others[-1]} have your "
        "nights in them."
    )


__all__ = [
    "LONGEST_MIN_NIGHTS",
    "YearRecap",
    "build_year_recap",
    "draw_year_poster",
    "first_night_by_target",
    "longest_night",
    "year_caption",
    "year_empty_message",
    "year_first_light_line",
    "year_headline",
    "year_hero_note",
    "year_longest_night_line",
    "year_poster_title",
    "year_sharpest_night_line",
    "year_stats",
    "years_by_target",
    "years_with_data",
]
