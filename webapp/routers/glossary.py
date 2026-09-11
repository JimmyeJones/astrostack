"""``GET /api/glossary`` — the plain-language reference, served to the web app.

The glossary has existed since the desktop days and, until now, only the
historical PySide6 GUI's F1 key could open it: it sat in ``docs/``, which
``docker/Dockerfile`` does not copy, so the owner's install has never had a copy
of it at all. It now ships as package data (:mod:`seestack.glossary`) and this
router hands it to the SPA, which renders it at ``/glossary`` with a search box
and one anchor per term.

Read-only, offline and free: the file is parsed once per process and never
touches the library, a project DB or the filesystem again, so the page costs
nothing to open and cannot fail because of the data on disk.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel

from seestack.glossary import load_glossary

router = APIRouter(tags=["glossary"])


class GlossaryTermOut(BaseModel):
    """One entry, as the page renders it."""

    #: Stable anchor — ``/glossary#fwhm``. Deep links are the point of having it.
    slug: str
    term: str
    #: Markdown, rendered by the frontend's small subset renderer. A couple of
    #: entries genuinely need a bullet list and some bold.
    body: str


class GlossaryOut(BaseModel):
    intro: str = ""
    terms: list[GlossaryTermOut] = []


@lru_cache(maxsize=1)
def _cached() -> GlossaryOut:
    """Parsed once per process — it is a file that ships inside the image and
    therefore cannot change while the app runs."""
    intro, terms = load_glossary()
    return GlossaryOut(
        intro=intro,
        terms=[GlossaryTermOut(slug=t.slug, term=t.term, body=t.body)
               for t in terms],
    )


@router.get("/api/glossary", response_model=GlossaryOut)
def get_glossary() -> GlossaryOut:
    """Every term in the app's glossary, in document order.

    An empty ``terms`` list is a valid answer (a build whose package data went
    missing): the page then shows its own "couldn't load" state rather than a
    broken route, which is the right failure for a reference page.
    """
    return _cached()
