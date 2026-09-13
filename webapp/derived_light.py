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
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from webapp.run_options import derived_from_run_id

#: The columns a re-render inherits from the stack it was rendered from, because
#: they are facts about the *light* rather than about the pixels. Kept as a tuple
#: (not spelled at the call sites) so the write-time list in
#: ``webapp.pipeline._apply_editor_to_run`` and this read-time one can be seen to
#: be the same set.
INHERITED_LIGHT_FACTS = ("total_exposure_s", "calstat", "transparency_ratio")


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


def _root_stack(run: Any, by_id: dict[Any, Any]) -> Any | None:
    """The stack at the bottom of this row's derived chain, or ``None``.

    An edit of an edit is ordinary (open the finished picture, adjust, save
    again), so the answer is not simply ``by_id[derived_from]``: that row may be
    an export too, and just as empty. Walk down to the first row that is not
    derived from anything still here. ``seen`` guards a cycle — nothing writes
    one, but a hand-edited ``options_json`` is user data and must not hang a
    page.
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
    """
    by_id = {r.id: r for r in runs}
    out: list[R] = []
    for run in runs:
        source = _root_stack(run, by_id)
        if source is None:
            out.append(run)
            continue
        missing = {
            field: getattr(source, field)
            for field in INHERITED_LIGHT_FACTS
            if getattr(run, field, None) is None
            and getattr(source, field, None) is not None
        }
        out.append(replace(run, **missing) if missing else run)  # type: ignore[type-var]
    return out
