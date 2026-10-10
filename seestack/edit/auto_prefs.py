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
from collections.abc import Iterable
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
    # The walk-back for "too green", and the one direction this vocabulary was
    # missing. ``green`` was the only one of the six parameters a cue could move
    # in a single direction: three "too green" taps take Auto's SCNR amount
    # 0.7 -> 1.0 (full green-cast removal) and nothing short of resetting the
    # *whole* profile could bring it back — while ``_BIAS_PHRASE`` already held
    # the sentence for a negative green bias ("with a lighter green-cast
    # removal") that no cue could produce. Unlike ``highlights`` (which starts at
    # the bottom of its range, see ``_PARAM_MIN_STEP``) less green removal is a
    # real taste, not just a walk-back to off, so this is symmetric: +-3 steps
    # span 0.4..1.0.
    #
    # Named for the symptom the user can see, like every other cue, and in the
    # words the editor already uses for it: over-strong SCNR rectifies the
    # green noise and drags the sky magenta, and the histogram read-out two
    # lines up says so ("Sky background has a magenta cast",
    # ``frontend/src/components/editor/skyCast.ts``). Until now that read-out
    # named a problem the feedback row had no chip for.
    "too_magenta":     ("green",      -1),
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
# other five parameters from the image (or, for ``green``, sets them) and each
# can be nudged either way from there, but highlight protection starts *off*
# (0 = the historical stretch), so there is nothing below neutral to ask for.
# Its negative cue ("the core looks flat") is a walk-back to neutral rather
# than an opposite direction — without this floor the bias would keep
# accumulating negative steps that the range clamp swallows, so the walk-back
# would need three taps to undo one.
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


def profile_of_biases(biases: dict[str, int]) -> dict[str, Any]:
    """A profile whose :func:`effective_biases` is exactly ``biases`` — for every
    ``object_type`` and at any ``now``.

    Not a store shape anybody persists: it is the "what if the taste were *this*
    instead?" input a caller needs to ask what one of the stored biases is
    actually doing to a picture. It carries no ``stamps`` (so recency decay never
    touches it) and no ``by_type`` overrides (so the answer cannot depend on which
    archetype it is read for), which is what makes it a faithful stand-in for a
    taste the caller has already resolved — see
    ``seestack.edit.presets.inert_bias_params``.
    """
    prof = empty_profile()
    prof["biases"] = {param: int(step) for param, step in biases.items() if step}
    return prof


def _coerce_bucket(raw: Any, *, keep_zero: bool = False) -> dict[str, Any]:
    """Sanitise one bias/counts/stamps bucket (the global set or a per-type
    override). A bucket with no ``stamps`` — every profile written before recency
    decay shipped — is kept exactly as it is; it simply never fades.

    ``keep_zero`` keeps a stored bias of **exactly 0**, which only a per-type
    bucket ever writes and which means something there that it cannot mean
    globally: "for this kind of target, no shift" — an override that cancels a
    non-zero global taste rather than deferring to it. See
    :func:`record_feedback`. A global 0 is still dropped (nothing to override)."""
    biases: dict[str, int] = {}
    counts: dict[str, int] = {}
    stamps: dict[str, float] = {}
    if isinstance(raw, dict):
        raw_b = raw.get("biases")
        if isinstance(raw_b, dict):
            for param, val in raw_b.items():
                if param in _PARAM_STEP and isinstance(val, (int, float)):
                    step = _clamp_step(param, round(val))
                    if step or keep_zero:
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
                    cb = _coerce_bucket(bucket, keep_zero=True)
                    if cb["biases"] or cb["counts"]:
                        by_type[otype] = cb
    return {"version": PROFILE_VERSION, "biases": top["biases"],
            "counts": top["counts"], "stamps": top["stamps"], "by_type": by_type}


