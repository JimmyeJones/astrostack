"""The bundled glossary: it parses, its anchors are stable, and it ships.

Two different things are pinned here. The first is the parser
(:mod:`seestack.glossary`) against hand-written markdown — slugs, bodies, the
intro. The second, and the reason the file moved out of ``docs/`` at all, is the
**real** glossary: that every heading yields a unique, typeable anchor, that no
entry is an empty heading, and that the file the app reads is the one inside the
package rather than one in a directory ``docker/Dockerfile`` never copies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seestack.glossary import _slugify, glossary_path, load_glossary

_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# The parser
# --------------------------------------------------------------------------


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "glossary.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_headings_become_terms_in_document_order(tmp_path: Path) -> None:
    intro, terms = load_glossary(_write(tmp_path, """# Title

Lead sentence.

---

## Drizzle

Higher resolution from dithered frames.

## Stacking

Averaging subs.
"""))
    assert intro == "Lead sentence."
    assert [t.term for t in terms] == ["Drizzle", "Stacking"]
    assert terms[0].body == "Higher resolution from dithered frames."


def test_a_heading_with_no_prose_is_not_offered_as_a_term(tmp_path: Path) -> None:
    """An empty entry would render as a heading a reader can click and learn
    nothing from — worse than the term simply not being listed yet."""
    _, terms = load_glossary(_write(tmp_path, "## Empty\n\n## Real\n\nProse.\n"))
    assert [t.term for t in terms] == ["Real"]


def test_a_missing_file_is_an_empty_glossary_not_an_exception(tmp_path: Path) -> None:
    """A reference page failing to load must never take its route down."""
    assert load_glossary(tmp_path / "nope.md") == ("", [])


@pytest.mark.parametrize(("heading", "slug"), [
    ("Drizzle", "drizzle"),
    # Spaced slash = a list of synonyms; the lead one is the anchor.
    ("Sub / sub-frame / light frame", "sub"),
    ("Alignment / registration", "alignment"),
    # A *bare* slash is part of one name, so it must not be cut at the slash.
    ("Min/max rejection", "min-max-rejection"),
    # Brackets are an expansion of the lead, never the anchor.
    ("FWHM (full width at half maximum)", "fwhm"),
    ("Cache (Stage 1 / Stage 2)", "cache"),
    # Non-ASCII is dropped, so every anchor is typeable in a URL bar.
    ("Noise σ (sigma)", "noise"),
])
def test_slugs_are_short_typeable_anchors(heading: str, slug: str) -> None:
    assert _slugify(heading) == slug


# --------------------------------------------------------------------------
# The real glossary
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real() -> tuple[str, list]:
    return load_glossary()


def test_the_bundled_glossary_parses_into_many_terms(real) -> None:
    intro, terms = real
    assert len(terms) >= 30, "the glossary is the app's whole term reference"
    assert intro, "the page's lead paragraph comes from the file, not the frontend"
    assert all(t.body for t in terms)


def test_every_anchor_is_unique(real) -> None:
    """Two terms sharing a slug means ``/glossary#x`` jumps to the wrong one, and
    React renders duplicate keys. Nothing but this file can introduce it."""
    _, terms = real
    slugs = [t.slug for t in terms]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    assert not dupes, f"duplicate glossary anchors: {sorted(dupes)}"
    assert all(slugs), "every heading must yield a non-empty anchor"


def test_the_glossary_lives_in_the_package_not_in_docs() -> None:
    """The move is the feature. ``docker/Dockerfile`` copies ``seestack/`` and
    not ``docs/``, so a glossary under ``docs/`` is present in every checkout and
    absent from the only build the owner runs — which is exactly where it spent
    its life before this. Fails the moment it drifts back."""
    assert glossary_path().is_file()
    assert glossary_path().parent == _ROOT / "seestack" / "data"
    assert not (_ROOT / "docs" / "glossary.md").exists(), (
        "two copies of the glossary is how the app and the docs start "
        "disagreeing about a word; there is one, and it ships"
    )


def test_the_terms_the_interface_says_out_loud_are_all_explained(real) -> None:
    """A spot-check, not a sweep: these are the words a beginner meets on the
    Target page and in the Stack form within their first session."""
    _, terms = real
    slugs = {t.slug for t in terms}
    for expected in ("fwhm", "drizzle", "sigma-clipping", "mosaic", "panel-depth",
                     "plate-solving", "stretching", "auto-stack", "incoming-folder"):
        assert expected in slugs, f"no glossary entry for {expected}"


def test_no_entry_still_describes_the_retired_gaia_colour_mode(real) -> None:
    """The Gaia colour-calibration mode was retired in v0.418.0 (it needed a
    network the app does not use). The glossary described it for as long as it
    was unreachable, which is how a reference page ends up teaching a control
    that no longer exists."""
    _, terms = real
    body = " ".join(t.body for t in terms).lower()
    assert "gaia" not in body
