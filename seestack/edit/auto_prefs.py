"""Adaptive Auto — a small per-library "taste" profile for the one-click Auto.

The one-click Auto recipe (:func:`seestack.edit.presets.auto_recipe`) computes
every parameter *from the image* — sky level → stretch, measured noise → denoise,
star FWHM → sharpen radius, and so on. This module lets the owner nudge those
data-driven values toward *their* taste with plain-language feedback ("too dark",
"over-sharpened", …), stored as a tiny profile of **bounded biases**.

Design guarantees (see AGENTS.md §9 upgrade-safety):

* **An empty/absent profile reproduces today's Auto byte-for-byte.** The nudge is
  purely additive; a never-configured library is unchanged.
* **Every bias is clamped**, so feedback can only ever shift a parameter *a little*
  (a few gentle steps), never override the measurement or run away — no matter how
  many times the same button is pressed.
* **Still data-driven.** The bias is applied *on top of* the value Auto measured
  from the image and then re-clamped to that parameter's safe range, so a bright
  sky still stretches less than a dark one — just shifted toward the owner's taste.
* **Reversible + transparent.** The profile is a plain dict the caller stores as
  JSON; :func:`describe_profile` turns it into a one-line "why" note and the caller
  can reset it to empty at any time.
* **Recent feedback weighs more.** A bias that stops being reinforced fades one
  step per :data:`DECAY_DAYS`, so a taste the owner has moved on from returns to
  the measured default on its own instead of skewing Auto forever. The fade is
  never silent — :func:`fade_note` says it is happening.

No webapp/DB imports — this is pure engine logic the webapp layer persists.
"""

from __future__ import annotations

import time
from typing import Any

# --- the feedback vocabulary -------------------------------------------------
# Each plain-language cue the UI can send maps to one Auto parameter and a signed
# unit step (+1 = "more of it", −1 = "less"). These string keys are the stable
# contract between the frontend chips and this module — add new cues here.
_CUE_STEP: dict[str, tuple[str, int]] = {
    "too_dark":        ("brightness", +1),
    "too_bright":      ("brightness", -1),
    "too_soft":        ("sharpen",    +1),
    "over_sharpened":  ("sharpen",    -1),
    "too_noisy":       ("denoise",    +1),
    "over_smoothed":   ("denoise",    -1),
    "too_green":       ("green",      +1),
    "undersaturated":  ("saturation", +1),
    "too_saturated":   ("saturation", -1),
    "core_clipped":    ("highlights", +1),
    "core_flat":       ("highlights", -1),
}

# The parameters a bias can shift. For each: the per-step magnitude and the safe
# range the *final* (measured + bias) value is clamped to. The ranges are a touch
# wider than auto_recipe's own measurement clamps so a bias has a little room to
# move, but still firmly bounded — a runaway is impossible.
_PARAM_STEP: dict[str, float] = {
    "brightness": 0.02,   # tone.stretch target_bg
    "saturation": 0.05,   # tone.saturation amount
    "sharpen":    0.10,   # detail.sharpen amount
    "denoise":    0.10,   # detail.denoise strength
    "green":      0.10,   # tone.scnr amount
    "highlights": 0.25,   # tone.stretch "hold back highlights"
}
_PARAM_RANGE: dict[str, tuple[float, float]] = {
    "brightness": (0.10, 0.30),
    "saturation": (1.00, 1.50),
    "sharpen":    (0.00, 1.00),
    "denoise":    (0.00, 1.00),
    "green":      (0.00, 1.00),
    "highlights": (0.00, 1.00),
}

# How many steps in either direction a bias can accumulate to. Bounds the total
# shift (e.g. brightness ±3·0.02 = ±0.06, sharpen ±3·0.10 = ±0.30).
MAX_STEPS = 3

