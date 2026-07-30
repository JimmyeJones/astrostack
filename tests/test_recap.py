"""The shareable "your sky, so far" recap poster (pure engine helpers + render)."""

from __future__ import annotations

from seestack.recap import (
    RecapFacts,
    draw_recap_poster,
    recap_caption,
    recap_since_line,
    recap_stats,
    recap_top_project_line,
)


def _full() -> RecapFacts:
    return RecapFacts(
        total_integration_s=30000.0,   # 8h 20m
        n_targets=4,
        n_subs_kept=1234,
        n_nights=12,
        first_light_utc="2026-01-14T21:03:00",
        top_target_name="M 31",
        top_target_integration_s=15120.0,  # 4h 12m
    )


# --- recap_stats -----------------------------------------------------------


def test_stats_lead_with_integration_then_nights_targets_subs():
    assert recap_stats(_full()) == [
        ("8h 20m", "of light collected"),
        ("12", "nights out"),
        ("4", "targets imaged"),
        ("1,234", "subs kept"),
    ]


def test_stats_drop_missing_and_zero_figures_rather_than_printing_them():
    """"0 nights" reads as a bug, not as a beginning — an absent figure is left
    out and the rest closes up."""
    facts = RecapFacts(total_integration_s=600.0, n_targets=0, n_nights=None,
                       n_subs_kept=7)
    assert recap_stats(facts) == [("10m", "of light collected"), ("7", "subs kept")]


def test_stats_singularise():
    facts = RecapFacts(n_nights=1, n_targets=1, n_subs_kept=1)
    assert recap_stats(facts) == [("1", "night"), ("1", "target imaged"),
                                  ("1", "sub kept")]


def test_stats_are_empty_on_an_untouched_library():
    """Nothing captured yet → no stats, which is the caller's cue not to offer a
    poster at all rather than render an empty one."""
    assert recap_stats(RecapFacts()) == []


# --- recap_caption ---------------------------------------------------------


def test_caption_reads_like_a_person_would_say_it():
    assert recap_caption(_full()) == (
        "12 nights under the sky · 8h 20m of light · 4 targets · "
        "biggest project: M 31 (4h 12m)"
    )


def test_caption_omits_every_missing_part_without_a_dangling_separator():
    assert recap_caption(RecapFacts(total_integration_s=7200.0)) == "2h of light"
    assert recap_caption(RecapFacts(top_target_name="  M 42  ")) == "biggest project: M 42"
    assert recap_caption(RecapFacts()) == ""


def test_caption_drops_the_biggest_project_duration_when_unknown():
    facts = RecapFacts(n_targets=2, top_target_name="NGC 7000")
    assert recap_caption(facts) == "2 targets · biggest project: NGC 7000"


def test_caption_singularises_one_night_and_one_target():
    facts = RecapFacts(n_nights=1, n_targets=1)
    assert recap_caption(facts) == "1 night under the sky · 1 target"


# --- recap_top_project_line ------------------------------------------------


def test_top_project_line_names_the_target_and_its_time():
    assert recap_top_project_line(_full()) == "Biggest project: M 31 · 4h 12m"


def test_top_project_line_uses_no_glyph_the_built_in_font_lacks():
    """Pillow's built-in font has no U+2014, so an em dash renders as a tofu box
    on the finished poster — the one character the user is about to post."""
    line = recap_top_project_line(_full())
    assert "—" not in line and "–" not in line


def test_top_project_line_degrades_and_self_hides():
    assert recap_top_project_line(RecapFacts(top_target_name="M 42")) \
        == "Biggest project: M 42"
    assert recap_top_project_line(RecapFacts(top_target_integration_s=3600.0)) == ""
    assert recap_top_project_line(RecapFacts(top_target_name="   ")) == ""


# --- recap_since_line ------------------------------------------------------


def test_since_line_formats_first_light_and_stays_empty_when_unparseable():
    assert recap_since_line(_full()) == "Since 14 Jan 2026"
    assert recap_since_line(RecapFacts(first_light_utc="not-a-date")) == ""
    assert recap_since_line(RecapFacts()) == ""


# --- draw_recap_poster -----------------------------------------------------


def test_poster_is_a_square_rgb_image_at_the_requested_size():
    img = draw_recap_poster(_full(), size=360)
    assert img.mode == "RGB"
    assert img.size == (360, 360)


def test_poster_renders_without_a_hero_picture():
    """A library with no finished stack yet must still get a poster, not a
    crash — the backdrop simply falls back to plain deep space."""
    img = draw_recap_poster(_full(), hero=None, size=240)
    assert img.size == (240, 240)
    # Something was actually drawn on the dark background.
    assert max(img.convert("L").tobytes()) > 100


def test_poster_uses_the_hero_picture_as_a_darkened_backdrop():
    """The user's own picture should show through — but veiled, so white text
    stays readable over a bright galaxy core."""
    from PIL import Image

    bright = Image.new("RGB", (400, 200), (255, 255, 255))
    img = draw_recap_poster(RecapFacts(), hero=bright, size=200)
    corner = img.getpixel((2, img.size[1] - 2))  # away from any text
    assert all(60 < c < 200 for c in corner), corner


def test_poster_cover_crops_a_wide_hero_without_letterboxing():
    """Cover-crop, not fit: a 2:1 picture must fill the square edge to edge, so
    no black bars land in the middle of a poster someone is about to post."""
    from PIL import Image

    wide = Image.new("RGB", (600, 300), (255, 255, 255))
    img = draw_recap_poster(RecapFacts(), hero=wide, size=200)
    # Top-left and bottom-left corners both come from the picture, not a bar.
    assert img.getpixel((1, 1))[0] > 60
    assert img.getpixel((1, 198))[0] > 60


def test_poster_renders_an_empty_library_without_failing():
    img = draw_recap_poster(RecapFacts(), size=200)
    assert img.size == (200, 200)


def test_poster_shrinks_a_very_long_target_name_to_fit():
    """A long name must never run off the edge of a shareable image. Rendering
    at two sizes with an absurd name is a smoke test that the fit loop
    terminates and the layout still produces an image."""
    facts = RecapFacts(top_target_name="A" * 200, top_target_integration_s=3600.0)
    for size in (200, 540):
        assert draw_recap_poster(facts, size=size).size == (size, size)
