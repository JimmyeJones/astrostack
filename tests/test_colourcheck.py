"""\"Does my colour look right?\" — the catalog family, the measurement, the note.

Three layers, tested separately because they fail differently: the curated
``nebula_class`` data (a correctness bar, cross-checked against each entry's own
blurb), :func:`~seestack.edit.histogram.measure_object_colour` (does it read the
object's colour, and does it stay quiet on noise?), and
:func:`~seestack.colourcheck.colour_expectation` (does it stay silent unless it
is confident?).
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.colourcheck import ColourNote, colour_expectation
from seestack.edit.histogram import measure_object_colour
from seestack.nightplan import load_catalog

# --- the scene ---------------------------------------------------------------

def _scene(obj_rgb, *, sky=0.12, sky_rgb=None, noise=0.004, n=320, seed=7,
           radius=48.0, stars=0):
    """A display-space frame: flat sky + noise + one soft coloured blob.

    ``obj_rgb`` is the blob's peak amplitude per channel *above* the sky, which
    is exactly what the measurement is supposed to recover the balance of.
    """
    rng = np.random.default_rng(seed)
    img = np.empty((n, n, 3), dtype=np.float32)
    levels = sky_rgb if sky_rgb is not None else (sky, sky, sky)
    for c in range(3):
        img[..., c] = levels[c] + rng.normal(0.0, noise, (n, n))
    yy, xx = np.mgrid[0:n, 0:n]
    blob = np.exp(-((np.hypot(yy - n / 2, xx - n / 2) / radius) ** 2))
    for c in range(3):
        img[..., c] += (blob * obj_rgb[c]).astype(np.float32)
    for _ in range(stars):
        y, x = rng.integers(4, n - 4, 2)
        img[y - 2:y + 3, x - 2:x + 3, :] += 0.9      # saturated, neutral-white
    return img


# --- the curated catalog data ------------------------------------------------

_VALID_CLASSES = {"emission", "reflection", "both", "unknown"}


def test_every_bundled_nebula_carries_a_vetted_class_and_nothing_else_does():
    # The field only means anything on type="nebula": a galaxy or a cluster has
    # no glow family, and a planetary nebula's colour swings object by object, so
    # neither may carry a class that would make the note speak about them.
    cat = load_catalog()
    nebulae = [o for o in cat if o.type == "nebula"]
    assert len(nebulae) >= 25, "the bundled nebula set shrank unexpectedly"
    for obj in nebulae:
        assert obj.nebula_class in _VALID_CLASSES, f"{obj.id}: {obj.nebula_class!r}"
    for obj in cat:
        if obj.type != "nebula":
            assert obj.nebula_class == "", f"{obj.id} ({obj.type}) must carry no class"


def test_the_curated_class_agrees_with_the_entry_s_own_blurb():
    # The evidence rule for this curation (the one v0.276.0's distance_ly pass
    # used): where an entry's *own* beginner blurb names the family, the vetted
    # class must agree with it. That catches a transcription slip without needing
    # an outside source, and it is why "both" exists — M20's blurb names both.
    for obj in load_catalog():
        if obj.type != "nebula" or not obj.blurb:
            continue
        blurb = obj.blurb.lower()
        says_emission = "emission" in blurb
        says_reflection = "reflection" in blurb
        if says_emission and says_reflection:
            assert obj.nebula_class == "both", obj.id
        elif says_emission:
            assert obj.nebula_class == "emission", obj.id
        elif says_reflection:
            assert obj.nebula_class == "reflection", obj.id


@pytest.mark.parametrize("obj_id,expected", [
    ("M42", "emission"),      # Orion — the classic first target
    ("M8", "emission"),       # Lagoon
    ("NGC 7000", "emission"), # North America
    ("M78", "reflection"),    # the textbook blue reflection nebula
    ("NGC 7023", "reflection"),  # Iris
    ("M20", "both"),          # Trifid — pink emission *and* blue reflection
    ("IC 405", "both"),       # Flaming Star
    ("NGC 2264", "unknown"),  # cluster + emission + dark nebula in one field
])
def test_the_targets_a_beginner_actually_shoots_are_classified_as_expected(
        obj_id, expected):
    obj = next(o for o in load_catalog() if o.id == obj_id)
    assert obj.nebula_class == expected


def test_an_entry_without_the_field_still_loads(tmp_path):
    # Upgrade-safety in the other direction: the loader must not require the new
    # key (a catalog file edited by hand, or a partially-updated checkout).
    import json

    from seestack.nightplan import _load_catalog_file

    path = tmp_path / "cat.json"
    path.write_text(json.dumps({"objects": [
        {"id": "X1", "name": "", "ra_deg": 1.0, "dec_deg": 2.0,
         "type": "nebula", "con": "Ori"},
    ]}), encoding="utf-8")
    obj = _load_catalog_file(path)[0]
    assert obj.nebula_class == ""
    assert colour_expectation(obj.nebula_class, None) is None


# --- the measurement ---------------------------------------------------------

def test_object_colour_reads_the_blob_not_the_sky():
    # The target is red-led; the *sky* is deliberately blue-led and brighter than
    # the target's own excess, which is the whole reason the measurement is
    # sky-subtracted. A raw median over the object pixels would read blue.
    img = _scene((0.30, 0.12, 0.16), sky_rgb=(0.10, 0.12, 0.20))
    m = measure_object_colour(img)
    assert m["measured"] is True
    assert m["balance"] > 0.15, m
    assert m["r"] > m["b"] > 0.0


def test_object_colour_is_quiet_on_a_frame_with_no_object():
    # Pure sky + noise, and a star field: neither carries a colour, so the
    # balance must sit at zero and no family verdict may fire off it.
    noise_only = _scene((0.0, 0.0, 0.0))
    m = measure_object_colour(noise_only)
    assert abs(m["balance"]) < 0.05 and abs(m["green_excess"]) < 0.05
    assert colour_expectation("emission", m) is None
    # The 2σ cut must select a *small* slice of a pure-noise frame. (Anchoring it
    # on the sky-population median with a lower-half MAD for σ selected ~34 % —
    # a third of a blank frame counted as "object".)
    assert m["fraction"] < 0.06, m["fraction"]

    stars = _scene((0.0, 0.0, 0.0), stars=250, seed=11)
    assert colour_expectation("emission", measure_object_colour(stars)) is None


def test_object_colour_ignores_nan_coverage_gaps_and_gives_up_on_an_empty_frame():
    img = _scene((0.30, 0.12, 0.16))
    img[:100, :, :] = np.nan                       # a third uncovered
    m = measure_object_colour(img)
    assert m["measured"] is True and m["balance"] > 0.1
    empty = measure_object_colour(np.full((80, 80, 3), np.nan, dtype=np.float32))
    assert empty["measured"] is False and empty["r"] is None
    tiny = measure_object_colour(np.full((4, 4, 3), 0.2, dtype=np.float32))
    assert tiny["measured"] is False


def test_saturated_star_cores_do_not_wash_the_colour_out():
    # A star core clips to neutral white whatever the nebula's colour is, so the
    # brightest slice of the object population is trimmed before the medians.
    clean = measure_object_colour(_scene((0.30, 0.12, 0.16)))
    starry = measure_object_colour(_scene((0.30, 0.12, 0.16), stars=250))
    assert starry["balance"] > 0.15
    assert starry["balance"] == pytest.approx(clean["balance"], abs=0.08)


# --- the verdict -------------------------------------------------------------

_RED = {"measured": True, "balance": 0.25, "green_excess": -0.10}
_BLUE = {"measured": True, "balance": -0.25, "green_excess": -0.10}
_GREEN = {"measured": True, "balance": 0.0, "green_excess": 0.25}
_FLAT = {"measured": True, "balance": 0.02, "green_excess": 0.0}


def test_a_red_emission_nebula_is_reassured_and_a_blue_one_is_nudged():
    ok = colour_expectation("emission", _RED)
    assert isinstance(ok, ColourNote) and ok.ok is True
    assert "looks right" in ok.text and "emission" in ok.text
    bad = colour_expectation("emission", _BLUE)
    assert bad is not None and bad.ok is False
    assert "red-pink" in bad.text and "blue" in bad.text
    # Never the word "wrong" — this has to read as help, not a verdict.
    assert "wrong" not in bad.text.lower()


def test_a_reflection_nebula_reads_the_mirror_image():
    ok = colour_expectation("reflection", _BLUE)
    assert ok is not None and ok.ok is True and "blue" in ok.text
    bad = colour_expectation("reflection", _RED)
    assert bad is not None and bad.ok is False and "red" in bad.text


def test_a_green_picture_is_pointed_at_the_green_removal_step():
    # No deep-sky object is green, so this is always a processing fault — and the
    # one case where there is a specific one-click answer to name.
    for family in ("emission", "reflection"):
        note = colour_expectation(family, _GREEN)
        assert note is not None and note.ok is False
        assert "SCNR" in note.text and "green" in note.text


def test_it_says_nothing_at_all_unless_it_is_confident():
    # Everything that must stay silent, in one place — this is the feature's
    # whole risk, and a regression here is a false accusation on a fine picture.
    assert colour_expectation("both", _BLUE) is None        # M20-shaped
    assert colour_expectation("unknown", _BLUE) is None
    assert colour_expectation("", _RED) is None             # galaxy/cluster/no match
    assert colour_expectation(None, _RED) is None
    assert colour_expectation("emission", None) is None     # nothing measured
    assert colour_expectation("emission", {"measured": False}) is None
    # The dead band: an emission nebula that came out roughly neutral is
    # unremarkable, not a fault — neither reassure nor nudge.
    assert colour_expectation("emission", _FLAT) is None
    # …and a mild green tint, still inside ordinary OSC variation, is not a nag.
    mild = {"measured": True, "balance": 0.25, "green_excess": 0.08}
    assert colour_expectation("emission", mild) is None


def test_the_reassurance_is_withheld_while_a_visible_green_cast_remains():
    # Red/blue balance can look fine while green still sits over both — saying
    # "colour looks right" there would bless a picture the user can see is off.
    green_but_red_led = {"measured": True, "balance": 0.25, "green_excess": 0.09}
    assert colour_expectation("emission", green_but_red_led) is None


def test_end_to_end_from_pixels_to_the_line_a_beginner_reads():
    emission_ok = colour_expectation(
        "emission", measure_object_colour(_scene((0.30, 0.12, 0.16))))
    assert emission_ok is not None and emission_ok.ok is True

    # The failure this feature exists to catch: the OSC's green-heavy raw balance
    # survived into the finished picture.
    broken = colour_expectation(
        "emission", measure_object_colour(_scene((0.12, 0.30, 0.13))))
    assert broken is not None and broken.ok is False and "SCNR" in broken.text

    # The same green picture of a *Trifid* says nothing, because the catalog
    # can't claim one expected colour for it.
    assert colour_expectation(
        "both", measure_object_colour(_scene((0.12, 0.30, 0.13)))) is None