def _bucket_biases(bucket: dict[str, Any], now: float, *,
                   keep_zero: bool = False) -> dict[str, int]:
    """One bucket's biases after recency decay, zeros dropped.

    ``keep_zero`` keeps a per-type bucket's **stored** 0 so it can *override* a
    non-zero global bias to neutral (the caller drops it from the merged result);
    without it the 0 would vanish and the global taste would silently win back.
    A bias that merely *faded* to 0 is still dropped either way — an override that
    has expired is meant to hand its parameter back to the global taste."""
    stamps = bucket.get("stamps") or {}
    out = {}
    for param, step in bucket["biases"].items():
        faded = _faded(step, stamps.get(param), now)
        if faded or (keep_zero and step == 0):
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
        biases.update(
            _bucket_biases(prof["by_type"][object_type], at, keep_zero=True))
        # A per-type override of 0 (walked back to neutral) drops the bias entirely
        # — including when it is cancelling a non-zero *global* bias, which is the
        # whole reason that 0 is stored rather than dropped at write time.
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
    # The global bias for this parameter, aged — i.e. what Auto is doing *right
    # now* for a target of this type before the tap, whenever the tap is going to
    # land in a per-type bucket that doesn't yet speak about this parameter.
    global_step = _faded(
        prof["biases"].get(param, 0), (prof.get("stamps") or {}).get(param), at)
    if object_type in KNOWN_OBJECT_TYPES:
        bucket = prof["by_type"].setdefault(
            object_type, {"biases": {}, "counts": {}, "stamps": {}})
        per_type = True
    else:
        bucket = prof
        per_type = False
        global_step = 0  # the global set *is* the bucket; there is nothing to seed
    stamps = bucket.setdefault("stamps", {})
    if per_type and param not in bucket["biases"]:
        # **Seed from the taste in force, not from neutral.** A per-type bucket
        # overrides the global one per parameter, so starting a fresh override at 0
        # made the first type-scoped tap *replace* the global value instead of
        # moving it one step: with a global "+2 brighter", one "too bright" on a
        # galaxy landed at −1 — a three-step jump in the direction the owner did
        # not ask for, and +1 was unreachable (tapping back returned to +2, so the
        # taste oscillated between two wrong values). Seeding makes one tap one
        # step, whichever bucket it lands in.
        cur = global_step
    else:
        cur = _faded(bucket["biases"].get(param, 0), stamps.get(param), at)
    new = _clamp_step(param, cur + delta)
    if new == 0 and not (per_type and global_step):
        bucket["biases"].pop(param, None)
        stamps.pop(param, None)
    else:
        # A per-type 0 is kept when there is a non-zero global bias underneath it:
        # dropping it would hand the parameter straight back to the global taste,
        # so "neutral for galaxies" would be the one setting the owner could never
        # reach — the same off-by-a-bucket jump as above, one step further on.
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


# --- "that tap changed nothing" ---------------------------------------------
# A tap can land somewhere it has no room to move, and in two different ways.
# **The taste is at its limit:** the bias is already at ``MAX_STEPS`` (or at a
# ``_PARAM_MIN_STEP`` floor), so a fourth identical tap stores nothing new.
# **This picture is at its limit:** the bias moves, but the value Auto measured
# for *this* image already sits at the end of its ``_PARAM_RANGE``, so ``_nudge``
# clamps the shift away. The second one is not an edge case — it is the ordinary
# state of a deep, clean mosaic, where ``auto_recipe`` leaves ``denoise_strength``
# at exactly 0.0 and an "over-smoothed" tap has nothing to ease back (and the
# mirror image on a very noisy one, where the denoise is already at
# ``presets._AUTO_DENOISE_MAX`` and "too noisy" has nothing to add). Either way
# the recipe Auto rebuilds is byte-for-byte the one on screen, and the editor
# answered every tap with *"Thanks — Auto will lean that way for you"*.
#
# The *decision* stays with the caller. Today it answers the first mechanism,
# which it can do for free and exactly — the biases either side of the tap are
# equal, so every input to ``auto_recipe`` is — while the second needs the
# picture and is filed in ``docs/IMPROVEMENTS.md`` with its measured cost. This
# table is only the sentence the caller says when the tap is inert: one phrase
# per cue, pinned against ``_CUE_STEP`` by
# ``tests/test_auto_feedback_cues_mirror.py`` so a cue added without one cannot
# silently fall back to the claim that is wrong.
_UNCHANGED_PHRASE: dict[str, str] = {
    "too_dark":        "Auto is already lifting this picture as far as it will go",
    "too_bright":      "Auto is already keeping it as dark as it will go",
    "too_soft":        "Auto is already sharpening as much as it will here",
    "over_sharpened":  "Auto is already sharpening as little as it will here",
    "too_noisy":       "Auto is already smoothing as much as it will here",
    "over_smoothed":   "Auto is already smoothing as little as it will here",
    "undersaturated":  "Auto is already boosting the colour as much as it will here",
    "too_saturated":   "Auto is already boosting the colour as little as it will here",
    "too_green":       "Auto is already taking out as much green as it will here",
    "too_magenta":     "Auto is already leaving in as much green as it will here",
    "core_clipped":    "Auto is already holding the bright cores back as much as it will",
    "core_flat":       "Auto is already leaving the bright cores alone here",
}


def unchanged_note(cue: str) -> str | None:
    """A plain-language line for a tap that leaves Auto's recipe for *this*
    picture byte-for-byte unchanged — ``None`` for a cue this module does not
    know. Whether a tap is such a tap is the caller's question, not this one's.

    It talks about the **picture**, not about the stored taste, on purpose: the
    tap may well have moved the bias (a profile is library-wide, and the same
    taste can bite on a noisier target tomorrow). What it did not do is change
    what the owner is looking at, which is the thing the old message claimed."""
    phrase = _UNCHANGED_PHRASE.get(cue)
    return None if phrase is None else f"That didn’t change this picture — {phrase}."


