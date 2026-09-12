"""Keep burned-in text inside the bundled font's glyph coverage.

Every server-rendered shareable — the nameplate, the keepsake mount, the recap
and life-list posters, the montage, the before/after pair, the deepening reel's
frame labels, the object labels and the scale-and-compass marks — draws its
text with Pillow's built-in scalable face (``ImageFont.load_default(size=…)``,
an Aileron subset). **That face is barely wider than ASCII.** Measured against
the bundled face, ``—``, ``–``, ``×``, ``→``, ``≈``, a non-breaking space, and
*every accented Latin letter* (``é``, ``ö``, ``ñ``, ``Å``, …) have no glyph at
all and draw as a hollow ``.notdef`` box.

That is a defect no test catches by reading strings: the text is correct and
the *pixels* are wrong, on the one image the user is about to post. Two
renderers already dodge it by hand — :func:`seestack.montage.montage_title` and
:func:`seestack.recap.recap_caption` both write ``·`` where they wanted an em
dash, and :attr:`seestack.scalebar.ScaleBar.ascii_label` exists solely for this
— but nothing protected the strings built from **user data**: a target is named
by its folder, so a beginner who called one ``Sh2-155 – Cave`` or ``Gómez's
Hamburger`` got boxes where the name should be.

:func:`safe_for_default_font` is the shared net. It **transliterates, never
strips**: a character the face can draw is passed through untouched, one it
cannot is replaced by the nearest thing it *can* draw, and a character with no
honest ASCII equivalent (a CJK or Cyrillic name) is left exactly as it was —
a box is bad, but silently deleting somebody's target name is worse.

Renderability is *measured against the real face* rather than hard-coded, so
the module stays correct if Pillow ever widens (or narrows) what it bundles.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

#: A private-use code point, guaranteed to have no glyph in any sane face. Its
#: rendered bitmap *is* the ``.notdef`` box we compare every other character
#: against.
_NOTDEF_PROBE = ""

#: The size the probe renders at. Small enough to be cheap, big enough that two
#: different glyphs can't collide into the same bitmap.
_PROBE_PX = 24

#: What to draw instead, for the characters this app actually produces (plus
#: the near neighbours of each, so a future copy edit is covered too). Consulted
#: **only** when the bundled face can't draw the original, so widening the face
#: silently retires an entry rather than overriding it.
_TRANSLITERATIONS: dict[str, str] = {
    # Dashes and minus — the em dash is this app's house punctuation, and the
    # single most likely character to reach a poster.
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-",
    # Quotes and primes (the typographic ones the face *does* carry fall
    # through the renderability check above and keep their own shape).
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "′": "'", "″": '"', "‵": "'", "‶": '"',
    # Maths and units we write in prose and in labels ("drizzle ×1.4").
    "×": "x", "÷": "/", "≈": "~", "≠": "!=",
    "≤": "<=", "≥": ">=", "√": "sqrt", "²": "2",
    "³": "3", "¹": "1", "½": "1/2", "¼": "1/4",
    "¾": "3/4", "⁄": "/",
    # Arrows, bullets and ellipsis.
    "←": "<-", "→": "->", "•": "*", "‣": "*",
    "▪": "*", "…": "...",
    # Spaces that are not U+0020. A no-break space draws a *box* in this face,
    # which is the worst of the lot: it turns an ordinary gap into damage.
    " ": " ", " ": " ", " ": " ", " ": " ",
    " ": " ", " ": " ", "　": " ",
    # Zero-width and invisible formatting. These are the one exception to
    # "transliterate, never strip": they were never meant to be seen, so a box
    # is the only thing dropping them can lose.
    "­": "", "​": "", "‌": "", "‍": "", "﻿": "",
    # Letters whose decomposition is not a plain base letter, so the NFKD fold
    # below can't reach them.
    "ß": "ss", "æ": "ae", "Æ": "AE", "ø": "o",
    "Ø": "O", "œ": "oe", "Œ": "OE", "ð": "d",
    "Ð": "D", "þ": "th", "Þ": "Th", "ł": "l",
    "Ł": "L", "đ": "d", "Đ": "D", "ı": "i",
    # Greek, because astronomy names stars with it — ``ω Centauri``, ``β
    # Cygni`` — and a folder named that way is a name, not decoration.
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "ε": "epsilon", "ζ": "zeta", "η": "eta", "θ": "theta",
    "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu",
    # U+00B5 MICRO SIGN is a *unit prefix*, not the Greek letter: "µm" is
    # micrometres, so it folds to "u" where U+03BC folds to "mu".
    "µ": "u", "ν": "nu", "ξ": "xi", "ο": "omicron",
    "π": "pi", "ρ": "rho", "σ": "sigma", "ς": "sigma",
    "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi",
    "ψ": "psi", "ω": "omega",
    "Α": "Alpha", "Β": "Beta", "Γ": "Gamma", "Δ": "Delta",
    "Ε": "Epsilon", "Ζ": "Zeta", "Η": "Eta", "Θ": "Theta",
    "Ι": "Iota", "Κ": "Kappa", "Λ": "Lambda", "Μ": "Mu",
    "Ν": "Nu", "Ξ": "Xi", "Ο": "Omicron", "Π": "Pi",
    "Ρ": "Rho", "Σ": "Sigma", "Τ": "Tau", "Υ": "Upsilon",
    "Φ": "Phi", "Χ": "Chi", "Ψ": "Psi", "Ω": "Omega",
}


def _load_probe_font():
    """The same face every burned-in caption uses, at :data:`_PROBE_PX`."""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=_PROBE_PX)
    except TypeError:  # pragma: no cover — Pillow <10.1 (below our pin)
        return ImageFont.load_default()


@lru_cache(maxsize=1)
def _notdef_bitmap() -> tuple[tuple[int, int], bytes]:
    """The shape and pixels of this face's ``.notdef`` box.

    The same reference :mod:`tests.glyphs` uses — deliberately, so the net and
    the guard that checks it can never disagree about what a box looks like.
    """
    return _render_probe(_NOTDEF_PROBE)


def _render_probe(ch: str) -> tuple[tuple[int, int], bytes]:
    """``ch``'s glyph mask from the bundled face, as ``(size, pixels)``."""
    mask = _load_probe_font().getmask(ch, mode="L")
    return tuple(mask.size), bytes(mask)


