"""How big is it, really? — an object's angular size in full Moons.

A beginner reads *"M 31 · 178 arcmin"* and it means nothing: arcminutes are an
expert unit, and nobody has an intuition for them. But *"about as wide as 6 full
Moons"* lands instantly — and "Andromeda is six Moons across" is one of the
classic wow-facts that make a newcomer fall for this hobby.

The full Moon is the **only** angular yardstick a non-astronomer already owns, so
it is the only comparison made here: no degrees, no fists at arm's length, no
"twice the Ring Nebula". Pure, offline, no dependency — it takes the major-axis
size the bundled catalog already stores and returns one ready-to-render sentence.

Two rules keep it honest, the same two :mod:`seestack.lighttravel` uses:

  * **Never guess.** ``None`` for a missing or non-positive size, so the card
    simply says nothing.
  * **Only comparisons that are true across their whole band.** Every phrase
    below holds for *every* size in its band — that is what makes it safe to
    render without a per-object check. The bands sit within about ±20 % of the
    fraction they name, which is inside the spread of published catalog sizes
    anyway (an object's "size" depends on how faint an isophote you measure to).

It also **stays quiet on small targets** (below about a third of a Moon). Down
there the comparison stops being illuminating — "well under the full Moon" says
nothing a beginner can picture — and the framing line right above it already
tells them it fits comfortably in one frame. One fewer always-on line beats a
line that adds nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Apparent diameter of the full Moon, in arcminutes. It varies over the month
# (~29.4' at apogee to ~33.5' at perigee); 31' is the round middle, and every
# band below is wide enough that the variation cannot flip a verdict.
MOON_DIAMETER_ARCMIN = 31.0

# Below this many Moons there is no comparison worth making — see the module
# docstring. ~9' at a 31' Moon, i.e. comfortably inside a single Seestar frame.
_QUIET_BELOW_MOONS = 0.28

# Sub-Moon bands, as ``(minimum ratio, sentence)``, largest first. Each sentence
# is true across its whole band: 0.6–0.8 → "three-quarters" (0.75 ±20 %),
# 0.4–0.6 → "half" (0.5 ±20 %), 0.28–0.4 → "a third" (0.33 ±20 %). The top band
# runs to :data:`_COUNT_FROM_MOONS`, where counting whole Moons takes over.
_FRACTION_BANDS: tuple[tuple[float, str], ...] = (
    (0.8, "In the sky it's roughly as wide as the full Moon."),
    (0.6, "In the sky it's about three-quarters as wide as the full Moon."),
    (0.4, "In the sky it's about half as wide as the full Moon."),
    (_QUIET_BELOW_MOONS, "In the sky it's about a third as wide as the full Moon."),
)

# At or above this many Moons the sentence counts Moons instead of naming a
# fraction of one. Chosen so the smallest count it can produce is "1½" — a bare
# "1 full Moon" is what the band below already says, better.
_COUNT_FROM_MOONS = 1.3

# Up to this count, round to the nearest half ("1½", "2½") — a beginner can
# picture two-and-a-half Moons side by side. Above it, halves are false
# precision, so it's whole Moons.
_HALVES_BELOW_MOONS = 3.0


@dataclass(frozen=True)
class AngularSize:
    """A ready-to-render "how big is it?" line for a captured object."""

    size_arcmin: float   # the catalog major-axis size this was built from
    moons: float         # that size in full-Moon widths, unrounded
    text: str            # the full sentence, ready to render


def _friendly_moons(moons: float) -> str:
    """A Moon count rounded hard for a beginner: ``"1½"``, ``"2"``, ``"6"``.

    Never a decimal — a beginner wants "6 Moons", never "5.74 Moons". Halves are
    kept only while they still mean something (below
    :data:`_HALVES_BELOW_MOONS`); above that the count is whole.
    """
    if moons < _HALVES_BELOW_MOONS:
        halves = int(math.floor(moons * 2.0 + 0.5))
        whole, half = divmod(halves, 2)
        if half:
            return f"{whole}½" if whole else "½"
        return str(whole)
    return f"{int(math.floor(moons + 0.5)):,}"


def angular_size(
    size_arcmin: float | None,
    *,
    moon_arcmin: float = MOON_DIAMETER_ARCMIN,
) -> AngularSize | None:
    """The "how big is it, really?" line for an object, or ``None``.

    ``size_arcmin`` is the major axis, as the bundled catalog records it.
    Returns ``None`` for a missing, non-positive or non-finite size — and also
    for anything below about a third of a Moon, where the comparison stops
    saying anything useful (see the module docstring). The caller renders
    nothing at all in either case, rather than a line that means nothing.
    """
    if size_arcmin is None:
        return None
    size = float(size_arcmin)
    if not math.isfinite(size) or size <= 0:
        return None
    if not math.isfinite(moon_arcmin) or moon_arcmin <= 0:
        return None

    moons = size / float(moon_arcmin)
    if moons < _QUIET_BELOW_MOONS:
        return None

    if moons >= _COUNT_FROM_MOONS:
        count = _friendly_moons(moons)
        # "1 full Moons" can't happen (the band floor rounds to 1½ at worst), but
        # a caller passing a custom ``moon_arcmin`` shouldn't be able to make the
        # sentence ungrammatical either.
        noun = "full Moon" if count == "1" else "full Moons"
        text = f"In the sky it's about as wide as {count} {noun}."
    else:
        text = next(sentence for floor, sentence in _FRACTION_BANDS if moons >= floor)

    return AngularSize(size_arcmin=size, moons=moons, text=text)
