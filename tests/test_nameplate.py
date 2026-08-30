"""Acquisition nameplate — caption text + baked-on footer bar."""

import numpy as np

from seestack.nameplate import (
    NameplateFields,
    _load_font,
    acquisition_parts,
    draw_nameplate,
    format_acq_date,
    nameplate_line,
)


def test_format_acq_date_parses_iso_datetime():
    assert format_acq_date("2026-07-19T21:03:00") == "19 Jul 2026"
    assert format_acq_date("2026-07-19") == "19 Jul 2026"
    assert format_acq_date("2026-01-05 04:00:00") == "5 Jan 2026"


def test_format_acq_date_empty_for_unparseable():
    assert format_acq_date(None) == ""
    assert format_acq_date("") == ""
    assert format_acq_date("not-a-date") == ""
    assert format_acq_date("2026-13-40") == ""   # out-of-range month/day
    assert format_acq_date("2026-07") == ""      # missing day


def test_nameplate_line_full():
    fields = NameplateFields(
        target="M 31", integration_s=15150, n_frames=505, sub_exposure_s=30,
        date_iso="2026-07-19T21:03:00", camera="ZWO Seestar S50",
    )
    assert nameplate_line(fields) == (
        "M 31 · 4h 12m (505x30s) · 19 Jul 2026 · ZWO Seestar S50"
    )


def test_every_caption_character_has_a_glyph_in_the_font_we_draw_with():
    """Regression: the sub detail used to read ``(505×30s)`` with a *typographic*
    multiplication sign, and Pillow's bundled Aileron face has no glyph for it —
    so every nameplate the owner shared baked a hollow ``.notdef`` box into the
    picture, right where the exposure should be.

    Rather than pin one character, pin the rule: nothing a caption can produce
    may be missing from the font that draws it. A future tidy-up that reaches for
    ``×``, an em dash or a curly quote fails here instead of shipping a box into
    someone's shared picture.
    """
    font = _load_font(32)
    # A private-use codepoint no font defines, so what it renders *is* this
    # font's .notdef box — the hollow rectangle a missing glyph shows as. Written
    # as chr() rather than a literal: an invisible character in source is exactly
    # the kind of thing a stray editor pass silently eats, and losing it would
    # turn this assertion into one that can never fail.
    notdef = np.asarray(font.getmask(chr(0xE000), mode="L"))
    assert notdef.size, (
        "the reference .notdef glyph came back empty, so this test could not "
        "tell a missing glyph from a blank — re-pick the reference codepoint"
    )

    def has_glyph(ch: str) -> bool:
        mask = np.asarray(font.getmask(ch, mode="L"))
        return mask.shape != notdef.shape or not np.array_equal(mask, notdef)

    # Every part a caption can carry: name, duration, sub detail, date, gear —
    # plus the one-sub and count-only degradations of the sub detail.
    captions = [
        nameplate_line(NameplateFields(
            target="M 31", integration_s=15150, n_frames=505, sub_exposure_s=30,
            date_iso="2026-07-19T21:03:00", camera="ZWO Seestar S50")),
        nameplate_line(NameplateFields(
            target="NGC 7000", integration_s=11520, n_frames=152)),
        nameplate_line(NameplateFields(target="M 42", n_frames=1)),
        nameplate_line(NameplateFields(
            integration_s=1.5, n_frames=3, sub_exposure_s=2.5,
            date_iso="2026-01-05")),
        # …and every shape of the multi-night span, which is where a tidy-up
        # would reach for an en dash the bundled font cannot draw.
        nameplate_line(NameplateFields(
            target="M 31", n_frames=505,
            date_iso="2024-11-15", date_end_iso="2024-11-18")),
        nameplate_line(NameplateFields(
            target="M 31", n_frames=505,
            date_iso="2024-10-28", date_end_iso="2024-11-03")),
        nameplate_line(NameplateFields(
            target="M 31", n_frames=505,
            date_iso="2024-12-28", date_end_iso="2025-01-03")),
        # …and the span carrying its night count.
        nameplate_line(NameplateFields(
            target="M 31", n_frames=505, nights=4,
            date_iso="2024-11-15", date_end_iso="2024-11-18")),
    ]
    for caption in captions:
        assert caption, "a caption with real data must not be empty"
        missing = sorted({ch for ch in caption if not has_glyph(ch)})
        assert not missing, (
            f"{missing!r} has no glyph in the bundled font, so it bakes a "
            f"hollow box into the shared picture: {caption!r}"
        )


