"""
Folder scanner: turn a folder of Seestar sub-folders into organised targets.

The Seestar app already does the hard part of organising — every time you
image something it drops the frames into their own sub-folder. The scanner
leans on that, and on the Seestar's **folder-naming convention** (see
``_apply_seestar_convention``):

  * ``<Target>_sub/`` holds the raw sub-frames (the lights to stack) and is
    the authoritative frame source; it becomes the target ``<Target>``.
    A mosaic's raw subs live in ``<Target>_mosaic_sub/`` and become the
    **separate** target ``<Target> (mosaic)`` — kept distinct from the
    single-field target because their fields of view / canvases differ.
  * ``<Target>/`` (no suffix) is the Seestar's *own on-device stacked
    output* — a single, often lower-resolution image, **not** raw subs. When
    a ``<Target>_sub/`` sibling exists we skip this output folder so we never
    build a bogus 1-frame "stack" from it. A bare folder with no ``_sub``
    sibling still ingests as a target (older / non-Seestar layouts).
  * ``*_video/`` folders are video captures and ``*_photo/`` folders are the
    single-shot stills the device takes in scenery/planetary photo mode
    (``Planetary_photo/``, ``Scenery_photo/``). Neither holds stackable
    deep-sky subs, so both are skipped entirely.
  * Loose FITS files sitting directly in the root (exports, one-offs, files
    that escaped a folder) are collected into a single ``Unsorted`` target
    you can sort out by hand later.

Two phases, kept separate so they're independently testable:

  1. ``scan_and_organize`` — pure file/DB bookkeeping. Walk the tree, create
     (or re-open) one target Project per sub-folder, register every frame.
     Re-running it is idempotent: already-known frames are skipped.
  2. ``run_qc_and_solve`` — the heavy compute. Runs the existing QC metrics
     and ASTAP plate-solving across a target's frames, in a process pool.

Stacking is deliberately *not* part of the scan — the design is "organise +
QC + solve, then stop", so you can review quality and reject bad frames
before committing CPU time to a stack.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from seestack.core.cache import CacheManager
from seestack.io.ingest import FITS_SUFFIXES, find_fits_files, ingest_files
from seestack.io.library import UNSORTED_TARGET_NAME, Library
from seestack.io.project import Project, is_seestar_output_filename
from seestack.io.wcs_io import wcs_text_is_usable

log = logging.getLogger(__name__)

# phase, done, total  — emitted by the progress callback throughout a scan.
ProgressFn = Callable[[str, int, int], None]
ShouldStopFn = Callable[[], bool]

# Seestar folder-naming convention (see the module docstring). The Seestar
# writes raw subs into "<Target>_sub/" ("<Target>_mosaic_sub/" for a mosaic)
# and its own on-device stacked OUTPUT into the bare "<Target>/". "*_video/"
# folders are video captures and "*_photo/" folders are single-shot stills
# (the device writes "Planetary_photo/", "Scenery_photo/" beside the matching
# "*_video/" ones) — neither holds stackable deep-sky subs. Suffixes are matched
# case-insensitively because the folder casing is not guaranteed across
# firmware/app versions.
_SUB_SUFFIX = "_sub"
_MOSAIC_SUB_SUFFIX = "_mosaic_sub"
_VIDEO_SUFFIX = "_video"
_PHOTO_SUFFIX = "_photo"

# How a mosaic's target is *named* once ingested: "<T> (mosaic)", deliberately
# distinct from the single-field "<T>" so their differing footprints are never
# co-stacked or auto-merged. One definition, because three things now depend on
# the exact spelling — the convention that builds it, the duplicate detector
# that names a "<T>_mosaic_sub" leftover's base, and the merge suggester that
# must not offer to combine a mosaic with its single field.
_MOSAIC_TARGET_SUFFIX = " (mosaic)"


def mosaic_target_name(base: str) -> str:
    """The target name a mosaic's raw-subs folder ``<base>_mosaic_sub/`` becomes."""
    return f"{base}{_MOSAIC_TARGET_SUFFIX}"


def is_mosaic_target_name(target_name: str) -> bool:
    """True when a target is a **mosaic**, by the name the convention gave it.

    A mosaic and the single field of the same object sit at the same plate-solved
    centre, so nothing about position can tell them apart — but their canvases
    differ, which is the whole reason the convention keeps them as two targets.
    Anything that groups targets by *where they point* needs this to avoid
    proposing a combination the ingest side deliberately refused to make."""
    return target_name.strip().lower().endswith(_MOSAIC_TARGET_SUFFIX)

# The capture-mode folders that never hold stackable deep-sky sub-frames, so the
# scanner skips them and the cleanup nudge offers to remove any a pre-convention
# scan already ingested. One tuple so the two can never disagree about the family.
_CAPTURE_SUFFIXES = (_VIDEO_SUFFIX, _PHOTO_SUFFIX)


@dataclass
class SkippedOutputFolder:
    """A bare ``<T>/`` folder the convention skipped, and what was in it.

    The skip itself is right and stays: a Seestar's on-device output is a
    finished picture, and stacking it with the raw subs beside it would be
    nonsense. But it was **silent**, and it does not check what it is skipping —
    so a plainly-named folder of a user's own raw subs that happens to sit beside
    a Seestar ``<T>_sub/`` disappears from the scan without a word, however many
    frames it holds. The owner's library has one of exactly that shape
    (``NGC 6888`` of 4,815 files beside ``NGC 6888_SUB`` of 3,110, holding
    genuinely different frames).

    ``n_device_output`` counts the files whose *name* is the device's own picture
    (``Stacked*.fit`` — see :func:`~seestack.io.project.is_seestar_output_filename`,
    the same rule the ingest-side reject uses). When it accounts for every file
    the skip is uncontroversial and nothing needs saying; when it does not, the
    scan has quietly passed over frames it cannot vouch for, and :attr:`n_unvouched`
    is how many.
    """

    name: str                 # the bare folder's name, as it is on disk
    parent: str               # its parent-directory key (the scan root, or a container)
    n_files: int              # FITS files in it
    n_device_output: int      # of those, files named like the device's own picture

    @property
    def n_unvouched(self) -> int:
        """Files in the skipped folder that are *not* named like device output."""
        return max(0, self.n_files - self.n_device_output)