def limit_hint(cue: str) -> str | None:
    """The same limit as :func:`unchanged_note`, said **before** the tap — the line
    the chips row shows on a chip that cannot move the picture in front of the
    owner. ``None`` for a cue this module does not know.

    Two sentences rather than one, because marking a chip raises a question the
    after-the-fact note does not: *then why is it still here?* It is still here
    because the taste profile is **library-wide**. "Less smoothing than you
    measured" is a real preference, and the deep clean mosaic this picture happens
    to be is simply the one target where Auto has no smoothing to ease back; the
    next noisy one will. So the chip stays tappable and keeps recording — what the
    hint corrects is the expectation that *this* picture will change.

    Whether a given cue is in that state is the caller's question, not this one's:
    it needs the knobs Auto measured from the picture, which is
    ``presets.inert_auto_cues``.
    """
    phrase = _UNCHANGED_PHRASE.get(cue)
    if phrase is None:
        return None
    return f"{phrase}. Tapping still teaches Auto for your other pictures."


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


def _and_list(parts: list[str]) -> str:
    """``[a]`` → "a"; ``[a, b]`` → "a and b"; more → "a, b, and c"."""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def describe_profile(profile: dict[str, Any] | None,
                     object_type: str | None = None,
                     now: float | None = None,
                     inert_params: Iterable[str] | None = None,
                     ) -> str | None:
    """A one-line, plain-language "why" note for the UI, or ``None`` when the
    profile is neutral for ``object_type``. e.g. "Auto is running a bit brighter
    and softer for you, based on your recent feedback." — so the owner always sees
    why Auto shifted and can reset it; it never drifts silently.

    When ``object_type`` is given and it carries its own per-type override, the note
    names the archetype ("… for your galaxies …") so the owner understands the
    taste is scoped to that kind of target. A bias that recency decay has faded
    away is already gone from the note — see :func:`fade_note`, which says so.

    ``inert_params`` are the biased parameters that **cannot change the picture the
    owner is looking at** — the taste is stored and real, but the value Auto
    measured for *this* image already sits at the end of that parameter's
    ``_PARAM_RANGE`` (or past an op's emit gate), so the shift is clamped away.
    Those phrases move into a clause that says so instead of being claimed as
    something Auto *is* doing, because on the owner's own shape they are not: a
    deep clean stack measures ``denoise_strength`` 0.0, so a "with less smoothing"
    taste changes nothing there, and the editor said it was running that way
    anyway — one line under the chips row that marks the same limit (v0.492.54)
    and the tap that reports it (v0.492.56). **Nothing is dropped**: the taste is
    library-wide and will bite on the next noisier target, and the note is the only
    place the Reset link lives, so a note that vanished would take a control with
    it. Which parameters those are is the caller's question, not this one's — it
    needs the knobs Auto measured from the picture
    (``presets.inert_bias_params``). Omitted ⇒ today's sentence, byte for byte."""
    biases = effective_biases(profile, object_type, now)
    if not biases:
        return None
    dead = set(inert_params or ())
    live: list[str] = []
    stalled: list[str] = []
    for param, step in biases.items():
        phrase = _BIAS_PHRASE.get((param, step > 0))
        if phrase is None:
            continue
        (stalled if param in dead else live).append(phrase)
    if not live and not stalled:
        return None
    # Name the archetype only when this type actually carries its own bias override
    # (otherwise it's the global taste, which applies to every kind of target — a
    # bucket that walked back to neutral keeps only its counts, not a bias).
    for_whom = "for you"
    bucket = _coerce(profile)["by_type"].get(object_type or "")
    # ...and only while that override is still *in force*: one faded to nothing
    # falls back to the global taste, so naming the archetype would be a lie.
    if bucket and _bucket_biases(bucket, _now(now)):
        for_whom = f"for your {_TYPE_PLURAL.get(object_type, object_type)}"
    if not stalled:
        return (f"Auto is running {_and_list(live)} {for_whom}, "
                "based on your recent feedback.")
    # Both halves of the honest version say the same two things the chips row's
    # own legend says: it will not move *this* picture, and the taste still counts
    # everywhere else.
    limit = ("but it is already at its limit there on this picture — your other "
             "pictures will still get it.")
    if not live:
        return (f"Auto would run {_and_list(stalled)} {for_whom}, "
                f"based on your recent feedback, {limit}")
    return (f"Auto is running {_and_list(live)} {for_whom}, based on your recent "
            f"feedback. It would also run {_and_list(stalled)}, {limit}")
