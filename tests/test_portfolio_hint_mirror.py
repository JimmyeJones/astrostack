"""The "My best pictures" hint and the scorer behind it must not drift apart.

The wall's count badge carries the one sentence that explains why the pictures
are in the order they are in. It is a claim about
:data:`seestack.portfolio.PORTFOLIO_WEIGHTS` — which metrics
:func:`seestack.portfolio.rank_portfolio` blends — and it was written once, next
to the badge, and then left behind by the scorer twice over:

* it named **three** metrics (integration, cleanliness, frame count) where the
  blend carries **four**; ``coverage`` has been a weighted term and unmentioned;
* it called the leading one ``total`` integration time, where the ranker
  deliberately reads integration, frames and coverage **per pixel** (each
  divided by the run's ``field_fulls``) so that a mosaic is judged on its depth
  rather than on the sum of its panels. On the owner's rasters those are an
  order of magnitude apart, and correcting exactly that substitution elsewhere
  is what v0.437.3–v0.438.14 spent themselves on.

``frontend/src/components/bestPictures.ts`` now owns the wording and builds it
from a hand-mirrored metric list (a TS file cannot import a Python dict). This
guard is what stops that list going stale again: add a fifth term to the blend,
or rename one, and the sentence on the wall stays silent about it with nothing
failing.
"""

from __future__ import annotations

import re
from pathlib import Path

from seestack.portfolio import PORTFOLIO_WEIGHTS

FRONTEND_SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
BEST_PICTURES_TS = FRONTEND_SRC / "components" / "bestPictures.ts"
BEST_PICTURES_ROUTE = FRONTEND_SRC / "routes" / "BestPictures.tsx"


def _mirrored_metric_words() -> dict[str, str]:
    """The ``RANKING_METRIC_WORDS`` map as spelled in the TypeScript.

    Fails loudly when the declaration can't be found: a renamed or relocated
    constant is itself the drift this guard exists to catch, and a check that
    silently passes when it can't find its subject enforces nothing.
    """
    src = BEST_PICTURES_TS.read_text(encoding="utf-8")
    block = re.search(
        r"^export const RANKING_METRIC_WORDS: Record<string, string> = \{(.*?)^\};",
        src, re.M | re.S,
    )
    assert block is not None, (
        "Could not find `export const RANKING_METRIC_WORDS` in "
        f"{BEST_PICTURES_TS.name}. If it was renamed or moved, update this guard "
        "and check the wall's hint still names every metric "
        "seestack.portfolio.PORTFOLIO_WEIGHTS blends — otherwise the one "
        "sentence explaining the ranking goes back to describing a different "
        "scorer."
    )
    return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", block.group(1)))


def test_the_hint_names_every_metric_the_scorer_blends():
    assert set(_mirrored_metric_words()) == set(PORTFOLIO_WEIGHTS), (
        "The 'My best pictures' hint and seestack.portfolio.rank_portfolio "
        "disagree about what the wall is ranked by, so the only sentence "
        "explaining the order of someone's pictures describes a scorer that "
        "isn't running."
    )


def test_every_metric_has_a_plain_word_and_reaches_the_sentence():
    words = _mirrored_metric_words()
    # Each phrase is non-empty and distinct — two metrics sharing one phrase
    # would read as a shorter list than the blend actually has.
    assert all(w.strip() for w in words.values())
    assert len(set(words.values())) == len(words)
    # …and `rankingHint()` is built from the map rather than re-spelled, so the
    # sentence on the wall contains each phrase verbatim.
    src = BEST_PICTURES_TS.read_text(encoding="utf-8")
    hint = re.search(
        r"export function rankingHint\(\): string \{(.*?)^\}", src, re.M | re.S)
    assert hint is not None, (
        f"Could not find `rankingHint()` in {BEST_PICTURES_TS.name} — the hint "
        "is meant to be built from RANKING_METRIC_WORDS, not written out."
    )
    body = hint.group(1)
    for key in words:
        assert re.search(rf"\b{key}\b", body), (
            f"rankingHint() never uses the '{key}' metric, so the wall's "
            "sentence names fewer things than the scorer weighs."
        )


def test_the_sentence_says_the_figures_are_per_pixel():
    """The half that was wrong even about the metric it *did* name.

    ``rank_portfolio`` runs every higher-is-better metric through
    ``per_pixel_total``; a hint that says "total" is describing the number the
    module exists to stop surfaces quoting.
    """
    src = BEST_PICTURES_TS.read_text(encoding="utf-8")
    hint = re.search(
        r"export function rankingHint\(\): string \{(.*?)^\}", src, re.M | re.S)
    assert hint is not None
    body = hint.group(1)
    assert "part of the picture" in body, (
        "The wall's hint no longer says that its figures are measured on one "
        "part of the picture — without that, 'integration time' reads as the "
        "target's total, which is the mosaic substitution the ranker corrects."
    )
    assert not re.search(r"\btotal integration\b", body), (
        "The wall's hint calls its leading metric a *total*, which is exactly "
        "what seestack.portfolio does not use."
    )


def test_the_wall_asks_for_the_sentence_instead_of_spelling_its_own():
    """The route may not write its own description of the ranking.

    This is the shape the bug arrived in: the sentence was a string literal on
    the badge, three files away from the scorer, so nothing connected the two
    and the copy simply stopped being true as the blend grew. Asking
    ``rankingHint()`` is what puts it behind the guards above.
    """
    src = BEST_PICTURES_ROUTE.read_text(encoding="utf-8")
    assert "rankingHint()" in src, (
        f"{BEST_PICTURES_ROUTE.name} no longer renders the shared "
        "`rankingHint()`, so the wall is describing its own ranking again with "
        "nothing holding that description to seestack.portfolio."
    )
    # …and it may not carry a hand-written one beside it. "cleanliness" is the
    # word the stale sentence used for `noise`; the shared helper says "how
    # clean it came out", so finding it here means a second copy has appeared.
    assert "cleanliness" not in src, (
        f"{BEST_PICTURES_ROUTE.name} spells its own ranking description again "
        "— that is the drift RANKING_METRIC_WORDS exists to prevent."
    )