def test_nameplate_line_folds_the_sub_detail_and_degrades_gracefully():
    # Integration + subs but no per-sub exposure → count only.
    assert nameplate_line(NameplateFields(
        target="M 42", integration_s=11520, n_frames=152,
    )) == "M 42 · 3h 12m (152 subs)"
    # A single sub reads "(1 sub)".
    assert nameplate_line(NameplateFields(
        target="NGC 7000", integration_s=75, n_frames=1,
    )) == "NGC 7000 · 1m (1 sub)"
    # Integration only (no sub count) → just the duration.
    assert nameplate_line(NameplateFields(
        target="M 51", integration_s=3600,
    )) == "M 51 · 1h"
    # Sub-exposure without a count is not enough to show a detail.
    assert nameplate_line(NameplateFields(
        target="M 13", sub_exposure_s=30,
    )) == "M 13"


def test_nameplate_line_omits_missing_parts_and_is_empty_for_nothing():
    # No target, no integration → just the date · camera, never a dangling "·".
    assert nameplate_line(NameplateFields(
        date_iso="2026-07-19", camera="ZWO Seestar S50",
    )) == "19 Jul 2026 · ZWO Seestar S50"
    # Zero frames / zero integration contribute nothing.
    assert nameplate_line(NameplateFields(
        target="M 31", integration_s=0, n_frames=0,
    )) == "M 31"
    # Nothing at all → empty (draw_nameplate then no-ops).
    assert nameplate_line(NameplateFields()) == ""


def test_draw_nameplate_darkens_the_footer_and_keeps_size():
    from PIL import Image

    img = Image.new("RGB", (400, 300), (120, 120, 120))
    fields = NameplateFields(target="M 31", integration_s=11520, n_frames=152,
                             camera="ZWO Seestar S50")
    out = draw_nameplate(img, fields)

    assert out.mode == "RGB"
    assert out.size == (400, 300)                 # never resized
    arr = np.asarray(out)
    # The footer band is darkened by the translucent bar; the top is untouched.
    top_mean = arr[:20].mean()
    bottom_mean = arr[-20:].mean()
    assert bottom_mean < top_mean - 10
    assert abs(top_mean - 120) < 1                # top row exactly the original grey
    # White caption text lands somewhere in the bottom band.
    assert arr[-40:].max() > 220


def test_draw_nameplate_is_a_noop_when_there_is_nothing_to_say():
    from PIL import Image

    img = Image.new("RGB", (200, 150), (77, 88, 99))
    out = draw_nameplate(img, NameplateFields())     # empty line
    assert np.array_equal(np.asarray(img), np.asarray(out))


def test_draw_nameplate_fits_a_long_caption_without_crashing_on_a_tiny_image():
    from PIL import Image

    img = Image.new("RGB", (64, 48), (10, 10, 10))
    fields = NameplateFields(
        target="A very long target designation that would overflow a narrow share",
        integration_s=11520, n_frames=152, sub_exposure_s=30,
        date_iso="2026-07-19", camera="ZWO Seestar S50",
    )
    out = draw_nameplate(img, fields)
    assert out.size == (64, 48)                    # shrank to fit, no crash


# --- the acquisition date, and the span a multi-night stack covers ------------
#
# A nameplate had *no date at all* until the stacker started stamping a capture
# time: it read a `DATE-OBS` card the master never carried, so the one field an
# acquisition caption is really for was silently missing from every shared
# picture. These pin what it says now.

