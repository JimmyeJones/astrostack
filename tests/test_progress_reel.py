"""The "watch your picture come together" progress reel (StackOptions.save_progress).

Slice (a): the stacker collects a bounded set of evenly-spaced autostretched
snapshots during pass 1 and assembles them into one small looping animation
beside the master — off by default (byte-for-byte unchanged output when off),
upgrade-safe, and best-effort (never fails the stack).
"""
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("photutils")
pytest.importorskip("PIL")
pytest.importorskip("tifffile")

from PIL import Image  # noqa: E402

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack import stacker as stk  # noqa: E402
from seestack.stack.stacker import (  # noqa: E402
    StackOptions,
    _PROGRESS_MAX_FRAMES,
    _QuickLook,
    assemble_progress_reel,
    plan_capture_nights,
    run_stack,
)
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def _build_project(tmp_path, n: int = 6, nights: list[str] | None = None) -> Project:
    """``nights``, when given, stamps frame *i* with ``nights[i]`` as its capture
    time — the only thing that lets the reel be read night by night."""
    proj = Project.create(tmp_path / "p", name="reeltest")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(n):
        path = write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, seed=10 + i, n_stars=30)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            timestamp_utc=(nights[i] if nights else None),
        ))
    return proj


def _stamps(*nights_and_counts: tuple[str, int]) -> list[str]:
    """``("2026-08-14", 2), ("2026-08-15", 1)`` → three evening stamps, in order."""
    out: list[str] = []
    for date, count in nights_and_counts:
        for i in range(count):
            out.append(f"{date}T22:{i:02d}:00Z")
    return out


def _reel_path(output_dir: Path, basename: str) -> Path | None:
    for suffix in ("_progress.webp", "_progress.png"):
        p = output_dir / f"{basename}{suffix}"
        if p.exists():
            return p
    return None


def test_save_progress_off_writes_no_reel(tmp_path):
    """Default (off): no reel file appears — output unchanged."""
    proj = _build_project(tmp_path, n=6)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     output_name="master"))
    finally:
        proj.close()
    out = proj.project_dir / "output"
    assert _reel_path(out, "master") is None


def test_save_progress_writes_an_animated_reel(tmp_path):
    """With save_progress on, a multi-frame looping animation lands beside the
    master and actually animates (>1 frame)."""
    proj = _build_project(tmp_path, n=6)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     save_progress=True, output_name="master"))
    finally:
        proj.close()
    out = proj.project_dir / "output"
    reel = _reel_path(out, "master")
    assert reel is not None and reel.exists()
    with Image.open(reel) as im:
        assert getattr(im, "is_animated", False)
        # 6 frames, interval max(1, 6//12)=1 → one snapshot per frame, ≥ the min.
        assert im.n_frames >= stk._PROGRESS_MIN_FRAMES


def test_reel_is_bounded_regardless_of_frame_count(tmp_path):
    """A large stack yields at most _PROGRESS_MAX_FRAMES snapshots (bounded)."""
    proj = _build_project(tmp_path, n=30)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     save_progress=True, output_name="master"))
    finally:
        proj.close()
    reel = _reel_path(proj.project_dir / "output", "master")
    assert reel is not None
    with Image.open(reel) as im:
        assert 1 < im.n_frames <= _PROGRESS_MAX_FRAMES


def test_restack_archives_the_previous_reel_as_a_sibling(tmp_path):
    """A re-stack keeps the previous run's reel resolvable next to its archived
    FITS (sibling pattern), and the fresh reel takes the canonical name."""
    proj = _build_project(tmp_path, n=6)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     save_progress=True, output_name="master"))
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     save_progress=True, output_name="master"))
    finally:
        proj.close()
    out = proj.project_dir / "output"
    # Canonical (newest) reel still present.
    assert _reel_path(out, "master") is not None
    # Exactly one archived reel sibling for the previous run.
    archived = list(out.glob("master_2*_progress.webp")) + \
        list(out.glob("master_2*_progress.png"))
    assert len(archived) == 1
    # Its FITS sibling exists too (same archived basename).
    fits_stem = archived[0].name.replace("_progress.webp", "").replace(
        "_progress.png", "")
    assert (out / f"{fits_stem}.fits").exists()


def test_reel_skipped_when_too_few_snapshots(tmp_path):
    """A tiny stack (< the min) produces no reel — nothing to 'watch'."""
    proj = _build_project(tmp_path, n=2)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     save_progress=True, output_name="master"))
    finally:
        proj.close()
    assert _reel_path(proj.project_dir / "output", "master") is None


