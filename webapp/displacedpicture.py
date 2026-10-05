"""Which History rows are showing a picture that is not their own.

Before the v0.81.7–0.81.8 overwrite guard a re-stack wrote the canonical
``master.*`` straight over the previous run's output, and
:meth:`seestack.io.project.Project.repoint_stack_runs` — which moves the older
row onto the archived name — runs **only at re-stack time** and is "purely
additive to history" (its own docstring). So nothing ever migrated the rows
written before the guard: they still name a file a *newer* run wrote. Observer
issue #1069 counts **56 of 745** such rows on the owner's library, on 15 shared
paths.

What that looks like on the History page is one card carrying two pictures' worth
of facts: the older run's frame count, integration time and canvas beside the
*newer* run's thumbnail and FITS. Every number on the card is true of the run;
the image is not. The old pixels were overwritten, so there is nothing to repoint
to — the only honest fix is to **say so**.

**The signature, and why this one.** Two rows naming one ``fits_path`` *is* the
bug: the guard exists precisely to stop that happening, so after it, no two rows
share a canonical path (a re-stack archives the set and repoints the old row; an
editor re-export under one basename does the same). The older row of such a pair
owns no files at all.

This is the cheapest of the three signatures and the only one that reads no
files. The History listing already holds every row in memory, so the answer costs
one pass over a list the endpoint has anyway — which matters because the cheap
History endpoints promise *no file read* (see
:func:`webapp.field_fulls.samples_per_pixel_of_run`), and a header read per row to
compare ``canvas_w``/``canvas_h`` against the file's ``NAXIS`` is the thing that
promise exists to avoid.

**What it does not catch, stated rather than discovered later.** A merge erases
the signature: :func:`seestack.io.merge._carry_pictures` takes a ``_free_basename``
per run and *copies* the files, so a displaced pair becomes two rows with distinct
paths, each pointing at its own copy. This then says nothing where a
``canvas``-vs-``NAXIS`` check would still fire. That is the safe direction — it
under-reports rather than mis-states — and it is why the sibling guard in
:func:`seestack.coverage_backfill._canvas_of`, which *is* already holding the file
open, keys on ``NAXIS`` instead. The two agree exactly on the owner's library
today: 71 rows on 15 shared paths is 56 non-writers, the same 56 the ``NAXIS``
comparison finds.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seestack.io.project import StackRunRow


def picture_owner_by_run_id(
    runs: Iterable[StackRunRow],
) -> dict[int, int]:
    """``{displaced run id: the run id whose picture that file actually is}``.

    A run is in the map when **another** run in ``runs`` names the same
    ``fits_path`` and was recorded later — so the file on disk is that later
    run's output and this row is only pointing at it. Runs that own their picture
    are simply absent, which is every run on an install that has only ever
    re-stacked since v0.81.8.

    Ordered by **row id**, not by ``timestamp_utc``: the id is the order the runs
    were recorded in, while the timestamp is a string that has been written in
    more than one format over the app's life (``…+00:00`` and ``…Z`` both appear),
    so comparing timestamps could put a pair the wrong way round. The later row is
    the one whose ``write_stack_outputs`` call last wrote those bytes.

    **Only when the file is still there.** A path no file sits at is already
    reported by ``has_fits``/``has_preview``, and the card says "no picture"
    without this; claiming it was *overwritten* would be a guess, since it may
    simply have been deleted. Restricting the claim to a file that exists is what
    makes "what you are looking at belongs to a later stack" literally true.

    Pure, read-only and file-system-light: one ``stat`` per *shared* path, and
    none at all for the overwhelmingly common case of a history with no duplicate
    (the existence check runs only inside a group of more than one row).
    """
    by_path: dict[str, list[StackRunRow]] = {}
    for run in runs:
        if run.id is None or not run.fits_path:
            continue
        by_path.setdefault(str(run.fits_path), []).append(run)

    owner: dict[int, int] = {}
    for path, group in by_path.items():
        if len(group) < 2:
            continue
        if not Path(path).exists():
            # Nothing to explain: the card already shows no picture, and which of
            # the two ways it went missing is not knowable from here.
            continue
        ordered = sorted(group, key=lambda r: int(r.id or 0))
        writer = ordered[-1]
        for run in ordered[:-1]:
            owner[int(run.id)] = int(writer.id or 0)
    return owner


def displaced_run_ids(runs: Sequence[StackRunRow]) -> set[int]:
    """Just the ids of the runs whose picture is not their own — the set form of
    :func:`picture_owner_by_run_id`, for a caller that does not need to say which
    run the picture belongs to."""
    return set(picture_owner_by_run_id(runs))
