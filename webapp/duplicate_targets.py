"""Is this library target a *duplicate* of another one — the same physical raw
subs registered twice under two folder spellings?

Two Library features need the same answer and used to disagree about it, which
is the bug this module exists to make impossible:

* **Cleanup suggestions** offers to remove a leftover ``<T>_sub``-named target
  whose frames the base ``<T>`` now owns ("these are the same raw subs").
* **Merge suggestions** clusters targets by plate-solved sky position and offers
  to combine them into one deeper picture. Two spellings of one folder sit at
  *exactly* the same coordinates, so they always cluster — and the nudge invited
  the owner to "combine" a target with its own duplicate, summing the same
  integration hours twice in the headline figure.

The detection is deliberately in two halves so the expensive one is rarely paid:
a **name-shape** test (:func:`duplicate_base_safe`, pure, no I/O) rules the
question out for all but a handful of targets, and only then does
:func:`confirm_duplicate_of_base` open both projects to check that the base
really owns *every* one of the duplicate's frames. That confirmation is what
keeps a genuine two-folder pair — the owner's ``NGC 6888`` (4815 subs) and
``NGC 6888_SUB`` (3110 subs), which hold *different* frames — treated as the
real merge candidate it is.
"""

from __future__ import annotations

from dataclasses import dataclass

from seestack.io.library import make_safe_name
from seestack.io.scanner import (
    duplicate_sub_base_name_from_name,
    duplicate_sub_target_base_name,
)


@dataclass(frozen=True)
class DuplicateOfBase:
    """A confirmed duplicate: every frame this target holds is already owned by
    the base target named here. ``has_own_runs`` reports whether the duplicate
    also carries a stack-run history of its own — data that lives *only* there,
    so removing the target would drop it from the UI even though the files on
    disk stay put. It is still a duplicate either way; only the offer to remove
    it is gated on this."""

    base_safe: str
    base_name: str
    has_own_runs: bool


def duplicate_base_safe(target_name: str) -> str | None:
    """The safe name of the target that ``target_name`` would be a duplicate
    *of*, from its name alone — or ``None`` when the name isn't that shape.

    Pure and free: ``<T>_sub`` → ``<T>``, ``<T>_mosaic_sub`` → ``<T> (mosaic)``.
    Says nothing about whether the base exists or owns the frames; that is
    :func:`confirm_duplicate_of_base`."""
    base = duplicate_sub_base_name_from_name(target_name)
    return make_safe_name(base) if base else None


def confirm_duplicate_of_base(lib, entry, base) -> DuplicateOfBase | None:  # noqa: ANN001
    """Confirm that ``entry`` holds nothing but raw subs ``base`` already owns,
    by reading both targets' frame source paths. Returns ``None`` — meaning
    "treat these as two real targets" — when the name shape doesn't match, when
    the two are the same target, when ``entry`` has no frames, or when it holds
    even one frame the base does not.

    Read-only: it opens each project, reads source paths (and, for ``entry``,
    whether any stack run exists) and closes it again. Nothing is written and
    nothing on disk is touched."""
    if base is None or base.safe_name == entry.safe_name:
        return None
    if duplicate_base_safe(entry.name) != base.safe_name:
        return None

    proj = lib.open_target(entry.safe_name)
    try:
        dup_sources = [f.source_path for f in proj.iter_frames()]
        has_own_runs = next(proj.iter_stack_runs(), None) is not None
    finally:
        proj.close()
    # Re-check the full shape (name *and* "every frame under one `*_sub/`
    # folder") through the engine's own detector, so this module can never
    # disagree with the scanner about what a duplicate looks like.
    if duplicate_sub_target_base_name(entry.name, dup_sources) is None:
        return None
    if not dup_sources:
        return None

    base_proj = lib.open_target(base.safe_name)
    try:
        base_sources = {f.source_path for f in base_proj.iter_frames()}
    finally:
        base_proj.close()
    if not all(s in base_sources for s in dup_sources):
        return None
    return DuplicateOfBase(
        base_safe=base.safe_name, base_name=base.name, has_own_runs=has_own_runs,
    )
