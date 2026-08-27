"""Gallery: every stacked image across all targets, with its stacking settings.

``GET /api/gallery`` returns one entry per stack run (newest first) — its
preview URL, basic stats, and the full set of :class:`StackOptions` that
produced it (parsed from the run's ``options_json``). The frontend renders this
as a browsable grid where each image can show exactly how it was stacked.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from seestack.stackhealth import seam_verdict
from webapp import deps

log = logging.getLogger(__name__)

router = APIRouter(tags=["gallery"])

# How many pictures the "best" wall returns at most. A generous cap so the
# frontend can show a full wall and slice a shorter Dashboard strip from the
# same response; the ranker returns fewer when the Library holds fewer targets.
BEST_PICTURES_MAX = 24
# The wall needs at least this many finished stacks to be worth showing — with
# one picture there's nothing to curate, so the endpoint self-hides (empty list).
BEST_PICTURES_MIN = 2


class GalleryItem(BaseModel):
    safe: str
    target_name: str
    run_id: int
    output_basename: str
    timestamp_utc: str
    n_frames_used: int
    canvas_w: int
    canvas_h: int
    # Effective integration time in seconds (None for pre-schema-4 runs).
    total_exposure_s: float | None
    # User label/notes for this run (e.g. "best RGB v2"), if set. Surfaced on the
    # card and matched by the Gallery search box alongside the target name.
    notes: str | None = None
    has_preview: bool
    has_fits: bool
    has_tiff: bool
    preview_url: str
    # Full StackOptions used for this run (parsed from options_json), so the UI
    # can display exactly how the image was produced. Empty dict if unparseable.
    options: dict[str, Any]
    # True when this run's settings can pre-fill the Stack form ("reuse settings").
    # False for editor-recipe / channel-combine runs, which carry no stack knobs.
    reusable: bool = False
    # Median transparency of the stacked frames ÷ the target's clear-sky baseline
    # (< ~0.6 ⇒ hazy). None for pre-schema-5 runs; drives a "hazy night" badge.
    transparency_ratio: float | None = None
    # Background-noise σ of the stacked image, normalized to its own signal range
    # (lower = cleaner). None for pre-schema-6 runs; drives a noise readout.
    noise_sigma: float | None = None
    # Which calibration masters were applied to the lights ("dark+flat", …), or
    # None when uncalibrated / pre-schema-7; drives a "dark+flat" chip.
    calstat: str | None = None
    # How flat this *mosaic's* panel joins came out, as a word: "flat" | "check",
    # or None when there's nothing honest to say (a single-field stack, a
    # pre-schema-15 run, or the ambiguous middle band). Same
    # `seestack.stackhealth.seam_verdict` call the run listing and the "How's my
    # stack?" notes use, so every surface reads one decision; drives the
    # "Panels even" / "Panels: check" chip on the Gallery and Compare cards.
    seam_verdict: str | None = None
    # True when the user saved an edit for this run in the editor but never
    # exported it, so the thumbnail here is still the plain auto-stretch of the
    # linear stack rather than the picture they made. Same
    # `webapp.routers.stack._unexported_edit` decision the Target hero and the
    # History card use — one definition, so the three surfaces can't drift.
    # Additive with a False default, which is what every ordinary run is.
    unexported_edit: bool = False


class VideoStillItem(BaseModel):
    """One finished Moon/Sun still, as the Gallery needs to show it.

    A video still is *not* a stack run — it has no target, no project DB, no
    stacking options and none of the per-run actions (edit, reuse settings, set
    as cover) apply — so it travels in its own list rather than being squeezed
    into :class:`GalleryItem`. Everything here is derived from the ``meta.json``
    the stack already wrote; the only action it carries is the framing crop,
    because the Gallery is where a user whose source video is long gone actually
    finds the picture.
    """

    capture_id: str
    #: "Moon" / "Sun" / the folder's base name — what the Moon & Sun page shows.
    label: str
    #: "lunar" | "solar" | "other".
    kind: str
    created_utc: str
    width: int
    height: int
    #: How many video frames were averaged into this picture.
    n_stacked: int
    #: The video file it came from, so a user with several clips can tell them apart.
    source_name: str
    preview_url: str
    #: The 16-bit TIFF of the same picture, when one is on disk — the full-quality
    #: copy to open in another app or send on. Additive and nullable: a still whose
    #: TIFF is missing (a half-written result) sends ``None`` and the surface simply
    #: doesn't offer it, and an older frontend ignores the field.
    tiff_url: str | None = None
    #: Framing, mirroring the same four fields on the Moon & Sun page's result so
    #: the two surfaces can offer the identical one-click crop. ``crop_applied``
    #: — this still was trimmed to the disk, so ``width``/``height`` are the
    #: cropped size and ``source_*`` the stack's own. ``crop_available`` — it
    #: wasn't, and there is enough empty sky around the subject to be worth
    #: trimming. ``crop_restorable`` — the full frame is still saved beside it,
    #: so the crop can be undone in a click. All additive with defaults that read
    #: as "not cropped, nothing to offer", which is what an older still was.
    crop_applied: bool = False
    crop_available: bool = False
    crop_trim_fraction: float = 0.0
    source_width: int = 0
    source_height: int = 0
    crop_restorable: bool = False
    #: How hard the finished picture was sharpened after stacking (0 = not at
    #: all), so the Gallery can explain the picture in the same words the Moon &
    #: Sun page does. Additive with a ``0.0`` default, which is exactly what
    #: every still made before sharpening existed was.
    sharpen_amount: float = 0.0
    #: Anything the stack wants the user to know about this picture — frames that
    #: couldn't be aligned, a truncated tail frame, and so on. The same
    #: ``meta.warnings`` list ``VideoResultOut`` carries, verbatim: these are
    #: engine strings, and one picture must read the same on both surfaces.
    #: Additive with an empty default, which is what a still with nothing to
    #: report has always been.
    warnings: list[str] = []
    #: Whether that strength can still be changed in place, i.e. without decoding
    #: the video again — false only for a picture whose *stack* sharpened it
    #: before the soft render was kept beside it. Same
    #: :func:`webapp.video.can_resharpen` call the Moon & Sun page's result uses,
    #: so neither surface can offer an edit the other knows would fail. Additive
    #: with a ``False`` default, which simply offers nothing.
    sharpen_editable: bool = False


class GalleryResponse(BaseModel):
    items: list[GalleryItem]
    #: Finished Moon/Sun stills, newest first. Additive: an older frontend
    #: ignores the field, and an install that has never stacked a video sends an
    #: empty list.
    videos: list[VideoStillItem] = []


def _parse_options(options_json: str | None) -> dict[str, Any]:
    if not options_json:
        return {}
    try:
        parsed = json.loads(options_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_reusable(options: dict[str, Any]) -> bool:
    """A run's settings can pre-fill the Stack form unless it's an editor-recipe
    or channel-combine run (those carry no stack knobs)."""
    return "editor_recipe" not in options and "channel_combine" not in options


@router.get("/api/gallery", response_model=GalleryResponse)
def get_gallery(request: Request) -> GalleryResponse:
    items: list[GalleryItem] = []
    lib = deps.open_library(request)
    try:
        from seestack.io.project import Project
        from webapp.routers.editor import (
            EXPORTED_RECIPE_META_PREFIX,
            RECIPE_META_PREFIX,
        )
        from webapp.routers.stack import _unexported_edit

        for t in lib.list_targets():
            proj = None
            try:
                proj = Project.open(lib.target_dir(t))
                runs = list(proj.iter_stack_runs())
            except Exception:  # noqa: BLE001 — a broken project must not 500 the gallery
                # One unreadable/corrupt project DB — or one stamped with a newer
                # schema after an image rollback (Project.open raises RuntimeError)
                # — must not hide *every* target's images. Skip it, like
                # stats.py / storage.py already do for the same call.
                if proj is not None:
                    proj.close()
                continue
            try:
                for run in runs:
                    try:
                        items.append(_gallery_item(
                            t, run, proj, RECIPE_META_PREFIX,
                            EXPORTED_RECIPE_META_PREFIX, _unexported_edit,
                        ))
                    except Exception:  # noqa: BLE001 — one bad run must not hide the rest
                        # Every required field is NOT NULL today, so nothing here
                        # is known to raise — but a future field (or one odd row
                        # on an in-place-upgraded install) must cost the owner
                        # one picture, not the whole page. Same degrade-don't-500
                        # rule the per-target skip above and stats.py already use.
                        log.debug(
                            "gallery item for %s run %s unreadable; skipping",
                            t.safe_name, run.id, exc_info=True,
                        )
                        continue
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()

    # Newest first across all targets.
    items.sort(key=lambda it: it.timestamp_utc, reverse=True)
    return GalleryResponse(items=items, videos=_video_stills(request))


def _gallery_item(t, run, proj, recipe_prefix: str, exported_prefix: str,
                  unexported_edit) -> GalleryItem:  # noqa: ANN001
    """One finished stack's gallery card. Split out so the loop above can skip a
    single unreadable run without losing every other target's pictures."""
    has_preview = bool(run.preview_path and Path(run.preview_path).exists())
    options = _parse_options(run.options_json)
    return GalleryItem(
        safe=t.safe_name,
        target_name=t.name,
        run_id=run.id,
        output_basename=run.output_basename,
        timestamp_utc=run.timestamp_utc,
        n_frames_used=run.n_frames_used,
        canvas_w=run.canvas_w,
        canvas_h=run.canvas_h,
        total_exposure_s=run.total_exposure_s,
        notes=run.notes,
        has_preview=has_preview,
        has_fits=bool(run.fits_path and Path(run.fits_path).exists()),
        has_tiff=bool(run.tiff_path and Path(run.tiff_path).exists()),
        preview_url=(
            f"/api/targets/{t.safe_name}/stack-runs/{run.id}/preview"
        ),
        options=options,
        reusable=_is_reusable(options),
        transparency_ratio=run.transparency_ratio,
        noise_sigma=run.noise_sigma,
        calstat=run.calstat,
        seam_verdict=seam_verdict(run.seam_residual),
        # Two extra keyed reads on the project DB the caller already has open —
        # the same near-free lookups the run listing does, which is what made
        # this affordable library-wide.
        unexported_edit=unexported_edit(
            run.options_json,
            proj.get_meta(f"{recipe_prefix}{run.id}"),
            proj.get_meta(f"{exported_prefix}{run.id}"),
        ),
    )


