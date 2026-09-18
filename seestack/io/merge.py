"""
Combine frames from multiple projects of the same target into one.

Use case: you imaged M51 across three nights, each saved as its own project.
You want to stack all of them together for maximum integration time. Rather
than re-ingesting raws, point at the existing project DBs and have Seestack
copy their frame rows (with WCS, QC metrics, etc.) into a destination project.

What gets merged:
  - Frame DB rows from every source project. Skipped silently if a frame's
    source path is already in the destination (no duplicate ingest).
  - Stage-1 cached files (the local copies of the raws) when available, so
    the destination project doesn't need to re-read the NAS.

Stack runs (the finished pictures) travel too, when the caller asks for it with
``copy_stack_runs`` — see :func:`carry_stack_runs`. They did not always: the
"combine these folders" merge deletes each source target's folder afterwards, so
"stack runs stay per-source" meant a one-click merge destroyed every picture the
app had already made of that object, under a nudge promising *"keeps every sub —
nothing is deleted"*.

What does NOT get merged:
  - Stage-2 caches (aligned data — invalidated when the destination's
    reference frame changes anyway).
"""

from __future__ import annotations

import contextlib
import logging
import re
import shutil
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from seestack.core.cache import CacheManager
from seestack.io.ingest import _dedup_key
from seestack.io.project import FrameRow, Project, StackRunRow

log = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Per-source-project outcome."""

    source_project: str
    n_added: int
    n_skipped_duplicate: int
    n_skipped_missing_file: int
    #: Finished pictures (``stack_runs`` rows, with their output files and their
    #: per-run project meta) carried into the destination. Always ``0`` unless the
    #: caller passed ``copy_stack_runs=True``, so every existing caller reads the
    #: same number it always did.
    n_runs_copied: int = 0
    #: Pictures this source still holds that could **not** be carried — a disk
    #: full, a permission error, an I/O fault. A caller that deletes the source
    #: afterwards must not, when this is non-zero: the whole point of carrying
    #: them is that the delete is about to make the originals unrecoverable.
    n_runs_lost: int = 0


def merge_projects(
    destination: Project,
    source_dirs: Iterable[str | Path],
    *,
    copy_cached_files: bool = True,
    copy_stack_runs: bool = False,
) -> Iterator[MergeResult]:
    """
    Pull every frame from each source project into ``destination``.

    Yields one ``MergeResult`` per source so the caller can show progress.

    ``copy_stack_runs`` additionally carries each source's finished pictures over
    (:func:`carry_stack_runs`). It defaults **off** so the plain
    "combine three nights' frame rows for a deeper stack" use this module was
    written for is unchanged; :meth:`seestack.io.library.Library.merge_targets`
    turns it on, because it deletes the source folder afterwards and would
    otherwise take the pictures with it.
    """
    dest_cache = CacheManager(destination.project_dir)
    dest_cache.ensure_dirs()
    # Dedup on the canonical (realpath) key, symmetrically to ingest — a change
    # of path spelling for one physical file (a symlinked NAS mount, a relative
    # vs absolute scan root) must not merge the same frame twice → double-weighted
    # in the stack. Mirrors the ingest fix; stored source_path is never rewritten.
    existing_sources = {_dedup_key(f.source_path) for f in destination.iter_frames()}

    for src_dir in source_dirs:
        src_path = Path(src_dir)
        if not (src_path / "project.sqlite").exists():
            log.warning("skipping %s: not a Seestack project", src_path)
            yield MergeResult(str(src_path), 0, 0, 0)
            continue
        src_project = Project.open(src_path)
        try:
            added = 0
            dup = 0
            missing = 0
            with destination.transaction():
                for frame in src_project.iter_frames():
                    key = _dedup_key(frame.source_path)
                    if key in existing_sources:
                        dup += 1
                        continue
                    # Copy the row sans id; let the destination assign a new one.
                    new_row = _frame_without_id(frame)
                    new_id = destination.add_frame(new_row)
                    existing_sources.add(key)
                    added += 1
                    # Copy the cached file if available.
                    if copy_cached_files and frame.cached_path:
                        old_cache = Path(frame.cached_path)
                        if old_cache.exists():
                            new_cache = dest_cache.stage1_path_for(new_id, old_cache.name)
                            try:
                                if not new_cache.exists() or new_cache.stat().st_size != old_cache.stat().st_size:
                                    shutil.copy2(old_cache, new_cache)
                                destination.update_frame(new_id, cached_path=str(new_cache))
                            except OSError as exc:
                                log.warning("cache copy failed: %s", exc)
                        else:
                            missing += 1
            carried = (carry_stack_runs(destination, src_project)
                       if copy_stack_runs else CarryResult(0, 0))
            yield MergeResult(str(src_path), added, dup, missing,
                              carried.copied, carried.lost)
        finally:
            src_project.close()


def _frame_without_id(frame: FrameRow) -> FrameRow:
    """Shallow copy without the id (destination assigns a new one)."""
    return FrameRow(
        source_path=frame.source_path,
        cached_path=None,  # we rewrite this after insert if we copy the cache
        aligned_cache_path=None,  # stage 2 not merged
        timestamp_utc=frame.timestamp_utc,
        exposure_s=frame.exposure_s,
        gain=frame.gain,
        sensor_temp_c=frame.sensor_temp_c,
        width_px=frame.width_px,
        height_px=frame.height_px,
        bayer_pattern=frame.bayer_pattern,
        # Telescope-target pointing hints (header-derived, not path-specific like
        # the deliberately-reset caches) — kept so a frame merged *before* it's
        # plate-solved still gets a localized ASTAP search around the mount's
        # pointing instead of a slow, failure-prone blind all-sky solve.
        ra_hint_deg=frame.ra_hint_deg,
        dec_hint_deg=frame.dec_hint_deg,
        wcs_json=frame.wcs_json,
        ra_center_deg=frame.ra_center_deg,
        dec_center_deg=frame.dec_center_deg,
        pixscale_arcsec=frame.pixscale_arcsec,
        rotation_deg=frame.rotation_deg,
        fwhm_px=frame.fwhm_px,
        star_count=frame.star_count,
        sky_adu_median=frame.sky_adu_median,
        eccentricity_median=frame.eccentricity_median,
        transparency_score=frame.transparency_score,
        streak_detected=frame.streak_detected,
        streak_count=frame.streak_count,
        mosaic_panel_id=frame.mosaic_panel_id,
        accept=frame.accept,
        reject_reason=frame.reject_reason,
        user_override=frame.user_override,
    )


# A ``project_meta`` key the web layer hangs off one stack-run id —
# ``editor_recipe:7``, ``calibration_warnings:7``, ``editor_auto_note:7``. The
# prefixes are owned by the modules that write them (``webapp.run_meta``
# collects the list), and this module cannot import those: the engine stays free
# of ``webapp`` imports (AGENTS.md §6). So the rule here is *shape*, not
# vocabulary — a trailing ``:<int>`` that names a run this project actually has —
# which also means a prefix added later travels with no change here.
# ``tests/webapp/test_merge_carries_pictures.py`` asserts every registered prefix
# matches it, so the two cannot drift apart.
_RUN_META_KEY = re.compile(r"^(?P<prefix>.+:)(?P<run_id>\d+)$")


def _per_run_meta(source: Project) -> dict[int, list[tuple[str, str]]]:
    """``{run_id: [(key_prefix, value), …]}`` for ``source``'s per-run annotations."""
    run_ids = {r.id for r in source.iter_stack_runs() if r.id is not None}
    out: dict[int, list[tuple[str, str]]] = {}
    for key, value in source.iter_meta():
        m = _RUN_META_KEY.match(key)
        if m is None:
            continue
        run_id = int(m.group("run_id"))
        if run_id in run_ids:
            out.setdefault(run_id, []).append((m.group("prefix"), value))
    return out


