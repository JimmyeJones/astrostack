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

No webapp/DB imports — this is pure engine logic the webapp layer persists.
"""

from __future__ import annotations

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
}
_PARAM_RANGE: dict[str, tuple[float, float]] = {
    "brightness": (0.10, 0.30),
    "saturation": (1.00, 1.50),
    "sharpen":    (0.00, 1.00),
    "denoise":    (0.00, 1.00),
    "green":      (0.00, 1.00),
}

# How many steps in either direction a bias can accumulate to. Bounds the total
# shift (e.g. brightness ±3·0.02 = ±0.06, sharpen ±3·0.10 = ±0.30).
MAX_STEPS = 3

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
    return {"version": PROFILE_VERSION, "biases": {}, "counts": {}, "by_type": {}}


def _coerce_bucket(raw: Any) -> dict[str, Any]:
    """Sanitise one bias/counts bucket (the global set or a per-type override)."""
    biases: dict[str, int] = {}
    counts: dict[str, int] = {}
    if isinstance(raw, dict):
        raw_b = raw.get("biases")
        if isinstance(raw_b, dict):
            for param, val in raw_b.items():
                if param in _PARAM_STEP and isinstance(val, (int, float)):
                    step = max(-MAX_STEPS, min(MAX_STEPS, int(round(val))))
                    if step:
                        biases[param] = step
        raw_c = raw.get("counts")
        if isinstance(raw_c, dict):
            for cue, val in raw_c.items():
                if cue in _CUE_STEP and isinstance(val, (int, float)) and val > 0:
                    counts[cue] = int(round(val))
    return {"biases": biases, "counts": counts}


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
            "counts": top["counts"], "by_type": by_type}


def effective_biases(profile: dict[str, Any] | None,
                     object_type: str | None = None) -> dict[str, int]:
    """The biases that actually apply for an image of ``object_type``: the global
    set, with the per-type override taking precedence per-parameter. With no
    ``object_type`` (or an unknown one) this is just the global set — so an
    unclassified image is never shifted by a galaxy-only taste."""
    prof = _coerce(profile)
    biases = dict(prof["biases"])
    if object_type in prof["by_type"]:
        biases.update(prof["by_type"][object_type]["biases"])
        # A per-type override of 0 (walked back to neutral) drops the bias entirely.
        biases = {p: s for p, s in biases.items() if s}
    return biases


def record_feedback(profile: dict[str, Any] | None, cue: str,
                    object_type: str | None = None) -> dict[str, Any]:
    """Fold one feedback cue into the profile and return the updated copy.

    A bounded signed accumulator: pressing the same cue repeatedly saturates at
    ``±MAX_STEPS`` (never runs away); pressing the opposite cue walks the bias back
    toward neutral (so "too dark" then later "too bright" nets out). An unknown cue
    returns the profile unchanged (sanitised).

    When ``object_type`` is a known archetype the cue is recorded into that type's
    override bucket (so taste learned on galaxies doesn't move clusters); otherwise
    it updates the global set, exactly as before."""
    prof = _coerce(profile)
    step = _CUE_STEP.get(cue)
    if step is None:
        return prof
    param, delta = step
    if object_type in KNOWN_OBJECT_TYPES:
        bucket = prof["by_type"].setdefault(object_type, {"biases": {}, "counts": {}})
    else:
        bucket = prof
    cur = bucket["biases"].get(param, 0)
    new = max(-MAX_STEPS, min(MAX_STEPS, cur + delta))
    if new == 0:
        bucket["biases"].pop(param, None)
    else:
        bucket["biases"][param] = new
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
    object_type: str | None = None,
) -> dict[str, float]:
    """Shift the five data-driven Auto parameters toward the stored taste, each
    re-clamped to its safe range. An empty/None profile returns them unchanged
    (so the default Auto stays byte-for-byte identical).

    ``object_type`` (galaxy/nebula/cluster) selects the per-type override on top of
    the global set; ``None``/unknown uses the global set only."""
    biases = effective_biases(profile, object_type)
    return {
        "target_bg": _nudge(target_bg, "brightness", biases),
        "saturation": _nudge(saturation, "saturation", biases),
        "sharpen_amount": _nudge(sharpen_amount, "sharpen", biases),
        "denoise_strength": _nudge(denoise_strength, "denoise", biases),
        "scnr_amount": _nudge(scnr_amount, "green", biases),
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
}


def is_neutral(profile: dict[str, Any] | None,
               object_type: str | None = None) -> bool:
    """True when the profile has no active biases for ``object_type`` (Auto behaves
    as its data-driven default)."""
    return not effective_biases(profile, object_type)


def describe_profile(profile: dict[str, Any] | None,
                     object_type: str | None = None) -> str | None:
    """A one-line, plain-language "why" note for the UI, or ``None`` when the
    profile is neutral for ``object_type``. e.g. "Auto is running a bit brighter
    and softer for you, based on your recent feedback." — so the owner always sees
    why Auto shifted and can reset it; it never drifts silently.

    When ``object_type`` is given and it carries its own per-type override, the note
    names the archetype ("… for your galaxies …") so the owner understands the
    taste is scoped to that kind of target."""
    biases = effective_biases(profile, object_type)
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
    bucket = _coerce(profile)["by_type"].get(object_type or "", {})
    if bucket.get("biases"):
        for_whom = f"for your {_TYPE_PLURAL.get(object_type, object_type)}"
    return f"Auto is running {shifted} {for_whom}, based on your recent feedback."