def _apply_seestar_convention(
    subdirs_with_fits: list[tuple[str, list[Path]]],
    parents: list[str] | None = None,
    skipped_out: list[SkippedOutputFolder] | None = None,
) -> list[tuple[str, list[Path]]]:
    """
    Map raw scan folders to ``(target_name, files)`` units, honouring the
    Seestar folder convention so we never ingest the Seestar's own output or
    video folders as if they were raw sub-frames.

    Rules, applied per folder:

    * ``*_video`` / ``*_photo`` → skipped (a video capture or a single-shot
      still, not stackable subs).
    * ``<T>_mosaic_sub`` → target ``"<T> (mosaic)"`` (a mosaic's raw subs, kept
      distinct from the single-field target so their differing footprints are
      never co-stacked or auto-merged).
    * ``<T>_sub`` → target ``"<T>"`` (a single field's raw subs).
    * a bare ``<T>`` whose ``<T>_sub`` **sibling** is also present → skipped
      (it's the Seestar's on-device stacked output, not raw subs).
    * any other bare folder → ingested unchanged (older / non-Seestar layouts
      whose subs live directly in a plainly-named folder).

    ``parents`` is an optional list parallel to ``subdirs_with_fits`` giving each
    folder's parent-directory key, so the "``<T>_sub`` sibling present" test is
    scoped to folders that actually share a parent. This matters once the scanner
    expands a whole-device container (``incoming/MyWorks/{M 31_sub, …}``) into the
    same unit list as ordinary root-level folders (``incoming/M 31/``): without
    parent scoping a bare ``incoming/M 31/`` of real subs is wrongly skipped as
    "output" merely because an **unrelated** ``incoming/MyWorks/M 31_sub/`` exists
    elsewhere in the drop, silently losing that session's frames. When ``parents``
    is omitted, every folder is treated as a sibling of every other (the original
    single-level behaviour), which is exactly right for a flat scan root.

    ``skipped_out``, when given, collects a :class:`SkippedOutputFolder` for every
    bare folder the sibling rule skipped, so the caller can *say* what it passed
    over instead of dropping it in silence. Collected here rather than re-derived
    by a second walk, because the rule that decides the skip and the rule that
    reports it must not be able to disagree.

    Order is preserved. Folder names are compared case-insensitively for the
    suffix tests, but the target name keeps the folder's original casing.
    """
    if parents is None:
        parents = [""] * len(subdirs_with_fits)
    # (parent, lowercased-name) so the sibling test never matches across parents.
    sibling_names = {
        (parent, name.lower())
        for (name, _), parent in zip(subdirs_with_fits, parents, strict=True)
    }
    units: list[tuple[str, list[Path]]] = []
    for (name, files), parent in zip(subdirs_with_fits, parents, strict=True):
        low = name.lower()
        if low.endswith(_CAPTURE_SUFFIXES):
            continue
        if low.endswith(_MOSAIC_SUB_SUFFIX):
            base = name[: -len(_MOSAIC_SUB_SUFFIX)].rstrip()
            units.append((mosaic_target_name(base) if base else name, files))
            continue
        if low.endswith(_SUB_SUFFIX):
            base = name[: -len(_SUB_SUFFIX)].rstrip()
            units.append((base if base else name, files))
            continue
        # A bare folder: skip it only when its raw-sub sibling (same parent) is
        # present (then it's the Seestar's own output). Otherwise ingest it.
        if (parent, low + _SUB_SUFFIX) in sibling_names:
            if skipped_out is not None:
                skipped_out.append(SkippedOutputFolder(
                    name=name,
                    parent=parent,
                    n_files=len(files),
                    n_device_output=sum(
                        1 for f in files if is_seestar_output_filename(str(f))
                    ),
                ))
            continue
        units.append((name, files))
    return units


def _looks_like_seestar_container(d: Path) -> bool:
    """True when ``d`` is a *container* level of a Seestar layout — a folder that
    holds no FITS of its own but wraps the real per-target folders one level
    deeper — recognised by at least one child folder named ``*_sub`` (the
    authoritative raw-subs marker, which also covers ``*_mosaic_sub``).

    This is the "I copied the whole Seestar share/SD card into incoming" shape
    (``incoming/MyWorks/{M 31_sub, M 31, …}``). A plainly-nested non-Seestar
    folder — whose children share no convention names (e.g. ``Andromeda/sub/``,
    ``MyProject/night1/``) — returns False so it still ingests as a single
    target, exactly as before.
    """
    try:
        children = [c for c in d.iterdir() if c.is_dir()]
    except OSError:
        return False
    return any(c.name.lower().endswith(_SUB_SUFFIX) for c in children)


