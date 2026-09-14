"""What the read-only token may read, said once in Python and once in TypeScript.

The gate's allowlist (:data:`webapp.main._READONLY_GET_PATHS`) *is* the whole
privilege the token carries. The Settings screen tells the owner what that
privilege is — in words, because that is what a person hands to a script on the
strength of — and the two cannot share code across the language boundary.

A wrong list on the screen is worse than no list: it is a promise about a secret.
Under-claim and the owner keeps looking for a workaround (which is what filed
this feature in the first place — the two available workarounds were both
root-equivalent); over-claim and they hand the token to something expecting it to
read more than it can, or, worse, trust the "and nothing else" half. So the two
are pinned together here, the same arrangement as
:mod:`tests.test_pace_constants_mirror`.
"""

from __future__ import annotations

import re
from pathlib import Path

from webapp.main import _READONLY_GET_PATHS

READONLY_TS = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "readonlyToken.ts"
)

#: How each allowlisted API path is named to a person. The gate's paths are the
#: authority for *what* is readable; this is only how each one is spelled in a
#: sentence, so the mapping lives beside the test that uses it.
_PATH_WORDS = {
    "/api/health": "health",
    "/api/logs": "logs",
    "/api/jobs": "jobs",
    "/api/stats": "stats",
    "/api/targets": "the target list",
    "/api/incoming-lag": "how far behind your imports are",
}


def _ts_string_list(name: str) -> list[str]:
    """The string literals of a top-level ``export const <name> = [...]``.

    Fails loudly when the declaration can't be found — a renamed or relocated
    list is itself the drift this test exists to catch, and a guard that passes
    when it cannot find its subject enforces nothing.
    """
    src = READONLY_TS.read_text(encoding="utf-8")
    m = re.search(rf"export const {re.escape(name)}\s*=\s*\[(.*?)\]", src, re.S)
    assert m, f"{name} not found in {READONLY_TS.name} — did it move or get renamed?"
    return re.findall(r'"([^"]*)"', m.group(1))


def test_every_path_the_gate_allows_is_named_on_the_settings_screen():
    words = _ts_string_list("readonlyAllowedReads")
    assert words, "the list came back empty — the regex matched nothing useful"
    # Every allowlisted path is accounted for in the words the screen shows…
    expected = {_PATH_WORDS[p] for p in _READONLY_GET_PATHS}
    assert set(words) == expected, (
        f"screen says {sorted(words)}, gate allows {sorted(expected)}"
    )
    # …and the mapping itself covers the gate, so adding a path to the allowlist
    # without deciding how to *say* it fails here rather than going unmentioned.
    assert _READONLY_GET_PATHS <= set(_PATH_WORDS)


def test_the_screen_never_claims_something_the_gate_refuses():
    words = set(_ts_string_list("readonlyAllowedReads"))
    for path, word in _PATH_WORDS.items():
        if path not in _READONLY_GET_PATHS:
            assert word not in words, (
                f"the screen names {word!r} but the gate no longer allows {path}"
            )
