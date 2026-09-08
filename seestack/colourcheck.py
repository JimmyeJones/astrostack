"""\"Does my colour look right?\" — an object-aware colour sanity note.

A beginner who stacks and auto-edits an emission nebula has no way to tell
whether the colour came out right: is that grey-green M42 a white balance they
should fix, or just what it looks like? The app already knows *what they shot*
(the bundled catalog's :attr:`~seestack.nightplan.CatalogObject.nebula_class`)
and it already measures *what colour the object came out*
(:func:`seestack.edit.histogram.measure_object_colour`). This module is the pure
join between the two: one plain-language line, or nothing at all.

**It is built to stay quiet.** A single wrong "your colour is off" on a
genuinely fine picture costs more trust than ten correct reassurances buy, so:

* only the two families with a confident, class-wide expectation ever produce a
  verdict — ``emission`` (Hα red-pink) and ``reflection`` (dust-lit blue). A
  ``both`` / ``unknown`` nebula, a planetary nebula, a supernova remnant, a
  galaxy, a cluster and an unidentified target all return ``None``;
* a nudge needs a **strong** deviation, well past ordinary OSC variation, and
  there is a deliberate dead band between "clearly right" and "clearly wrong"
  in which the answer is silence rather than a hedge;
* it reads the *stretched, sky-subtracted display* image, never the linear
  stack, so raw OSC green-dominance cannot trip it.

Pure and offline: no I/O, no pixels, no network — it takes the class and the
measurement and returns a note.
"""

from __future__ import annotations

from dataclasses import dataclass

# Which nebula families carry a confident, class-wide colour expectation. Every
# other catalog type (planetary nebula, supernova remnant, galaxy, cluster …) is
# absent on purpose: a planetary's colour swings from Cat's-Eye teal to Ring red
# depending on the object, so there is no class-wide claim to make.
_EXPECTED: dict[str, str] = {"emission": "red-pink", "reflection": "blue"}

# `balance` = (r - b) / (r + b) of the sky-subtracted object medians, so +1 is
# pure red and -1 pure blue. The expected side must lead by this much before we
# say the colour looks right…
_REASSURE_MARGIN = 0.05
# …and the *wrong* side must lead by this much — three times as far — before we
# say anything is off. Between the two the note is absent: an emission nebula
# that came out roughly neutral is unremarkable, not a fault worth a caption.
_NUDGE_MARGIN = 0.15

# Green standing this far above the stronger of red and blue (as a share of the
# three) is the one cast that is a *processing* fault rather than a taste: no
# deep-sky object is green, so it always means the OSC's green-heavy raw balance
# survived. Checked before the red/blue balance because it has a better answer
# to offer (SCNR), and because a green-grey picture can sit at any balance.
_GREEN_NUDGE = 0.12
# A picture may not be *reassured* while it still carries a visible green cast,
# even if its red/blue balance is fine.
_GREEN_OK = 0.06


@dataclass(frozen=True)
class ColourNote:
    """One plain-language line about the finished picture's colour."""

    ok: bool        # True = it looks right; False = a gentle, actionable nudge
    expected: str   # the family's expected dominant colour, e.g. "red-pink"
    family: str     # "emission" | "reflection"
    text: str       # the line to show, already phrased for a beginner


def colour_expectation(nebula_class: str | None,
                       colour: dict | None) -> ColourNote | None:
    """Compare a finished picture's object colour against its family's.

    ``nebula_class`` is the catalog's vetted family (``""``/``None`` for
    everything that isn't a classified nebula) and ``colour`` is a
    :func:`~seestack.edit.histogram.measure_object_colour` result. Returns a
    :class:`ColourNote`, or ``None`` whenever there is no confident thing to say
    — which is most of the time, and is the point.
    """
    family = (nebula_class or "").strip().lower()
    expected = _EXPECTED.get(family)
    if expected is None:
        return None
    if not colour or not colour.get("measured"):
        return None
    balance = colour.get("balance")
    green_excess = colour.get("green_excess")
    if balance is None or green_excess is None:
        return None
    balance = float(balance)
    green_excess = float(green_excess)

    noun = "Emission nebulae like this" if family == "emission" \
        else "Reflection nebulae like this"
    verb = "glow" if family == "emission" else "shine"

    if green_excess >= _GREEN_NUDGE:
        return ColourNote(
            ok=False, expected=expected, family=family,
            text=(f"{noun} usually {verb} {expected}, but yours is coming out "
                  "green — that's the camera's own colour balance showing "
                  "through. Add the \"Remove green (SCNR)\" step, or press "
                  "Auto-process to redo the colour."),
        )

    # Positive balance is red-led, negative blue-led; flip the sign so a single
    # comparison serves both families and "how far the expected colour leads" is
    # one number.
    lead = balance if family == "emission" else -balance
    if lead <= -_NUDGE_MARGIN:
        came_out = "blue" if family == "emission" else "red"
        return ColourNote(
            ok=False, expected=expected, family=family,
            text=(f"{noun} usually {verb} {expected}, but yours is coming out "
                  f"{came_out}. Press Auto-process to redo the colour, or check "
                  "the colour-calibration step."),
        )
    if lead >= _REASSURE_MARGIN and green_excess < _GREEN_OK:
        glow = "a warm red-pink glow" if family == "emission" \
            else "a cool blue glow"
        return ColourNote(
            ok=True, expected=expected, family=family,
            text=(f"Colour looks right for {'an' if family == 'emission' else 'a'} "
                  f"{family} nebula — {glow} ✓"),
        )
    return None
