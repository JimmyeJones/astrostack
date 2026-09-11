"""The app's own glossary — "what does this word mean?", answered in the app.

``seestack/data/glossary.md`` is the plain-language reference for every term the
interface says out loud (FWHM, drizzle, sigma clipping, panel depth…). It is
**bundled with the package**, not left in ``docs/``, for one specific reason:
``docker/Dockerfile`` copies ``frontend/``, ``seestack/``, ``webapp/``,
``pyproject.toml`` and ``README.md`` — and nothing else. A glossary living in
``docs/`` is therefore present in every checkout, every test run and every CI job,
and **absent from the only build the owner actually runs** (AGENTS.md §8: "green
means the checkout passed, not that the owner's install works"). That is how it
spent its whole life reachable only from the historical desktop GUI's F1 key.

This module is the parser, and it is deliberately pure: it turns the markdown
into a list of terms with stable slugs, so the webapp can serve them and the
frontend can deep-link to one (``/glossary#fwhm``) without either of them knowing
anything about markdown headings.

The body text stays **markdown**, not stripped plain text — a couple of entries
genuinely need a bullet list and some bold — and the frontend renders the small
subset actually used. Keeping the source a readable ``.md`` file is the point:
the glossary is prose, and prose is edited as prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_GLOSSARY_PATH = Path(__file__).parent / "data" / "glossary.md"

#: A slash that separates synonyms ("Alignment / registration"), as opposed to
#: one that is part of a single name ("Min/max rejection"). The spacing is the
#: only thing that tells them apart, and this file is written to respect it.
_SPACED_SLASH = re.compile(r"\s+/\s+")


@dataclass(frozen=True)
class GlossaryTerm:
    """One ``## heading`` and the prose under it."""

    #: URL-safe anchor, stable across edits to the prose. See :func:`_slugify`.
    slug: str
    #: The heading verbatim, e.g. ``"FWHM (full width at half maximum)"``.
    #:
    #: There is deliberately no separate list of *aliases* beside it. The obvious
    #: design — split ``"Alignment / registration"`` into searchable synonyms —
    #: buys nothing, because every one of those spellings is a substring of the
    #: heading itself, so the page's plain substring search already finds the
    #: entry by any of them. The alias branch would have been a rule that only a
    #: synthetic fixture could ever exercise.
    term: str
    #: The markdown body, with trailing blank lines trimmed.
    body: str


def _slugify(heading: str) -> str:
    """A short, stable anchor for a heading.

    The *lead* name only: any parenthesis and anything after a **spaced** slash
    are dropped, so ``"Cache (Stage 1 / Stage 2)"`` is ``cache`` and ``"Sub /
    sub-frame / light frame"`` is ``sub`` — an anchor someone could plausibly
    type. The slash must be spaced because a bare one is part of the name rather
    than a list of synonyms: ``"Min/max rejection"`` is ``min-max-rejection``,
    not ``min``. Non-ASCII is dropped rather than transliterated (``"Noise σ
    (sigma)"`` → ``noise``), which keeps every anchor typeable in a URL bar.

    Uniqueness is not enforced here; ``tests/test_glossary.py`` asserts the real
    file has no collision, which is the only place one could appear.
    """
    lead = _SPACED_SLASH.split(heading.split("(", 1)[0], maxsplit=1)[0]
    return re.sub(r"[^a-z0-9]+", "-", lead.lower()).strip("-")


def _split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """``(intro, [(heading, body), …])`` for a glossary markdown document.

    The intro is everything before the first ``## `` heading, minus the document
    title and the ``---`` rule under it — i.e. the sentences that explain what the
    page is. Kept because the page needs a lead paragraph and writing a second
    one in the frontend is how two accounts of one page start to disagree.
    """
    lines = text.splitlines()
    intro: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
        elif line.startswith("# ") or line.strip() == "---":
            continue
        else:
            intro.append(line)
    return (
        "\n".join(intro).strip(),
        [(h, "\n".join(b).strip()) for h, b in sections],
    )


def load_glossary(path: Path | None = None) -> tuple[str, list[GlossaryTerm]]:
    """The bundled glossary as ``(intro, terms)``, in document order.

    Reads the packaged markdown. ``path`` exists for tests; production callers
    pass nothing. A missing file is an empty glossary rather than an exception —
    a reference page failing to load must never take a route down with it.
    """
    src = Path(path) if path is not None else _GLOSSARY_PATH
    try:
        text = src.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover — the file is package data
        return "", []
    intro, sections = _split_sections(text)
    return intro, [
        GlossaryTerm(slug=_slugify(h), term=h, body=body)
        for h, body in sections
        if body
    ]


def glossary_path() -> Path:
    """Where the bundled markdown lives — for the desktop GUI's viewer, and for
    the packaging test that checks it reached the wheel."""
    return _GLOSSARY_PATH