def _video_stills(request: Request) -> list[VideoStillItem]:
    """Finished Moon/Sun stills, newest first.

    Folded in here because the Gallery is where *every other* finished picture
    lives: before this, a beginner who stacked their first Moon picture went
    looking for it alongside their deep-sky stacks and found nothing. It is an
    extra source that never touches the Library, and one that must never break
    the gallery if it fails.

    The framing is backfilled per still exactly as the Moon & Sun page does it
    (:func:`webapp.video.ensure_framing_measured` — measured once, then written
    back), so a picture made before framing existed gets the crop offer here too
    instead of reading as "nothing to trim" because nobody ever looked.
    """
    from webapp import video

    settings = deps.get_settings(request)
    try:
        metas = video.iter_results(settings)
    except Exception:  # noqa: BLE001 — a video-store problem must not 500 the gallery
        return []
    items: list[VideoStillItem] = []
    for m in metas:
        try:
            meta = video.ensure_framing_measured(settings, m.capture_id, m)
            restorable = video.crop_is_restorable(settings, m.capture_id, meta)
            has_tiff = video.has_tiff(settings, m.capture_id)
        except Exception:  # noqa: BLE001 — one unreadable still must not hide the rest
            meta, restorable, has_tiff = m, False, False
        try:
            items.append(VideoStillItem(
                capture_id=meta.capture_id,
                label=meta.label,
                kind=meta.kind,
                created_utc=meta.created_utc,
                width=meta.width,
                height=meta.height,
                n_stacked=meta.n_stacked,
                source_name=meta.source_name,
                preview_url=f"/api/videos/{meta.capture_id}/preview.png",
                tiff_url=(
                    f"/api/videos/{meta.capture_id}/download.tiff" if has_tiff else None
                ),
                crop_applied=meta.crop_applied,
                crop_available=meta.crop_available,
                crop_trim_fraction=meta.crop_trim_fraction,
                source_width=meta.source_width,
                source_height=meta.source_height,
                crop_restorable=restorable,
                warnings=list(meta.warnings),
                sharpen_amount=meta.sharpen_amount,
                sharpen_editable=video.can_resharpen(meta),
            ))
        except Exception:  # noqa: BLE001 — one bad meta.json must not 500 the gallery
            # A ``meta.json`` can be JSON-valid but wrong-*typed* (hand-edited, or
            # written by a foreign/older version on an in-place-upgraded install):
            # the plain dataclass accepts it, the Pydantic model rejects it. Skip
            # that one still rather than losing every picture on the page.
            log.debug(
                "video still %s has unusable metadata; skipping", m.capture_id,
                exc_info=True,
            )
            continue
    return items


