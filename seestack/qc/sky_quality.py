"""How bright was the sky? — a night-by-night read on the observer's own sky.

A Seestar owner has no sky-quality meter and no way to know whether last night's
sky was unusually bright — yet that is exactly what decides whether a faint
nebula was ever going to work, and the most common reason a night's result comes
out washed out with a strong gradient. We already measure ``sky_adu_median`` on
every sub during QC, so the raw material is sitting in the frames table.

What this module deliberately does *not* do is claim an **absolute** sky
brightness (a Bortle class or mag/arcsec²). Turning ADU into surface brightness
needs per-model, per-gain calibration of the Seestar's optics and sensor that we
have no validated numbers for, and a confidently-wrong "your sky is Bortle 4"
would be worse than saying nothing. Instead it answers the question a beginner
can actually act on, using only their own data as the yardstick:

    *"Was the sky on this night brighter than it usually is here?"*

Method
------
1. Keep only frames with a usable sky measurement and a positive exposure.
2. Group by ``(gain, exposure_s)`` and keep the **largest** group. Sky ADU scales
   with both, so mixing a 10 s and a 30 s sub would read as a sky change that
   isn't one. A Seestar shoots a whole session at one setting, so the dominant
   group is normally every frame of every night.
3. Within that group, each frame's sky **rate** is ``sky_adu_median /
   exposure_s``. Take a per-night median (robust to a passing cloud or a
   satellite), bucketing by observing night (local noon-to-noon, the same
   convention the activity calendar uses, so subs either side of midnight are one
   night).
4. Compare the most recent night's rate against the median of this target's
   **other** nights — leave-one-out, so a night is never part of the yardstick
   it is measured against (the same rule
   :func:`seestack.session_recap._typical_other_fwhm` and
   :func:`seestack.activity_calendar.off_night` already follow, and the same
   rule the card's own wording — "compared with your other N nights" — has
   always promised). Including it made the card quietly self-cancelling: on an
   odd number of nights, a night that *is* the median is its own baseline, so
   the ratio is exactly 1.0 and the verdict is "typical" by construction, and
   on any count a genuinely unusual night drags the yardstick toward itself and
   under-reports how unusual it was. The ratio is what gets bucketed and
   phrased.

Everything here is pure and deterministic, so it is unit-testable without a DB.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from seestack.activity_calendar import night_date_of

# A night needs this many measured subs before its median rate is trustworthy —
# fewer and one hazy patch of sky sets the whole verdict.
MIN_FRAMES_PER_NIGHT = 5
# And we need this many qualifying nights before "brighter than usual" means
# anything at all: with one or two nights there is no "usual" to compare against,
# so the card stays hidden rather than guessing.
MIN_NIGHTS = 3

# Ratio of latest-night rate to the target's median night. Chosen wide enough
# that ordinary night-to-night variation (transparency, altitude, a little moon)
# reads as "typical" rather than crying wolf.
_DARKER_BELOW = 0.80
_BRIGHTER_ABOVE = 1.25
_MUCH_BRIGHTER_ABOVE = 1.80


@dataclass(frozen=True)
class SkyBrightnessRead:
    """A plain-language read on the latest night's sky brightness."""

    level: str          # 'darker' | 'typical' | 'brighter' | 'much_brighter'
    label: str          # short chip text
    text: str           # one-sentence explanation + what to do about it
    night: str          # ISO date of the night being reported (YYYY-MM-DD)
    # How many nights the comparison is based on — the reported night's own
    # **other** nights, never itself (see the module docstring's step 4). It is
    # what the card's "compared with your other N nights" counts, so a target
    # with three qualifying nights reports 2.
    nights: int
    ratio: float        # latest night's sky rate ÷ the median of the others

    def as_dict(self) -> dict:
        return {
            "level": self.level, "label": self.label, "text": self.text,
            "night": self.night, "nights": self.nights,
            "ratio": round(self.ratio, 3),
        }


@dataclass(frozen=True)
class SkySample:
    """One frame's sky measurement, as stored on the frames row."""

    timestamp_utc: str | None
    sky_adu_median: float | None
    exposure_s: float | None
    gain: float | None


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])


