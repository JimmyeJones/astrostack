"""Is the picture a target is *showing* deep enough to be worth looking at?

The Python half of ``frontend/src/components/target/thinStack.ts``, which has
answered this for the Gallery card, the Target page and the Jobs page since
v0.419.1 and which owns the wording. All that lives here is the *decision* — is
this run thin? — because the Library wall's chip is served by an endpoint that
scans the whole library, so the threshold has to be applied before the list goes
on the wire rather than after.

**Why the wall needed it at all.** A Library card's frame badge reads
``900/1000 frames``, which on a mosaic is the flattering number this app has now
corrected in five other places: the subs are spread over the raster, so a 12×8
at 900 subs is about nine on each patch of sky, and a 3×3 at thirty is three.
The card said nothing about that, and a picture that is one sub deep everywhere
— the "gibberish" case — sat on the wall looking like any other. The Gallery
card of the very same run already turns its badge orange.

**One definition, two languages.** The threshold below is a hand-mirror of the
TypeScript constant, guarded by ``tests/test_thin_picture_mirror.py`` the way
``test_fullres_cap_mirror.py`` guards the full-res cap — a stale copy here would
put a chip on a card the Gallery calls healthy, with nothing failing. The
*sentence* is never written here: the endpoint serves the two numbers
``thinStackWarning`` needs (``n_frames_used`` and ``field_fulls``) and the wall
asks that same function, so the chip's hint and the Gallery's tooltip are one
string produced once.
"""

from __future__ import annotations

import math

#: At or under this many subs **on one patch of sky** a stack is genuinely noisy
#: and worth saying so. Hand-mirror of ``THIN_STACK_MAX_FRAMES`` in
#: ``frontend/src/components/target/thinStack.ts`` — see the module docstring for
#: the drift guard. Chosen there from the √N noise curve: below ~5 frames the
#: stack has barely started averaging the sky down.
THIN_PICTURE_MAX_SAMPLES = 4


def samples_on_one_patch(n_frames_used: object,
                         field_fulls: float | None) -> float | None:
    """How many subs one patch of this run's sky has, as ``thinStackWarning``
    computes it — ``None`` when the count is missing or nonsensical.

    Mirrors the TypeScript exactly, including *when* it rounds: a single field
    (no ``field_fulls``, or one at or below 1.0) answers with the raw frame
    count, because every sub covers every pixel and the count already *is* the
    depth; a mosaic answers with the rounded quotient, so the sentence and the
    threshold agree on one integer rather than disagreeing by a fifth of a sub.

    ``round`` is spelled ``floor(x + 0.5)`` on purpose: JavaScript's ``Math.round``
    takes a half up and Python's ``round`` takes it to even, so a depth of 4.5
    would be thin in one language and healthy in the other.
    """
    try:
        used = float(n_frames_used)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(used) or used < 0:
        return None
    fulls = float(field_fulls) if field_fulls is not None else 1.0
    if not math.isfinite(fulls) or fulls <= 1.0:
        return used                      # a single field: the count is the depth
    return math.floor(used / fulls + 0.5)


def picture_is_thin(n_frames_used: object,
                    field_fulls: float | None) -> bool:
    """True when this run's picture is only a few subs deep on any one patch.

    ``False`` for anything unmeasurable — a run with no usable frame count is not
    evidence of a thin picture, and a chip that appeared because a number was
    *missing* would accuse an upgrading install's whole wall.
    """
    depth = samples_on_one_patch(n_frames_used, field_fulls)
    return depth is not None and depth <= THIN_PICTURE_MAX_SAMPLES
