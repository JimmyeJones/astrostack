"""Every field the Settings page's "More settings" section writes really exists.

``frontend/src/components/settings/moreSettings.ts`` is the plain-words home for
the settings the owner called *"very confusing … scary to mess with"* (the
owner-approved redesign, ``docs/design/settings-redesign.md``). Each card there
names, in its ``keys``, the ``Settings`` fields it can write — and those names
are **strings in TypeScript**, so nothing in either language stops a rename on
the Python side from leaving a card quietly editing a field that no longer
exists. A settings PUT carrying an unknown key is not an error the owner would
see either: the store ignores it, and the control simply stops working.

So this is the mirror test for that list. It reads the ``keys`` arrays out of the
TypeScript and asserts each one is a real field on :class:`webapp.config.Settings`
— and, because the whole point of the section is that it is *safe* to use, that
none of them is one of the credentials the settings API refuses to take from a
client.

Renaming a settings field is already a §9 breach on its own; this makes the
frontend half of it fail loudly in CI rather than on the owner's box.
"""

from __future__ import annotations

import re
from pathlib import Path

from webapp.config import Settings
from webapp.routers.settings import _AUTH_KEYS

_ROOT = Path(__file__).resolve().parents[1]
_MORE_TS = _ROOT / "frontend" / "src" / "components" / "settings" / "moreSettings.ts"

#: ``keys: ["a", "b"],`` — the one declaration each card makes of what it writes.
_KEYS_RE = re.compile(r"\bkeys:\s*\[([^\]]*)\]", re.S)
_STRING_RE = re.compile(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""")


def _declared_keys() -> list[str]:
    text = _MORE_TS.read_text(encoding="utf-8")
    out: list[str] = []
    for block in _KEYS_RE.findall(text):
        out.extend(_STRING_RE.findall(block))
    return out


def test_the_cards_declare_the_fields_they_write() -> None:
    """Sanity: the regex really found the section, not an empty file."""
    keys = _declared_keys()
    assert len(keys) >= 15, keys
    # The three the owner is most likely to reach for, as a canary that a
    # refactor hasn't moved the declarations somewhere this test can't see.
    assert {"copy_to_cache", "max_stack_memory_gb", "cpu_workers"} <= set(keys)


def test_every_field_more_settings_writes_exists_on_the_model() -> None:
    unknown = sorted(set(_declared_keys()) - set(Settings.model_fields))
    assert not unknown, (
        "More settings names fields that are not on Settings — a rename on the "
        f"Python side left the control writing nothing: {unknown}"
    )


def test_more_settings_never_offers_a_credential() -> None:
    """The auth keys are managed by ``/api/auth/password`` and stripped from a
    settings PUT; a card editing one would be a control that silently does
    nothing, on the one page where "it did something" has to be true."""
    offered = sorted(set(_declared_keys()) & set(_AUTH_KEYS))
    assert not offered, offered