class BestPicture(BaseModel):
    """One entry on the auto-curated *My best pictures* wall — the fields the wall
    (and its lightbox/share/download) need, plus the ranking ``score`` (0–1) so the
    UI can show a transparent "why it's here" line."""

    safe: str
    target_name: str
    run_id: int
    output_basename: str
    timestamp_utc: str
    n_frames_used: int
    canvas_w: int
    canvas_h: int
    total_exposure_s: float | None
    noise_sigma: float | None
    has_preview: bool
    has_fits: bool
    has_tiff: bool
    preview_url: str
    # Quality-blend score in [0, 1], relative to this Library's own collection.
    score: float
    # True when this picture is the one the user pinned as its target's cover
    # ("Set as cover" in History). A pinned picture represents its target here
    # instead of the newest stack, and is floated above the ranked tail so the
    # automatic ranking can never hide the favourite. False for an ordinary
    # auto-picked entry (and ignored outright by an older frontend).
    pinned: bool = False


class BestPicturesResponse(BaseModel):
    items: list[BestPicture]


def _run_has_preview(run: Any) -> bool:
    """Whether a run has a rendered preview still on disk (a *finished picture*)."""
    return bool(run.preview_path and Path(run.preview_path).exists())


def _representative_run(runs: list[Any], cover_run_id: int | None) -> tuple[Any, bool]:
    """The one picture that represents a target on the wall, plus whether the
    user **pinned** it.

    Precedence mirrors ``targets._cover_preview_path`` (what the Library /
    Dashboard tile already does): the target's pinned cover run wins when it's set
    *and* still has a preview on disk; otherwise the newest run with a preview,
    exactly as before. So a cover that was pruned, or whose preview file has gone,
    degrades silently to the newest picture rather than dropping the target off
    the wall entirely.

    ``runs`` is the project's runs newest-first (``Project.iter_stack_runs``).
    Returns ``(None, False)`` when the target has no finished picture at all.
    Split out so the precedence is unit-testable on plain records."""
    if cover_run_id is not None:
        cover = next(
            (r for r in runs if r.id == cover_run_id and _run_has_preview(r)), None)
        if cover is not None:
            return cover, True
    return next((r for r in runs if _run_has_preview(r)), None), False


