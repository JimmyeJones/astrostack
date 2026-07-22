"""The cross-run "night after night" deepening reel (engine side).

Covers the fair-comparison contract that makes the reel honest: every frame is
tone-mapped with one shared stretch (so only the noise/detail changes, never the
brightness), frames are unified to the deepest frame's size, and the whole thing
degrades gracefully below two usable stacks.
"""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from seestack.render.deepening import (
    _apply_stf_params,
    _solve_stf_params,
    build_deepening_reel,
    deepening_frame_label,
    render_deepening_frames,
)
from seestack.render.thumbnail import autostretch


def _same_target_scene(h: int, w: int, *, noise: float, seed: int,
                       glow: float = 0.15) -> np.ndarray:
    """A 3-channel (C, H, W) linear stack of one target: identical sky level and
    extended glow, only the per-pixel noise differs — exactly the "same object,
    deeper each night" case the reel exists to show."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    signal = 0.10 + glow * np.exp(-(((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / (0.15 * h * w)))
    chan = (signal + noise * rng.standard_normal((h, w))).astype(np.float32)
    chan[int(h / 2) - 2:int(h / 2) + 2, int(w / 2) - 2:int(w / 2) + 2] = 0.9  # bright core
    return np.stack([chan, chan * 0.7, chan * 0.5]).astype(np.float32)


def _write_cube(path, cube) -> str:
    fits.PrimaryHDU(data=cube).writeto(path, overwrite=True)
    return str(path)


def test_solved_params_reproduce_autostretch_exactly():
    # The solve/apply split must mirror thumbnail.autostretch's maths precisely,
    # so a single frame stretched via the shared params is byte-for-byte what the
    # normal autostretch would have produced. This pins the "common stretch" to
    # the real render and flags any future autostretch drift.
    cube = _same_target_scene(48, 48, noise=0.02, seed=1)
    rgb = np.transpose(cube, (1, 2, 0))
    params = _solve_stf_params(rgb)
    assert params is not None
    replayed = _apply_stf_params(rgb, params)
    reference = autostretch(rgb)
    assert np.allclose(replayed, reference, atol=1e-6)


def test_reel_shares_one_stretch_across_depths(tmp_path):
    # Two stacks of the SAME target — same sky, same glow — one noisy (shallow),
    # one clean (deep, listed last). Under the shared stretch anchored to the
    # deepest frame, the sky renders at the same brightness in both (no flicker),
    # while the deep frame's sky is visibly less noisy (the whole point).
    shallow = _write_cube(tmp_path / "a.fits", _same_target_scene(64, 64, noise=0.05, seed=2))
    deep = _write_cube(tmp_path / "b.fits", _same_target_scene(64, 64, noise=0.008, seed=3))

    frames = render_deepening_frames([shallow, deep], max_width=64)
    assert len(frames) == 2
    assert frames[0].size == frames[1].size

    a = np.asarray(frames[0]).astype(np.float32)
    b = np.asarray(frames[1]).astype(np.float32)
    # A corner sky patch (away from the central glow/core).
    sa, sb = a[:16, :16], b[:16, :16]
    # Same black point → same mean brightness (no jump between frames).
    assert abs(sa.mean() - sb.mean()) < 12.0  # out of 255
    # Deeper stack = quieter sky.
    assert sb.std() < sa.std()


def test_display_space_frame_rendered_verbatim(tmp_path):
    # An editor-export (display-space) run is already tone-mapped [0,1]; it must
    # be shown as written, not stretched a second time.
    from seestack.stack.output import DISPLAY_SPACE_CARD

    lin = _write_cube(tmp_path / "lin.fits", _same_target_scene(48, 48, noise=0.01, seed=4))
    # A flat mid-grey display-space export.
    disp_cube = np.full((3, 48, 48), 0.5, dtype=np.float32)
    hdu = fits.PrimaryHDU(data=disp_cube)
    hdu.header[DISPLAY_SPACE_CARD] = True
    dpath = tmp_path / "disp.fits"
    hdu.writeto(dpath, overwrite=True)

    frames = render_deepening_frames([lin, str(dpath)], max_width=48)
    assert len(frames) == 2
    verbatim = np.asarray(frames[1]).astype(np.float32)
    # 0.5 * 255 ≈ 127.5, shown verbatim (a real stretch would move it far off).
    assert abs(verbatim.mean() - 127.5) < 2.0


def test_frames_unified_to_deepest_size(tmp_path):
    # The canvas can grow across nights (more area covered); frames are unified to
    # the last (deepest) frame's size so the encoder gets a uniform series.
    small = _write_cube(tmp_path / "s.fits", _same_target_scene(40, 40, noise=0.03, seed=5))
    big = _write_cube(tmp_path / "g.fits", _same_target_scene(64, 64, noise=0.01, seed=6))
    frames = render_deepening_frames([small, big], max_width=128)
    assert len({f.size for f in frames}) == 1
    assert frames[0].size == frames[-1].size


def test_reel_needs_two_stacks(tmp_path):
    one = _write_cube(tmp_path / "only.fits", _same_target_scene(32, 32, noise=0.02, seed=7))
    assert render_deepening_frames([one], max_width=32) == []
    assert build_deepening_reel([one], tmp_path, "master") is None


def test_bad_frame_is_skipped(tmp_path):
    good1 = _write_cube(tmp_path / "g1.fits", _same_target_scene(48, 48, noise=0.03, seed=8))
    good2 = _write_cube(tmp_path / "g2.fits", _same_target_scene(48, 48, noise=0.01, seed=9))
    frames = render_deepening_frames([good1, str(tmp_path / "missing.fits"), good2],
                                     max_width=48)
    assert len(frames) == 2  # the unreadable path dropped out


def test_build_deepening_reel_writes_animation(tmp_path):
    a = _write_cube(tmp_path / "a.fits", _same_target_scene(48, 48, noise=0.04, seed=10))
    b = _write_cube(tmp_path / "b.fits", _same_target_scene(48, 48, noise=0.02, seed=11))
    c = _write_cube(tmp_path / "c.fits", _same_target_scene(48, 48, noise=0.006, seed=12))
    out = build_deepening_reel([a, b, c], tmp_path, "master", max_width=48)
    assert out is not None
    assert out.exists()
    assert out.name in ("master_deepening.webp", "master_deepening.png")

    from PIL import Image
    with Image.open(out) as im:
        assert getattr(im, "n_frames", 1) == 3


def test_solve_handles_degenerate_frame():
    flat = np.full((16, 16, 3), np.nan, dtype=np.float32)
    assert _solve_stf_params(flat) is None


def test_deepening_frame_label_formats_date_and_subs():
    # Date + count → the full caption; the sub count degrades gracefully.
    assert deepening_frame_label("2026-07-19T21:03:00", 120) == "19 Jul 2026 · 120 subs"
    assert deepening_frame_label("2026-07-19", 1) == "19 Jul 2026 · 1 sub"
    # Missing/garbage date drops just that part; a non-positive count drops too.
    assert deepening_frame_label(None, 90) == "90 subs"
    assert deepening_frame_label("not-a-date", 90) == "90 subs"
    assert deepening_frame_label("2026-07-19", 0) == "19 Jul 2026"
    # Nothing known → a clean empty label (a no-op when drawn).
    assert deepening_frame_label(None, None) == ""
    assert deepening_frame_label(None, 0) == ""


def test_labels_are_burned_into_the_bottom_left_corner(tmp_path):
    # A frame rendered WITH a label differs from the same frame rendered WITHOUT
    # one — and only in the bottom-left corner (the label backing), never in the
    # top-left sky the fair-comparison tests rely on.
    a = _write_cube(tmp_path / "a.fits", _same_target_scene(96, 96, noise=0.04, seed=20))
    b = _write_cube(tmp_path / "b.fits", _same_target_scene(96, 96, noise=0.01, seed=21))

    plain = render_deepening_frames([a, b], max_width=96)
    labelled = render_deepening_frames([a, b], labels=["1 Jun 2026 · 50 subs",
                                                       "3 Jul 2026 · 400 subs"],
                                       max_width=96)
    assert len(plain) == len(labelled) == 2
    for p, lab in zip(plain, labelled, strict=True):
        pa, la = np.asarray(p), np.asarray(lab)
        # The label lives in the bottom-left; that region must change …
        assert not np.array_equal(pa[-24:, :48], la[-24:, :48])
        # … while the top-left sky patch is untouched (no double-processing).
        assert np.array_equal(pa[:24, :24], la[:24, :24])


def test_a_frame_label_follows_its_frame_through_a_skip(tmp_path):
    # The middle path is unreadable and drops out; the surviving two frames must
    # keep the labels of *their own* paths (index 0 and 2), not shift onto the
    # skipped path's label. Frame 0's label is empty (→ no backing bar), frame 1
    # (the survivor from path 2) carries a real label (→ a bar), which pins the
    # alignment: a naive positional zip would give frame 1 the skipped "MID".
    good1 = _write_cube(tmp_path / "g1.fits", _same_target_scene(96, 96, noise=0.04, seed=22))
    good2 = _write_cube(tmp_path / "g2.fits", _same_target_scene(96, 96, noise=0.01, seed=23))
    baseline = render_deepening_frames([good1, good2], max_width=96)  # no labels

    frames = render_deepening_frames(
        [good1, str(tmp_path / "missing.fits"), good2],
        labels=["", "MID SKIPPED", "3 Jul 2026 · 400 subs"], max_width=96)
    assert len(frames) == 2
    f0, f1 = np.asarray(frames[0]), np.asarray(frames[1])
    b0, b1 = np.asarray(baseline[0]), np.asarray(baseline[1])
    # Survivor 0 (path g1) had an empty label → unchanged from the no-label render.
    assert np.array_equal(f0[-24:, :64], b0[-24:, :64])
    # Survivor 1 (path g2) carries path-2's label → a backing bar appears.
    assert not np.array_equal(f1[-24:, :64], b1[-24:, :64])
