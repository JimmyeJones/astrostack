"""Fill in an older stack run's thin-coverage share from the map it already wrote.

``stack_runs.coverage_thin_frac`` (schema 20) is the number "How's my stack?"
judges a ragged border on — the share of the picture covered by far fewer frames
than the best-covered part. Every run recorded *before* that column existed has
NULL there, and the panel reads NULL as "say nothing", deliberately: the test it
replaced fired on every stack the app had ever made, so re-using it on old runs
would mean knowingly repeating a false alarm. The cost of that correct default is
that a library stacked before the upgrade gets **no** coverage advice at all,
good or bad, until each target happens to be stacked again.

It does not have to wait. The share is a pure function of the per-pixel coverage
map every run already writes beside its master
(:func:`seestack.stack.stacker.coverage_thin_fraction`), so it can be computed
once, from disk, and written back to the row — after which the run answers like
any freshly-stacked one.

This is that heal, and it is deliberately **lazy**: one map read for one run, on
the request that is already grading it. A sweep over the library at startup would
turn the first "How's my stack?" on a big library into a stall, for advice about
runs nobody is looking at.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seestack.io.project import Project, StackRunRow

log = logging.getLogger(__name__)


def backfill_coverage_thin_frac(project: Project,
                                run: StackRunRow) -> float | None:
    """Compute ``run``'s thin-coverage share from its coverage sibling, record it
    on the row, and return it — or ``None`` when it can't be known.

    A no-op (returns the stored value) for a run that already has one, so callers
    can call it unconditionally. ``run`` is updated in place on success, so the
    caller's copy grades exactly like a freshly-stacked run.

    Which map: the honest per-pixel **frame count** (``{stem}_framecov.fits``)
    when the run wrote one, else the weighted coverage map — the same preference,
    in the same order, that :func:`seestack.stack.stacker.run_stack` itself makes
    when it stamps the column on a new run.

    ``None`` — no master path, no sibling on disk, an unreadable one, or a map
    with nothing covered — leaves the row NULL and the panel silent. It never
    falls back to the ``coverage_min`` test that column replaced.
    """
    if run.coverage_thin_frac is not None:
        return float(run.coverage_thin_frac)
    if not run.fits_path:
        return None

    from seestack.edit.proxy import load_coverage, load_frame_coverage
    from seestack.stack.stacker import coverage_thin_fraction

    cov = load_frame_coverage(run.fits_path)
    if cov is None:
        cov = load_coverage(run.fits_path)
    if cov is None:
        return None
    share = coverage_thin_fraction(cov)
    if share is None:
        return None

    if run.id is not None:
        try:
            project.set_stack_coverage_thin_frac(run.id, share)
        except sqlite3.Error:
            # A read-only DB (or one another process has locked) just means this
            # run pays the map read again next time — never an error to the user,
            # who only asked how their stack looks.
            log.debug("could not record coverage_thin_frac for run %s", run.id,
                      exc_info=True)
    run.coverage_thin_frac = share
    return share