def test_a_span_writes_its_shared_parts_once():
    from seestack.nameplate import format_acq_range

    assert format_acq_range("2024-11-15", "2024-11-18") == "15-18 Nov 2024"
    assert format_acq_range("2024-10-28", "2024-11-03") == "28 Oct-3 Nov 2024"
    assert format_acq_range("2024-12-28", "2025-01-03") == (
        "28 Dec 2024-3 Jan 2025")


def test_one_night_captions_exactly_as_it_always_did():
    from seestack.nameplate import format_acq_date, format_acq_range

    for iso in ("2026-07-19T21:03:00", "2026-01-05"):
        assert format_acq_range(iso, iso) == format_acq_date(iso)
        assert format_acq_range(iso, None) == format_acq_date(iso)
        assert format_acq_range(iso) == format_acq_date(iso)


def test_a_span_reads_forwards_however_it_arrives():
    from seestack.nameplate import format_acq_range

    assert format_acq_range("2024-11-18", "2024-11-15") == "15-18 Nov 2024"


def test_an_unusable_end_degrades_to_the_single_date():
    from seestack.nameplate import format_acq_range

    assert format_acq_range("2024-11-15", "not-a-date") == "15 Nov 2024"
    assert format_acq_range("2024-11-15", "") == "15 Nov 2024"
    assert format_acq_range(None, "2024-11-15") == "15 Nov 2024"
    assert format_acq_range(None, None) == ""


def test_the_caption_carries_the_span():
    assert nameplate_line(NameplateFields(
        target="M 31", integration_s=15150, n_frames=505, sub_exposure_s=30,
        date_iso="2024-11-15", date_end_iso="2024-11-18",
        camera="ZWO Seestar S50",
    )) == "M 31 · 4h 12m (505x30s) · 15-18 Nov 2024 · ZWO Seestar S50"


def test_a_span_says_how_many_nights_when_the_run_recorded_it():
    """"11-14 Sep 2024" is equally consistent with two nights and with four.
    The count is the part that says how much work the picture was."""
    assert nameplate_line(NameplateFields(
        target="M 31", integration_s=15150, n_frames=505, sub_exposure_s=30,
        date_iso="2024-11-15", date_end_iso="2024-11-18", nights=4,
        camera="ZWO Seestar S50",
    )) == "M 31 · 4h 12m (505x30s) · 15-18 Nov 2024 (4 nights) · ZWO Seestar S50"


def test_the_night_count_is_omitted_when_it_would_say_nothing():
    """One night is already named by the date; an unrecorded count (every run
    predating the column) captions exactly as it did before."""
    one_night = dict(target="M 31", n_frames=505, date_iso="2024-11-15")
    assert nameplate_line(NameplateFields(**one_night, nights=1)) == (
        "M 31 · (505 subs) · 15 Nov 2024")
    assert nameplate_line(NameplateFields(**one_night)) == (
        "M 31 · (505 subs) · 15 Nov 2024")
    span = dict(target="M 31", date_iso="2024-11-15", date_end_iso="2024-11-18")
    assert nameplate_line(NameplateFields(**span)) == "M 31 · 15-18 Nov 2024"
    assert nameplate_line(NameplateFields(**span, nights=1)) == (
        "M 31 · 15-18 Nov 2024")


def test_a_count_never_contradicts_a_single_date():
    """Defence in depth: a run whose window degraded to one date must not be
    captioned "15 Nov 2024 (4 nights)", whatever the count says."""
    assert nameplate_line(NameplateFields(
        target="M 31", date_iso="2024-11-15", nights=4,
    )) == "M 31 · 15 Nov 2024"
    assert nameplate_line(NameplateFields(
        target="M 31", date_iso="2024-11-15", date_end_iso="2024-11-15",
        nights=4,
    )) == "M 31 · 15 Nov 2024"


def test_the_keepsake_subtitle_carries_the_night_count_too():
    """The two captioning surfaces share ``acquisition_parts`` precisely so they
    cannot drift on a fact like this."""
    parts = acquisition_parts(NameplateFields(
        target="M 31", n_frames=505, nights=4,
        date_iso="2024-11-15", date_end_iso="2024-11-18",
    ), include_target=False)
    assert "15-18 Nov 2024 (4 nights)" in parts