def test_quicklook_and_progress_share_one_render(tmp_path):
    """The legacy quick-look and the reel co-exist (both cadences honoured)."""
    proj = _build_project(tmp_path, n=6)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     save_progress=True, quick_look_interval=2,
                                     output_name="master"))
    finally:
        proj.close()
    out = proj.project_dir / "output"
    assert (out / "master_quicklook.png").exists()
    assert _reel_path(out, "master") is not None


def test_assemble_progress_reel_returns_none_on_empty():
    assert assemble_progress_reel([], Path("/tmp"), "master") is None


def test_reel_never_fails_the_stack(tmp_path, monkeypatch):
    """A broken assembler is swallowed — the stack still completes and writes a
    master (a reel is a nicety, never critical)."""
    def boom(*a, **k):
        raise RuntimeError("no encoder")

    monkeypatch.setattr(stk, "assemble_progress_reel", boom)
    proj = _build_project(tmp_path, n=6)
    try:
        result = run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                              save_progress=True,
                                              output_name="master"))
    finally:
        proj.close()
    assert result.fits_path.exists()
    assert _reel_path(proj.project_dir / "output", "master") is None


def test_quicklook_sanitizes_traversal_basename(tmp_path):
    """save_progress with a path-traversal output_name never escapes output/."""
    ql = _QuickLook(tmp_path, "../../../etc/pwned", StackOptions(save_progress=True), 6)
    assert "/" not in ql.out_basename and ".." not in ql.out_basename


# --- slice (b): the reel lands on capture-night boundaries -------------------
# The owner's own request: "a progression video per target, ordered by when the
# subs were SHOT, so I can see how my added frames affect targets." The
# accumulator is already cumulative, so snapshotting it at each night boundary
# yields "night 1; nights 1-2; ..." for the price of one stack.


def _row(fid: int, ts: str | None) -> FrameRow:
    return FrameRow(id=fid, source_path=f"/x/{fid}.fit", timestamp_utc=ts)


def test_plan_capture_nights_gives_one_step_per_night():
    frames = [_row(i, t) for i, t in enumerate(
        _stamps(("2026-08-14", 2), ("2026-08-15", 3), ("2026-08-19", 1)))]
    plan = plan_capture_nights(frames)
    assert plan is not None
    assert plan.n_steps == 3
    assert [plan.chunk_of_frame[f.id] for f in frames] == [0, 0, 1, 1, 1, 2]
    # Every step is cumulative, so every caption starts at the first sub…
    assert plan.start_ts.startswith("2026-08-14")
    # …and ends on its own last night.
    assert [e[:10] for e in plan.end_ts] == [
        "2026-08-14", "2026-08-15", "2026-08-19"]


def test_plan_capture_nights_keeps_a_dusk_to_dawn_session_as_one_night():
    """A session running past midnight UTC is one observing night, not two —
    the same noon-to-noon rule the activity calendar buckets on."""
    frames = [
        _row(0, "2026-08-14T21:00:00Z"), _row(1, "2026-08-15T01:30:00Z"),
        _row(2, "2026-08-15T22:00:00Z"), _row(3, "2026-08-16T02:00:00Z"),
        _row(4, "2026-08-16T23:00:00Z"),
    ]
    plan = plan_capture_nights(frames)
    assert plan is not None
    assert plan.n_steps == 3
    assert [plan.chunk_of_frame[f.id] for f in frames] == [0, 0, 1, 1, 2]


def test_plan_capture_nights_declines_an_out_of_order_stack():
    """Lucky imaging re-orders the list by FWHM. A cumulative snapshot taken
    part-way through then is not "the nights so far", so there is no night reel
    to tell — the evenly-spaced one is the honest fallback."""
    stamps = _stamps(("2026-08-14", 2), ("2026-08-15", 2), ("2026-08-16", 2))
    shuffled = [stamps[0], stamps[4], stamps[1], stamps[2], stamps[5], stamps[3]]
    assert plan_capture_nights([_row(i, t) for i, t in enumerate(shuffled)]) is None


def test_plan_capture_nights_declines_without_capture_stamps():
    frames = [_row(0, "2026-08-14T22:00:00Z"), _row(1, None),
              _row(2, "2026-08-16T22:00:00Z"), _row(3, "2026-08-17T22:00:00Z")]
    assert plan_capture_nights(frames) is None


def test_plan_capture_nights_declines_fewer_than_three_nights():
    """One or two nights is not a progression; the reel stays the even one."""
    frames = [_row(i, t) for i, t in enumerate(
        _stamps(("2026-08-14", 3), ("2026-08-15", 3)))]
    assert plan_capture_nights(frames) is None


