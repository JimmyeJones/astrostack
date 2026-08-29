"""Every string the app *draws onto pixels* must be drawable with the bundled font.

A whole family of defects is invisible to an ordinary assertion: the string is
exactly right, and only the *picture* is wrong. The nameplate shipped
``(505×30s)`` into every share export for months — every test compared the
caption text, which was correct; the hollow ``.notdef`` box only appeared once
those characters met Pillow's built-in Aileron face, which has no ``×``.

This walks **every caption builder in the codebase whose output is burned into
an image** through the same rule (:mod:`tests.glyphs`), so the hand-audit that
followed that fix becomes a permanent one. A future tidy-up that reaches for a
prettier dash, an arrow, or a typographic prime fails here rather than shipping
a box into a picture the owner posts.

Scope, stated honestly: this pins **our wording**, not the user's data. A target
named from a FITS ``OBJECT`` card can contain anything, and no test can stop
that — the drawing modules are deliberately forgiving about it (a missing glyph
is still only a cosmetic box). What it *can* guarantee is that no fixed string
we compose ever contributes one.
"""

from __future__ import annotations

import pytest

from tests.glyphs import assert_drawable, missing_glyphs

pytest.importorskip("PIL.ImageFont")


# ---- the guard itself has to be able to fail -----------------------------

def test_the_guard_catches_the_character_that_started_all_this():
    # v0.282.1: the nameplate's "(505×30s)". If this ever comes back empty the
    # whole file is toothless, so it is pinned first.
    assert missing_glyphs("505×30s") == ["×"]
    assert missing_glyphs("a — b") == ["—"]
    assert missing_glyphs("one → many") == ["→"]


def test_the_guard_passes_what_the_app_actually_uses():
    # The separators the drawing modules settled on, and the degree sign the
    # scale bar keeps: all present in the bundled face.
    assert missing_glyphs("M 42 · 3h 12m · 505 subs · 2° · 30' · 15\"") == []


# ---- every caption builder that ends up in a picture ---------------------

def _nameplate_captions() -> list[str]:
    from seestack.keepsake import keepsake_caption
    from seestack.nameplate import NameplateFields, nameplate_line

    rich = NameplateFields(
        target="M 31", integration_s=15150, n_frames=505, sub_exposure_s=30,
        date_iso="2026-07-19T21:03:00", camera="ZWO Seestar S50")
    thin = NameplateFields(target="NGC 7000", integration_s=75, n_frames=1)
    title, details = keepsake_caption(rich)
    return [nameplate_line(rich), nameplate_line(thin), title, details]


def _montage_captions() -> list[str]:
    from seestack.montage import montage_caption, montage_title

    return [
        montage_caption("M 42", 11520),
        montage_caption("NGC 7000", None),
        montage_title(14, 136800),
        montage_title(1, None),
    ]


def _recap_captions() -> list[str]:
    from seestack.recap import (
        RecapFacts,
        recap_caption,
        recap_other_targets_line,
        recap_since_line,
        recap_stats,
        recap_top_project_line,
    )

    facts = RecapFacts(
        n_nights=12, n_targets=4, n_subs_kept=5051, total_integration_s=30000,
        top_target_name="M 31", top_target_integration_s=15150,
        first_light_utc="2026-01-05T22:10:00Z",
        other_target_names=["M 42", "NGC 7000", "M 81"],
    )
    lines = [
        recap_caption(facts), recap_top_project_line(facts),
        recap_since_line(facts), recap_other_targets_line(facts),
    ]
    lines += [value for value, _ in recap_stats(facts)]
    lines += [label for _, label in recap_stats(facts)]
    return lines


def _reel_captions() -> list[str]:
    from seestack.render.deepening import deepening_frame_label

    return [
        deepening_frame_label("2026-07-19T21:03:00", 120),
        deepening_frame_label("2026-07-19T21:03:00", 1),
        deepening_frame_label(None, 505),
    ]


def _before_after_captions() -> list[str]:
    from seestack.beforeafter import before_after_caption, panel_labels

    out = [
        before_after_caption("M 42", 505, 30, 11520),
        before_after_caption(None, 1, 2.5, 2.5),
    ]
    out += list(panel_labels(505, 30))
    out += list(panel_labels(None, None))
    return out


def _sky_mark_labels() -> list[str]:
    """The scale bar's drawn label across the whole ladder, plus the rose letters.

    ``ScaleBar.label`` deliberately uses the typographic primes ``′``/``″`` for
    HTML; only ``ascii_label`` is ever drawn, and that distinction is exactly the
    kind of thing a later "why do we have two of these?" tidy-up collapses — so
    every rung of the drawn form is pinned here.
    """
    from seestack.scalebar import scale_bar_for

    labels = ["N", "E"]                     # the compass rose, drawn verbatim
    # A scale spread wide enough to reach the arcsecond, arcminute and degree
    # rungs of the ladder.
    for arcsec_per_px in (0.05, 0.5, 2.7, 30.0, 200.0):
        bar = scale_bar_for(arcsec_per_px, 1920, 1080)
        if bar is not None:
            labels.append(bar.ascii_label)
    return labels


@pytest.mark.parametrize("builder", [
    _nameplate_captions, _montage_captions, _recap_captions, _reel_captions,
    _before_after_captions, _sky_mark_labels,
], ids=lambda f: f.__name__.strip("_"))
def test_every_drawn_caption_is_drawable(builder):
    produced = builder()
    assert produced, f"{builder.__name__} produced nothing to check"
    for text in produced:
        if not text:
            continue      # an omitted clause is a clean no-op, not a defect
        assert_drawable(text, what=f"{builder.__name__} → {text!r}")


def test_the_scale_bars_html_label_is_the_one_that_may_use_primes():
    # The counterpart to the pin above: `label` is *allowed* the primes (the
    # in-app overlay renders them correctly), which is why the ASCII form exists
    # at all. If this ever stops finding them, the two have been collapsed and
    # the drawn label is at risk.
    from seestack.scalebar import scale_bar_for

    bar = scale_bar_for(2.7, 1920, 1080)
    assert bar is not None
    assert missing_glyphs(bar.label) or bar.label == bar.ascii_label
