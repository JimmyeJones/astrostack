"""The two languages' "this picture is thin" bar must not drift apart.

``thinStackWarning`` (``frontend/src/components/target/thinStack.ts``) has owned
this judgement since v0.419.1 and writes the sentence for it on the Target,
Gallery and Jobs surfaces. The Library wall's chip (v0.450.0) comes off an
endpoint that scans the whole library, so the *decision* has to be made in Python
before the list goes on the wire — ``webapp.thinpicture``.

Two copies of one threshold, and nothing to fail if they diverge: the wall would
chip a card the Gallery calls healthy, or stay silent on one it warns about,
which is the exact "two surfaces, one fact, opposite answers" this codebase keeps
undoing. Guarded here the same way ``test_fullres_cap_mirror.py`` guards the
full-res cap.

The *rounding* is mirrored too, and it is not decoration: JavaScript's
``Math.round`` takes a half up while Python's ``round`` takes it to even, so a
mosaic measured at exactly 4.5 subs a patch would be thin in one language and
healthy in the other.
"""

from __future__ import annotations

import re
from pathlib import Path

from webapp.thinpicture import (
    THIN_PICTURE_MAX_SAMPLES,
    picture_is_thin,
    samples_on_one_patch,
)

THIN_STACK_TS = (Path(__file__).resolve().parents[1] / "frontend" / "src"
                 / "components" / "target" / "thinStack.ts")


def _ts_number(name: str) -> float:
    """The numeric value of a top-level ``const`` in ``thinStack.ts``.

    Fails loudly when the declaration can't be found: a renamed or relocated
    constant is itself the drift this guard exists to catch, and a check that
    silently passes when it can't find its subject enforces nothing."""
    src = THIN_STACK_TS.read_text(encoding="utf-8")
    m = re.search(rf"^export const {name}\s*=\s*([0-9.]+)\s*;", src, re.M)
    assert m is not None, (
        f"Could not find `export const {name}` in {THIN_STACK_TS.name}. If it "
        "was renamed or moved, update this guard and check it still agrees with "
        "webapp/thinpicture.py's THIN_PICTURE_MAX_SAMPLES — otherwise the "
        "Library wall and the Gallery card start disagreeing about which "
        "pictures are thin."
    )
    return float(m.group(1))


def test_the_walls_bar_matches_the_gallery_badges():
    assert float(THIN_PICTURE_MAX_SAMPLES) == _ts_number("THIN_STACK_MAX_FRAMES"), (
        "webapp/thinpicture.py and frontend/src/components/target/thinStack.ts "
        "disagree about how many subs on one patch of sky is 'thin'. Change "
        "them together."
    )


def test_a_single_field_is_judged_on_its_own_frame_count():
    """No field-fulls scale means every sub covered every pixel, so the count
    *is* the depth — which is what the TypeScript does when `fieldFulls` is
    absent or at/below 1.0."""
    assert samples_on_one_patch(4, None) == 4
    assert samples_on_one_patch(4, 1.0) == 4
    assert picture_is_thin(4, None) is True
    assert picture_is_thin(5, None) is False
    # A scale below 1.0 would *inflate* the apparent depth; both languages clamp.
    assert picture_is_thin(3, 0.25) is True


def test_a_mosaics_total_is_divided_by_the_sky_it_covers():
    """Thirty subs over a 3x3 raster is three on each patch — the substitution
    the whole module exists to undo."""
    assert samples_on_one_patch(30, 9.0) == 3
    assert picture_is_thin(30, 9.0) is True
    # The same thirty subs on a single field are not thin at all.
    assert picture_is_thin(30, None) is False


def test_the_half_rounds_the_way_javascript_does():
    """4.5 subs a patch is "about 5", i.e. healthy — `Math.round`'s answer, not
    `round`'s (which would take it to 4 and call the picture thin)."""
    assert samples_on_one_patch(9, 2.0) == 5      # 4.5 -> 5
    assert picture_is_thin(9, 2.0) is False
    assert samples_on_one_patch(7, 2.0) == 4      # 3.5 -> 4
    assert picture_is_thin(7, 2.0) is True


def test_nothing_measurable_is_never_read_as_thin():
    """A chip that appeared because a number was *missing* would accuse an
    upgrading install's whole wall."""
    for bad in (None, "", "abc", -1, float("nan"), float("inf")):
        assert samples_on_one_patch(bad, 4.0) is None or not picture_is_thin(
            bad, 4.0), bad
        assert picture_is_thin(bad, 4.0) is False, bad
    # A nonsense scale falls back to "no scaling" rather than to a guess.
    assert picture_is_thin(30, float("nan")) is False
    assert picture_is_thin(3, float("nan")) is True
