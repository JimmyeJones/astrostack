"""Per-target "finish my pictures for me?" preference — the override the owner
made a condition of saying yes.

`Settings.auto_edit_on_autostack` decides, library-wide, whether the unattended
walk-away chain also runs the one-click Auto recipe on each new stack so the
owner comes back to a *picture* rather than a flat linear master. When he
approved that on 2026-09-08 his answer carried a condition — *"yes, but should be
easy to override with manual settings"* — and a library-wide switch is not an
override for **one** target he wants left alone. This is that override: a
tri-state stored per target, which is why it survives the next night rather than
lasting until the page is closed.

* ``None`` (the key is absent, and every existing project) — follow the library
  setting. Byte-for-byte today's behaviour.
* ``True`` — always auto-finish this target's unattended stacks, even with the
  library setting off.
* ``False`` — never; leave this target's pictures alone.

It lives in the existing key/value ``project_meta`` table (the `webapp/goals.py`
pattern), so storing it needs **no schema migration** and an old project simply
has no key. Like that module, the parse treats a stale or hand-edited value as
*unset* rather than raising: a garbled project must fall back to the library
setting, never 500 a page or strand a night's stack.

**Scope, deliberately.** This governs the *unattended* pass only. Pressing
"Process target" is an explicit "make me a finished picture" and has always
auto-edited regardless of the setting; leaving that alone keeps this change to
the walk-away behaviour the owner's condition is actually about.
"""

from __future__ import annotations

#: Project-meta key holding the per-target override. The name matches the
#: library setting it overrides, so the two are recognisably one decision.
AUTO_EDIT_META_KEY = "auto_edit_on_autostack"

#: What is written for each state. Stored as "1"/"0" rather than "true"/"false"
#: because the meta table is text and these are the values the rest of the app's
#: boolean meta keys already use.
_TRUE = "1"
_FALSE = "0"


def read_auto_edit_pref(proj) -> bool | None:  # noqa: ANN001 — any open Project
    """This target's override, or ``None`` for "follow the library setting".

    Anything that isn't recognisably a stored ``True``/``False`` reads as
    ``None``: an unset key, an older project, and a hand-edited value all mean
    "nobody has expressed a preference here", which is the only safe reading —
    the alternative is a typo silently turning a target's auto-finishing off.
    """
    raw = proj.get_meta(AUTO_EDIT_META_KEY)
    if raw is None:
        return None
    val = str(raw).strip().lower()
    if val in (_TRUE, "true", "yes", "on"):
        return True
    if val in (_FALSE, "false", "no", "off"):
        return False
    return None


def write_auto_edit_pref(proj, value: bool | None) -> None:  # noqa: ANN001
    """Set the override, or clear it (``None``) to follow the library setting.

    Clearing *deletes* the key rather than writing a value, so "follow the
    setting" and "someone once chose the same thing the setting says" are the
    same state on disk — otherwise a later change to the library setting would
    silently not reach a target whose stale override happened to match it.
    """
    if value is None:
        proj.delete_meta(AUTO_EDIT_META_KEY)
        return
    proj.set_meta(AUTO_EDIT_META_KEY, _TRUE if value else _FALSE)


def wants_auto_edit(proj, library_default: bool) -> bool:  # noqa: ANN001
    """Should the **unattended** pass finish this target's new stack?

    One place answers it, so the pipeline that acts and the endpoint that
    reports the effective answer to the user cannot disagree about a target.
    """
    pref = read_auto_edit_pref(proj)
    return library_default if pref is None else pref
