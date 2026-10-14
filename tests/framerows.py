"""Counting the ``FrameRow`` objects *one call* builds, in a shared process.

``seestack.io.project._row_to_frame`` is the single seam every whole-row read
goes through, which is what makes "this surface reads columns, not whole rows" a
checkable claim at all (v0.495.5 — v0.495.7): the answers are identical either
way, so nothing else in the suite would notice a ``SELECT *`` coming back.

**But it is a module global, and a webapp test does not have the process to
itself.** ``JobManager.stop()`` signals its worker and pushes a sentinel but
never joins it, so a job already in flight keeps running on a daemon thread
after the ``client`` fixture's app has shut down — a ``job-worker`` is still
alive in the *next* test, working on the previous test's data root, and its QC
phase builds exactly one ``FrameRow`` per frame
(``qc.runner.apply_qc_result_to_db`` → ``Project.get_frame``). A plain
``monkeypatch.setattr(project, "_row_to_frame", counting)`` counts those rows
too, and they are not the surface's.

That is what turned ``main``'s own CI run 2294 red on
``test_the_card_builds_no_frame_row_for_the_whole_library`` (*"built 1 FrameRow
objects for the Last-night card"*) while every local ``-n 4`` run passed: CI
runs the suite **sequentially**, in one process, so both the neighbours and the
timing are different ones. The read under test was innocent.

So a row is counted only when the call being measured is somewhere in its own
caller chain. Same assertion, same fail-before, and nothing another thread does
can reach it — a stray row is built on a stack that holds no frame of ours.

The functions are passed as **objects**, not names, and matched on their code
object, so a typo or a rename cannot quietly turn one of these tests into a
tautology. ``tests/`` own project-level tests keep the plain counter: they build
no app, so there is no worker to leak into them.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable, Iterator

import seestack.io.project as _project


@contextlib.contextmanager
def frame_rows_built_by(
    *under: Callable[..., object],
) -> Iterator[Callable[[], int]]:
    """Count the ``FrameRow`` objects built *underneath* any of ``under``.

    Yields a zero-argument callable giving the count so far; read it after the
    block, where the window being measured is exactly the block::

        with frame_rows_built_by(stats.get_last_night) as built:
            body = client.get("/api/last-night").json()
        assert built() == 0

    Name the entry point the claim is about — the endpoint function for a
    request, or the engine/pipeline function for a direct call. Anything a
    *different* thread builds while the block is open is ignored, which is the
    whole point; see the module docstring.
    """
    codes = {fn.__code__ for fn in under}
    if not codes:
        raise ValueError("name at least one function whose rows are being counted")
    built = 0
    real = _project._row_to_frame

    def counting(row):  # noqa: ANN001, ANN202 — mirrors _row_to_frame
        nonlocal built
        frame = sys._getframe()
        while frame is not None:
            if frame.f_code in codes:
                built += 1
                break
            frame = frame.f_back
        return real(row)

    _project._row_to_frame = counting
    try:
        yield lambda: built
    finally:
        _project._row_to_frame = real
