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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class PinnedOption:
    """One stack option a target's saved blob holds away from the global default.

    ``saved`` is what the target will actually stack with; ``global_value`` is
    what it would use if it had never pressed *Save as defaults*.
    """

    key: str
    label: str
    saved: Any
    global_value: Any


def _same_option_value(a: Any, b: Any) -> bool:
    """Would these two option values stack identically?

    ``==`` alone is too loose in one direction and too tight in the other.
    ``False == 0`` and ``True == 1`` in Python, so a checkbox left off would read
    as "same" as a numeric field holding 0 — different options, but the same key
    can change *type* between app versions (an old blob's ``0`` where the field
    is now a bool), and calling that a deliberate pin would nag about a value the
    user never chose. So a bool is only ever the same as a bool. Numbers, on the
    other hand, compare across ``int``/``float`` (``2 == 2.0`` is the same
    stack), which is exactly what a JSON round-trip of a float-typed field can
    hand back.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    return bool(a == b)


def pinned_stack_options(
    saved: Mapping[str, Any],
    global_opts: Mapping[str, Any],
    fields: Sequence[tuple[str, str, Any]],
) -> list[PinnedOption]:
    """Which saved per-target options *override* the global default, and to what.

    "Save as defaults" on the Stack form persists the **whole** form, not the
    handful of things the user changed — so a target saved months ago carries an
    explicit value for every option that existed on that day, including a string
    of ``false``\\ s for checkboxes nobody opened the advanced group to look at.
    A target's blob then wins over ``default_stack_options`` in *both* readers
    (the Stack form's seed and ``pipeline._stack_target(auto=True)``), so a
    switch the owner later flips globally silently does nothing on that target,
    for ever, with nothing on any screen saying so. This is the "say it" half:
    a read-only list naming exactly which options are held back and at what.

    ``fields`` is ``(key, label, app_default)`` per form descriptor, in the order
    they should be reported — passed in rather than imported so this module stays
    pure. A key absent from ``global_opts`` (or present as ``None``, which means
    "use the default") falls back to ``app_default``, mirroring what
    ``get_stack_defaults`` fills the form with.

    Only keys the blob actually holds are considered, and a saved ``None`` is
    skipped for the same reason ``put_stack_defaults`` refuses to persist one.
    A target saved back when the global agreed with it therefore reports
    **nothing** — the list is empty until the two genuinely disagree, which is
    the only moment worth a sentence.
    """
    out: list[PinnedOption] = []
    for key, label, app_default in fields:
        if key not in saved:
            continue
        value = saved[key]
        if value is None:
            continue
        current = global_opts.get(key)
        if current is None:
            current = app_default
        if not _same_option_value(value, current):
            out.append(PinnedOption(key=key, label=label,
                                    saved=value, global_value=current))
    return out


def stack_defaults_delta(
    posted: Mapping[str, Any],
    unsaved: Mapping[str, Any],
    always_persist: Sequence[str] = (),
) -> dict[str, Any]:
    """The part of a *Save as defaults* post worth storing: what the user
    actually **changed**, rather than a snapshot of the whole form.

    The Stack form seeds itself from every descriptor key and posts all of them
    back, so the blob a target saved in July pins every option that existed in
    July — including a string of ``false``\\ s for checkboxes nobody opened. Since
    the blob wins over ``default_stack_options`` in both readers, a switch the
    owner later flips *globally* never reaches that target again. Persisting only
    the differences fixes that at the source: an option the user never touched
    stays absent, so it keeps following the global setting the way an unsaved
    target does. :func:`pinned_stack_options` is the read-only half of the same
    fact and shares :func:`_same_option_value` with this, so what we decline to
    store and what we report as *pinned* cannot drift.

    ``unsaved`` is what the target would be **stacked** with if it had never
    pressed Save — the global blob filled out with each descriptor's own default.
    Deliberately *not* the value the form was seeded with: the Stack form seeds a
    never-configured target's ``auto_reject`` **on** without that being stored
    anywhere, and dropping a key on the strength of a form-only seed would change
    what the target stacks with, which is the one thing this must never do.

    ``always_persist`` names keys whose mere **presence** is the decision, so
    matching the default is not the same as saying nothing:
    :data:`AUTO_REJECT_OPT_KEYS` and ``drizzle_reject`` gate
    :func:`apply_unattended_rejection`, and ``sigma_clip``'s own engine default
    is ``True`` — so dropping a saved ``sigma_clip: true`` would hand the
    unattended chain a target that "never chose", letting it pick the method
    instead. That is exactly the behaviour ``auto_reject_on_unattended``
    (v0.337.0) exists to make **opt-in**, and it must not arrive by the side door.

    Keys absent from ``unsaved`` (a calibration-master pick, an option from a
    newer version) are always kept: with nothing to compare against, the only
    safe answer is to remember what the user posted.
    """
    keep = set(always_persist)
    out: dict[str, Any] = {}
    for key, value in posted.items():
        if key in keep or key not in unsaved:
            out[key] = value
            continue
        if not _same_option_value(value, unsaved[key]):
            out[key] = value
    return out


def rejection_choice_expressed(opts: Mapping[str, Any]) -> bool:
    """Did the user pick a rejection method for this stack?

    ``True`` when any of :data:`AUTO_REJECT_OPT_KEYS` is *present* — presence,
    not truthiness: an explicitly-saved ``sigma_clip: false`` is a choice too,
    and the unattended chain must not overrule it.
    """
    return any(k in opts for k in AUTO_REJECT_OPT_KEYS)


def apply_unattended_rejection(opts: dict[str, Any], *,
                               override_saved_choice: bool = False) -> dict[str, Any]:
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

    ``override_saved_choice`` (the opt-in ``Settings.auto_reject_on_unattended``,
    **off** by default) lifts the first gate only: the unattended chain then
    picks the method on *every* walk-away stack, even when a saved default names
    one. It exists because a method saved once is a decision made at one depth
    and then applied to every night after it — an owner who saved ``sigma_clip``
    gets plain κ-σ on every unattended stack, silently reaching nothing on any
    night, or any mosaic panel, thinner than ``kappa_min_frames``. Nothing else
    changes: the interactive Stack form and reprocess-all never pass this,
    ``drizzle_reject``'s own gate is untouched, and with the setting off the
    built options are byte-for-byte what they are today.

    The superseded ``sigma_clip``/``min_max_reject`` keys are **dropped** when
    the override fires, so the blob reads exactly as a target that never chose —
    which is the whole meaning of the flag. ``_resolve_auto_reject`` would
    overwrite both from the frame count regardless, so no pixel moves either way;
    what the drop buys is that everything *downstream of this function* reads the
    live answer instead of a superseded one. Concretely, ``_stack_target``'s
    quality-weighting guard skips weighting when the options ask for min/max
    (that combine works by rank and ignores weights) — left in place, a saved
    ``min_max_reject`` would go on suppressing weighting for a run that is now
    free to resolve to κ-σ.
    """
    if override_saved_choice:
        opts["auto_reject"] = True
        opts.pop("sigma_clip", None)
        opts.pop("min_max_reject", None)
    elif not rejection_choice_expressed(opts):
        opts["auto_reject"] = True
    if opts.get("drizzle") and "drizzle_reject" not in opts:
        opts["drizzle_reject"] = True
    return opts
