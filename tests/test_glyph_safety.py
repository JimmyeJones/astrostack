"""The net that keeps *user data* inside the bundled font's glyph coverage.

:mod:`tests.test_drawn_text_glyphs` already pins **our own wording** — no
caption the app composes may reach a picture carrying a character Pillow's
bundled Aileron face cannot draw. Its docstring states the gap it cannot close:

    Scope, stated honestly: this pins **our wording**, not the user's data. A
    target named from a FITS ``OBJECT`` card can contain anything, and no test
    can stop that.

A test can't, but a transliteration can, and
:mod:`seestack.render.glyphs` is it. A target is named by its folder, so
``Sh2-155 – Cave``, ``Gómez's Hamburger`` or ``ω Centauri`` are all things a
beginner types and all things this face draws as a row of hollow boxes — on the
nameplate, the keepsake mount, the montage, the posters and the reel, i.e. on
every picture they are about to post.

This file pins three separate claims:

* the net itself replaces what it must, keeps what it can, and — the care that
  matters — **never silently deletes a name it cannot transliterate**;
* every renderer that burns text into pixels actually runs its text through
  the net, proven by rendering the hostile string and the sanitised string and
  comparing the *pixels*;
* a tenth renderer cannot be written the old way without this file going red.
"""

from __future__ import annotations

import pytest

from seestack.render.glyphs import (
    can_draw,
    safe_for_default_font,
    unrenderable_characters,
)
from tests.glyphs import missing_glyphs

pytest.importorskip("PIL.ImageFont")

Image = pytest.importorskip("PIL.Image")


# --------------------------------------------------------------------------
# The net itself
# --------------------------------------------------------------------------

def test_the_probe_can_tell_a_missing_glyph_from_a_present_one():
    """Armed before anything else: a private-use codepoint has no glyph in any
    face, a capital A has one in every one. If these ever agree, every other
    assertion in this file passes for the wrong reason."""
    assert can_draw("A")
    assert not can_draw("")


def test_ascii_is_returned_untouched_and_unmeasured():
    for text in ("M 42 · 3.2 h", "", "NGC 7000 (505x30s)", "a-b_c/d"):
        # `·` is not ASCII but *is* in the face, so it survives too.
        assert safe_for_default_font(text) == text


def test_the_characters_this_face_does_carry_are_left_alone():
    """The net is not a de-typographer: it only touches what would draw as a
    box. The middle dot is this app's house separator and the degree sign is
    the scale bar's top rung — both must come through unchanged."""
    kept = "· ° … ’ ‘ “ ” ±"
    assert can_draw("·") and can_draw("°") and can_draw("…")
    assert safe_for_default_font(kept) == kept
    assert missing_glyphs(kept) == []


@pytest.mark.parametrize(("raw", "expected"), [
    ("My deep-sky wall — 14 targets", "My deep-sky wall - 14 targets"),
    ("Sh2-155 – Cave Nebula", "Sh2-155 - Cave Nebula"),
    ("505×30s", "505x30s"),
    ("30″ / 15′", "30\" / 15'"),
    ("one → many", "one -> many"),
    ("≈ 3 h", "~ 3 h"),
    ("ω Centauri", "omega Centauri"),
    ("β Cygni", "beta Cygni"),
    ("naïve café", "naive cafe"),
    ("Gómez's Hamburger", "Gomez's Hamburger"),
    ("Åland", "Aland"),
    ("straße", "strasse"),
    ("Ørsted", "Orsted"),
    ("2 µm", "2 um"),
])
def test_it_replaces_what_the_face_cannot_draw(raw, expected):
    assert safe_for_default_font(raw) == expected
    assert unrenderable_characters(safe_for_default_font(raw)) == ()


def test_a_no_break_space_becomes_a_real_one():
    """The one missing character that reads as *damage* rather than as a
    missing letter: U+00A0 draws a box in the middle of an ordinary gap. It is
    also the case ``tests.glyphs.missing_glyphs`` cannot see, because it skips
    anything ``str.isspace()`` — so the net is the only thing that catches it.
    """
    assert not can_draw(" ")
    assert missing_glyphs("a b") == []          # the existing guard is blind here
    assert safe_for_default_font("a b") == "a b"