def _collect_best_pictures(
    request: Request, limit: int,
) -> list[tuple[BestPicture, str]]:
    """The ranked wall, each entry paired with its preview file's path on disk.

    Split out of :func:`get_best_pictures` so the bulk `.zip` download can archive
    **exactly** the pictures the wall shows, from one definition of "this target's
    picture" — the path never leaves the server (the JSON response drops it).
    """
    from seestack.io.project import Project
    from seestack.portfolio import PortfolioEntry, rank_portfolio

    # One representative per target (pinned cover, else newest with a rendered
    # preview on disk), keyed so the ranker's result maps straight back to the
    # full record.
    by_key: dict[str, BestPicture] = {}
    paths: dict[str, str] = {}
    entries: list[PortfolioEntry] = []

    lib = deps.open_library(request)
    try:
        for t in lib.list_targets():
            proj = None
            try:
                proj = Project.open(lib.target_dir(t))
                runs = list(proj.iter_stack_runs())
            except Exception:  # noqa: BLE001 — one broken project must not 500 the wall
                # Same guard the gallery/stats/storage cross-target reads use: a
                # corrupt or newer-schema (rolled-back) project DB is skipped, not
                # allowed to hide every other target's best picture.
                if proj is not None:
                    proj.close()
                continue
            try:
                # runs are newest-first; the user's pinned cover wins over them.
                pick, pinned = _representative_run(runs, t.cover_stack_run_id)
                if pick is None:
                    continue
                key = f"{t.safe_name}:{pick.id}"
                by_key[key] = BestPicture(
                    safe=t.safe_name,
                    target_name=t.name,
                    run_id=pick.id,
                    output_basename=pick.output_basename,
                    timestamp_utc=pick.timestamp_utc,
                    n_frames_used=pick.n_frames_used,
                    canvas_w=pick.canvas_w,
                    canvas_h=pick.canvas_h,
                    total_exposure_s=pick.total_exposure_s,
                    noise_sigma=pick.noise_sigma,
                    has_preview=True,
                    has_fits=bool(pick.fits_path and Path(pick.fits_path).exists()),
                    has_tiff=bool(pick.tiff_path and Path(pick.tiff_path).exists()),
                    preview_url=(
                        f"/api/targets/{t.safe_name}/stack-runs/{pick.id}/preview"
                    ),
                    score=0.0,  # filled in from the ranking below
                    pinned=pinned,
                )
                paths[key] = str(pick.preview_path)
                entries.append(PortfolioEntry(
                    key=key,
                    n_frames_used=pick.n_frames_used,
                    total_exposure_s=pick.total_exposure_s,
                    noise_sigma=pick.noise_sigma,
                    coverage_max=pick.coverage_max,
                    pinned=pinned,
                ))
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()

    # Not enough finished pictures to curate → self-hide.
    if len(by_key) < BEST_PICTURES_MIN:
        return []

    ranked = rank_portfolio(entries, limit=limit)
    return [
        (by_key[r.key].model_copy(update={"score": r.score}), paths[r.key])
        for r in ranked
    ]


