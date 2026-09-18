"""Every glossary link the app offers lands on an entry that exists.

``seestack/data/glossary.md`` opens by promising that *"every entry has its own
link — so a screen that uses a word can point straight at the word, and nobody
has to leave the app to understand something on screen."* v0.460.2 is that
promise kept for the two screens densest in jargon (the Stack form and the
editor), and the mechanism is a slug written by hand next to a control
(``StackOptionField.glossary``, ``OpSpec.glossary``).

A slug written by hand is a slug that can be wrong — mistyped, or correct until
somebody rewords a heading, since :func:`seestack.glossary._slugify` derives the
anchor from the heading text. A wrong one is silent: the page loads, the entry
does not open, and the beginner who asked what a word means is left on a list of
forty other words. So the link is only as good as this test.
"""

from __future__ import annotations

import pytest

from seestack.glossary import load_glossary


@pytest.fixture(scope="module")
def slugs() -> set[str]:
    _intro, terms = load_glossary()
    assert terms, "the bundled glossary is empty — this guard would be vacuous"
    return {t.slug for t in terms}


def test_every_stack_option_glossary_slug_is_a_real_entry(slugs):
    from webapp.schemas import stack_option_fields

    linked = [f for f in stack_option_fields() if f.glossary]
    assert linked, "no stacking control links to the glossary any more"
    missing = sorted({f.glossary for f in linked} - slugs)
    assert not missing, f"stack options link at glossary entries that don't exist: {missing}"


def test_every_editor_op_glossary_slug_is_a_real_entry(slugs):
    from webapp.schemas import editor_ops_schema

    ops = editor_ops_schema()
    linked = [o for o in ops if o.glossary]
    assert linked, "no editor op links to the glossary any more"
    missing = sorted({o.glossary for o in linked} - slugs)
    assert not missing, f"editor ops link at glossary entries that don't exist: {missing}"
    # Op *params* travel through the same adapter, so check them too — none is
    # linked today, but the field exists and the next one added must be right.
    param_slugs = {p.glossary for o in ops for p in o.params if p.glossary}
    assert not sorted(param_slugs - slugs)


def test_the_frontends_hard_coded_glossary_links_are_real_entries(slugs):
    """The links written directly into a component, not served by a descriptor.

    `FrameColumnGuide` has pointed at ``/glossary#fwhm`` since the glossary
    shipped, and nothing checked it. Any future prose link is covered by the
    same sweep.
    """
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "frontend" / "src"
    pattern = re.compile(r"/glossary#([a-z0-9-]+)")
    found: dict[str, str] = {}
    for path in src.rglob("*.tsx"):
        for slug in pattern.findall(path.read_text(encoding="utf-8")):
            found.setdefault(slug, str(path.relative_to(src)))
    assert found, "no component links into the glossary at all"
    missing = {s: where for s, where in found.items() if s not in slugs}
    assert not missing, f"components link at glossary entries that don't exist: {missing}"
