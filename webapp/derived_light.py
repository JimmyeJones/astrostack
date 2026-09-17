"""What a finished picture keeps of the light it was made from.

An editor export is a *re-render* of pixels a stack already combined: the same
subs, the same nights, the same darks and flats. ``_apply_editor_to_run`` records
it as a ``stack_runs`` row of its own, and until v0.438.7 that row left
``total_exposure_s``, ``calstat`` and ``transparency_ratio`` at their NULL
defaults — so the picture the owner actually shares and pins as a cover was the
one with no integration time on its card, and "My best pictures" ranked it over
two of the four metrics its blend has (``seestack.portfolio._score``
renormalises over the figures an entry carries, so a missing one is a quietly
lower placing).

The export now carries those three forward at write time. This module is the
other half: **the exports already on disk**, which no fix at write time can
reach. It is the same lazy, read-side heal :mod:`seestack.coverage_backfill`
performs for the columns whose input is still beside the master — except that
here the input is cheaper still, a sibling row in the same table, already in
hand wherever a listing is built. So nothing is read, nothing is written, and a
row that cannot be resolved is returned exactly as it was.

**Only facts about the light travel.** The line is the one
``_apply_editor_to_run`` documents at the point of writing:

* ``noise_sigma``, ``stack_fwhm_px``, ``seam_residual``, ``grain_ratio`` are
  measurements of the *combined image*; a denoise or a sharpen moves them, so
  inheriting one would present a measurement of a different picture as this
  one's.
* ``is_mosaic`` is read **behaviourally** — ``editor._run_is_mosaic`` falls back
  to the coverage map only while the column is NULL, and an export's coverage is
  uniform — so filling it would make re-opening an edit trim a border off a
  picture Auto has already trimmed.
* ``duration_s`` and the rejection/coverage columns describe what the stacker
  did, which an export did not do.

The coverage columns need one more sentence than that, because a reader can be
*worse off* than not knowing: ``_apply_editor_to_run`` does not leave them NULL,
it writes a literal ``coverage_min = coverage_max = 1``. See
:func:`stacking_coverage_max`.

``canvas_w``/``canvas_h`` are a third kind again. They are a true statement about
the export — those really are its pixels, and the surfaces that *describe* the
file (the full-res PNG's dimensions, the print sizes) must keep reading them —
but they are the wrong row to *divide* a per-pixel figure by, because a crop
shrinks them while the light stays what it was. See
:func:`stacking_field_fulls`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from seestack.stackhealth import readable_transparency_ratio
from webapp.field_fulls import drizzle_scale_from_options, field_fulls_of_sky
from webapp.run_options import derived_from_run_id

#: The columns a re-render inherits from the stack it was rendered from, because
#: they are facts about the *light* rather than about the pixels. Kept as a tuple
#: (not spelled at the call sites) so the write-time list in
#: ``webapp.pipeline._apply_editor_to_run`` and this read-time one can be seen to
#: be the same set.
INHERITED_LIGHT_FACTS = ("total_exposure_s", "calstat", "transparency_ratio")

#: How to *read* an inherited fact off the source row, where reading it is more
#: than an attribute lookup. ``transparency_ratio`` is: its estimator moved in
#: v0.304.2 and a mosaic figure from before it is on a different scale from the
#: bar it would be read through, so the source answers ``None`` for one nobody
#: can date — see :func:`seestack.stackhealth.readable_transparency_ratio`. An
#: export carries neither ``is_mosaic`` (deliberately, see the module docstring)
#: nor the source's ``engine_version``, so nothing downstream could make that
#: judgement for itself; it has to be made here, where the source row is in hand.
_INHERIT_READERS = {"transparency_ratio": readable_transparency_ratio}


def stacking_coverage_max(run: Any) -> int:
    """This row's peak stacking depth, or ``0`` where it never stacked.

    ``coverage_max`` is "how many frames landed on the deepest pixel", and on an
    ordinary run it is a measurement. On a **re-render** it is not: an editor
    export combines nothing, so ``_apply_editor_to_run`` writes a literal
    ``coverage_min = coverage_max = 1`` to describe a single-layer raster.

    That literal is the problem. ``seestack.portfolio`` is built so that a metric
    an entry does not carry *neither helps nor hurts* — the blend renormalises
    over whatever is present — but a placeholder ``1`` is present, and it reads
    as a picture one sub deep at its deepest point. Measured on the wall's own
    scorer: a finished picture that is the best in the collection on every metric
    it actually carries scored **0.868 instead of 1.000**, and against a deeper
    rival 0.578 instead of 0.667 — i.e. the one picture the owner edited, shares
    and pins was ranked down for having been finished.

    So the honest answer for anything that reads this column as a *depth* is
    ``0``, the same "unrecorded" every pre-schema run already gives. The stored
    row is untouched; this is a read-side rule, like the rest of this module.

    Deliberately keyed on the row being a re-render (``derived_from``) rather
    than on the value ``1``: a genuine one-frame stack also records 1, and there
    the number is true.
    """
    if derived_from_run_id(getattr(run, "options_json", None)) is not None:
        return 0
    return int(getattr(run, "coverage_max", 0) or 0)


def stacking_field_fulls(
    run: Any,
    by_id: dict[Any, Any],
    native_shape: tuple[float, float] | None,
) -> float | None:
    """How many field-fulls of sky this row's **light** was spread over.

    :func:`webapp.field_fulls.field_fulls_of_sky` is the divisor that turns a
    run's totals into per-pixel figures — integration, frame count, the wall's
    ranking — and it is canvas area ÷ one native frame. On a stack that is the
    right question asked of the right row. On a **re-render** it is the right
    question asked of the wrong one: an editor export records the canvas it
    actually wrote (``canvas_h=out.shape[0]``, ``_apply_editor_to_run``), and a
    crop makes that smaller while carrying the source's ``n_frames_used`` and
    ``total_exposure_s`` forward whole. The divisor falls, the quotient rises,
    and the picture claims a depth its pixels never had.

    Not a rare edit, either: the editor seeds Auto on first open (v0.390.0) and
    Auto trims the border, so every finished mosaic is cropped by default.

    **Measured on the bundled 2×2 mosaic sample** (21 subs, 907×615 canvas),
    against the mean of the frame-coverage map over the surviving pixels — the
    directly measured answer to "how many subs does a pixel here hold?":

    ==========================  ========  ==========  ===========
    crop                        measured  own canvas  this rule
    ==========================  ========  ==========  ===========
    none (the whole canvas)        5.855       5.783       5.783
    Auto's border trim (92.6 %)    5.890       6.244       5.783
    a content crop (25 %)          6.631      21.000       5.783
    ==========================  ========  ==========  ===========

    So the two halves the lead separated do behave differently — trimming a
    ragged border is only +6.0 % out, because the pixels it removes really were
    the shallow ones, while cropping to the subject is **3.2× out**, because the
    pixels it removes were as deep as the ones that stayed. But they do not need
    two rules: reading the source stack's canvas is within 1.8 % on the trim and
    12.8 % on the content crop, and — the property that decides it — it errs
    *low* in both, where the row's own canvas errs high. This is the same
    direction :func:`field_fulls_of_sky` already clamps for: a number that
    overstates a picture's depth tells a beginner to stop shooting.

    A row that is not a re-render, and one whose source has been pruned from
    History, both answer from their own canvas — which is what they have always
    done, and for the pruned row is the only thing left to answer with. The
    drizzle scale travels with the canvas for the same reason: it is the
    stacking run that drizzled, and an export's options record no scale at all.

    ``native_shape`` is the target's native sub shape (one ``LIMIT 1`` read per
    target, which every caller already makes); ``None`` there — or any missing
    dimension — answers ``None``, i.e. "no scaling", exactly as before.
    """
    if native_shape is None:
        return None
    measured = root_stack(run, by_id) or run
    return field_fulls_of_sky(
        getattr(measured, "canvas_w", None),
        getattr(measured, "canvas_h", None),
        frame_w=native_shape[0],
        frame_h=native_shape[1],
        drizzle_scale=drizzle_scale_from_options(
            getattr(measured, "options_json", None)),
    )


def stacking_samples_per_pixel(
    run: Any,
    by_id: dict[Any, Any],
    native_shape: tuple[float, float] | None,
) -> float | None:
    """How many subs landed on **one pixel** of this row's picture.

    :func:`webapp.field_fulls.samples_per_pixel_of_run` with the denominator
    :func:`stacking_field_fulls` corrects — the numerator needs no correction,
    because ``_apply_editor_to_run`` already carries the source's
    ``n_frames_used`` forward (an export combines nothing of its own).

    ``None`` whenever the answer would be a guess, so every caller keeps its
    depth-unaware behaviour.
    """
    fulls = stacking_field_fulls(run, by_id, native_shape)
    if fulls is None or fulls <= 0:
        return None
    n_used = getattr(run, "n_frames_used", None)
    try:
        used = float(n_used)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    depth = used / fulls
    if not math.isfinite(depth) or depth <= 0:
        return None
    return depth


def root_stack(run: Any, by_id: dict[Any, Any]) -> Any | None:
    """The stack at the bottom of this row's derived chain, or ``None``.

    An edit of an edit is ordinary (open the finished picture, adjust, save
    again), so the answer is not simply ``by_id[derived_from]``: that row may be
    an export too, and just as empty. Walk down to the first row that is not
    derived from anything still here. ``seen`` guards a cycle — nothing writes
    one, but a hand-edited ``options_json`` is user data and must not hang a
    page.

    Public because the light facts are not the only thing a re-render cannot
    answer for itself: :mod:`webapp.framing_advice` needs the same row for the
    same reason, and two walks of one chain would be two chances to disagree
    about it.
    """
    seen = {run.id}
    current = run
    while True:
        source_id = derived_from_run_id(current.options_json)
        if source_id is None or source_id in seen:
            break
        source = by_id.get(source_id)
        if source is None:
            break
        seen.add(source_id)
        current = source
    return None if current is run else current


def with_inherited_light_facts[R](runs: Sequence[R]) -> list[R]:
    """``runs`` with each re-render's missing light facts filled from its stack.

    Pure and total: the rows come back in the order they went in, an ordinary
    stack is returned **identically** (the same object, not a copy), and a value
    the row already carries is never overwritten — this only ever answers where
    the row said "unknown". A derived row whose source has been pruned from
    History keeps its blanks, because there is then nothing to answer with.

    A fact the *source* cannot vouch for is not handed over either
    (:data:`_INHERIT_READERS`): "unknown" is the honest thing to inherit, and an
    export is the one row that could never re-derive it for itself.
    """
    by_id = {r.id: r for r in runs}
    out: list[R] = []
    for run in runs:
        source = root_stack(run, by_id)
        if source is None:
            out.append(run)
            continue
        missing: dict[str, Any] = {}
        for field in INHERITED_LIGHT_FACTS:
            if getattr(run, field, None) is not None:
                continue
            reader = _INHERIT_READERS.get(field)
            value = reader(source) if reader else getattr(source, field, None)
            if value is not None:
                missing[field] = value
        out.append(replace(run, **missing) if missing else run)  # type: ignore[type-var]
    return out