# Per-parameter floor on the accumulated bias, when it isn't the symmetric
# ``-MAX_STEPS``. ``highlights`` is the one one-sided knob: Auto measures its
# other four parameters from the image and can be nudged either way from there,
# but highlight protection starts *off* (0 = the historical stretch), so there is
# nothing below neutral to ask for. Its negative cue ("the core looks flat") is a
# walk-back to neutral rather than an opposite direction — without this floor the
# bias would keep accumulating negative steps that the range clamp swallows, so
# the walk-back would need three taps to undo one.
_PARAM_MIN_STEP: dict[str, int] = {"highlights": 0}

# --- recency decay -----------------------------------------------------------
# "Recent feedback weighs more" (the original ask), done the simplest way that a
# beginner can be told in one sentence: a bias loses **one step** for every
# ``DECAY_DAYS`` that pass without being reinforced, so a saturated ±3 taste takes
# three quiet spells to return to neutral and a single stray tap is gone in one.
# The owner shoots across seasons, so this is deliberately slow — a taste survives
# a cloudy month untouched, but doesn't outlive a change of screen or of mind.
#
# **Upgrade-safe by construction (§9):** decay is driven by a per-parameter
# ``stamps`` entry written when a cue is recorded. A profile from before this
# shipped has no stamps, so **it never decays** and reads byte-for-byte as it does
# today; its parameters start ageing only from the next tap that touches them.
DECAY_DAYS = 90.0
_DECAY_SECONDS = DECAY_DAYS * 86400.0


def _clamp_step(param: str, value: int) -> int:
    """Clamp an accumulated bias to this parameter's step range."""
    return max(_PARAM_MIN_STEP.get(param, -MAX_STEPS), min(MAX_STEPS, int(value)))


def _now(now: float | None) -> float:
    """Wall clock, injectable so tests (and the decay maths) stay deterministic."""
    return time.time() if now is None else float(now)