def _run_file_set(run: StackRunRow, project_dir: Path) -> tuple[Path, str]:
    """``(directory, basename)`` of the files ``run`` actually wrote.

    The basename is taken from the recorded ``fits_path``, not from
    ``output_basename``: a re-stack archives the previous set to
    ``{base}_{stamp}.*`` and repoints the row's three path columns
    (:meth:`~seestack.io.project.Project.repoint_stack_runs`) while leaving
    ``output_basename`` alone, so the column and the disk disagree for every run
    but the newest. This is the same rule
    :func:`webapp.routers.storage.delete_run_artifacts` resolves a run's whole
    file set by, so the set that travels and the set that would be deleted are
    one set.
    """
    from seestack.stack.output import OUTPUT_DIRNAME

    for recorded in (run.fits_path, run.tiff_path):
        if recorded:
            p = Path(recorded)
            return p.parent, (p.name[: -len(p.suffix)] if p.suffix else p.name)
    if run.preview_path:
        p = Path(run.preview_path)
        stem = p.name[: -len(p.suffix)] if p.suffix else p.name
        if stem.endswith("_preview"):
            stem = stem[: -len("_preview")]
        return p.parent, stem
    return Path(project_dir) / OUTPUT_DIRNAME, run.output_basename


def _free_basename(base: str, out_dir: Path, tag: str) -> str:
    """A basename in ``out_dir`` that no artefact of an existing run occupies.

    Two targets of the same object are usually two nights of the *same* Seestar
    folder convention, so their stacks are both ``master`` — copying one over the
    other would silently replace the destination's own picture with the source's.
    ``tag`` (the source target's folder name) is tried first because a merged
    history reads better as ``master_M_31_night_2`` than ``master_2``.
    """
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES

    def taken(candidate: str) -> bool:
        return any((out_dir / f"{candidate}{sfx}").exists()
                   for sfx in RUN_ARTEFACT_SUFFIXES.values())

    if not taken(base):
        return base
    tagged = f"{base}_{tag}" if tag else base
    if tagged != base and not taken(tagged):
        return tagged
    n = 2
    while taken(f"{tagged}_{n}"):
        n += 1
    return f"{tagged}_{n}"


