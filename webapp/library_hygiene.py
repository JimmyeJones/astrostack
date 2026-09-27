"""What the app knows about a library target that isn't a real target: is it a
*duplicate* of another one (the same physical raw subs registered twice under two
folder spellings), and is it *junk* (built from the Seestar's own output, video or
photo folder rather than raw subs)?

Both facts are shared, and used to be held by only one of the two features that
needed them — which is the bug this module exists to make impossible:

* **Cleanup suggestions** offers to remove a leftover ``<T>_sub``-named target
  whose frames the base ``<T>`` now owns, and any junk target.
* **Merge suggestions** clusters targets by plate-solved sky position and offers
  to combine them into one deeper picture. It knew neither fact. Two spellings of
  one folder sit at *exactly* the same coordinates, so they always cluster — and
  the nudge invited the owner to "combine" a target with its own duplicate,
  summing the same integration hours twice in the headline figure; a junk
  on-device output sits at the same coordinates too, and was offered as a merge
  partner while the cleanup card was offering to delete it.

Duplicate detection is deliberately in two halves so the expensive one is rarely
paid: a **name-shape** test (:func:`duplicate_base_safe`, pure, no I/O) rules the
question out for all but a handful of targets, and only then does
:func:`confirm_duplicate_of_base` open both projects to check that the base
really owns *every* one of the duplicate's frames. That confirmation is what
keeps a genuine two-folder pair — the owner's ``NGC 6888`` (4815 subs) and
``NGC 6888_SUB`` (3110 subs), which hold *different* frames — treated as the
real merge candidate it is.

Finding the base at all is :func:`find_duplicate_base`, and it is a two-step
lookup for a reason: a base whose folder stem was already taken lives at a
hash-suffixed ``safe_name`` and cannot be found by computing one. See that
function — it is the shape the Seestar mints for every mosaic.
"""

from __future__ import annotations

from dataclasses import dataclass

from seestack.io.library import make_safe_name
from seestack.io.scanner import (
    JunkTargetVerdict,
    classify_seestar_junk_target,
    duplicate_sub_base_name_from_name,
    duplicate_sub_target_base_name,
    is_capture_mode_target_name,
    is_temp_folder_target_name,
    junk_output_examine_cap,
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


def find_duplicate_base(target_name: str, by_name: dict, by_safe: dict):  # noqa: ANN001, ANN201
    """The library target ``target_name`` would be a duplicate *of*, picked out of
    the caller's own ``{name: entry}`` and ``{safe_name: entry}`` indexes — **by
    display name first**, and only then by safe name.

    Looking the base up by safe name alone is wrong whenever the base's own
    folder stem was already taken: :meth:`Library._allocate_safe_name`
    disambiguates a colliding display name with a ``-<sha1[:8]>`` suffix, so the
    base does not live at ``make_safe_name(<its name>)`` at all. The Seestar
    produces that collision routinely — a mosaic's raw-subs folder becomes the
    target ``"<T> (mosaic)"``, whose safe stem ``<T>_mosaic`` is *identical* to
    the stem of the device's own ``<T>_mosaic/`` output folder, so whichever of
    the two is ingested second is hash-suffixed. The safe-name lookup then
    returned the **on-device output** target: a different target holding
    different files, whose frames of course do not include the duplicate's, so
    :func:`confirm_duplicate_of_base` answered "not a duplicate" and both
    features that share this module went blind on exactly that shape. Cleanup
    offered nothing at all, and the merge nudge — which drops known duplicates
    precisely so it can never invite you to combine a target with itself — went
    on offering the pair and summing the same integration hours twice.

    The safe-name lookup stays, as the fallback, because a *renamed* base no
    longer answers to the name the convention derives from the duplicate: the
    duplicate ``NGC 6888_sub`` still points at base name ``NGC 6888``, while the
    base it belongs to has been renamed "Crescent Nebula" and keeps only its
    ``NGC_6888`` folder."""
    base_name = duplicate_sub_base_name_from_name(target_name)
    if base_name is None:
        return None
    found = by_name.get(base_name)
    if found is not None:
        return found
    return by_safe.get(make_safe_name(base_name))


def _is_duplicate_base_of(target_name: str, base) -> bool:  # noqa: ANN001
    """Whether ``base`` is the target ``target_name`` claims to duplicate — the
    same two-step answer :func:`find_duplicate_base` gives, re-checked against a
    single candidate so :func:`confirm_duplicate_of_base` cannot be handed an
    unrelated target by a caller that indexed its own dictionary differently."""
    base_name = duplicate_sub_base_name_from_name(target_name)
    if base_name is None:
        return False
    return base.name == base_name or base.safe_name == make_safe_name(base_name)


def confirm_duplicate_of_base(lib, entry, base) -> DuplicateOfBase | None:  # noqa: ANN001
    """Confirm that ``entry`` holds nothing but raw subs ``base`` already owns,
    by reading both targets' frame source paths. Returns ``None`` — meaning
    "treat these as two real targets" — when the name shape doesn't match, when
    the two are the same target, when ``entry`` has no frames, or when it holds
    even one frame the base does not.

    Read-only: it opens each project, reads source paths (and, for ``entry``,
    whether any stack run exists) and closes it again. Nothing is written and
    nothing on disk is touched. The reads go through ``Project.source_paths()``,
    which selects the one column this needs rather than building a ``FrameRow``
    per row — the confirmation runs over the owner's thousand-frame targets on
    every Library poll."""
    if base is None or base.safe_name == entry.safe_name:
        return None
    if not _is_duplicate_base_of(entry.name, base):
        return None

    proj = lib.open_target(entry.safe_name)
    try:
        dup_sources = proj.source_paths()
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
        base_sources = set(base_proj.source_paths())
    finally:
        base_proj.close()
    if not all(s in base_sources for s in dup_sources):
        return None
    return DuplicateOfBase(
        base_safe=base.safe_name, base_name=base.name, has_own_runs=has_own_runs,
    )


def junk_verdict(lib, entry) -> JunkTargetVerdict | None:  # noqa: ANN001
    """The Seestar-junk verdict for one library target, or ``None`` for a real
    one — the same answer the Library's cleanup nudge shows, so nothing else can
    offer to *use* a target the app is offering to delete.

    Cheap by construction, because it is called for every target on a poll: a
    ``_video``/``_photo`` capture target is decided by **name** at any frame
    count — as is another program's scratch folder, whose size says nothing about
    what it holds — and anything else must first be small enough to *plausibly*
    be on-device output (:func:`junk_output_examine_cap`) before its project is
    opened at all. A real target of hundreds or thousands of subs is never read.

    The ceiling is deliberately the *examine* cap rather than the frame cap the
    classifier's count test uses. The device writes one stacked output per
    **session**, so a folder shot across a season holds a pile of them (the
    owner's ``M 3`` carries 22) and a count alone cannot tell that from a real
    target — the classifier settles those by the frames' own filenames, which it
    can only do if it is handed them. Reading one column of a few hundred rows
    is free; doing it for a 5,477-sub target on every poll is not, which is what
    the ceiling is for.

    Read-only: it opens the project, reads source paths and closes it again."""
    if is_capture_mode_target_name(entry.name) or is_temp_folder_target_name(entry.name):
        return classify_seestar_junk_target(entry.name, [], entry.n_frames)
    if entry.n_frames > junk_output_examine_cap():
        return None
    proj = lib.open_target(entry.safe_name)
    try:
        source_paths = proj.source_paths()
    finally:
        proj.close()
    return classify_seestar_junk_target(entry.name, source_paths, entry.n_frames)
