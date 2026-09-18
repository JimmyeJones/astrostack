"""The glossary slug reaches the browser, not only the descriptor table.

The engine-side guard that no slug is dead lives in
``tests/test_glossary_links.py``; this is the other half — that the two
descriptor endpoints the Stack form and the editor render from actually carry
it, and carry it as an *additive optional* (always present, explicitly null)
rather than a key that appears and disappears.
"""

from __future__ import annotations

from seestack.glossary import load_glossary


def _slugs() -> set[str]:
    _intro, terms = load_glossary()
    return {t.slug for t in terms}


def test_the_stack_form_schema_serves_the_slug(client):
    fields = client.get("/api/stack/options/schema").json()
    assert all("glossary" in f for f in fields)
    linked = {f["key"]: f["glossary"] for f in fields if f.get("glossary")}
    assert linked, "no stacking control offers the glossary"
    assert linked["sigma_clip"] == "sigma-clipping"
    assert set(linked.values()) <= _slugs()
    # A field with no entry says so rather than omitting the key, so an older
    # client reading `field.glossary` gets null instead of undefined.
    assert next(f for f in fields if f["key"] == "output_name")["glossary"] is None


def test_the_editor_op_schema_serves_the_slug(client):
    ops = {o["id"]: o for o in client.get("/api/editor/ops/schema").json()}
    assert ops["tone.stretch"]["glossary"] == "stretching"
    assert ops["tone.scnr"]["glossary"] == "scnr"
    assert ops["geometry.rotate"]["glossary"] is None
    assert {o["glossary"] for o in ops.values() if o["glossary"]} <= _slugs()