def container_target_children(
    container_dir: Path, source_paths: Sequence[str | Path]
) -> set[str] | None:
    """The distinct *immediate child folder* names of ``container_dir`` that
    ``source_paths`` live under — or ``None`` if any path is **not** inside the
    container (so the frames are not a clean whole-container drop).

    Used to recognise a legacy giant target: before the scanner expanded a
    whole-device / mixed-folder container (``incoming/MyWorks/{M 31_sub, M 31,
    NGC 7000_mosaic_sub, Lunar_video}``), an old scan ingested that entire
    container as ONE target, so its frames span **several** child folders. A real
    single-field target's frames all sit under one folder. Pure and
    filesystem-free (it only reasons about the given paths).
    """
    cdir = Path(container_dir)
    children: set[str] = set()
    for p in source_paths:
        path = Path(p)
        if cdir not in path.parents:
            return None
        rel = path.relative_to(cdir)
        if len(rel.parts) >= 2:  # <child folder>/.../<file>
            children.add(rel.parts[0])
    return children


def _flag_legacy_container_drop(library: Library, container_dir: Path) -> None:
    """When a container is expanded, flag the pre-existing giant target an OLD
    scan built from the same container (so cleanup-suggestions can surface it).

    Cheap and conservative: the old scan named that target after the container
    folder, so we look it up by ``make_safe_name(container_dir.name)`` — one
    registry read — and only when such a target exists do we open it (once, at
    scan time) to confirm its frames really span ≥2 of the container's child
    folders (the mixed-drop signature) before flagging. A freshly-scanned library
    has no such target, and a coincidentally same-named real single-field target
    (all frames in one folder) is never flagged.
    """
    from seestack.io.library import make_safe_name

    safe = make_safe_name(container_dir.name)
    entry = library.find_target(safe)
    if entry is None or entry.legacy_mixed_drop:
        return
    proj = library.open_target(safe)
    try:
        sources = [f.source_path for f in proj.iter_frames()]
    finally:
        proj.close()
    children = container_target_children(container_dir, sources)
    if children is not None and len(children) >= 2:
        library.flag_legacy_mixed_drop(safe)
        log.info(
            "Flagged legacy whole-device drop target %r (frames span %d folders "
            "under %r) for one-click cleanup — the correct per-target versions "
            "were re-ingested this scan.",
            entry.name, len(children), container_dir.name,
        )


def _seestar_output_bases(
    subdirs_with_fits: list[tuple[str, list[Path]]],
    parents: list[str] | None = None,
) -> dict[str, str]:
    """Map each single-field ``<T>_sub`` target name to the bare ``<T>`` folder
    basename whose already-registered frames (the Seestar's on-device stacked
    output) must be additively rejected from that target on a re-scan.

    This is the *upgrade-path* companion to ``_apply_seestar_convention``: the
    convention stops us ingesting a bare ``<T>/`` output folder going forward,
    but a library first scanned before v0.184.9 already merged that output frame
    into the ``<T>`` target (both fold to the same safe name). See
    ``Project.reject_seestar_output_frames``. Mosaics are skipped here — their
    on-device output naming is device-specific and tracked as a separate bug.

    ``parents`` is the same optional parallel list ``_apply_seestar_convention``
    takes, and it is what keeps the two halves telling the same story. A bare
    ``<T>/`` folder with no same-parent ``<T>_sub`` sibling is *real subs* — the
    convention ingests it — so registering ``<T>`` as an output base would turn
    round and reject the very frames that were just ingested. (Only 1–2 of them,
    thanks to ``reject_seestar_output_frames``' size guard, but that is exactly
    the small root-level session nobody would think to check.) So a base whose
    bare folder this scan is *ingesting* is left out. A base whose bare folder is
    skipped as output, or isn't in the drop at all, still registers — the healing
    an already-migrated library depends on is untouched.
    """
    if parents is None:
        parents = [""] * len(subdirs_with_fits)
    sibling_names = {
        (parent, name.lower())
        for (name, _), parent in zip(subdirs_with_fits, parents, strict=True)
    }
    # The bare folders this scan will ingest as real subs — the same test
    # ``_apply_seestar_convention`` makes, so the two can't disagree.
    ingested_bare = {
        name.lower()
        for (name, _), parent in zip(subdirs_with_fits, parents, strict=True)
        if not name.lower().endswith((*_CAPTURE_SUFFIXES, _SUB_SUFFIX))
        and (parent, name.lower() + _SUB_SUFFIX) not in sibling_names
    }
    bases: dict[str, str] = {}
    for name, _ in subdirs_with_fits:
        low = name.lower()
        if low.endswith(_MOSAIC_SUB_SUFFIX):
            continue
        if low.endswith(_SUB_SUFFIX):
            base = name[: -len(_SUB_SUFFIX)].rstrip()
            if base and base.lower() not in ingested_bare:
                bases[base] = base
    return bases


# A Seestar's own on-device stacked OUTPUT folder holds a single image, so a
# target the pre-``_apply_seestar_convention`` scanner built from one is a
# 1-frame "stack". Allow a tiny margin above 1 (an occasional two-file output)
# while never flagging a real light-frame stack (dozens–thousands of subs).
_MAX_JUNK_OUTPUT_FRAMES = 2

# ...except for a MOSAIC, whose on-device output is one stacked image **per
# panel**, not one image. The owner's real S30 library proves the single-image
# cap is wrong there: "M 44_mosaic" holds 11 frames and "NGC 6960_mosaic" 7,
# so both sail past the ≤2 gate and linger as junk targets forever. This cap is
# still an order of magnitude below any real light-frame target (hundreds to
# thousands of subs), and the positive-evidence requirement is unchanged — the
# folder must be a bare "<T>_mosaic/" whose "<T>_mosaic_sub/" raw-subs sibling
# is actually present on disk — so a real target is still never mistaken for junk.
_MAX_JUNK_MOSAIC_OUTPUT_FRAMES = 32

