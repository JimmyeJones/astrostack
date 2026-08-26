"""How far did you just see? — light-travel time for a captured object.

A beginner who stacks a faint grey smudge has no intuitive sense of what they
just did. The single most striking fact about it is *when the light left*: the
photons in an Andromeda picture started their journey before our species
existed. That one sentence turns a smudge into a genuine wow moment, and it is
the kind of thing people screenshot and share.

Distance in light-years **is** the travel time in years, so this needs no
astronomy at all — just the object's distance from the bundled catalog and some
care about wording. Pure, offline, no dependency.

Two rules keep it honest:

  * **Never guess.** ``None`` for an object with no vetted ``distance_ly``, so
    the card simply says nothing — the same discipline ``size_arcmin`` and the
    framing hint already use.
  * **Only comparisons that are true across their whole band.** Each historical
    anchor below is chosen so it holds for *every* distance in its band, with
    room to spare, rather than being cute at one end and wrong at the other.
    The number is always stated too, so the sentence still carries the fact even
    where no anchor applies.
"""

from __future__ import annotations

from dataclasses import dataclass

# Historical anchors, as ``(minimum distance in light-years, phrase)``, most
# distant first. Each phrase must be true for *every* distance at or above its
# threshold — that is what makes this safe to render without a per-object check:
#
#   1 Mly     Homo sapiens is ~300,000 years old, so any megalight-year object's
#             light predates our species by a wide margin.
#   100 kly   Comfortably older than any human record of anything.
#   10 kly    The first cities are ~6,000 years old.
#   2 kly     The western Roman Empire fell ~1,550 years ago.
#   500 ly    The telescope was invented in 1608, ~420 years ago.
#
# Below 500 ly there is no anchor that stays true across the band, so nothing is
# claimed and the sentence is just the (still striking) number.
_ANCHORS: tuple[tuple[float, str], ...] = (
    (1_000_000, "before our species existed"),
    (100_000, "long before recorded history"),
    (10_000, "before the first cities were built"),
    (2_000, "before the Roman Empire fell"),
    (500, "before the telescope was invented"),
)


@dataclass(frozen=True)
class LightTravel:
    """A ready-to-render "how far did you see?" line for a captured object."""

    distance_ly: float   # the catalog distance this was built from
    years: str           # the friendly duration alone, e.g. "2.5 million years"
    text: str            # the full sentence, ready to render


def _friendly_years(distance_ly: float) -> str:
    """A distance in light-years as a friendly duration.

    Rounded hard on purpose: published distances to deep-sky objects carry real
    uncertainty, and "about 2.5 million years" is right whether the catalog says
    2.48 or 2.54 Mly. One decimal below ten of a unit and whole numbers above
    it. The "thousand" wording only starts at ten thousand — "1.3 thousand
    years" is clumsier than the plain "1,340 years" a beginner reads at a
    glance — and below that it's the comma-grouped number, to the nearest ten.
    """
    for unit, name, floor in ((1_000_000.0, "million", 1_000_000.0),
                              (1_000.0, "thousand", 10_000.0)):
        if distance_ly >= floor:
            v = distance_ly / unit
            shown = f"{v:.1f}".rstrip("0").rstrip(".") if v < 10 else f"{v:.0f}"
            return f"{shown} {name} years"
    n = max(10, int(round(distance_ly / 10.0)) * 10)
    return f"{n:,} years"


def light_travel(distance_ly: float | None) -> LightTravel | None:
    """The "the light in this picture left N years ago" line, or ``None``.

    Returns ``None`` for a missing or non-positive distance — never a guess, so
    an object the catalog hasn't got a vetted distance for renders nothing at
    all rather than a made-up number.
    """
    if distance_ly is None or distance_ly <= 0:
        return None
    years = _friendly_years(float(distance_ly))
    anchor = next((phrase for floor, phrase in _ANCHORS if distance_ly >= floor), None)
    text = f"The light in this picture left about {years} ago"
    text += f" — {anchor}." if anchor else "."
    return LightTravel(distance_ly=float(distance_ly), years=years, text=text)
