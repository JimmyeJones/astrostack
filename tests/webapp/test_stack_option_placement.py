"""The frontend's stack-option placement snapshot must match the engine.

``frontend/src/test/stackOptionPlacement.json`` is what the Stack and Settings
forms' hand-written ``StackOptionField`` fixtures are checked against, so that a
fixture can't quietly put a control somewhere the running app never does. The
editor's equivalent guard (``test_editor_op_placement.py``) exists because
v0.240.0 shipped a button no beginner could see for exactly that reason; these
two screens render through the *same* descriptor-driven control, with the same
simple/advanced accordion split, and a beginner touches the Stack form far more
often than the editor.

A snapshot is only worth having if it can't go stale, which is this test's whole
job: change a descriptor's ``group``/``type``/``depends_on`` in
``webapp/schemas.py`` and this fails until the file is regenerated.
"""

from __future__ import annotations

import json
from pathlib import Path

from webapp.schemas import stack_option_fields

SNAPSHOT = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "test" / "stackOptionPlacement.json"
)

#: Printed on failure so the fix is a copy/paste, not an archaeology exercise.
REGENERATE = (
    "Regenerate it with:\n"
    "  python -c \"import json,pathlib;from webapp.schemas import "
    "stack_option_fields;p=pathlib.Path('frontend/src/test/"
    "stackOptionPlacement.json');p.write_text(json.dumps({f.key:{'type':f.type,"
    "'group':f.group,'depends_on':f.depends_on} for f in stack_option_fields()},"
    "indent=2,sort_keys=True)+chr(10))\""
)


def _current_placement() -> dict:
    return {
        f.key: {"type": f.type, "group": f.group, "depends_on": f.depends_on}
        for f in stack_option_fields()
    }


def test_snapshot_matches_the_engine_stack_descriptors():
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert saved == _current_placement(), (
        "frontend/src/test/stackOptionPlacement.json is out of date with the "
        "engine's StackOptions descriptors, so the Stack/Settings fixture-drift "
        f"guard is checking against a stale placement.\n{REGENERATE}"
    )


def test_snapshot_covers_every_field():
    """A silently *empty* snapshot would make the frontend guard a no-op."""
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    fields = stack_option_fields()
    assert len(saved) == len(fields) > 0
    assert set(saved) == {f.key for f in fields}