# The bare on-device output folder of a mosaic ("<T>_mosaic/", beside its raw
# subs in "<T>_mosaic_sub/"). Confirmed as this device's real naming from the
# owner's live S30 share — the bare "<T>/" shape never occurs for a mosaic.
_MOSAIC_SUFFIX = "_mosaic"


def junk_output_frame_cap(target_name: str) -> int:
    """The largest frame count worth *examining* as a possible on-device output
    target, given only its name. Two values, because a single field's on-device
    output is one stacked image while a mosaic's is one image per panel (see
    :data:`_MAX_JUNK_MOSAIC_OUTPUT_FRAMES`).

    Exists so a caller can skip opening a big target's project without keeping —
    and drifting from — its own copy of the engine's limits. It only decides
    *whether to look*; :func:`classify_seestar_junk_target` still requires the
    positive on-disk evidence before anything is flagged."""
    if target_name.strip().lower().endswith(_MOSAIC_SUFFIX):
        return _MAX_JUNK_MOSAIC_OUTPUT_FRAMES
    return _MAX_JUNK_OUTPUT_FRAMES


# Scratch folders that some *other* program leaves in a shared astro folder. They
# are not created by this app (grepped: no match) and hold whatever a run of that
# tool happened to be working on, so a target built from one is junk — but only
# **after the fact and with the user confirming**: the cleanup nudge offers to
# remove the target record, and nothing here ever touches the scan-time ingest.
#
# Deliberately an EXACT, explicit list rather than a "*_tmp" pattern. A pattern
# costs nothing on the folder it was written for and silently condemns a real
# folder someone named badly — and the on-by-default ingest path is exactly where
# AGENTS.md §1 says not to guess. Extend it with a name actually observed in a
# real share, never with one that merely looks temporary.
_TEMP_FOLDER_NAMES = frozenset({"batch_stack_tmp"})


@dataclass(frozen=True)
class JunkTargetVerdict:
    """Why a target looks like Seestar output/capture junk, not raw subs."""

    reason: str   # "video" | "photo" | "on_device_output" | "temp_folder"
    detail: str   # plain-language, beginner-facing explanation


def is_temp_folder_target_name(target_name: str) -> bool:
    """True when a target's *name* alone marks it as another program's scratch
    folder (:data:`_TEMP_FOLDER_NAMES`) rather than an object in the sky. Decided
    by name at any frame count — a temp folder holds whatever that tool was
    mid-way through, so its size says nothing — which also lets a caller answer
    without opening the target's project."""
    return target_name.strip().lower() in _TEMP_FOLDER_NAMES


def _temp_folder_verdict(folder_name: str) -> JunkTargetVerdict:
    """The verdict for a target built from another program's scratch folder."""
    return JunkTargetVerdict(
        "temp_folder",
        f"Built from a “{folder_name}” folder — a working folder another "
        "stacking program leaves behind, not one of your capture folders. "
        "Whatever is in it is a leftover of that program's run, so it isn't "
        "worth keeping as a target here.",
    )


def is_capture_mode_target_name(target_name: str) -> bool:
    """True when a target's *name* alone marks it as one of the Seestar's
    capture-mode folders (``*_video`` / ``*_photo``) — neither of which holds
    stackable subs, at any frame count. Lets a caller decide by name before
    paying to open the target's project."""
    return target_name.strip().lower().endswith(_CAPTURE_SUFFIXES)


def _capture_folder_verdict(suffix: str) -> JunkTargetVerdict:
    """The verdict for one of the Seestar's capture-mode folders
    (:data:`_CAPTURE_SUFFIXES`) — a video clip or a single-shot still. Both are
    "there are no subs in here", but the wording has to name the right thing or
    the nudge reads as nonsense beside a folder full of scenery snapshots."""
    if suffix == _PHOTO_SUFFIX:
        return JunkTargetVerdict(
            "photo",
            "Built from a Seestar “_photo” folder — the single snapshots it "
            "takes in scenery/planetary photo mode, not raw sub-frames, so "
            "there is nothing here to stack into a deep image.",
        )
    return JunkTargetVerdict(
        "video",
        "Built from a Seestar “_video” capture folder, not raw sub-frames — "
        "it can't be stacked into a deep image.",
    )


