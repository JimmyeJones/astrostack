"""The ``project_meta`` keys the web layer hangs off a single stack-run id.

A stack run is a row in ``stack_runs``, but several features annotate one out of
band, as a ``project_meta`` key of the form ``<prefix><run_id>``: the editor's
saved recipe and the recipe an export of that run rendered, the plain-language
"what Auto did" note, the two colour measurements an unattended auto-edit
records, and the calibration skipped/warnings notes a stack job stamps.

Each prefix stays owned by the module that writes it — this module only
*collects* them, so that deleting a run can take its annotations with it instead
of leaving orphan rows nothing will ever read, and so a future per-run key has
one obvious place to be registered. ``tests/webapp/test_run_purge.py`` fails if a
new ``…_PREFIX`` is used with a run id without being listed here.
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
        AUTO_EDIT_COLORCAL_PREFIX,
        AUTO_EDIT_NOTE_PREFIX,
        AUTO_EDIT_SKYCAST_PREFIX,
        EXPORTED_RECIPE_META_PREFIX,
        RECIPE_META_PREFIX,
    )

    return (
        RECIPE_META_PREFIX,
        EXPORTED_RECIPE_META_PREFIX,
        AUTO_EDIT_NOTE_PREFIX,
        AUTO_EDIT_SKYCAST_PREFIX,
        AUTO_EDIT_COLORCAL_PREFIX,
        CALIBRATION_SKIPPED_META_PREFIX,
        CALIBRATION_WARNINGS_META_PREFIX,
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