def _faded(step: int, stamp: float | None, now: float) -> int:
    """``step`` after recency decay: one step of magnitude dropped per
    ``DECAY_DAYS`` elapsed since ``stamp``, never crossing zero. No stamp (an
    older profile) ⇒ unchanged. A stamp in the future (clock skew) reads as
    "just now" rather than ageing backwards."""
    if not step or stamp is None:
        return step
    elapsed = max(0.0, now - stamp)
    lost = int(elapsed // _DECAY_SECONDS)
    if lost <= 0:
        return step
    magnitude = max(0, abs(step) - lost)
    return magnitude if step > 0 else -magnitude


PROFILE_VERSION = 1

# The coarse object archetypes the editor's ``classify_target`` recognises. A
# profile keeps one *global* bias set plus an optional per-type override for each
# of these, so a "brighter core" taste learned on galaxies doesn't also brighten a
# star cluster. Any other/unclassified image just uses the global set.
KNOWN_OBJECT_TYPES: tuple[str, ...] = ("galaxy", "nebula", "cluster")

# Friendly plurals for the per-type "why" note.
_TYPE_PLURAL: dict[str, str] = {
    "galaxy": "galaxies", "nebula": "nebulae", "cluster": "star clusters",
}


def known_cues() -> tuple[str, ...]:
    """The feedback cue keys this module understands (for validation/UX)."""
    return tuple(_CUE_STEP.keys())


def empty_profile() -> dict[str, Any]:
    """A neutral profile — equivalent to no profile at all (today's Auto)."""
    return {"version": PROFILE_VERSION, "biases": {}, "counts": {},
            "stamps": {}, "by_type": {}}


def _coerce_bucket(raw: Any) -> dict[str, Any]:
    """Sanitise one bias/counts/stamps bucket (the global set or a per-type
    override). A bucket with no ``stamps`` — every profile written before recency
    decay shipped — is kept exactly as it is; it simply never fades."""
    biases: dict[str, int] = {}
    counts: dict[str, int] = {}
    stamps: dict[str, float] = {}
    if isinstance(raw, dict):
        raw_b = raw.get("biases")
        if isinstance(raw_b, dict):
            for param, val in raw_b.items():
                if param in _PARAM_STEP and isinstance(val, (int, float)):
                    step = _clamp_step(param, round(val))
                    if step:
                        biases[param] = step
        raw_c = raw.get("counts")
        if isinstance(raw_c, dict):
            for cue, val in raw_c.items():
                if cue in _CUE_STEP and isinstance(val, (int, float)) and val > 0:
                    counts[cue] = int(round(val))
        raw_s = raw.get("stamps")
        if isinstance(raw_s, dict):
            for param, val in raw_s.items():
                # A stamp only means anything alongside a live bias, and a
                # non-finite/negative epoch is garbage from a broken store.
                if (param in biases and isinstance(val, (int, float))
                        and not isinstance(val, bool) and val > 0
                        and val == val and val != float("inf")):
                    stamps[param] = float(val)
    return {"biases": biases, "counts": counts, "stamps": stamps}


def _coerce(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Return a sanitised copy: only known params/cues/types, ints clamped.

    Tolerant of anything an older/garbled store might hold (a §9 upgrade-safe
    loader never raises — an unreadable profile degrades to neutral). An older
    profile with no ``by_type`` key simply yields an empty per-type map, so it
    keeps behaving exactly as its global biases dictate."""
    # The global set lives at the top level of the profile (back-compat with the
    # original flat shape).
    top = _coerce_bucket(profile)
    by_type: dict[str, Any] = {}
    if isinstance(profile, dict):
        raw_t = profile.get("by_type")
        if isinstance(raw_t, dict):
            for otype, bucket in raw_t.items():
                if otype in KNOWN_OBJECT_TYPES:
                    cb = _coerce_bucket(bucket)
                    if cb["biases"] or cb["counts"]:
                        by_type[otype] = cb
    return {"version": PROFILE_VERSION, "biases": top["biases"],
            "counts": top["counts"], "stamps": top["stamps"], "by_type": by_type}


def _bucket_biases(bucket: dict[str, Any], now: float) -> dict[str, int]:
    """One bucket's biases after recency decay, zeros dropped."""
    stamps = bucket.get("stamps") or {}
    out = {}
    for param, step in bucket["biases"].items():
        faded = _faded(step, stamps.get(param), now)
        if faded:
            out[param] = faded
    return out


def effective_biases(profile: dict[str, Any] | None,
                     object_type: str | None = None,
                     now: float | None = None) -> dict[str, int]:
    """The biases that actually apply for an image of ``object_type``: the global
    set, with the per-type override taking precedence per-parameter. With no
    ``object_type`` (or an unknown one) this is just the global set — so an
    unclassified image is never shifted by a galaxy-only taste.

    Each bias is returned **after recency decay** (see :data:`DECAY_DAYS`), so a
    taste that stopped being reinforced has already faded by the time Auto reads
    it. A stored bias whose per-type override has faded to nothing falls back to
    the global set, which is the same rule a walked-back override follows."""
    at = _now(now)
    prof = _coerce(profile)
    biases = _bucket_biases(prof, at)
    if object_type in prof["by_type"]:
        biases.update(_bucket_biases(prof["by_type"][object_type], at))
        # A per-type override of 0 (walked back to neutral) drops the bias entirely.
        biases = {p: s for p, s in biases.items() if s}
    return biases


def record_feedback(profile: dict[str, Any] | None, cue: str,
                    object_type: str | None = None,
                    now: float | None = None) -> dict[str, Any]:
    """Fold one feedback cue into the profile and return the updated copy.

    A bounded signed accumulator: pressing the same cue repeatedly saturates at
    ``±MAX_STEPS`` (never runs away); pressing the opposite cue walks the bias back
    toward neutral (so "too dark" then later "too bright" nets out). An unknown cue
    returns the profile unchanged (sanitised).

    When ``object_type`` is a known archetype the cue is recorded into that type's
    override bucket (so taste learned on galaxies doesn't move clusters); otherwise
    it updates the global set, exactly as before.

    The parameter being touched is **aged first** (:data:`DECAY_DAYS`), so a tap
    builds on the taste that is actually in force rather than on a stale saturated
    value the owner stopped meaning years ago; it is then re-stamped, which restarts
    that parameter's fade."""
    prof = _coerce(profile)
    step = _CUE_STEP.get(cue)
    if step is None:
        return prof
    at = _now(now)
    param, delta = step
    if object_type in KNOWN_OBJECT_TYPES:
        bucket = prof["by_type"].setdefault(
            object_type, {"biases": {}, "counts": {}, "stamps": {}})
    else:
        bucket = prof
    stamps = bucket.setdefault("stamps", {})
    cur = _faded(bucket["biases"].get(param, 0), stamps.get(param), at)
    new = _clamp_step(param, cur + delta)
    if new == 0:
        bucket["biases"].pop(param, None)
        stamps.pop(param, None)
    else:
        bucket["biases"][param] = new
        stamps[param] = at
    bucket["counts"][cue] = bucket["counts"].get(cue, 0) + 1
    return prof


def _nudge(value: float, param: str, biases: dict[str, int]) -> float:
    step = biases.get(param, 0)
    if not step:
        return value
    lo, hi = _PARAM_RANGE[param]
    return float(min(hi, max(lo, value + step * _PARAM_STEP[param])))


def apply_profile(
    profile: dict[str, Any] | None,
    *,
    target_bg: float,
    saturation: float,
    sharpen_amount: float,
    denoise_strength: float,
    scnr_amount: float,
    highlight_protect: float = 0.0,
    object_type: str | None = None,
    now: float | None = None,
) -> dict[str, float]:
    """Shift the data-driven Auto parameters toward the stored taste, each
    re-clamped to its safe range. An empty/None profile returns them unchanged
    (so the default Auto stays byte-for-byte identical).

    ``highlight_protect`` is the ``tone.stretch`` "hold back highlights" strength;
    it defaults to 0 (off) both here and in ``auto_recipe``, so a caller that
    doesn't pass it — and any profile with no ``highlights`` bias — is unaffected.

    ``object_type`` (galaxy/nebula/cluster) selects the per-type override on top of
    the global set; ``None``/unknown uses the global set only. ``now`` is the clock
    the recency decay is measured against (defaults to wall time)."""
    biases = effective_biases(profile, object_type, now)
    return {
        "target_bg": _nudge(target_bg, "brightness", biases),
        "saturation": _nudge(saturation, "saturation", biases),
        "sharpen_amount": _nudge(sharpen_amount, "sharpen", biases),
        "denoise_strength": _nudge(denoise_strength, "denoise", biases),
        "scnr_amount": _nudge(scnr_amount, "green", biases),
        "highlight_protect": _nudge(highlight_protect, "highlights", biases),
    }


# Plain-language fragment for each biased parameter, keyed by (param, sign>0).
_BIAS_PHRASE: dict[tuple[str, bool], str] = {
    ("brightness", True): "a bit brighter",
    ("brightness", False): "a bit darker",
    ("saturation", True): "more colourful",
    ("saturation", False): "less saturated",
    ("sharpen", True): "a little sharper",
    ("sharpen", False): "softer",
    ("denoise", True): "with more noise reduction",
    ("denoise", False): "with less smoothing",
    ("green", True): "with a stronger green-cast removal",
    ("green", False): "with a lighter green-cast removal",
    # ``highlights`` is one-sided (see ``_PARAM_MIN_STEP``): the negative cue only
    # walks the bias back to neutral, which drops it from the profile entirely, so
    # there is no "less than off" phrase to write.
    ("highlights", True): "with the bright cores held back",
}


def is_neutral(profile: dict[str, Any] | None,
               object_type: str | None = None,
               now: float | None = None) -> bool:
    """True when the profile has no active biases for ``object_type`` (Auto behaves
    as its data-driven default) — including when the last of them has faded away."""
    return not effective_biases(profile, object_type, now)


def steps_faded(profile: dict[str, Any] | None,
                object_type: str | None = None,
                now: float | None = None) -> int:
    """How many bias steps recency decay has dropped from the taste that applies to
    ``object_type`` — 0 when nothing has faded (which includes every profile written
    before decay shipped, since those carry no stamps).

    This is what makes the fade *visible* rather than a silent drift: the caller
    turns a non-zero answer into :func:`fade_note`."""
    at = _now(now)
    prof = _coerce(profile)
    # Counted per **bucket**, over the ones that feed this object_type's taste,
    # rather than by differencing the merged result. A faded per-type override
    # stops winning and hands its parameter back to the global bias it was
    # hiding, so the *merged* magnitude for that parameter can go **up** even
    # though both buckets faded — differencing would net a real fade away to
    # nothing. ``_faded`` only ever reduces magnitude, so every term is ≥ 0.
    buckets = [prof]
    if object_type in prof["by_type"]:
        buckets.append(prof["by_type"][object_type])
    total = 0
    for bucket in buckets:
        stamps = bucket.get("stamps") or {}
        for param, step in bucket["biases"].items():
            total += abs(step) - abs(_faded(step, stamps.get(param), at))
    return total


def fade_note(profile: dict[str, Any] | None,
              object_type: str | None = None,
              now: float | None = None) -> str | None:
    """A plain-language line for the UI when recency decay has actually moved
    something, or ``None``. Two shapes, because the case that most needs explaining
    is the one where the "why Auto shifted" note has vanished entirely: a taste
    still partly in force says it is easing off; a fully faded one says Auto is back
    to its measured default and why."""
    if not steps_faded(profile, object_type, now):
        return None
    if is_neutral(profile, object_type, now):
        return ("Your older feedback has faded, so Auto is back to its measured "
                "default — tap again any time to lean it back.")
    return ("Older feedback is gently fading, so Auto drifts back toward its "
            "measured default unless you keep nudging it.")


def describe_profile(profile: dict[str, Any] | None,
                     object_type: str | None = None,
                     now: float | None = None) -> str | None:
    """A one-line, plain-language "why" note for the UI, or ``None`` when the
    profile is neutral for ``object_type``. e.g. "Auto is running a bit brighter
    and softer for you, based on your recent feedback." — so the owner always sees
    why Auto shifted and can reset it; it never drifts silently.

    When ``object_type`` is given and it carries its own per-type override, the note
    names the archetype ("… for your galaxies …") so the owner understands the
    taste is scoped to that kind of target. A bias that recency decay has faded
    away is already gone from the note — see :func:`fade_note`, which says so."""
    biases = effective_biases(profile, object_type, now)
    if not biases:
        return None
    parts = [
        _BIAS_PHRASE[(param, step > 0)]
        for param, step in biases.items()
        if (param, step > 0) in _BIAS_PHRASE
    ]
    if not parts:
        return None
    if len(parts) == 1:
        shifted = parts[0]
    elif len(parts) == 2:
        shifted = f"{parts[0]} and {parts[1]}"
    else:
        shifted = f"{', '.join(parts[:-1])}, and {parts[-1]}"
    # Name the archetype only when this type actually carries its own bias override
    # (otherwise it's the global taste, which applies to every kind of target — a
    # bucket that walked back to neutral keeps only its counts, not a bias).
    for_whom = "for you"
    bucket = _coerce(profile)["by_type"].get(object_type or "")
    # ...and only while that override is still *in force*: one faded to nothing
    # falls back to the global taste, so naming the archetype would be a lie.
    if bucket and _bucket_biases(bucket, _now(now)):
        for_whom = f"for your {_TYPE_PLURAL.get(object_type, object_type)}"
    return f"Auto is running {shifted} {for_whom}, based on your recent feedback."
