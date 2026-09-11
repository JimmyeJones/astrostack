"""``GET /api/glossary`` — the reference page's only request.

The endpoint is read-only, offline and library-free, and these tests pin exactly
that: it answers the same way with no data at all, it carries the anchors the
frontend deep-links to, and it never opens anything.
"""

from __future__ import annotations


def test_the_glossary_is_served_with_its_intro_and_terms(client) -> None:
    r = client.get("/api/glossary")
    assert r.status_code == 200
    data = r.json()
    assert data["intro"], "the page's lead paragraph comes from the bundled file"
    assert len(data["terms"]) >= 30
    first = data["terms"][0]
    assert set(first) == {"slug", "term", "body"}


def test_every_term_carries_a_unique_anchor_on_the_wire(client) -> None:
    """``/glossary#fwhm`` is the deep link, and React keys the list by slug."""
    terms = client.get("/api/glossary").json()["terms"]
    slugs = [t["slug"] for t in terms]
    assert all(slugs)
    assert len(slugs) == len(set(slugs))
    assert "fwhm" in slugs


def test_the_body_arrives_as_markdown_the_frontend_renders(client) -> None:
    """Not stripped to plain text: a couple of entries need a bullet list, and
    the frontend's small renderer is what turns them into a list."""
    terms = client.get("/api/glossary").json()["terms"]
    bodies = {t["slug"]: t["body"] for t in terms}
    assert bodies["master-dark"].count("\n- ") >= 2


def test_the_heading_carries_the_expansion_the_reader_will_search_for(client) -> None:
    """Why there is no alias list: the page's substring search over the heading
    already finds FWHM by the words it stands for."""
    terms = {t["slug"]: t for t in client.get("/api/glossary").json()["terms"]}
    assert "full width at half maximum" in terms["fwhm"]["term"].lower()


def test_answering_opens_nothing_on_disk(client, monkeypatch) -> None:
    """A reference page on a NAS-backed install must not pay for a library read.

    The trap is armed against the two things every other router reaches for, and
    the test proves it armed by checking the parse is served from cache — i.e.
    the answer is identical with the library made unopenable.
    """
    from seestack.io.library import Library

    def boom(*a, **k):  # pragma: no cover — the point is that it never runs
        raise AssertionError("the glossary opened the library")

    monkeypatch.setattr(Library, "open_or_create", staticmethod(boom))
    monkeypatch.setattr(Library, "open", staticmethod(boom), raising=False)
    again = client.get("/api/glossary")
    assert again.status_code == 200
    assert again.json()["terms"]
