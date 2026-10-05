"""The ``project_meta`` keys the web layer hangs off a single stack-run id.

A stack run is a row in ``stack_runs``, but several features annotate one out of
band, as a ``project_meta`` key of the form ``<prefix><run_id>``: the editor's
saved recipe and the recipe an export of that run rendered, the plain-language
"what Auto did" note, the three measurements an unattended auto-edit records
(its colour cast, its colour calibration and its highlight reading), the
calibration skipped/warnings notes a stack job stamps, and the remembered
"stacking cut your noise ~N×" measurement.

Each prefix stays owned by the module that writes it — this module only
*collects* them, so that deleting a run can take its annotations with it instead
of leaving orphan rows nothing will ever read, and so a future per-run key has
one obvious place to be registered. ``tests/webapp/test_run_purge.py`` fails if a
new ``…_PREFIX`` is used with a run id without being listed here — and it reads
the *source* of every file under ``webapp/`` to do it, because resolving the name
on the module that **uses** it is defeated by the lazy imports below and left
7 of 9 sites in ``webapp/pipeline.py`` unchecked in silence until 2026-10-05
(observer issue #1079).
"""

from __future__ import annotations

import contextlib
from typing import Any


def per_run_meta_prefixes() -> tuple[str, ...]:
    """Every ``project_meta`` key prefix that is keyed by a stack-run id.

    Imported lazily from the owning modules (``webapp.pipeline`` is heavy and
    imports routers) so this module stays cheap and cycle-free.
    """
    from webapp.pipeline import (
        CALIBRATION_SKIPPED_META_PREFIX,
        CALIBRATION_WARNINGS_META_PREFIX,
    )
    from webapp.routers.editor import (
        AUTO_EDIT_BAKED_LOOK_PREFIX,
        AUTO_EDIT_COLORCAL_PREFIX,
        AUTO_EDIT_HIGHLIGHT_PREFIX,
        AUTO_EDIT_NOTE_PREFIX,
        AUTO_EDIT_SKYCAST_PREFIX,
        EXPORTED_RECIPE_META_PREFIX,
        RECIPE_META_PREFIX,
    )
    from webapp.routers.stack import NOISE_RATIO_META_PREFIX

    return (
        RECIPE_META_PREFIX,
        EXPORTED_RECIPE_META_PREFIX,
        AUTO_EDIT_NOTE_PREFIX,
        AUTO_EDIT_SKYCAST_PREFIX,
        AUTO_EDIT_COLORCAL_PREFIX,
        # The sibling of the sky-cast above, stamped by the same unattended
        # auto-edit sixteen lines further down (``webapp/pipeline.py``), and
        # missed when it shipped: registered 2026-10-05 from observer issue
        # #1079. Nothing read the orphans it left (the roll-up looks each
        # existing run up by its own id) and `stack_runs.id` is AUTOINCREMENT, so
        # an orphan could never be picked up by a later run — it was dead weight
        # in ``project_meta``, and the guard that exists to catch exactly this was
        # blind to the module both prefixes are written from.
        AUTO_EDIT_HIGHLIGHT_PREFIX,
        AUTO_EDIT_BAKED_LOOK_PREFIX,
        CALIBRATION_SKIPPED_META_PREFIX,
        CALIBRATION_WARNINGS_META_PREFIX,
        NOISE_RATIO_META_PREFIX,
    )


def delete_run_meta(proj: Any, run_id: int) -> None:
    """Drop every per-run annotation for ``run_id``.

    Only ever called for a run being deleted in the same breath — never as a
    sweep over the whole table. A recipe is the user's own work, so the one safe
    moment to remove it is when the picture it describes is going too.
    """
    for prefix in per_run_meta_prefixes():
        with contextlib.suppress(Exception):
            proj.delete_meta(f"{prefix}{run_id}")