def classify_seestar_junk_target(
    target_name: str,
    source_paths: Sequence[str | Path],
    n_frames: int,
) -> JunkTargetVerdict | None:
    """
    Decide whether a library target was built from a Seestar *output*, *video* or
    *photo* folder rather than raw sub-frames — the leftover "junk" targets an old,
    pre-``_apply_seestar_convention`` scan produced before the scanner learned the
    Seestar folder convention (v0.184.9).

    Pure and side-effect-free apart from a **read-only** ``<T>_sub`` sibling check
    on disk — the same signal ``_apply_seestar_convention`` uses to skip an
    on-device output. Returns ``None`` for a normal target. It never deletes
    anything: the caller surfaces the verdict for the user to confirm.

    * ``video`` — the target name (or every frame's source folder) ends with
      ``_video``: a video capture, not stackable deep-sky subs.
    * ``photo`` — the same, for ``_photo``: the single stills the device takes in
      scenery/planetary photo mode. Same family, same "nothing to stack here"
      verdict, different wording.
    * ``on_device_output`` — a small (≤ ``_MAX_JUNK_OUTPUT_FRAMES``) target whose
      frames all sit in a single **bare** ``<T>/`` folder that has a raw-subs
      ``<T>_sub/`` sibling on disk: the Seestar's own single stacked output, which
      "stacks" to one lower-resolution frame (colour speckle).
    * ``temp_folder`` — the target name, or the one folder all its frames sit in,
      is exactly one of :data:`_TEMP_FOLDER_NAMES`: another program's scratch
      folder sharing the astro share, not a capture folder.

    Conservative by design — it only flags a target with positive evidence
    (a ``_video``/``_photo`` name/folder, an exact scratch-folder name, or a bare
    output folder whose ``_sub`` sibling is actually present), so a real target is
    never mistaken for junk.
    """
    low_name = target_name.strip().lower()
    if is_capture_mode_target_name(target_name):
        for suffix in _CAPTURE_SUFFIXES:
            if low_name.endswith(suffix):
                return _capture_folder_verdict(suffix)
    if is_temp_folder_target_name(target_name):
        return _temp_folder_verdict(target_name.strip())

    folders = {Path(p).parent for p in source_paths}
    if not folders:
        return None
    folder_names = {f.name.lower() for f in folders}
    for suffix in _CAPTURE_SUFFIXES:
        if all(n.endswith(suffix) for n in folder_names):
            return _capture_folder_verdict(suffix)

    if len(folders) == 1:
        folder = next(iter(folders))
        low = folder.name.lower()
        # An exact scratch-folder name is positive evidence on its own, whatever
        # the frame count — unlike an on-device output, a temp folder can hold
        # any number of files, so no size guard applies.
        if low in _TEMP_FOLDER_NAMES:
            return _temp_folder_verdict(folder.name)
        # A raw-subs folder ("_sub"/"_mosaic_sub") is never junk — only a *bare*
        # output folder is. "_mosaic_sub" ends with "_sub", so one test covers both.
        # The cap comes from the FOLDER's name, which is the actual evidence: a
        # mosaic's output holds one image per panel, a single field's holds one.
        if (
            not low.endswith((_SUB_SUFFIX, *_CAPTURE_SUFFIXES))
            and n_frames <= junk_output_frame_cap(folder.name)
        ):
            sibling = folder.parent / f"{folder.name}{_SUB_SUFFIX}"
            try:
                is_output = sibling.is_dir()
            except OSError:
                is_output = False
            if is_output:
                is_mosaic = low.endswith(_MOSAIC_SUFFIX)
                what = (
                    "its own stacked image of each mosaic panel"
                    if is_mosaic
                    else "the Seestar's own single stacked image"
                )
                consequence = (
                    "stacking them just reproduces those few lower-resolution "
                    "panel images."
                    if is_mosaic
                    else "stacking it just reproduces that one lower-resolution "
                    "frame."
                )
                return JunkTargetVerdict(
                    "on_device_output",
                    f"Looks like {what} (its “{folder.name}_sub” raw-subs folder "
                    f"is right beside it), not raw subs — {consequence}",
                )
    return None


def duplicate_sub_target_base_name(
    target_name: str,
    source_paths: Sequence[str | Path],
) -> str | None:
    """Return the base target name (``<T>``) if this target looks like a leftover
    ``<T>_sub``-named **duplicate** that a pre-v0.184.9 scan built, else ``None``.

    Before the scanner learned the Seestar convention it mapped a raw-subs folder
    ``<T>_sub/`` to a target literally named ``<T>_sub``. The convention (v0.184.9)
    now maps that same folder to target ``<T>``, so on an upgraded install a
    re-scan registers those subs under ``<T>`` while the old ``<T>_sub``-named
    target lingers holding the *same* frames — a harmless-but-cluttering duplicate
    (two library tiles for one object, double auto-stack compute). The frames are
    correct raw subs, so this is **not** the ``on_device_output`` junk case; it is
    a de-duplication hint.

    **A mosaic is the same story with a different base name.** A leftover
    ``<T>_mosaic_sub``-named target duplicates the ``<T> (mosaic)`` target the
    convention now builds from that folder — *not* the single-field ``<T>``, whose
    footprint is different. (The owner's live library has three of these:
    ``M 3_MOSAIC_SUB``, ``M 44_MOSAIC_SUB``, ``NGC 6960_MOSAIC_SUB``.) The
    ``(mosaic)`` suffix is taken from :func:`_apply_seestar_convention` so the two
    can never disagree about what the duplicate's base is called.

    Pure and side-effect-free: it only recognises the *shape* (name ends ``_sub``
    and every frame sits under a single ``*_sub/`` folder). The caller must confirm
    the base target actually exists and already owns these subs before offering
    removal, so a legitimately-named standalone ``…_sub`` target (or one whose subs
    the base doesn't yet own) is never flagged.
    """
    base = duplicate_sub_base_name_from_name(target_name)
    if base is None:
        return None
    folders = {Path(p).parent for p in source_paths}
    if len(folders) != 1:
        return None
    folder = next(iter(folders))
    if not folder.name.lower().endswith(_SUB_SUFFIX):
        return None
    return base


def duplicate_sub_base_name_from_name(target_name: str) -> str | None:
    """The *name-shape* half of :func:`duplicate_sub_target_base_name`: given only
    a target's name, the name of the target the convention would fold its folder
    into (``<T>_sub`` → ``<T>``, ``<T>_mosaic_sub`` → ``<T> (mosaic)``), or
    ``None`` if the name isn't that shape.

    Split out because a caller that has a *set* of target names — the merge
    suggester, deciding whether two members of one sky-position cluster are the
    same physical files under two spellings — can rule the question out by name
    alone, and only pay to open both projects for the pairs that could be it."""
    name = target_name.strip()
    low = name.lower()
    if not low.endswith(_SUB_SUFFIX):
        return None
    if low.endswith(_MOSAIC_SUB_SUFFIX):
        base = name[: -len(_MOSAIC_SUB_SUFFIX)].rstrip()
        return mosaic_target_name(base) if base else None
    base = name[: -len(_SUB_SUFFIX)].rstrip()
    return base if base else None


