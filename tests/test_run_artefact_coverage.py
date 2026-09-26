"""Every file written beside a stack run's basename is one the delete path knows.

A run is more than its three recorded paths: the writer leaves a coverage map and
a frame-coverage sibling, and the webapp later caches a progress reel, a zoom
clip, a share render and a cross-run deepening reel *next to* the master, each
named ``{basename}_<something>``. :data:`seestack.stack.output.RUN_ARTEFACT_SUFFIXES`
is the one list all three operations on a run's whole file set read — archiving it
aside on a re-stack, carrying it on a merge, and **deleting it**, where
"reclaiming space is the entire point of the button".

``tests/webapp/test_run_purge.py`` already runs the real ``write_stack_outputs``
and checks everything *it* produces is registered. That cannot see the caches,
which are written later and elsewhere — and one of them was not registered: the
deepening reel and its signature survived a run delete for good (2.0 MB on a
synthetic run; a reel is a 1024 px animation of every stack a target has).

So this is the other half of that guard, done statically: it finds every
``f"{<basename>}_<name>.<ext>"`` in ``seestack/`` and ``webapp/`` and requires the
suffix to be registered. **A new sibling is not a bug; an unregistered one is.**
Register it, or — if the string is not a file beside a run at all — name it in
:data:`_EXEMPT` with the reason, because that sentence is what the next reader
needs.
"""

from __future__ import annotations

import re
from pathlib import Path

from seestack.stack.output import RUN_ARTEFACT_SUFFIXES

_ROOT = Path(__file__).resolve().parents[1]
_PY_DIRS = ("seestack", "webapp")

#: Suffixes that look like a run sibling and are not one. Keep this tiny.
_EXEMPT: dict[str, str] = {
    # `GET …/full-res.png` names its *download* after the run
    # (Content-Disposition), so the browser saves "master_fullres.png". Nothing is
    # written to the output tree — the PNG is the response body.
    "_fullres.png": "a download filename in a Content-Disposition header, never a file",
}

#: `f"{basename}_zoom.webp"`, `f"{out_basename}_coverage.fits"`, … — an f-string
#: whose one placeholder is a run basename/stem, followed by a literal suffix.
#: Deliberately matched on the *variable name* rather than on the shape alone: a
#: run's siblings are the files named after its basename, and that is what the
#: delete path resolves from (the FITS stem).
_SIBLING_RE = re.compile(
    r'f"\{[a-z_]*(?:base|basename|stem)[a-z_]*\}(_[A-Za-z0-9_]+\.[a-z0-9]+)"'
)


def _sibling_literals() -> dict[str, list[str]]:
    """Every hand-spelled ``{basename}<suffix>`` literal, suffix → where."""
    found: dict[str, list[str]] = {}
    for directory in _PY_DIRS:
        for path in sorted((_ROOT / directory).rglob("*.py")):
            for line_no, line in enumerate(path.read_text().splitlines(), start=1):
                for m in _SIBLING_RE.finditer(line):
                    where = f"{path.relative_to(_ROOT).as_posix()}:{line_no}"
                    found.setdefault(m.group(1), []).append(where)
    return found


def test_every_run_sibling_written_by_name_is_a_registered_artefact():
    registered = set(RUN_ARTEFACT_SUFFIXES.values())
    found = _sibling_literals()
    assert found, "the scan found no run siblings at all — the pattern has rotted"
    unregistered = {
        suffix: sites for suffix, sites in found.items()
        if suffix not in registered and suffix not in _EXEMPT
    }
    assert not unregistered, (
        "these files are named after a run's basename but are not in "
        "RUN_ARTEFACT_SUFFIXES, so deleting the run leaves them on disk for "
        f"good: {unregistered}"
    )


def test_the_exempt_list_names_only_suffixes_that_still_appear():
    """An exemption for a string that has gone is a comment pretending to be a
    rule — and it would silently excuse the next unregistered sibling that
    happened to reuse the name."""
    found = _sibling_literals()
    stale = sorted(s for s in _EXEMPT if s not in found)
    assert not stale, f"these exempted suffixes no longer appear anywhere: {stale}"


def test_the_deepening_reel_is_registered_under_the_names_its_writer_uses():
    """The reel is the sibling this test was written for, and the writer and the
    delete path now read the *same* table rather than two copies of three
    strings."""
    assert RUN_ARTEFACT_SUFFIXES["deepening_webp"] == "_deepening.webp"
    assert RUN_ARTEFACT_SUFFIXES["deepening_apng"] == "_deepening.png"
    assert RUN_ARTEFACT_SUFFIXES["deepening_sig"] == "_deepening.sig"