@lru_cache(maxsize=4096)
def can_draw(ch: str) -> bool:
    """Can the bundled face draw ``ch`` as itself, rather than as a box?

    ASCII is answered without rendering: the face covers U+0020–U+007E whole,
    and anything below that is a control character the callers never draw.
    Everything else is *measured* — its bitmap is compared with the
    ``.notdef`` box's — and memoised, so a poster's worth of text costs one
    render per distinct character.
    """
    if len(ch) != 1:  # pragma: no cover — callers pass one character
        return all(can_draw(c) for c in ch)
    if ord(ch) < 128:
        return True
    try:
        return _render_probe(ch) != _notdef_bitmap()
    except Exception:  # noqa: BLE001 — a font probe must never sink a render
        return False


def _drawable(text: str) -> bool:
    return all(can_draw(c) for c in text)


def _fold(ch: str) -> str:
    """``ch`` with its accents removed (``é`` → ``e``), or ``""``.

    NFKD splits a precomposed letter into its base plus combining marks; the
    marks have no glyph either, so they are dropped and the base kept. Returns
    ``""`` when the decomposition leaves nothing the face can draw — a Cyrillic
    or CJK character decomposes to itself, and the caller then keeps it.
    """
    decomposed = unicodedata.normalize("NFKD", ch)
    kept = "".join(c for c in decomposed
                   if unicodedata.category(c) != "Mn" and can_draw(c))
    return kept


def safe_for_default_font(text: str) -> str:
    """``text`` with every character the bundled face can't draw replaced by
    the nearest one it can.

    Pure, idempotent, and a no-op on the ASCII that almost every string already
    is (checked first, so the common path never touches Pillow). The order is
    deliberate: **draw it if we can**, then the explicit table, then an accent
    fold, and only then give up and leave the character alone — losing a name
    is worse than showing a box, so nothing is ever silently deleted except the
    zero-width formatting characters that were invisible to begin with.
    """
    if not text or all(ord(c) < 128 for c in text):
        return text
    out: list[str] = []
    for ch in text:
        if can_draw(ch):
            out.append(ch)
            continue
        replacement = _TRANSLITERATIONS.get(ch)
        if replacement is not None and _drawable(replacement):
            out.append(replacement)
            continue
        folded = _fold(ch)
        out.append(folded if folded else ch)
    return "".join(out)


def unrenderable_characters(text: str) -> tuple[str, ...]:
    """Every distinct character of ``text`` that would draw as a ``.notdef``
    box, in the order it first appears.

    The check behind the drift test that keeps new poster copy honest — and the
    reason that test can assert something about *pixels* while only handling
    strings.
    """
    seen: dict[str, None] = {}
    for ch in text or "":
        if not can_draw(ch):
            seen.setdefault(ch, None)
    return tuple(seen)