def test_plan_capture_nights_groups_consecutive_nights_past_the_cap():
    """A target with more nights than the reel has room for keeps the feature:
    consecutive nights are grouped, and the caption names the range."""
    frames = [_row(i, f"2026-08-{1 + i:02d}T22:00:00Z") for i in range(20)]
    plan = plan_capture_nights(frames, max_steps=4)
    assert plan is not None
    assert plan.n_steps == 4
    # Five nights each, in order, every frame placed, nothing out of sequence.
    steps = [plan.chunk_of_frame[f.id] for f in frames]
    assert steps == sorted(steps)
    assert steps.count(0) == steps.count(3) == 5
    assert [e[:10] for e in plan.end_ts] == [
        "2026-08-05", "2026-08-10", "2026-08-15", "2026-08-20"]


def test_the_reel_has_one_frame_per_capture_night(tmp_path):
    """End to end: six subs over three nights make a THREE-frame reel — one per
    night, cumulative — instead of the six evenly-spaced snapshots the
    frame-count rule produces for the same run."""
    proj = _build_project(tmp_path, n=6, nights=_stamps(
        ("2026-08-14", 2), ("2026-08-15", 3), ("2026-08-19", 1)))
    try:
        res = run_stack(proj, StackOptions(subpixel_refine=False,
                                           save_progress=True,
                                           output_name="master"))
    finally:
        proj.close()
    reel = _reel_path(res.output_dir, "master")
    assert reel is not None
    with Image.open(reel) as im:
        assert getattr(im, "n_frames", 1) == 3


def test_a_single_night_run_still_gets_the_evenly_spaced_reel(tmp_path):
    """The fallback is not a downgrade: one night of six subs still produces the
    clip it always did (one snapshot per frame at this size)."""
    proj = _build_project(tmp_path, n=6, nights=_stamps(("2026-08-14", 6)))
    try:
        res = run_stack(proj, StackOptions(subpixel_refine=False,
                                           save_progress=True,
                                           output_name="master"))
    finally:
        proj.close()
    reel = _reel_path(res.output_dir, "master")
    assert reel is not None
    with Image.open(reel) as im:
        assert getattr(im, "n_frames", 1) == 6
        # …and it is captioned too, with the plain depth rather than a date
        # range: a shared clip should say what it is whichever reel it is.
        im.seek(3)
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
        h, w = rgb.shape[:2]
        corner = rgb[int(h * 0.88):, : int(w * 0.35)]
        assert corner.min() < 90 and corner.max() > 180


def test_every_reel_frame_carries_its_caption(tmp_path):
    """A downloaded clip travels without the card around it, so each frame says
    what it is. Checked by pixels: the caption's dark backing strip sits in the
    bottom-left of every frame."""
    proj = _build_project(tmp_path, n=6, nights=_stamps(
        ("2026-08-14", 2), ("2026-08-15", 3), ("2026-08-19", 1)))
    try:
        res = run_stack(proj, StackOptions(subpixel_refine=False,
                                           save_progress=True,
                                           output_name="master"))
    finally:
        proj.close()
    reel = _reel_path(res.output_dir, "master")
    assert reel is not None
    with Image.open(reel) as im:
        n = getattr(im, "n_frames", 1)
        assert n == 3
        for i in range(n):
            im.seek(i)
            rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
            h, w = rgb.shape[:2]
            corner = rgb[int(h * 0.88):, : int(w * 0.35)]
            # A label draws a translucent black strip with white glyphs, so the
            # corner holds both very dark and very bright pixels.
            assert corner.min() < 90 and corner.max() > 180


def test_the_night_reel_survives_a_frame_that_cannot_be_stacked(tmp_path):
    """The boundary is "a sub from the next step arrived", not "one designated
    frame landed" — so losing the last sub of a night still closes that night."""
    proj = _build_project(tmp_path, n=6, nights=_stamps(
        ("2026-08-14", 2), ("2026-08-15", 3), ("2026-08-19", 1)))
    try:
        frames = list(proj.iter_frames())
        # The last sub of night 1 points at nothing, so its align fails.
        proj.update_frame(frames[1].id, cached_path="/nonexistent/gone.fit")
        proj.update_frame(frames[1].id, source_path="/nonexistent/gone.fit")
        res = run_stack(proj, StackOptions(subpixel_refine=False,
                                           save_progress=True,
                                           output_name="master"))
    finally:
        proj.close()
    assert res.n_frames_used == 5
    reel = _reel_path(res.output_dir, "master")
    assert reel is not None
    with Image.open(reel) as im:
        assert getattr(im, "n_frames", 1) == 3
