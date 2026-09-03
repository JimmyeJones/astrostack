"""What the *unattended* stack chain will actually stack a target with.

The watcher's auto-stack and the one-click "Process target" both stack with
``_stack_target(..., auto=True)``, which merges the global
``default_stack_options`` with the target's own "Save as defaults" blob and then
fills in a couple of choices the user never made. Those injections decide
whether a passing satellite ends up baked into the finished picture, so more
than one surface needs to be able to *say* what they will be — the Target page
answers "will the rejection your saved settings resolve to actually reach a lone
trail?" **before** the night, where ``seestack.stackhealth`` only answers it
afterwards, on a picture that already has the trail in it.

This module holds the pieces both the chain and those read-only surfaces need,
so a second surface can never drift from what the chain really does. It is pure:
no I/O, no engine import, no webapp state.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

#: The three option keys that express a rejection *choice*. The unattended chain
#: only picks a method for the user when none of them is present, so a saved
#: per-target default or an explicit form post is always honoured verbatim.
AUTO_REJECT_OPT_KEYS = ("auto_reject", "sigma_clip", "min_max_reject")


def parse_saved_stack_defaults(raw: str | None) -> dict[str, Any]:
    """The target's persisted "Save as defaults" blob, as a dict.

    Returns ``{}`` for "nothing saved" and for anything that isn't a JSON object.
    A valid-JSON *non-dict* (a legacy / hand-edited / foreign-version meta row —
    the writer only ever stores a dict) survives ``json.loads`` but would make
    ``opts.update()`` raise ``TypeError``, which on the walk-away path crashes
    the whole auto-stack for that target. Every reader of this row has to
    degrade to "no saved defaults" instead, so they share one reader.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def rejection_choice_expressed(opts: Mapping[str, Any]) -> bool:
    """Did the user pick a rejection method for this stack?

    ``True`` when any of :data:`AUTO_REJECT_OPT_KEYS` is *present* — presence,
    not truthiness: an explicitly-saved ``sigma_clip: false`` is a choice too,
    and the unattended chain must not overrule it.
    """
    return any(k in opts for k in AUTO_REJECT_OPT_KEYS)


def apply_unattended_rejection(opts: dict[str, Any]) -> dict[str, Any]:
    """Fill in the rejection choices an unattended run's user never made.

    Mutates and returns ``opts``. Two injections, both gated on the merged
    options expressing no preference, so a saved per-target default and the
    manual Stack form are honoured verbatim:

    * ``auto_reject`` — let the engine auto-pick min/max (small stacks) vs κ-σ
      (large) so a lone trail is removed even below the ~11-frame threshold κ-σ
      is blind under. Without it a walk-away stack of a handful of subs runs
      plain κ-σ and clips nothing.
    * ``drizzle_reject``, and only when drizzle is actually on, so a non-drizzle
      run's recorded options are unchanged. Drizzle has its own two-pass
      rejection; without this a drizzled walk-away stack combined with no outlier
      rejection at all, keeping every satellite, plane trail and cosmic ray that
      slipped past frame-level QC. Whether that pass is *affordable* is settled
      later, in the engine (``stacker._afford_drizzle_reject``) — it holds ~7
      canvas planes against the single pass's 4, and only ``run_stack`` knows the
      real (for a mosaic, union) canvas it would allocate them on.
    """
    if not rejection_choice_expressed(opts):
        opts["auto_reject"] = True
    if opts.get("drizzle") and "drizzle_reject" not in opts:
        opts["drizzle_reject"] = True
    return opts