@dataclass
class TargetScanResult:
    """What the organise phase did for one target."""

    target_name: str
    safe_name: str
    n_frames_found: int = 0
    n_frames_added: int = 0
    n_skipped_existing: int = 0
    n_errors: int = 0
    # Dedup-skipped frames whose content was refreshed (a mid-copy sub whose
    # source later completed, or a reused path overwritten with a different
    # capture) — their QC was reset, so the target needs re-QC even though no
    # *new* frame was added.
    n_frames_refreshed: int = 0
    # DB ids of those refreshed frames, so the caller can invalidate their cached
    # previews (which key on id alone and would keep showing the old image).
    refreshed_frame_ids: list[int] = field(default_factory=list)
    # Frames additively rejected because they are the Seestar's on-device output
    # (a pre-v0.184.9 library merged that output into this target as a fake sub).
    n_output_frames_rejected: int = 0


@dataclass
class ScanResult:
    """Outcome of a whole ``scan_and_organize`` pass."""

    root: str
    targets: list[TargetScanResult] = field(default_factory=list)
    # Bare "<T>/" folders the Seestar convention passed over because a "<T>_sub/"
    # sibling was there. Reported rather than dropped: the skip is right for the
    # device's own finished picture and wrong for a plainly-named folder of a
    # user's own subs, and nothing downstream could previously tell the user
    # which one just happened. See :class:`SkippedOutputFolder`.
    skipped_output_folders: list[SkippedOutputFolder] = field(default_factory=list)

    @property
    def n_targets(self) -> int:
        return len(self.targets)

    @property
    def unvouched_skips(self) -> list[SkippedOutputFolder]:
        """The skipped folders holding files the device's naming can't vouch for.

        A folder of pure ``Stacked*.fit`` is the convention working exactly as
        designed and is not worth a word. This is the subset worth telling the
        user about — and on a healthy Seestar library it is empty, which is the
        point: the report is silent until something is actually unexplained.
        """
        return [s for s in self.skipped_output_folders if s.n_unvouched > 0]

    @property
    def total_found(self) -> int:
        return sum(t.n_frames_found for t in self.targets)

    @property
    def total_added(self) -> int:
        return sum(t.n_frames_added for t in self.targets)


def scan_and_organize(
    library: Library,
    root: str | Path,
    *,
    copy_to_cache: bool = False,
    progress: ProgressFn | None = None,
) -> ScanResult:
    """
    Walk ``root`` and organise every FITS file into a library target.

    Parameters
    ----------
    library
        The library to populate. Targets are created/re-opened inside it.
    root
        The folder to scan. Its immediate sub-folders each become a target;
        loose FITS files in the root go to the ``Unsorted`` target.
    copy_to_cache
        When True, every frame is copied into its target's Stage-1 cache
        (useful if the source folder is on a NAS). The default is False:
        the scanned folder is normally already on local disk, so we just
        reference the originals in place and skip the (potentially huge)
        duplication.
    progress
        Optional ``progress(phase, done, total)`` callback.

    Re-running a scan is safe — frames already registered (matched by their
    absolute source path) are skipped, so you can scan again after adding
    more nights to the same folders.
    """
    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise NotADirectoryError(f"scan root is not a directory: {root}")

    result = ScanResult(root=str(root))

    # Each immediate sub-directory containing FITS files = one target.
    subdirs = sorted(d for d in root.iterdir() if d.is_dir())
    # Loose FITS directly in the root → the Unsorted catch-all.
    loose = sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in FITS_SUFFIXES
    )

    subdirs_with_fits: list[tuple[str, list[Path]]] = []
    # Parent-directory key for each entry above, so the convention's "<T>_sub
    # sibling present" skip is scoped to folders that truly share a parent. A
    # container-expanded child's parent is the container; a root-level folder's
    # is the scan root. Without this a bare root-level "<T>/" of real subs is
    # skipped merely because an unrelated container child happens to be "<T>_sub".
    parents: list[str] = []
    for d in subdirs:
        # Whole-device drop: the Seestar share/SD card copied wholesale keeps a
        # container level (e.g. "MyWorks/") intact, so a subdir may hold no FITS
        # directly but wrap the real "<T>_sub"/"<T>" folders one level deeper.
        # Expand such a container into its children so each real target is kept
        # separate, instead of lumping every object + output + video into ONE
        # giant target named after the container.
        if not find_fits_files(d, recursive=False) and _looks_like_seestar_container(d):
            for child in sorted(c for c in d.iterdir() if c.is_dir()):
                child_fits = find_fits_files(child, recursive=True)
                if child_fits:
                    subdirs_with_fits.append((child.name, child_fits))
                    parents.append(str(d))
            # Heal the OLD shape: before this expansion existed, a scan lumped the
            # whole container into ONE giant target named after it, mixing several
            # objects' subs with on-device outputs/videos — it keeps auto-stacking
            # gibberish and both cheap junk detectors are blind to it. Flag that
            # pre-existing giant target (once, cheaply, here at scan time) so the
            # Library's cleanup-suggestions can offer one-click removal without
            # opening every big project on every poll.
            _flag_legacy_container_drop(library, d)
            continue
        fits = find_fits_files(d, recursive=True)
        if fits:
            subdirs_with_fits.append((d.name, fits))
            parents.append(str(root))
    # Fold the Seestar folder convention in (raw "_sub" folders → targets;
    # skip on-device outputs and videos) before turning folders into targets.
    # The skipped bare "<T>/" folders come back with it so the scan can say what
    # it passed over instead of dropping thousands of files without a word.
    units = _apply_seestar_convention(
        subdirs_with_fits, parents, result.skipped_output_folders)
    for skip in result.unvouched_skips:
        log.warning(
            "Skipped %r (%d file(s)) — a %r folder sits beside it, so the "
            "convention reads it as the Seestar's own finished picture. But %d "
            "of its files are not named like the device's output, so they may "
            "be raw subs that are now not being stacked. Nothing was changed on "
            "disk; look in that folder if the target seems short of frames.",
            skip.name, skip.n_files, skip.name + _SUB_SUFFIX, skip.n_unvouched,
        )
    # Upgrade path: a library first scanned before v0.184.9 may already hold the
    # Seestar's on-device output inside a "<T>" target the raw "<T>_sub" subs now
    # map to — additively reject those output frames so they leave the stack pool.
    output_bases = _seestar_output_bases(subdirs_with_fits, parents)
    if loose:
        units.append((UNSORTED_TARGET_NAME, loose))

    total = len(units)
    for i, (target_name, files) in enumerate(units):
        if progress is not None:
            progress("Organizing", i, total)
        tsr = _ingest_into_target(library, target_name, files,
                                  copy_to_cache=copy_to_cache,
                                  reject_output_base=output_bases.get(target_name))
        result.targets.append(tsr)
    if progress is not None:
        progress("Organizing", total, total)

    return result