@router.get("/api/gallery/best", response_model=BestPicturesResponse)
def get_best_pictures(
    request: Request,
    limit: int = Query(BEST_PICTURES_MAX, ge=1, le=BEST_PICTURES_MAX),
) -> BestPicturesResponse:
    """Auto-curated cross-target portfolio: one *finished* stack per target,
    ranked best-first by the transparent quality blend
    (:func:`seestack.portfolio.rank_portfolio`). Read-only aggregation over the
    Library — no schema/state change. Self-hides (empty list) until at least
    :data:`BEST_PICTURES_MIN` targets have a finished picture, so a brand-new
    install shows nothing rather than a wall of one.

    A target's representative is the run the user **pinned as its cover** ("Set as
    cover" in History) when there is one and its preview still exists, otherwise
    its newest run with a preview — the same precedence the Library/Dashboard tile
    already uses, so the picture someone chose to represent a target represents it
    on this wall too instead of being silently replaced by the newest stack. A
    pinned entry is also floated above the ranked tail, so the automatic ranking
    can never drop the one picture they said was their favourite."""
    return BestPicturesResponse(
        items=[pic for pic, _ in _collect_best_pictures(request, limit)])


# Characters an archive member name may keep. Everything else becomes "_", so a
# target called "M 42 / Orion" can't write outside the folder it's unzipped into,
# on any operating system.
_ZIP_NAME_OK = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,-_()+'")


def zip_entry_name(target_name: str, suffix: str, taken: set[str]) -> str:
    """A friendly, safe, unique archive member name for one target's picture.

    Named for the *target*, not the run — an archive of "M 42.png, NGC 7000.png"
    is the one a beginner can drop straight into a phone album, where
    "M_42_20260814_213355.png" is not. Kept ASCII-safe and separator-free so
    unzipping can never write outside the destination folder, and de-duplicated
    (``… (2)``) so two targets that sanitise to the same name can't have one
    silently overwrite the other. ``taken`` is updated in place.
    """
    cleaned = "".join(c if c in _ZIP_NAME_OK else "_" for c in target_name).strip()
    # A name that is only dots (or empty) is not a filename on any platform.
    base = cleaned.strip(".") or "picture"
    name = f"{base}{suffix}"
    n = 2
    while name.lower() in taken:
        name = f"{base} ({n}){suffix}"
        n += 1
    taken.add(name.lower())
    return name


