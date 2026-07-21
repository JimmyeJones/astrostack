"""Acquisition nameplate — caption text + baked-on footer bar."""

import numpy as np

from seestack.nameplate import (
    NameplateFields,
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
        "M 31 · 4h 12m (505×30s) · 19 Jul 2026 · ZWO Seestar S50"
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
