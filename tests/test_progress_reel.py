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
    run_stack,
)
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def _build_project(tmp_path, n: int = 6) -> Project:
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
        ))
    return proj


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