class _ZipSink:
    """A write-only file object :mod:`zipfile` can stream into.

    ``ZipFile`` supports an unseekable output stream (it falls back to data
    descriptors), so the archive can be handed out chunk by chunk instead of
    being built in memory or spooled to disk first — which matters here because
    the members are full-resolution previews and a library can hold dozens.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def write(self, data) -> int:
        self._buf += data
        return len(data)

    def flush(self) -> None:  # pragma: no cover — required by the file protocol
        pass

    def drain(self) -> bytes:
        out = bytes(self._buf)
        del self._buf[:]
        return out


def _stream_pictures_zip(members: list[tuple[str, str]]):
    """Yield a ``.zip`` of ``(archive name, source path)`` pairs, one chunk at a
    time — never more than one read buffer plus the zip's own bookkeeping in
    memory.

    Stored, not deflated: every member is an already-compressed PNG, so
    compressing again costs CPU on a NAS for no size win. A picture that can't be
    read is skipped and named in a trailing ``_skipped.txt`` rather than sinking
    the whole archive — the same boundary the gallery draws around one bad
    preview.
    """
    import zipfile

    chunk = 1 << 18
    skipped: list[str] = []
    sink = _ZipSink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED) as zf:
        for name, path in members:
            try:
                src = open(path, "rb")  # noqa: SIM115 — closed in the finally below
            except OSError:
                skipped.append(f"{name} — the picture file could not be opened")
                continue
            try:
                with zf.open(name, "w") as dst:
                    while True:
                        try:
                            data = src.read(chunk)
                        except OSError:
                            skipped.append(f"{name} — only partly readable")
                            break
                        if not data:
                            break
                        dst.write(data)
                        yield sink.drain()
            finally:
                src.close()
            yield sink.drain()
        if skipped:
            zf.writestr("_skipped.txt", (
                "These pictures couldn't be read when this archive was made, so "
                "they aren't in it:\n\n" + "\n".join(skipped) + "\n"))
            yield sink.drain()
    yield sink.drain()


@router.get("/api/gallery/best.zip")
def download_best_pictures_zip(
    request: Request,
    limit: int = Query(BEST_PICTURES_MAX, ge=1, le=BEST_PICTURES_MAX),
):
    """Download **every** finished picture in the library as one ``.zip``.

    The app could already show the whole collection (the best-pictures wall) and
    post it as one image (the montage), but the only way to actually *get* the
    pictures was one target at a time — so backing a season's work up to a hard
    drive, or dropping it all into a phone album, meant visiting twenty targets
    and pressing download twenty times. Bulk *upload* has existed since v0.229.0;
    this is the symmetric bulk download.

    Exactly the wall's contents, from the same enumeration: one picture per
    target (the pinned cover when there is one, else the newest finished stack),
    ranked, capped at :data:`BEST_PICTURES_MAX`. Each member is the stored
    display-space preview PNG — what you saw is what you get, with no re-render
    and no editor recompute — named after its target.

    Read-only: it opens existing result files and streams bytes out. Nothing is
    written to the library, and ``incoming/`` is never touched. 404s (rather than
    serving an archive of one) on a library too young for the wall, so the offer
    self-hides exactly when the wall does.
    """
    from fastapi.responses import StreamingResponse

    picks = _collect_best_pictures(request, limit)
    if not picks:
        raise HTTPException(
            status_code=404,
            detail="You need finished pictures of at least two targets to download.")

    taken: set[str] = set()
    members = [
        (zip_entry_name(pic.target_name, Path(path).suffix or ".png", taken), path)
        for pic, path in picks
    ]
    return StreamingResponse(
        _stream_pictures_zip(members),
        media_type="application/zip",
        headers={
            "Content-Disposition":
                'attachment; filename="my-astrostack-pictures.zip"',
        },
    )


class UnexportedEditItem(BaseModel):
    safe: str
    target_name: str
    run_id: int
    timestamp_utc: str


class UnexportedEditsResponse(BaseModel):
    #: How many pictures across the whole Library carry a saved-but-never-exported
    #: edit. Never capped — this is the number the note says out loud.
    count: int
    #: The newest few of them, so a note can link straight at one instead of
    #: sending the user hunting. Capped at :data:`UNEXPORTED_EDITS_MAX`.
    items: list[UnexportedEditItem] = []


# How many un-exported edits the response names. The count is exact; this only
# bounds the list, which exists so a single one can be linked directly.
UNEXPORTED_EDITS_MAX = 12


def _scan_unexported_edits(lib) -> list[UnexportedEditItem]:
    """Every saved-but-never-exported edit in the Library, newest first.

    One definition, two callers: the note's count reads it, and "finish them all"
    exports exactly what it returns — so the button can never act on a different
    list from the one the sentence above it described.

    **This is the cheap path, and that is the whole design.** Per target it reads
    the ``project_meta`` rows whose key starts with the editor-recipe prefix
    (:meth:`Project.iter_meta_prefix`) and stops there when there are none — which
    is every target that has never been edited. Only when a target *does* carry
    recipes does it take a second prefix scan for the already-exported markers and
    look up those specific runs' two columns (:meth:`Project.stack_run_options`);
    no run listing, no file stats, no preview checks. A broken project DB is
    skipped exactly as the other cross-target reads skip it, so one corrupt target
    can't cost the whole answer.
    """
    from seestack.io.project import Project
    from webapp.routers.editor import EXPORTED_RECIPE_META_PREFIX, RECIPE_META_PREFIX
    from webapp.routers.stack import _unexported_edit

    def _by_run_id(proj: Project, prefix: str) -> dict[int, str]:
        """``{run_id: value}`` for one per-run meta prefix, in one prefix scan."""
        out: dict[int, str] = {}
        for key, value in proj.iter_meta_prefix(prefix):
            try:
                out[int(key[len(prefix):])] = value
            except ValueError:  # a meta key we don't own — ignore it
                continue
        return out

    found: list[UnexportedEditItem] = []
    for t in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            # The common case: this target has never been edited, so the one
            # prefix scan comes back empty and nothing else is read from its
            # DB at all — neither the already-exported markers nor any run.
            recipes = _by_run_id(proj, RECIPE_META_PREFIX)
            exported = (
                _by_run_id(proj, EXPORTED_RECIPE_META_PREFIX) if recipes else {}
            )
            summaries = (
                proj.stack_run_options(recipes) if recipes else {}
            )
        except Exception:  # noqa: BLE001 — one broken project must not 500 the count
            continue
        finally:
            if proj is not None:
                proj.close()
        for run_id, (timestamp_utc, options_json) in summaries.items():
            if _unexported_edit(options_json, recipes.get(run_id),
                                exported.get(run_id)):
                found.append(UnexportedEditItem(
                    safe=t.safe_name,
                    target_name=t.name,
                    run_id=run_id,
                    timestamp_utc=timestamp_utc,
                ))
    found.sort(key=lambda it: it.timestamp_utc, reverse=True)
    return found


@router.get("/api/gallery/unexported-edits", response_model=UnexportedEditsResponse)
def get_unexported_edits(request: Request) -> UnexportedEditsResponse:
    """How many pictures in the whole Library carry an edit the user saved and
    never exported (see :func:`webapp.routers.stack._unexported_edit`).

    Why its own endpoint rather than a field on something existing: the three
    surfaces that admit "this thumbnail isn't your version" all need you to be
    *looking at that picture* already, so someone who dialled in a look, pressed
    Save and moved on never finds out. Answering it library-wide needs a
    cross-target read — but ``/api/gallery`` lists every run of every target, and
    ``/api/stats`` is polled every 10 s, so neither is an honest place to put it.

    The scan itself, and why it is affordable, is in
    :func:`_scan_unexported_edits`.
    """
    lib = deps.open_library(request)
    try:
        found = _scan_unexported_edits(lib)
    finally:
        lib.close()
    return UnexportedEditsResponse(count=len(found), items=found[:UNEXPORTED_EDITS_MAX])


@router.post("/api/gallery/unexported-edits/export")
def export_unexported_edits(request: Request) -> dict:
    """Finish **every** edit the user saved and never exported, in one job.

    The note above this button names up to three pictures and links each into the
    editor, which is the right shape for one or two. Someone who edits across
    several nights and never exports accumulates a dozen, and clicking through a
    dozen editors to press Export a dozen times is exactly the manual chain this
    app exists to remove — every input is already stored, because the saved recipe
    *is* the instruction, so the app can do it unattended.

    **It exports what the note counted, and nothing else:** the list comes from
    :func:`_scan_unexported_edits`, the same function the count reads, so the
    button can't act on a different set from the sentence describing it. A run
    whose edit was already exported is not in that list — the marker
    (``editor_exported:<id>``) is what makes this feature possible at all, since
    without it the job would re-export the same pictures every time it ran.

    **Nothing is overwritten.** Each item goes through the one export path
    (``pipeline._apply_editor_to_run``), which writes a *new* stack run beside the
    original and leaves the source untouched — so the worst case of pressing this
    twice is duplicate pictures, never a lost one. It is a single job on the
    normal single-worker queue: cancellable from the Jobs page, reporting progress
    per picture, and skipping-with-a-reason rather than aborting the batch when
    one run's source FITS has gone missing.
    """
    from webapp import pipeline

    lib = deps.open_library(request)
    try:
        found = _scan_unexported_edits(lib)
    finally:
        lib.close()
    if not found:
        raise HTTPException(
            status_code=400,
            detail="There are no saved edits waiting to be exported.")

    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    job = pipeline.submit_editor_batch(
        settings, jm,
        [{"safe": it.safe, "run_id": it.run_id} for it in found],
        # None = give every picture its own saved recipe, rather than one shared
        # look. This is the whole difference from "apply this look to N pictures".
        recipe_dict=None,
    )
    return {"job_id": job.id, "count": len(found)}


# How many pictures the montage puts on the wall by default, and the ceiling a
# caller may raise it to. Mirrors the engine's own caps so the query parameter
# can't ask for a contact sheet of thumbnails.
MONTAGE_DEFAULT_TILES = 9
MONTAGE_MAX_TILES = 16


def _montage_tiles(request: Request, limit: int) -> tuple[list, float]:
    """``(tiles, integration_s)`` for the wall — the integration of the pictures
    actually on it, not the library's total.

    One picture per **target** — the library's own exposure-ranked heroes, which
    is already "targets whose finished preview still exists on disk" — so the
    wall answers *"what have I captured?"* rather than showing one busy target
    five times. Best-effort per tile: a preview that has since been deleted or
    can't be decoded is dropped and the next hero takes its place, exactly like
    the recap poster's backdrop search.

    A target's picture is the run the user **pinned as its cover** ("Set as
    cover" in History) when there is one and its preview still exists, otherwise
    its newest stack's preview — the same precedence the Library tile,
    ``/api/gallery/best`` and ``/api/imaging-log`` already use. Without it a
    target whose newest run is a linear master or a quick restack put *that* on
    the wall instead of the finished picture its owner chose, which is the one
    thing the wall exists to show. Resolving a cover costs one project open, so
    it happens only for the targets that actually have one pinned; that trade is
    fine on a deliberate one-tap download (it is the same one ``/api/imaging-log``
    makes) and would not be on a page render.
    """
    from PIL import Image

    from seestack.library_summary import summarize_library
    from seestack.montage import MontageTile, montage_caption

    # Package-private helper, shared rather than re-implemented so the wall can
    # never disagree with the Library tile about which picture is a target's.
    from webapp.routers.targets import _cover_preview_path

    lib = deps.open_library(request)
    try:
        targets = list(lib.list_targets())
        summary = summarize_library(
            targets, preview_exists=lambda p: bool(p) and Path(p).exists())
        by_safe = {t.safe_name: t for t in targets}
        tiles: list[MontageTile] = []
        shown_s = 0.0
        for hero in summary.heroes:
            if len(tiles) >= limit:
                break
            entry = by_safe.get(hero.safe)
            cover = _cover_preview_path(lib, entry) if entry is not None else None
            path = cover if cover is not None else (
                getattr(entry, "last_stack_preview", None) if entry else None)
            if not path:
                continue
            try:
                with Image.open(path) as img:
                    loaded = img.convert("RGB")
            except Exception:  # noqa: BLE001 — a bad preview must not sink the wall
                continue
            tiles.append(MontageTile(
                image=loaded,
                caption=montage_caption(hero.name, hero.total_exposure_s)))
            shown_s += float(hero.total_exposure_s or 0.0)
    finally:
        lib.close()
    return tiles, shown_s


@router.get("/api/gallery/montage.jpg")
def get_gallery_montage(request: Request, limit: int = MONTAGE_DEFAULT_TILES):
    """Download "My deep-sky wall" — the library's best pictures as one JPEG.

    The gallery can only ever show one picture at a time, so there is no single
    image that says *"look at everything I've captured"* — which is the thing a
    beginner actually posts after a good run of clear nights. This renders it on
    demand from the previews the app already keeps: nothing is written to the
    library, exactly like the recap poster (``/api/recap.jpg``).

    404s (rather than serving a one-picture "wall") when fewer than two targets
    have a readable finished picture, so the offer can self-hide on a young
    library.
    """
    import io

    from fastapi.responses import Response

    from seestack.montage import build_montage, montage_title

    limit = max(2, min(int(limit), MONTAGE_MAX_TILES))
    tiles, shown_s = _montage_tiles(request, limit)
    image = build_montage(
        tiles, title=montage_title(len(tiles), shown_s), max_tiles=limit)
    if image is None:
        raise HTTPException(
            status_code=404,
            detail="You need finished pictures of at least two targets to make a wall.")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=92)
    return Response(
        content=buf.getvalue(),
        media_type="image/jpeg",
        headers={"Content-Disposition": 'attachment; filename="my-deep-sky-wall.jpg"'},
    )