@dataclass(frozen=True)
class CarryResult:
    """What :func:`carry_stack_runs` managed to move."""

    #: Pictures now in the destination.
    copied: int
    #: Pictures still only in the source, because something on the way failed.
    lost: int


def carry_stack_runs(destination: Project, source: Project) -> CarryResult:
    """Copy ``source``'s finished pictures into ``destination``.

    A stack run is a history row *plus* an output file set *plus* whatever the
    web layer annotated it with (the saved edit recipe first). All three travel,
    because the caller that asks for this —
    :meth:`seestack.io.library.Library.merge_targets` — deletes the source
    target's folder immediately afterwards, and its Library nudge promises the
    user that *"nothing is deleted"*.

    Oldest first, so the destination's new ids stay in the order the pictures
    were made. A run whose files are all gone from disk is **not** carried and is
    **not** counted as lost: there is no picture left to keep, and a row pointing
    at nothing is not something this merge should invent.

    Copies rather than moves, deliberately. A move would be faster and would not
    need room for both sets at once (a mosaic master is ~100 MB, its share render
    tens more), but it would gut a source project this function does not own —
    ``copy_stack_runs`` is a parameter, and only one caller happens to delete the
    source afterwards. The transient second copy is freed by that delete.

    A picture whose files cannot all be copied — a full disk, a permission error —
    is reported in :attr:`CarryResult.lost` rather than raising: the frames have
    already been merged by the time this runs, so aborting here would leave a
    half-done job. The caller decides, and
    :meth:`seestack.io.library.Library.merge_targets_result` decides by **not
    deleting that source folder**, which keeps the promise either way.
    """
    from seestack.stack.output import OUTPUT_DIRNAME, RUN_ARTEFACT_SUFFIXES

    runs = list(source.iter_stack_runs())
    if not runs:
        return CarryResult(0, 0)
    dst_out = Path(destination.project_dir) / OUTPUT_DIRNAME
    dst_out.mkdir(parents=True, exist_ok=True)
    meta = _per_run_meta(source)
    tag = Path(source.project_dir).name
    copied = 0
    lost = 0
    for run in reversed(runs):                      # iter_stack_runs is newest first
        src_dir, src_base = _run_file_set(run, Path(source.project_dir))
        new_base = _free_basename(src_base, dst_out, tag)
        landed: dict[str, Path] = {}
        present = 0
        for kind, suffix in RUN_ARTEFACT_SUFFIXES.items():
            src_file = src_dir / f"{src_base}{suffix}"
            if not src_file.is_file():
                continue
            present += 1
            dst_file = dst_out / f"{new_base}{suffix}"
            try:
                shutil.copy2(src_file, dst_file)
            except OSError as exc:
                log.warning("merge: could not carry %s: %s", src_file, exc)
                continue
            landed[kind] = dst_file
        if present and len(landed) < present:
            # Half a picture set is not a picture. Take the partial copies back
            # out rather than leaving files in the destination that no row names
            # and nothing will ever clean up.
            for stray in landed.values():
                with contextlib.suppress(OSError):
                    stray.unlink()
            log.warning("merge: run %s only partly carried (%d of %d files); "
                        "leaving it where it is", run.id, len(landed), present)
            lost += 1
            continue
        if not landed:
            log.info("merge: run %s has no files left on disk; not carried", run.id)
            continue
        new_id = destination.add_stack_run(replace(
            run,
            id=None,
            output_basename=new_base,
            fits_path=str(landed["fits"]) if "fits" in landed else None,
            tiff_path=str(landed["tiff"]) if "tiff" in landed else None,
            preview_path=str(landed["preview"]) if "preview" in landed else None,
        ))
        for prefix, value in meta.get(run.id if run.id is not None else -1, ()):
            destination.set_meta(f"{prefix}{new_id}", value)
        copied += 1
    return CarryResult(copied, lost)
