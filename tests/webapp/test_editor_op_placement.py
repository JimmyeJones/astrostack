"""The frontend's editor-op placement snapshot must match the engine.

``frontend/src/test/editorOpPlacement.json`` is what the editor's hand-written
``EditOp`` test fixtures are checked against, so that a fixture can't quietly
put a control somewhere the running app never does. v0.240.0 shipped a "from
your image" button no beginner could see for exactly that reason: the fixture
said ``group: "simple"`` while the engine says ``advanced``, and advanced params
live behind a collapsed accordion.

A snapshot is only worth having if it can't go stale, which is this test's whole
job: change a param's ``group``/``type``/``depends_on`` in ``seestack/edit`` and
this fails until the file is regenerated.
"""

from __future__ import annotations

import json
from pathlib import Path

from webapp.schemas import editor_ops_schema

SNAPSHOT = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "test" / "editorOpPlacement.json"
)

#: Printed on failure so the fix is a copy/paste, not an archaeology exercise.
REGENERATE = (
    "Regenerate it with:\n"
    "  python -c \"import json,pathlib;from webapp.schemas import "
    "editor_ops_schema;p=pathlib.Path('frontend/src/test/editorOpPlacement.json');"
    "p.write_text(json.dumps({o.id:{q.key:{'type':q.type,'group':q.group,"
    "'depends_on':q.depends_on} for q in o.params} for o in editor_ops_schema()},"
    "indent=2,sort_keys=True)+chr(10))\""
)


def _current_placement() -> dict:
    return {
        op.id: {
            p.key: {"type": p.type, "group": p.group, "depends_on": p.depends_on}
            for p in op.params
        }
        for op in editor_ops_schema()
    }


def test_snapshot_matches_the_engine_op_specs():
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert saved == _current_placement(), (
        "frontend/src/test/editorOpPlacement.json is out of date with the engine's "
        "editor op specs, so the editor's fixture-drift guard is checking against a "
        f"stale placement.\n{REGENERATE}"
    )


def test_snapshot_covers_every_op_and_param():
    """A silently *empty* snapshot would make the frontend guard a no-op."""
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    specs = editor_ops_schema()
    assert len(saved) == len(specs) > 0
    for op in specs:
        assert set(saved[op.id]) == {p.key for p in op.params}
