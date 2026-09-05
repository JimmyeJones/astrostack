"""Every finished picture, at the size you'd print it, in one file.

``/api/gallery/pictures.zip`` streams what the app has been *showing* — each
target's stored preview, which :func:`~seestack.stack.output._write_preview_png`
caps at 1024 px. That is the honest default for "the pictures as you see them",
and the card that offers it says so. But someone backing up a season, or
printing the picture they spent an evening editing, wants the *full-resolution*
render — and today they have to open every target and press "Full-res PNG" one
at a time, which is exactly the friction the bulk download exists to remove.

The full-size version cannot be the same streaming response: a target's
native-resolution picture has **no file on disk** (the per-run download renders
it per request from the master FITS plus the run's saved recipe), so an archive
of them has to be *built*, which takes minutes on a library of any size. So this
is a job — submitted, progress-reported, cancellable — that writes one archive
into ``<data_root>/exports/`` and hands it over when it's done, the same shape
the editor's PNG/share/print downloads already use.

Three rules the design follows:

* **Nothing is re-exported, and nothing the user owns is touched.** Renders go
  straight into the archive; no new stack run, no new preview, no edit marker.
  The only bytes written are the archive itself, inside a directory this module
  owns. ``incoming/`` is never read from or written to (AGENTS.md §10).
* **One archive at a time.** The previous archive is deleted before a new one is
  built, so a NAS with a fixed disk allowance carries one copy of this rather
  than one per press. It is a *cache* — deleting it by hand costs nothing.
* **A picture that can't be rendered still gets in.** A run whose master FITS
  has been pruned can't be rendered at native resolution, so its stored preview
  is copied instead and named in a ``_preview_size.txt`` note inside the
  archive — an archive that quietly mixed sizes without saying so is the same
  trust cost this feature exists to fix.
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

#: Where a built archive lands: a new, app-owned directory under the data root.
#: Additive — no existing layout moves (AGENTS.md §9) — and holding it outside
#: the library keeps it out of every walk that looks for targets or results.
ARCHIVE_DIRNAME = "exports"

#: The archive's file name. Fixed, because only one is kept.
ARCHIVE_FILENAME = "my-astrostack-pictures-full.zip"

#: The note listing entries that are the stored preview rather than a full-res
#: render (see the module docstring's third rule).
PREVIEW_NOTE_NAME = "_preview_size.txt"

#: The note listing pictures that could not be added at all — the same promise
#: ``pictures.zip`` makes, so an archive never quietly claims to be complete.
SKIPPED_NOTE_NAME = "_skipped.txt"


def unique_entry_name(stem: str, suffix: str, used: dict[str, int]) -> str:
    """``"<stem><suffix>"``, with a ``-2``/``-3`` suffix when that name is taken.

    ``used`` is the caller's running tally, keyed case-insensitively so the
    archive stays unambiguous on a case-insensitive filesystem (a Mac or Windows
    unzip would otherwise silently overwrite one member with the other).

    The **generated** ``-N`` name is reserved in ``used`` too, not just the base
    name: without that, a later real stem that happens to equal an earlier
    generated name (e.g. a ``pic-2`` target after two ``pic`` collisions, or a
    third source that sanitises onto a suffixed same-day still) would be treated
    as fresh and emitted unchanged, colliding with the earlier generated member —
    and ``zipfile`` accepts the duplicate (a ``UserWarning``) while every unzip
    tool silently overwrites, dropping a picture from a "download all" backup. So
    we advance past any generated name that is itself already taken.

    Lives here rather than beside the streaming zip so both archives name their
    members by one rule: two downloads that call themselves "all my pictures"
    disagreeing about which picture is ``M_42-2.png`` would be its own small bug.
    """
    name = f"{stem}{suffix}"
    seen = used.get(name.lower())
    if not seen:
        used[name.lower()] = 1
        return name
    # Name taken: find the next `-N` form that is itself free, then reserve it so
    # a future real stem equal to it collides rather than duplicating.
    n = seen + 1
    candidate = f"{stem}-{n}{suffix}"
    while candidate.lower() in used:
        n += 1
        candidate = f"{stem}-{n}{suffix}"
    used[name.lower()] = n
    used[candidate.lower()] = 1
    return candidate


@dataclass
class PicturePick:
    """One member of the archive: either a run to render, or a file to copy.

    ``run`` is a stack-run row detached from its (closed) project, carrying
    everything :func:`webapp.pipeline.render_run_full_res_png` needs; ``path`` is
    a file already on disk at full size (a Moon/Sun still) or the stored preview
    of a run that can no longer be rendered. Exactly one of the two is set.
    """

    name: str
    run: object | None = None
    recipe_json: str | None = None
    path: Path | None = None
    #: True when ``path`` is a *preview* standing in for a render we couldn't do.
    preview_only: bool = False


@dataclass
class ArchiveReport:
    """What a build produced — the job result, in plain numbers."""

    path: str = ""
    filename: str = ""
    n_pictures: int = 0
    n_full_res: int = 0
    n_preview_only: int = 0
    skipped: list[str] = field(default_factory=list)
    size_bytes: int = 0
    #: True when the user cancelled part-way; no archive is left behind.
    cancelled: bool = False


def archive_dir(settings) -> Path:  # noqa: ANN001 — webapp.config.Settings
    """The directory built archives live in (not created here)."""
    return Path(settings.data_root) / ARCHIVE_DIRNAME


def archive_path(settings) -> Path:  # noqa: ANN001 — webapp.config.Settings
    """The one archive this install keeps."""
    return archive_dir(settings) / ARCHIVE_FILENAME


def _target_pick(lib, entry, used: dict[str, int]) -> PicturePick | None:  # noqa: ANN001
    """The target's current picture, resolved to something the archive can hold.

    Mirrors :func:`webapp.routers.targets.current_picture_path`'s precedence —
    the pinned cover run, else the newest run that still has a preview on disk —
    but stops at the **run** rather than the preview file, because a full-res
    render needs the run's master FITS and its saved recipe. A run whose FITS is
    gone falls back to its preview (flagged ``preview_only``); a target with no
    readable run at all yields ``None`` and is simply absent, exactly as it is
    from the Library tile and the streaming zip.
    """
    from webapp.routers.editor import RECIPE_META_PREFIX
    from webapp.routers.stack import _preview_is_display_space

    try:
        proj = lib.open_target(entry.safe_name)
    except Exception:  # noqa: BLE001 — a missing/broken project is just no picture
        return None
    try:
        runs = list(proj.iter_stack_runs())  # newest first
        cover_id = getattr(entry, "cover_stack_run_id", None)
        ordered = runs
        if cover_id is not None:
            pinned = [r for r in runs if r.id == cover_id]
            # The pinned cover wins when it is still there and still has a
            # picture; otherwise we degrade to the newest, never to nothing.
            ordered = pinned + [r for r in runs if r.id != cover_id]
        chosen = None
        for run in ordered:
            preview = getattr(run, "preview_path", None)
            if preview and Path(preview).exists():
                chosen = run
                break
        if chosen is None:
            return None
        stem = entry.safe_name or f"target-{entry.id}"
        fits_path = getattr(chosen, "fits_path", None)
        if not fits_path or not Path(fits_path).exists():
            # Nothing to render from: the master was pruned, or this is an older
            # run that never had one. Its preview is still the picture — hand it
            # over and say so, rather than dropping the target from a backup.
            path = Path(chosen.preview_path)
            return PicturePick(name=unique_entry_name(stem, path.suffix, used),
                               path=path, preview_only=True)
        recipe_json = None
        if _preview_is_display_space(getattr(chosen, "options_json", None)):
            recipe_json = proj.get_meta(f"{RECIPE_META_PREFIX}{chosen.id}")
        return PicturePick(name=unique_entry_name(stem, ".png", used),
                           run=chosen, recipe_json=recipe_json)
    except Exception:  # noqa: BLE001 — an unreadable run list must not sink the job
        log.warning("could not resolve a full-size picture for %s",
                    getattr(entry, "safe_name", "?"), exc_info=True)
        return None
    finally:
        proj.close()


def _video_still_picks(settings, used: dict[str, int]) -> list[PicturePick]:  # noqa: ANN001
    """Every finished Moon/Sun still, copied verbatim.

    A still's ``stack.png`` is already written at native resolution
    (``write_full_res_png``), so there is nothing to render: these members are
    byte-for-byte the same in both archives. Named through the same
    ``make_safe_name`` and the same collision tally as the target side, so the
    two sources can't produce two members with one name.
    """
    from seestack.io.library import make_safe_name
    from webapp import video

    try:
        metas = list(video.iter_results(settings))
    except Exception:  # noqa: BLE001 — a video-store problem must not sink the job
        log.warning("could not list video stills for the full-size archive",
                    exc_info=True)
        return []
    picks: list[PicturePick] = []
    for meta in metas:
        path = video.result_dir(settings, meta.capture_id) / video.PNG_NAME
        if not path.is_file():
            continue
        day = (meta.created_utc or "")[:10]
        stem = make_safe_name(f"{meta.label} {day}".strip() or meta.capture_id)
        picks.append(PicturePick(name=unique_entry_name(stem, path.suffix, used),
                                 path=path))
    return picks


def plan_full_size_pictures(settings) -> list[PicturePick]:  # noqa: ANN001
    """Every picture the archive will hold, in the order it will hold them.

    Targets first (one picture each, the same one every other screen shows),
    then the finished Moon/Sun stills — the same population as
    ``/api/gallery/pictures.zip``, so "all my pictures" means one thing however
    you download it.
    """
    from seestack.io.library import Library

    used: dict[str, int] = {}
    picks: list[PicturePick] = []
    lib = Library.open_or_create(settings.resolved_library_root)
    try:
        for entry in lib.list_targets():
            pick = _target_pick(lib, entry, used)
            if pick is not None:
                picks.append(pick)
    finally:
        lib.close()
    picks.extend(_video_still_picks(settings, used))
    return picks


def build_full_size_archive(
    settings,  # noqa: ANN001 — webapp.config.Settings
    picks: list[PicturePick],
    *,
    progress: Callable[[str, int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    max_long_edge: int | None = None,
) -> ArchiveReport:
    """Render/copy every pick into one archive and return what it holds.

    Writes to a ``.part`` file and renames on success, so a cancelled or crashed
    build never leaves a half-written archive looking finished. Each picture is
    rendered, written and dropped before the next one starts, so peak memory is
    one picture rather than one library.

    ``progress`` takes the engine's ``(phase, done, total)`` shape so a job can
    pass its own callback straight in; ``should_stop`` is checked between
    pictures (a render is not interruptible), and a stop leaves **no** archive —
    a half-built backup that looked complete would be worse than none.
    """
    from webapp.pipeline import render_run_full_res_png
    from webapp.routers.stack import _FULL_RES_PNG_MAX_LONG_EDGE

    cap = _FULL_RES_PNG_MAX_LONG_EDGE if max_long_edge is None else max_long_edge
    out_dir = archive_dir(settings)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_path(settings)
    part = dest.with_suffix(dest.suffix + ".part")
    # One archive at a time: the old one goes before the new one is built, so the
    # box never holds two copies of the same season.
    for stale in (dest, part):
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            log.warning("could not remove the previous archive at %s", stale)

    report = ArchiveReport(path=str(dest), filename=ARCHIVE_FILENAME)
    preview_only: list[str] = []
    total = len(picks)
    with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED) as zf:
        for i, pick in enumerate(picks):
            if should_stop is not None and should_stop():
                report.cancelled = True
                break
            if progress is not None:
                progress(f"Preparing {pick.name}", i, total)
            try:
                if pick.run is not None:
                    png = render_run_full_res_png(
                        pick.run, pick.recipe_json, max_long_edge=cap)
                    zf.writestr(pick.name, png)
                    del png
                    report.n_full_res += 1
                elif pick.path is not None:
                    zf.write(pick.path, pick.name)
                    if pick.preview_only:
                        report.n_preview_only += 1
                        preview_only.append(pick.name)
                    else:
                        report.n_full_res += 1
                else:  # pragma: no cover — a pick always carries one of the two
                    continue
                report.n_pictures += 1
            except Exception as exc:  # noqa: BLE001 — one bad picture must not sink the archive
                log.warning("skipping %s in the full-size archive: %s",
                            pick.name, exc)
                report.skipped.append(f"{pick.name} — could not be added ({exc})")
        if not report.cancelled:
            if preview_only:
                zf.writestr(
                    PREVIEW_NOTE_NAME,
                    "These pictures are the smaller preview, not a full-resolution "
                    "render:\n\n" + "\n".join(preview_only)
                    + "\n\nThe stacked image file they were made from is no longer "
                      "on disk, so there was nothing to render at full size. "
                      "Stacking that target again would give you a full-resolution "
                      "picture.\n",
                )
            if report.skipped:
                zf.writestr(
                    SKIPPED_NOTE_NAME,
                    "These pictures could not be added to the archive:\n\n"
                    + "\n".join(report.skipped) + "\n",
                )
    if report.cancelled:
        part.unlink(missing_ok=True)
        report.path = ""
        return report
    part.replace(dest)
    try:
        report.size_bytes = dest.stat().st_size
    except OSError:
        report.size_bytes = 0
    if progress is not None:
        progress("Archive ready", total, total)
    return report