def test_invisible_formatting_is_the_one_thing_it_drops():
    # A soft hyphen and a zero-width joiner were never meant to be seen, so
    # dropping them loses nothing; every *visible* character is kept or mapped.
    assert safe_for_default_font("soft­hyphen") == "softhyphen"
    assert safe_for_default_font("zero​width") == "zerowidth"


def test_a_name_it_cannot_transliterate_is_kept_rather_than_deleted():
    """The care the whole design turns on: a box is bad, and losing somebody's
    target name is worse. A script with no honest ASCII equivalent comes back
    byte-for-byte, boxes and all — never shortened, never blanked."""
    for name in ("Туманность Андромеды", "ヘルクレス座", "銀河"):
        assert safe_for_default_font(name) == name
        assert unrenderable_characters(name)      # still unrenderable, honestly so


def test_it_never_makes_a_string_less_drawable():
    """The property behind every renderer call site: whatever goes in, nothing
    the face *could* draw comes out as something it cannot."""
    samples = [
        "M 31 · 4.2 h (505x30s)", "Gómez — ω Cen ×2", "Туманность — 3 h",
        "", "…", "a b", "ß æ Œ ø", "M42",
    ]
    for raw in samples:
        out = safe_for_default_font(raw)
        assert set(unrenderable_characters(out)) <= set(unrenderable_characters(raw))


def test_it_is_idempotent():
    for raw in ("Gómez — ω Cen ×2", "Туманность", "M 42 · 3.2 h", ""):
        once = safe_for_default_font(raw)
        assert safe_for_default_font(once) == once


# --------------------------------------------------------------------------
# Every renderer that burns text into pixels
#
# Each case renders the hostile string and the already-sanitised string and
# asserts the two pictures are identical — which is only true if the renderer
# sanitises. Before the fix each pair differs: one draws boxes, the other
# letters.
# --------------------------------------------------------------------------

#: A target name a beginner could really type, carrying one of each class the
#: face cannot draw: an en dash, an accent, a Greek letter and a `×`.
HOSTILE = "ω Cen – Gómez ×2"


def _picture(w: int = 320, h: int = 240, shade: int = 40):
    return Image.new("RGB", (w, h), (shade, shade + 8, shade + 20))


def _nameplate(text: str):
    from seestack.nameplate import NameplateFields, draw_nameplate

    return draw_nameplate(_picture(), NameplateFields(target=text, n_frames=12))


def _keepsake(text: str):
    from seestack.keepsake import NameplateFields, draw_keepsake

    return draw_keepsake(_picture(), NameplateFields(target=text, n_frames=12))


def _corner_label(text: str):
    from seestack.render.deepening import _draw_corner_label

    return _draw_corner_label(_picture(), text)


def _montage_title(text: str):
    from seestack.montage import MontageTile, build_montage

    tiles = [MontageTile(image=_picture(120, 90), caption="") for _ in range(3)]
    return build_montage(tiles, title=text, width=480)


def _montage_caption(text: str):
    from seestack.montage import MontageTile, build_montage

    tiles = [MontageTile(image=_picture(120, 90), caption=text) for _ in range(3)]
    return build_montage(tiles, title="", width=480)


def _before_after_caption(text: str):
    from seestack.beforeafter import build_before_after

    return build_before_after(_picture(120, 90), _picture(120, 90), caption=text,
                              width=480)


def _before_after_labels(text: str):
    from seestack.beforeafter import build_before_after

    return build_before_after(_picture(120, 90), _picture(120, 90),
                              labels=(text, text), width=480)


def _poster(text: str):
    from seestack.recap import draw_poster

    return draw_poster(title=text, stats=[(text, text)], lines=[text], size=420)


def _life_list_heading(text: str):
    from seestack.lifelistcard import GridCell, build_life_list_grid

    cells = [GridCell(label=f"M{i}", captured=i < 4) for i in range(1, 13)]
    return build_life_list_grid(cells, title=text, subtitle=text, width=420,
                                min_captured=1)


def _life_list_tile(text: str):
    from seestack.lifelistcard import GridCell, build_life_list_grid

    cells = [GridCell(label=text, captured=i < 4) for i in range(1, 13)]
    return build_life_list_grid(cells, title="", subtitle="", width=420,
                                min_captured=1)