def night_sky_rates(
    samples: Iterable[SkySample], *, lon_deg: float | None = None,
) -> dict[date, float]:
    """Per-observing-night median sky rate (ADU/s), for the dominant setting.

    Returns an empty dict when nothing usable survives the filters. Exposed
    separately from :func:`sky_brightness` so a caller (or a test) can inspect
    the underlying trend rather than only the verdict.
    """
    by_setting: dict[tuple[float, float], list[tuple[date, float]]] = {}
    for s in samples:
        sky, exposure = s.sky_adu_median, s.exposure_s
        if sky is None or exposure is None or not s.timestamp_utc:
            continue
        try:
            sky_f, exp_f = float(sky), float(exposure)
        except (TypeError, ValueError):
            continue
        # A non-positive or non-finite exposure can't normalise anything, and a
        # negative sky measurement is a bad row rather than a dark sky.
        if not (exp_f > 0.0) or sky_f < 0.0 or sky_f != sky_f or exp_f != exp_f:
            continue
        night = night_date_of(s.timestamp_utc, lon_deg)
        if night is None:
            continue
        gain = 0.0 if s.gain is None else float(s.gain)
        by_setting.setdefault((gain, exp_f), []).append((night, sky_f / exp_f))

    if not by_setting:
        return {}
    # The setting the owner actually shot most of this target at.
    dominant = max(by_setting.values(), key=len)
    per_night: dict[date, list[float]] = {}
    for night, rate in dominant:
        per_night.setdefault(night, []).append(rate)
    return {night: _median(rates) for night, rates in sorted(per_night.items())
            if len(rates) >= MIN_FRAMES_PER_NIGHT}


def _phrase(level: str, ratio: float, nights: int) -> tuple[str, str]:
    """Label + sentence for one verdict. ``nights`` is the number of **other**
    nights behind the baseline, which is what "your other N nights" counts."""
    percent = abs(round((ratio - 1.0) * 100))
    if level == "darker":
        return ("Darker than usual", (
            f"The sky on this night measured about {percent}% darker than your "
            f"typical night on this target — good conditions. Faint nebulae and "
            f"galaxies have the best chance on nights like this."
        ))
    if level == "brighter":
        return ("Brighter than usual", (
            f"The sky on this night measured about {percent}% brighter than your "
            f"typical night on this target — moonlight, haze or light pollution. "
            f"Expect a flatter, washed-out result on faint targets; bright "
            f"galaxies, clusters and the Moon cope much better."
        ))
    if level == "much_brighter":
        return ("Much brighter than usual", (
            f"The sky on this night measured about {percent}% brighter than your "
            f"typical night on this target — a strongly lit sky (a bright Moon or "
            f"heavy haze). Faint detail is unlikely to come through no matter how "
            f"many subs you stack; save this target for a darker night."
        ))
    return ("Typical for your sky", (
        f"The sky on this night was about as bright as your other "
        f"{nights} nights on this target — nothing unusual to explain the result."
    ))


def sky_brightness(
    samples: Iterable[SkySample], *, lon_deg: float | None = None,
) -> SkyBrightnessRead | None:
    """Read the latest night's sky brightness against this target's own history.

    Returns ``None`` — meaning "say nothing" — whenever the data can't support an
    honest answer: no sky measurements, too few subs per night, or fewer than
    :data:`MIN_NIGHTS` nights to form a "usual" to compare against.
    """
    rates = night_sky_rates(samples, lon_deg=lon_deg)
    if len(rates) < MIN_NIGHTS:
        return None
    nights = sorted(rates)
    latest = nights[-1]
    # Leave-one-out: the latest night is never part of its own yardstick (see
    # the module docstring). ``MIN_NIGHTS`` is 3, so there are always at least
    # two others — the gate on when the card appears at all is unchanged.
    others = [rates[n] for n in nights[:-1]]
    baseline = _median(others)
    if not (baseline > 0.0):
        return None
    ratio = rates[latest] / baseline

    if ratio < _DARKER_BELOW:
        level = "darker"
    elif ratio > _MUCH_BRIGHTER_ABOVE:
        level = "much_brighter"
    elif ratio > _BRIGHTER_ABOVE:
        level = "brighter"
    else:
        level = "typical"
    label, text = _phrase(level, ratio, len(others))
    return SkyBrightnessRead(
        level=level, label=label, text=text, night=latest.isoformat(),
        nights=len(others), ratio=ratio,
    )