def _ingest_into_target(
    library: Library,
    target_name: str,
    files: list[Path],
    *,
    copy_to_cache: bool,
    reject_output_base: str | None = None,
) -> TargetScanResult:
    """Open (or create) the target and ingest ``files`` into its project.

    ``reject_output_base``, when given, is the bare ``<T>/`` output-folder
    basename for a Seestar single-field target: after ingest, any already-
    registered frame that lives in that folder (the Seestar's own on-device
    output, mis-ingested by a pre-v0.184.9 scan) is additively rejected so it
    leaves the stack/reference pool.
    """
    entry, proj = library.open_or_create_target(target_name)
    tsr = TargetScanResult(
        target_name=entry.name,
        safe_name=entry.safe_name,
        n_frames_found=len(files),
    )
    try:
        cache = CacheManager(library.target_dir(entry))
        for res in ingest_files(proj, cache, files, copy_to_cache=copy_to_cache):
            # Check ``skipped`` first: a benign skip (e.g. a still-copying sub) is
            # never a failure even if it carries a note, so it can't inflate n_errors.
            if res.skipped:
                tsr.n_skipped_existing += 1
                if res.refreshed:
                    tsr.n_frames_refreshed += 1
                    if res.refreshed_frame_id is not None:
                        tsr.refreshed_frame_ids.append(res.refreshed_frame_id)
            elif res.error is not None:
                tsr.n_errors += 1
            else:
                tsr.n_frames_added += 1
        if reject_output_base:
            rejected = proj.reject_seestar_output_frames(reject_output_base)
            tsr.n_output_frames_rejected = len(rejected)
            if rejected:
                log.info(
                    "Rejected %d Seestar on-device output frame(s) from target "
                    "%r (source folder %r) — they are excluded from stacking; "
                    "re-accept them if you really want them stacked.",
                    len(rejected), entry.name, reject_output_base,
                )
    finally:
        proj.close()
    # Keep the registry's cached counts in step with the project DB.
    library.refresh_target_stats(entry.safe_name)
    return tsr


