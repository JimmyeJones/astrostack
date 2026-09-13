"""The settings list's "a mosaic turns this on itself" note must name exactly the
passes the stacker turns on itself.

A finished run stores its *effective* ``StackOptions`` verbatim, and the Gallery
card's "Stacking settings" disclosure dumps that record key by key. For two keys
the dump is wrong on a mosaic, because :func:`seestack.stack.stacker.run_stack`
overrides them from the **canvas** rather than from the options::

    if options.photometric_normalize or is_mosaic_canvas:
    do_final_grad = options.final_gradient_removal or is_mosaic_canvas

so a mosaic's card printed ``Off`` against a pass that had run — measured on the
bundled 2x2 sample, whose run stamps ``PHOTNORM`` with 18 frames adjusted under a
settings row reading ``Off``. ``frontend/src/stackSettings.ts`` now annotates
those rows, and its list of keys is a hand mirror of those two gates.

A TS module cannot import a Python constant, so the mirror is guarded here — the
``fullres.ts`` / ``weightingHint.ts`` arrangement. What makes this one worth
having rather than a comment is the *direction* it fails in: the gates live in
the engine and the copy lives in the frontend, so a third automatic pass (or a
mosaic pass that stops being automatic) would be added by someone who has no
reason to open a TypeScript file, and nothing else would notice. The engine's own
source is read here instead of a second copy of the list, so the two cannot agree
with each other while both being wrong.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from seestack.stack import stacker

STACK_SETTINGS_TS = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "stackSettings.ts"
)

#: An option OR-ed with the mosaic-canvas flag, i.e. a pass the canvas turns on
#: whatever the run asked for. Deliberately matches the expression rather than a
#: particular statement, so it finds an ``if`` gate and an assignment alike.
_AUTO_GATE = re.compile(r"options\.(\w+)\s+or\s+is_mosaic_canvas")


def _engine_auto_for_mosaic() -> set[str]:
    """Option keys ``run_stack`` runs on a mosaic canvas regardless of the option."""
    return set(_AUTO_GATE.findall(inspect.getsource(stacker)))


def _ts_mosaic_auto_options() -> list[str]:
    """The keys ``stackSettings.ts`` annotates as automatic on a mosaic.

    Fails loudly when the declaration can't be found: a renamed or relocated
    constant is itself the drift this guard exists to catch, and a check that
    silently passes when it cannot find its subject enforces nothing.
    """
    src = STACK_SETTINGS_TS.read_text(encoding="utf-8")
    m = re.search(
        r"^export const MOSAIC_AUTO_OPTIONS = \[(.*?)\] as const;",
        src, re.M | re.S,
    )
    assert m is not None, (
        f"Could not find `export const MOSAIC_AUTO_OPTIONS` in "
        f"{STACK_SETTINGS_TS.name}. If it was renamed or moved, update this "
        "guard and check the list still agrees with run_stack's "
        "`or is_mosaic_canvas` gates — otherwise a mosaic's settings list goes "
        "back to printing 'Off' against a pass that ran."
    )
    return re.findall(r'"(\w+)"', m.group(1))


def test_the_engine_really_does_turn_these_on_for_a_mosaic():
    """…and the gate is read out of the engine, not asserted from memory."""
    assert _engine_auto_for_mosaic() == {
        "photometric_normalize", "final_gradient_removal",
    }, (
        "run_stack's set of passes a mosaic canvas enables by itself has "
        "changed. The Gallery card's settings list annotates exactly this set "
        "(frontend/src/stackSettings.ts), so update MOSAIC_AUTO_OPTIONS and its "
        "explanatory sentences to match."
    )


def test_the_frontend_annotates_exactly_those_keys():
    assert sorted(_ts_mosaic_auto_options()) == sorted(_engine_auto_for_mosaic()), (
        "The settings list's 'a mosaic turns this on itself' note and the "
        "stacker's own mosaic gates disagree, so a card is either claiming a "
        "pass that did not run or printing 'Off' against one that did."
    )


def test_every_named_key_is_a_real_stack_option():
    """A typo'd key would annotate nothing and fail silently, which is the one
    way this mirror could be green and useless."""
    fields = {f.name for f in stacker.StackOptions.__dataclass_fields__.values()}
    for key in _ts_mosaic_auto_options():
        assert key in fields, key
