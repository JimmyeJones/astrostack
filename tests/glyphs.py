"""Shared guard: every character we *draw onto pixels* must exist in the font.

The app bakes text into pictures the owner shares — a nameplate over a stack, a
keepsake's caption, a montage title, a reel's corner label, a scale bar's length,
the before/after caption. All of them draw with Pillow's built-in scalable face
(``ImageFont.load_default(size=…)``, no bundled asset), and that face does **not**
cover typographic punctuation: ``×``, ``—``, ``→`` and curly quotes all render as
a hollow ``.notdef`` box.

That failure mode is invisible to an ordinary assertion. The nameplate shipped
``(505×30s)`` into every share export for months while every test in the suite
compared the caption *string*, which was exactly right — the defect only existed
once the characters met the font. This module turns the hand-audit that followed
into a permanent one: :func:`missing_glyphs` renders each character and compares
its mask to the font's own ``.notdef``, so a future tidy-up that reaches for a
prettier dash fails here instead of shipping a box into someone's picture.

Used by :mod:`tests.test_drawn_text_glyphs` (which walks every caption builder in
the codebase) and available to any module-specific test that wants the same rule.
"""

from __future__ import annotations

import numpy as np

# A private-use codepoint no font defines, so what it renders *is* this font's
# .notdef box. Written as ``chr()`` rather than a literal: an invisible character
# in source is exactly the kind of thing a stray editor pass silently eats, and
# losing it would turn every assertion here into one that can never fail.
_NOTDEF_CODEPOINT = 0xE000


def load_default_font(size: int = 32):
    """The face every drawing module in the app uses, at ``size`` px.

    Mirrors ``seestack.nameplate._load_font`` and its siblings — deliberately the
    *same* call, so this guard can never test a font the app doesn't draw with.
    """
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover — Pillow <10.1 (below our pin)
        return ImageFont.load_default()


def missing_glyphs(text: str, *, size: int = 32) -> list[str]:
    """The sorted, de-duplicated characters of ``text`` the font has no glyph for.

    Empty for anything safe to draw. Whitespace is skipped (a space legitimately
    renders as nothing, and comparing it against ``.notdef`` proves nothing).
    """
    font = load_default_font(size)
    notdef = np.asarray(font.getmask(chr(_NOTDEF_CODEPOINT), mode="L"))
    # If a future Pillow ever maps unmapped codepoints to a *blank* rather than a
    # box, this reference comes back empty and the comparison below would quietly
    # pass for everything. Fail loudly instead of silently going toothless.
    assert notdef.size, (
        "the reference .notdef glyph came back empty, so this guard could not "
        "tell a missing glyph from a blank — re-pick the reference codepoint"
    )
    missing = set()
    for ch in text:
        if ch.isspace():
            continue
        mask = np.asarray(font.getmask(ch, mode="L"))
        if mask.shape == notdef.shape and np.array_equal(mask, notdef):
            missing.add(ch)
    return sorted(missing)


def assert_drawable(text: str, *, what: str = "this string", size: int = 32) -> None:
    """Assert every character of ``text`` has a glyph in the font we draw with."""
    missing = missing_glyphs(text, size=size)
    assert not missing, (
        f"{what} contains {missing!r}, which has no glyph in the bundled font — "
        f"drawn, it bakes a hollow box into the picture: {text!r}"
    )