def _object_labels(text: str):
    from seestack.objectlabels import ObjectLabel, ObjectLabels, draw_object_labels

    labels = ObjectLabels(labels=(ObjectLabel(text=text, x=0.5, y=0.5,
                                              notability=0.0),))
    return draw_object_labels(_picture(640, 480), labels)


def _sky_marks(text: str):
    from seestack.skymarks import SkyDirections, SkyMarks, draw_sky_marks

    marks = SkyMarks(bar_px=120.0, bar_label=text,
                     directions=SkyDirections(north_deg=0.0, east_deg=90.0))
    return draw_sky_marks(_picture(640, 480), marks)


@pytest.mark.parametrize("render", [
    _nameplate, _keepsake, _corner_label, _montage_title, _montage_caption,
    _before_after_caption, _before_after_labels, _poster, _life_list_heading,
    _life_list_tile, _object_labels, _sky_marks,
], ids=lambda f: f.__name__.strip("_"))
def test_a_renderer_draws_the_sanitised_text_not_the_raw(render):
    raw = render(HOSTILE)
    already_safe = render(safe_for_default_font(HOSTILE))
    assert raw is not None and already_safe is not None
    assert raw.tobytes() == already_safe.tobytes(), (
        "this renderer draws its text without going through "
        "safe_for_default_font, so a target name with an accent, a dash or a "
        "Greek letter bakes hollow boxes into the shared picture"
    )


def test_the_hostile_fixture_really_is_hostile():
    """The pair test above is vacuous if ``HOSTILE`` is already drawable, and a
    future Pillow widening its bundled face would do exactly that silently."""
    assert missing_glyphs(HOSTILE), (
        "the bundled face can now draw every character of HOSTILE, so the "
        "renderer tests prove nothing — pick characters it still lacks"
    )
    assert missing_glyphs(safe_for_default_font(HOSTILE)) == []


# --------------------------------------------------------------------------
# The drift guard — a tenth renderer can't be written the old way
# --------------------------------------------------------------------------

#: The marker a module writes to opt out, with its reason on the same line.
EXEMPT_MARKER = "glyph-safe-exempt:"


def _modules_that_draw_text(root):
    """Every ``.py`` under ``root`` that composes text onto pixels.

    Keyed on ``ImageDraw`` plus an actual ``.text(`` call, which is what a
    renderer looks like — a module that only *lays out* images (no text) has
    nothing to sanitise and is not flagged.
    """
    found = []
    for path in sorted(root.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "ImageDraw" in src and ".text(" in src:
            found.append((path, src))
    return found


def test_every_module_that_draws_text_runs_it_through_the_net():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "seestack"
    modules = _modules_that_draw_text(root)
    # An empty sweep and a clean tree look identical, so pin that it walked.
    assert len(modules) >= 9, (
        f"the sweep found only {len(modules)} text-drawing modules, which is "
        "fewer than the nine that exist — it is not reading the tree"
    )
    names = {p.name for p, _ in modules}
    assert {"nameplate.py", "recap.py", "skymarks.py"} <= names
    offenders = [
        p.relative_to(root).as_posix() for p, src in modules
        if "safe_for_default_font" not in src and EXEMPT_MARKER not in src
    ]
    assert not offenders, (
        f"{offenders} draw text without seestack.render.glyphs."
        "safe_for_default_font — a target name with an accent or a dash will "
        "bake hollow boxes into the picture they render"
    )


def test_the_drift_guard_fires_on_a_renderer_written_the_old_way(tmp_path):
    """Proven armed by mutation, not trusted: a grep-shaped guard that never
    fires is indistinguishable from one that cannot."""
    (tmp_path / "shiny_new_poster.py").write_text(
        "from PIL import ImageDraw\n"
        "def draw(img, name):\n"
        "    ImageDraw.Draw(img).text((0, 0), name)\n",
        encoding="utf-8",
    )
    found = _modules_that_draw_text(tmp_path)
    assert [p.name for p, _ in found] == ["shiny_new_poster.py"]
    assert all("safe_for_default_font" not in src for _p, src in found)


def test_the_drift_guard_ignores_a_module_that_draws_no_text(tmp_path):
    (tmp_path / "layout_only.py").write_text(
        "from PIL import ImageDraw\n"
        "def frame(img):\n"
        "    ImageDraw.Draw(img).rectangle((0, 0, 4, 4))\n",
        encoding="utf-8",
    )
    assert _modules_that_draw_text(tmp_path) == []