def run_qc_and_solve(
    project: Project,
    *,
    astap_path: str | Path | None = None,
    astap_fov_deg: float | None = None,
    astap_timeout_s: float | None = None,
    max_workers: int | None = None,
    run_qc: bool = True,
    run_solve: bool = True,
    serial: bool = False,
    only_new_qc: bool = False,
    use_solve_hints: bool = True,
    auto_reject_streaks: bool = True,
    bootstrap_solve: bool = False,
    progress: ProgressFn | None = None,
    should_stop: ShouldStopFn | None = None,
) -> dict:
    """
    Run QC metrics and ASTAP plate-solving across one target's frames.

    Both phases fan their work out to a ``ProcessPoolExecutor`` (heavy
    numeric / subprocess work needs real parallelism). Pass ``serial=True``
    to run in-process instead — used by tests and tiny projects where the
    pool spin-up isn't worth it.

    DB writes happen on the calling thread (the one that opened ``project``),
    which keeps SQLite access single-threaded per project.

    Returns a small summary dict: ``{'qc_done', 'qc_total', 'solve_done',
    'solve_total', 'solve_ok'}``. The ``*_done`` figures are progress counters
    (frames *attempted*); ``solve_ok`` is how many of them actually came back
    with a usable plate solution.
    """
    from seestack.qc.runner import (
        apply_qc_result_to_db,
        build_qc_arglist,
        compute_for_db_row,
        reconcile_streak_rejections,
    )
    from seestack.solve.runner import (
        apply_solve_result_to_db,
        build_solve_arglist,
        solve_one,
    )

    summary = {"qc_done": 0, "qc_total": 0, "solve_done": 0, "solve_total": 0}

    if run_qc and not _stopped(should_stop):
        qc_args = build_qc_arglist(project, only_new=only_new_qc)
        summary["qc_total"] = len(qc_args)
        for done, result in _map_jobs(
            compute_for_db_row, qc_args,
            serial=serial, max_workers=max_workers,
            phase="QC", progress=progress, should_stop=should_stop,
        ):
            if result is not None:
                try:
                    apply_qc_result_to_db(
                        project, result, auto_reject=auto_reject_streaks)
                except Exception as exc:  # noqa: BLE001
                    log.warning("QC DB write failed: %s", exc)
            summary["qc_done"] = done
        # A stationary bright extended object (edge-on galaxy, elongated nebula)
        # trips the shape-only streak detector on most/all subs, so an unguarded
        # auto-reject would silently discard the whole target. Re-accept the
        # streak rejections when they cover a majority of the target (they can't
        # be transient trails); stacking's per-pixel rejection still cleans any
        # genuine trail. No-op in the normal case (a few real satellite subs).
        if auto_reject_streaks:
            restored = reconcile_streak_rejections(project)
            if restored:
                summary["streak_reaccepted"] = len(restored)

    if run_solve and not _stopped(should_stop):
        solve_args = build_solve_arglist(project, use_hint=use_solve_hints)
        # build_solve_arglist reads astap_path/fov/timeout from project meta
        # (usually unset for freshly-scanned targets) — override each with the
        # caller-supplied value so the whole scan uses the app's configured
        # ASTAP, field of view, and timeout. The FOV here is the *fallback*: a
        # frame whose header carries FOCALLEN/XPIXSZ derives its own true FOV in
        # ``solve_one`` (S30 ≈ 2.1°, S50 ≈ 1.27°); this Settings value only
        # applies to headers that lack those fields. Project meta stays a
        # per-target override for any key the caller didn't supply.
        if astap_path is not None or astap_fov_deg is not None or astap_timeout_s is not None:
            solve_args = [
                (
                    fid, path,
                    str(astap_path) if astap_path is not None else ap,
                    astap_fov_deg if astap_fov_deg is not None else fov,
                    astap_timeout_s if astap_timeout_s is not None else to,
                    *rest,
                )
                for (fid, path, ap, fov, to, *rest) in solve_args
            ]
        summary["solve_total"] = len(solve_args)
        # ``solve_done`` counts frames *attempted* (it's the progress counter), so
        # it can't answer "how many did we actually locate?" — a field where every
        # solve failed still finishes with solve_done == solve_total. Count the
        # genuine successes separately so a caller can report an honest number.
        # The bar is the same one ``apply_solve_result_to_db`` writes a WCS for:
        # ASTAP said yes *and* a usable WCS came out of the sidecar.
        solve_ok = 0
        for done, result in _map_jobs(
            solve_one, solve_args,
            serial=serial, max_workers=max_workers,
            phase="Solving", progress=progress, should_stop=should_stop,
        ):
            if result is not None:
                if result.solved and wcs_text_is_usable(result.wcs_text):
                    solve_ok += 1
                try:
                    apply_solve_result_to_db(project, result)
                except Exception as exc:  # noqa: BLE001
                    log.warning("solve DB write failed: %s", exc)
            summary["solve_done"] = done
        summary["solve_ok"] = solve_ok

        # Stack-then-solve bootstrap: if the per-sub pass left most subs unsolved
        # (a faint / sparse-star field), integrate the accepted-but-unsolved subs
        # into a deep image, solve that once, and propagate the WCS back — so the
        # whole burst can stack instead of the handful that solved individually.
        # Opt-in and self-guarded (a no-op unless enough subs stayed unsolved).
        if bootstrap_solve and not _stopped(should_stop):
            try:
                from seestack.solve.bootstrap import bootstrap_solve as _bootstrap

                bres = _bootstrap(
                    project,
                    astap_path=str(astap_path) if astap_path is not None else None,
                    fov_deg=astap_fov_deg if astap_fov_deg is not None else 1.3,
                    timeout_s=astap_timeout_s if astap_timeout_s is not None else 60.0,
                )
                if bres.engaged:
                    summary["bootstrap_engaged"] = True
                    summary["bootstrap_solved"] = bres.deep_solved
                    summary["bootstrap_propagated"] = bres.n_propagated
                    if bres.n_propagated:
                        log.info(
                            "stack-then-solve bootstrap rescued %d sub(s) for %s",
                            bres.n_propagated, project.name,
                        )
            except Exception as exc:  # noqa: BLE001 — a bootstrap failure is non-fatal
                log.warning("stack-then-solve bootstrap failed: %s", exc)

    return summary


def _stopped(should_stop: ShouldStopFn | None) -> bool:
    return should_stop is not None and should_stop()


def _map_jobs(
    func,
    arg_tuples: list[tuple],
    *,
    serial: bool,
    max_workers: int | None,
    phase: str,
    progress: ProgressFn | None,
    should_stop: ShouldStopFn | None,
):
    """
    Yield ``(done_count, result)`` for each completed job.

    ``result`` is whatever ``func`` returned, or None if that job raised.
    Honours cancellation via ``should_stop`` between completions.
    """
    total = len(arg_tuples)
    if total == 0:
        return

    if serial:
        for i, args in enumerate(arg_tuples, start=1):
            if _stopped(should_stop):
                return
            try:
                value = func(*args)
            except Exception as exc:  # noqa: BLE001
                log.warning("%s job failed: %s", phase, exc)
                value = None
            if progress is not None:
                progress(phase, i, total)
            yield i, value
        return

    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(func, *args): args for args in arg_tuples}
        done = 0
        for fut in as_completed(futures):
            if _stopped(should_stop):
                # Drop everything still queued and bail out promptly.
                ex.shutdown(wait=False, cancel_futures=True)
                return
            try:
                value = fut.result()
            except Exception as exc:  # noqa: BLE001
                log.warning("%s job failed: %s", phase, exc)
                value = None
            done += 1
            if progress is not None:
                progress(phase, done, total)
            yield done, value
