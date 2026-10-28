"""The cross-run "night after night" deepening reel (engine side).

Covers the fair-comparison contract that makes the reel honest: every frame is
tone-mapped with one shared stretch (so only the noise/detail changes, never the
brightness), frames are unified to the deepest frame's size, and the whole thing
degrades gracefully below two usable stacks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from astropy.io import fits

from seestack.render.deepening import (
    _apply_stf_params,
    _solve_stf_params,
    build_deepening_reel,
    deepening_frame_label,
    deepening_series,
    series_depth_is_monotone,
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


def test_a_differently_shaped_night_is_letterboxed_not_squashed(tmp_path):
    """A night whose canvas has a different *aspect ratio* (a single portrait
    panel that later grew into a wide mosaic) must be fitted whole and centred,
    not stretched to the final frame's shape.

    Regression: both size-unifying spots did a plain ``resize(target_size)``, so
    the earlier nights were geometrically distorted — round stars became
    ellipses in exactly the frames the reel exists to compare."""
    tall = _write_cube(tmp_path / "n1.fits", _same_target_scene(64, 32, noise=0.03, seed=21))
    wide = _write_cube(tmp_path / "n2.fits", _same_target_scene(32, 64, noise=0.01, seed=22))
    frames = render_deepening_frames([tall, wide], max_width=64)
    assert len(frames) == 2
    target = frames[-1].size
    assert frames[0].size == target  # uniform series for the encoder

    arr = np.asarray(frames[0])
    h, w = arr.shape[:2]
    # The 64×32 (h×w) night, fitted into a 32×64 canvas, keeps its 1:2 ratio →
    # a 16-wide column of picture with black bars either side (fail-before: the
    # whole width was filled by a 2× horizontal stretch).
    lit_cols = np.flatnonzero(arr.reshape(h, w, 3).max(axis=(0, 2)) > 0)
    assert lit_cols.size < w  # something is padded, not stretched edge to edge
    # ...and the content is centred: equal blank margins left and right.
    assert lit_cols[0] == w - 1 - lit_cols[-1]
    assert arr[:, :lit_cols[0]].max() == 0 and arr[:, lit_cols[-1] + 1:].max() == 0
    # The picture's own aspect ratio survives the fit (1:2, within a pixel).
    lit_rows = np.flatnonzero(arr.reshape(h, w, 3).max(axis=(1, 2)) > 0)
    fitted_h, fitted_w = lit_rows.size, lit_cols.size
    assert abs(fitted_h / fitted_w - 2.0) < 0.1


def test_same_aspect_frames_are_resized_exactly_as_before(tmp_path):
    """The common case — every night the same shape, the canvas just bigger — must
    be untouched by the letterboxing: a full-bleed resize with no black bars."""
    small = _write_cube(tmp_path / "s.fits", _same_target_scene(32, 48, noise=0.03, seed=23))
    big = _write_cube(tmp_path / "g.fits", _same_target_scene(64, 96, noise=0.01, seed=24))
    frames = render_deepening_frames([small, big], max_width=96)
    arr = np.asarray(frames[0])
    assert frames[0].size == frames[-1].size
    # No padded rows/columns anywhere — the frame fills its canvas.
    assert arr.max(axis=(0, 2)).min() > 0
    assert arr.max(axis=(1, 2)).min() > 0


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


# --- the series' ordering clock ------------------------------------------------
# `timestamp_utc` is when the stack *ran*; `capture_start_utc`/`capture_end_utc`
# are when its subs were *shot*. `webapp.capture_nights` states the app's rule —
# anything that says "shot on …" has to use the second pair — and the reel, whose
# own title is "night after night", was the one surface still ordering and
# labelling by the first.


@dataclass
class _Run:
    """The handful of `StackRunRow` attributes `deepening_series` reads."""

    id: int
    timestamp_utc: str
    n_frames_used: int = 100
    capture_start_utc: str | None = None
    capture_end_utc: str | None = None
    options_json: str = "{}"


def test_a_night_stacked_on_its_own_makes_the_series_step_back_in_depth():
    """The shape the card's lead sentence could not describe.

    Stack night 1, then nights 1-2, then *just tonight's* subs on their own: the
    third run has the newest capture window, so it lands last while holding the
    fewest subs, and the reel really does get grainier at that step. The ordering
    is right (the owner asked for the subs' own clock, and depth only breaks
    ties) — what was wrong was promising "more subs each time" over it.
    """
    n1 = _Run(id=1, timestamp_utc="2026-06-11T00:00:00Z", n_frames_used=100,
              capture_start_utc="2026-06-10T22:00:00Z",
              capture_end_utc="2026-06-10T23:00:00Z")
    n12 = _Run(id=2, timestamp_utc="2026-07-11T00:00:00Z", n_frames_used=200,
               capture_start_utc="2026-06-10T22:00:00Z",
               capture_end_utc="2026-07-10T23:00:00Z")
    tonight = _Run(id=3, timestamp_utc="2026-08-11T00:00:00Z", n_frames_used=30,
                   capture_start_utc="2026-08-10T22:00:00Z",
                   capture_end_utc="2026-08-10T23:00:00Z")
    series = deepening_series([n1, n12, tonight])
    assert [r.n_frames_used for r in series.runs] == [100, 200, 30]
    assert series_depth_is_monotone(series.runs) is False


def test_a_series_that_only_deepens_says_so():
    a = _Run(id=1, timestamp_utc="2026-06-11T00:00:00Z", n_frames_used=100,
             capture_start_utc="2026-06-10T22:00:00Z",
             capture_end_utc="2026-06-10T23:00:00Z")
    b = _Run(id=2, timestamp_utc="2026-07-11T00:00:00Z", n_frames_used=200,
             capture_start_utc="2026-06-10T22:00:00Z",
             capture_end_utc="2026-07-10T23:00:00Z")
    series = deepening_series([a, b])
    assert series_depth_is_monotone(series.runs) is True
    # Equal depth is not a step back — two stacks of one night's subs still read
    # as "no worse than before", which is what the wording claims.
    assert series_depth_is_monotone([_Run(id=1, timestamp_utc="x", n_frames_used=50),
                                     _Run(id=2, timestamp_utc="y", n_frames_used=50)])
    # Nothing to measure reads as "no step back": the reassuring sentence is the
    # right one for a series whose depths cannot be read.
    assert series_depth_is_monotone([]) is True
    assert series_depth_is_monotone([_Run(id=1, timestamp_utc="x", n_frames_used=0),
                                     _Run(id=2, timestamp_utc="y", n_frames_used=0)])
    # …and an unreadable step is skipped rather than counted as a drop to zero.
    class _NoCount:
        n_frames_used = None
    assert series_depth_is_monotone(
        [_Run(id=1, timestamp_utc="x", n_frames_used=100), _NoCount(),
         _Run(id=2, timestamp_utc="y", n_frames_used=200)]) is True


def test_series_orders_by_when_the_subs_were_shot_not_when_the_stack_ran():
    # A back catalogue reprocessed out of order: the June night was stacked last.
    july = _Run(id=1, timestamp_utc="2026-08-01T00:00:00Z", n_frames_used=200,
                capture_start_utc="2026-07-10T22:00:00Z",
                capture_end_utc="2026-07-10T23:00:00Z")
    june = _Run(id=2, timestamp_utc="2026-08-02T00:00:00Z", n_frames_used=100,
                capture_start_utc="2026-06-10T22:00:00Z",
                capture_end_utc="2026-06-10T23:00:00Z")
    series = deepening_series([july, june])
    assert series.dated_by == "capture"
    assert [r.id for r in series.runs] == [2, 1]  # June's night first


def test_series_falls_back_to_stack_time_when_one_run_has_no_window():
    # All-or-nothing: a pre-schema-18 row (or a channel combine) keeps the whole
    # series on the stack clock rather than interleaving two different ones.
    a = _Run(id=1, timestamp_utc="2026-08-01T00:00:00Z",
             capture_start_utc="2026-07-10T22:00:00Z",
             capture_end_utc="2026-07-10T23:00:00Z")
    b = _Run(id=2, timestamp_utc="2026-08-02T00:00:00Z")
    series = deepening_series([b, a])
    assert series.dated_by == "stack"
    assert [r.id for r in series.runs] == [1, 2]


def test_a_reprocess_of_the_same_nights_is_not_a_new_deepening_step():
    n1 = _Run(id=1, timestamp_utc="2026-06-11T00:00:00Z", n_frames_used=100,
              capture_start_utc="2026-06-10T22:00:00Z",
              capture_end_utc="2026-06-10T23:00:00Z")
    n2 = _Run(id=2, timestamp_utc="2026-07-11T00:00:00Z", n_frames_used=200,
              capture_start_utc="2026-06-10T22:00:00Z",
              capture_end_utc="2026-07-10T23:00:00Z")
    # "Reprocess everything" re-stacks exactly the same two nights again.
    redo = _Run(id=3, timestamp_utc="2026-09-01T00:00:00Z", n_frames_used=200,
                capture_start_utc="2026-06-10T22:00:00Z",
                capture_end_utc="2026-07-10T23:00:00Z")
    series = deepening_series([n1, n2, redo])
    assert series.dated_by == "capture"
    # Two steps, not three — and the newest render of the deeper step wins.
    assert [r.id for r in series.runs] == [1, 3]


def test_a_linear_master_is_preferred_over_an_editor_export_of_the_same_nights():
    linear = _Run(id=1, timestamp_utc="2026-06-11T00:00:00Z", n_frames_used=100,
                  capture_start_utc="2026-06-10T22:00:00Z",
                  capture_end_utc="2026-06-10T23:00:00Z")
    export = _Run(id=2, timestamp_utc="2026-06-12T00:00:00Z", n_frames_used=100,
                  capture_start_utc="2026-06-10T22:00:00Z",
                  capture_end_utc="2026-06-10T23:00:00Z",
                  options_json='{"display_space": true, "derived_from": 1}')
    later = _Run(id=3, timestamp_utc="2026-07-11T00:00:00Z", n_frames_used=200,
                 capture_start_utc="2026-06-10T22:00:00Z",
                 capture_end_utc="2026-07-10T23:00:00Z")
    series = deepening_series([linear, export, later])
    # The export arrives already denoised/sharpened, so it would show the noise
    # dropping for a reason other than more subs.
    assert [r.id for r in series.runs] == [1, 3]


def test_collapsing_never_dissolves_a_two_stack_card():
    # Both stacks are of the one night, so the collapse would leave a single
    # step — and the reel self-hides below two. Keep both instead.
    a = _Run(id=1, timestamp_utc="2026-06-11T00:00:00Z", n_frames_used=100,
             capture_start_utc="2026-06-10T22:00:00Z",
             capture_end_utc="2026-06-10T23:00:00Z")
    b = _Run(id=2, timestamp_utc="2026-06-12T00:00:00Z", n_frames_used=100,
             capture_start_utc="2026-06-10T22:00:00Z",
             capture_end_utc="2026-06-10T23:00:00Z")
    series = deepening_series([a, b])
    assert series.dated_by == "capture"
    assert [r.id for r in series.runs] == [1, 2]


def test_a_half_recorded_window_still_orders_by_capture():
    # One usable DATE-OBS is an honest single night, treated as both ends — the
    # same rule `capture_night_range` follows.
    # Stack times deliberately run the *other* way, so agreeing with them would
    # not produce this order.
    a = _Run(id=1, timestamp_utc="2026-08-01T00:00:00Z",
             capture_end_utc="2026-07-10T23:00:00Z")
    b = _Run(id=2, timestamp_utc="2026-08-02T00:00:00Z",
             capture_start_utc="2026-06-10T22:00:00Z")
    series = deepening_series([a, b])
    assert series.dated_by == "capture"
    assert [r.id for r in series.runs] == [2, 1]


def test_empty_series_is_stack_dated_and_empty():
    series = deepening_series([])
    assert series.runs == []
    assert series.dated_by == "stack"


def test_frame_label_names_the_span_a_multi_night_step_covers():
    # A step made of four nights dated by one of them is the defect the capture
    # ordering exists to fix, one layer down in the burned-in caption.
    assert deepening_frame_label("2024-09-11", 600, "2024-09-14") == \
        "11-14 Sep 2024 · 600 subs"
    # One night, an equal end, or no end at all ⇒ exactly the old single date.
    assert deepening_frame_label("2024-09-11", 600, "2024-09-11") == \
        "11 Sep 2024 · 600 subs"
    assert deepening_frame_label("2024-09-11", 600) == "11 Sep 2024 · 600 subs"


def test_two_stacks_of_one_night_run_shallow_to_deep():
    """Found by a running-app `--restack` dogfood pass, which reported a reel
    running **6 subs → 3 subs**. Both stacks end on the same sub, so the window's
    end cannot separate them, and ordering on the *start* put the wider window —
    i.e. the deeper stack — first. That is the exact reverse of the card's own
    "cleaner and deeper" sentence."""
    thin = _Run(id=1, timestamp_utc="2026-06-11T00:00:00Z", n_frames_used=3,
                capture_start_utc="2024-11-15T22:13:00Z",
                capture_end_utc="2024-11-15T22:15:00Z")
    deep = _Run(id=2, timestamp_utc="2026-06-12T00:00:00Z", n_frames_used=6,
                capture_start_utc="2024-11-15T22:10:00Z",
                capture_end_utc="2024-11-15T22:15:00Z")
    series = deepening_series([thin, deep])
    assert series.dated_by == "capture"
    assert [r.n_frames_used for r in series.runs] == [3, 6]


def test_a_single_late_night_stacked_alone_still_lands_by_its_own_date():
    """Depth is only the tie-break, never the axis: a shallow stack of a *later*
    night belongs after a deeper stack of earlier ones, because that is when its
    subs were shot — what the owner asked for. The reel then honestly shows a
    step that is not deeper rather than reordering the library's history."""
    deep_early = _Run(id=1, timestamp_utc="2026-06-11T00:00:00Z", n_frames_used=400,
                      capture_start_utc="2026-06-10T21:00:00Z",
                      capture_end_utc="2026-06-11T23:00:00Z")
    thin_late = _Run(id=2, timestamp_utc="2026-07-11T00:00:00Z", n_frames_used=50,
                     capture_start_utc="2026-07-10T21:00:00Z",
                     capture_end_utc="2026-07-10T23:00:00Z")
    series = deepening_series([thin_late, deep_early])
    assert [r.id for r in series.runs] == [1, 2]


def test_a_cumulative_step_names_its_place_in_the_progression():
    """The reel-from-history half of the owner's ask: "night 1; nights 1-2; …".
    The date says *when* the newest subs were shot; the prefix says *where in the
    series* this frame is, which is the thing he asked the reel to show."""
    assert deepening_frame_label("2024-09-11", 120, None, 1) == \
        "Night 1 · 11 Sep 2024 · 120 subs"
    assert deepening_frame_label("2024-09-11", 600, "2024-09-14", 4) == \
        "Nights 1-4 · 11-14 Sep 2024 · 600 subs"


def test_a_label_without_a_night_count_is_byte_for_byte_what_it_was():
    """The prefix only ever appears on a series the caller has *shown* to be
    cumulative, so every other reel — and every reel built before this existed —
    keeps the caption it had."""
    for nights in (None, 0):
        assert deepening_frame_label("2024-09-11", 600, "2024-09-14", nights) == \
            "11-14 Sep 2024 · 600 subs"
        assert deepening_frame_label("2024-09-11", 600, None, nights) == \
            "11 Sep 2024 · 600 subs"
        assert deepening_frame_label(None, None, None, nights) == ""


def test_the_night_prefix_stands_alone_when_nothing_else_is_known():
    """A step whose date and sub count are both unreadable still has a true
    thing to say about where it sits in the series."""
    assert deepening_frame_label(None, None, None, 3) == "Nights 1-3"


# ── Sky placement: a mosaic that grew panel by panel ─────────────────────────
#
# Regression (Scout 2026-10-21, sweep 4): every earlier frame was fitted and
# centred onto the newest canvas, never placed by its WCS — so a single S30
# panel (night 1) against the 2×1 mosaic it became (night 2) jumped ~23 % of the
# reel's width sideways, and against a 2×2 it was magnified ~1.85× to fill the
# frame. The shapes below are the owner's panel at quarter size (1080×1920 →
# 270×480, at four times the pixel scale), the same ratios the probe used.

_PANEL_W, _PANEL_H = 270, 480
_SCALE_DEG = 4 * 3.9 / 3600.0  # S30 ~3.9"/px, at quarter size


def _tan_wcs(width: int, height: int, ra: float, dec: float):
    from astropy.wcs import WCS

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(width + 1) / 2.0, (height + 1) / 2.0]
    w.wcs.cd = [[-_SCALE_DEG, 0.0], [0.0, _SCALE_DEG]]
    return w


def _star_field(width: int, height: int, wcs, stars_radec, *, seed: int) -> np.ndarray:
    """A (3, H, W) linear field with a faint noisy sky and a gaussian star at each
    sky position that falls on this canvas."""
    rng = np.random.default_rng(seed)
    plane = (0.10 + 0.004 * rng.standard_normal((height, width))).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    for ra, dec in stars_radec:
        sx, sy = wcs.all_world2pix([[ra, dec]], 0)[0]
        plane += (2.0 * np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / (2 * 2.0 ** 2))
                  ).astype(np.float32)
    return np.stack([plane, plane, plane])


def _write_solved(path, cube, wcs) -> str:
    hdu = fits.PrimaryHDU(data=cube)
    hdu.header.update(wcs.to_header())
    hdu.writeto(path, overwrite=True)
    return str(path)


def _star_xy(img) -> tuple[float, float]:
    """Intensity-weighted centroid of the brightest blob in a reel frame."""
    arr = np.asarray(img).astype(np.float64).sum(axis=2)
    y0, x0 = np.unravel_index(int(np.argmax(arr)), arr.shape)
    ys, xs = slice(max(0, y0 - 4), y0 + 5), slice(max(0, x0 - 4), x0 + 5)
    win = arr[ys, xs] - np.median(arr)
    win = np.clip(win, 0.0, None)
    gy, gx = np.mgrid[ys, xs]
    return float((gx * win).sum() / win.sum()), float((gy * win).sum() / win.sum())


def _grown_mosaic(tmp_path, cols: int, rows: int):
    """Night 1: one panel (the mosaic's top-left). Night 2: the cols×rows mosaic
    it became. One star at the same sky position, inside the first panel."""
    overlap = 20
    mw = cols * _PANEL_W - (cols - 1) * overlap
    mh = rows * _PANEL_H - (rows - 1) * overlap
    mosaic = _tan_wcs(mw, mh, 180.0, 30.0)
    p_ra, p_dec = mosaic.all_pix2world([[(_PANEL_W - 1) / 2.0, (_PANEL_H - 1) / 2.0]], 0)[0]
    panel = _tan_wcs(_PANEL_W, _PANEL_H, float(p_ra), float(p_dec))
    star = tuple(mosaic.all_pix2world([[70.0, 130.0]], 0)[0])
    n1 = _write_solved(tmp_path / "night1.fits",
                       _star_field(_PANEL_W, _PANEL_H, panel, [star], seed=31), panel)
    n2 = _write_solved(tmp_path / "night2.fits",
                       _star_field(mw, mh, mosaic, [star], seed=32), mosaic)
    return n1, n2, (mw, mh)


def test_a_grown_2x1_mosaic_keeps_the_object_in_place(tmp_path):
    n1, n2, (mw, _mh) = _grown_mosaic(tmp_path, 2, 1)
    frames = render_deepening_frames([n1, n2], max_width=256)
    assert len(frames) == 2 and frames[0].size == frames[1].size
    (x1, y1), (x2, y2) = _star_xy(frames[0]), _star_xy(frames[1])
    # Where the star truly sits on the night-2 reel frame.
    k = frames[1].size[0] / mw
    assert abs(x2 - (70.5 * k - 0.5)) < 1.0 and abs(y2 - (130.5 * k - 0.5)) < 1.0
    # Fail-before: night 1 was centred and drawn at x≈ +60 reel px from here.
    assert abs(x1 - x2) < 1.0 and abs(y1 - y2) < 1.0
    # The panel covers only its own part of the canvas; the rest is "no data".
    arr = np.asarray(frames[0])
    assert arr[:, -10:].max() == 0


def test_a_grown_2x2_mosaic_is_not_magnified_to_fill_the_frame(tmp_path):
    n1, n2, (mw, _mh) = _grown_mosaic(tmp_path, 2, 2)
    frames = render_deepening_frames([n1, n2], max_width=256)
    (x1, y1), (x2, y2) = _star_xy(frames[0]), _star_xy(frames[1])
    assert abs(x1 - x2) < 1.0 and abs(y1 - y2) < 1.0
    # The single panel fills about its own quarter, not the whole frame (the
    # fit-and-centre scale was 1 here: the panel was blown up ~1.85×).
    arr = np.asarray(frames[0]).max(axis=2)
    lit_cols = np.flatnonzero(arr.max(axis=0) > 0)
    w = frames[0].size[0]
    assert lit_cols.size == pytest.approx(w * _PANEL_W / mw, abs=2)


def test_an_unchanged_single_field_is_byte_for_byte_the_old_reel(tmp_path):
    """Two stacks of one field on one grid: the sky placement is the identity,
    so the frames are exactly what fit-and-centre produced (what an unsolved
    pair of the same masters still produces)."""
    wcs = _tan_wcs(_PANEL_W, _PANEL_H, 83.8, -5.4)
    star = tuple(wcs.all_pix2world([[100.0, 200.0]], 0)[0])
    a = _star_field(_PANEL_W, _PANEL_H, wcs, [star], seed=41)
    b = _star_field(_PANEL_W, _PANEL_H, wcs, [star], seed=42)
    solved = render_deepening_frames(
        [_write_solved(tmp_path / "a.fits", a, wcs), _write_solved(tmp_path / "b.fits", b, wcs)],
        max_width=128)
    plain = render_deepening_frames(
        [_write_cube(tmp_path / "pa.fits", a), _write_cube(tmp_path / "pb.fits", b)],
        max_width=128)
    for s, p in zip(solved, plain, strict=True):
        assert np.array_equal(np.asarray(s), np.asarray(p))


def test_a_frame_without_a_wcs_falls_back_to_fit_and_centre(tmp_path):
    """An editor export whose recipe rotated (written with no WCS), or a pre-WCS
    master, keeps the old placement — never a guessed one."""
    n1, n2, _ = _grown_mosaic(tmp_path, 2, 1)
    stripped = _write_cube(tmp_path / "night1_nowcs.fits", fits.getdata(n1))
    solved_ref = render_deepening_frames([stripped, n2], max_width=256)
    unsolved = render_deepening_frames(
        [stripped, _write_cube(tmp_path / "night2_nowcs.fits", fits.getdata(n2))],
        max_width=256)
    assert np.array_equal(np.asarray(solved_ref[0]), np.asarray(unsolved[0]))


def test_a_frame_of_other_sky_falls_back_rather_than_going_black(tmp_path):
    """Two masters whose skies do not overlap at all (a mislabelled run): drawing
    one on the other's grid would be an all-black frame, so it is fitted instead."""
    here = _tan_wcs(_PANEL_W, _PANEL_H, 10.0, 41.0)
    there = _tan_wcs(_PANEL_W, _PANEL_H, 83.8, -5.4)
    a = _star_field(_PANEL_W, _PANEL_H, there, [], seed=51)
    b = _star_field(_PANEL_W, _PANEL_H, here, [], seed=52)
    frames = render_deepening_frames(
        [_write_solved(tmp_path / "a.fits", a, there), _write_solved(tmp_path / "b.fits", b, here)],
        max_width=128)
    assert np.asarray(frames[0]).max() > 0


# ── Depth on a grown or shrunk canvas ────────────────────────────────────────
#
# Regression (Scout 2026-10-28, sweep 1): each master was decimated by its *own*
# factor, then the earlier one was resampled bilinearly as stretched u8 — so on a
# mosaic whose canvas changed, the shallow night came out ~a third *quieter* and
# visibly brighter than the deep newest one (σ 25.3 vs 37.7, sky 73 vs 51), the
# reverse of the reel's whole story.

def _flat_field(width: int, height: int, *, noise: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    plane = (0.10 + noise * rng.standard_normal((height, width))).astype(np.float32)
    return np.stack([plane, plane, plane])


def _depth_pair(tmp_path, *, shrink: bool):
    """A panel and the 2×2 mosaic it sits in, at a shallow and a deep noise. Grown:
    the panel is the shallow first night and the mosaic the deep newest one.
    Shrunk: the mosaic is the shallow first night and the panel the deep newest."""
    overlap = 20
    mw, mh = 2 * _PANEL_W - overlap, 2 * _PANEL_H - overlap
    mosaic = _tan_wcs(mw, mh, 180.0, 30.0)
    p_ra, p_dec = mosaic.all_pix2world([[(_PANEL_W - 1) / 2.0, (_PANEL_H - 1) / 2.0]], 0)[0]
    panel = _tan_wcs(_PANEL_W, _PANEL_H, float(p_ra), float(p_dec))
    shallow, deep = 0.00566, 0.004
    if shrink:
        first = _write_solved(tmp_path / "first.fits",
                              _flat_field(mw, mh, noise=shallow, seed=61), mosaic)
        newest = _write_solved(tmp_path / "newest.fits",
                               _flat_field(_PANEL_W, _PANEL_H, noise=deep, seed=62), panel)
    else:
        first = _write_solved(tmp_path / "first.fits",
                              _flat_field(_PANEL_W, _PANEL_H, noise=shallow, seed=61), panel)
        newest = _write_solved(tmp_path / "newest.fits",
                               _flat_field(mw, mh, noise=deep, seed=62), mosaic)
    return first, newest


def _panel_footprint_stats(frames) -> list[tuple[float, float]]:
    """(σ, median) of the green channel inside the panel's footprint on the newest
    reel frame, inset so a placement edge never counts."""
    out = []
    newest = np.asarray(frames[-1])[..., 1].astype(np.float64)
    lit = newest > 0
    for frame in frames:
        g = np.asarray(frame)[..., 1].astype(np.float64)
        both = lit & (g > 0)
        ys, xs = np.nonzero(both)
        y0, y1 = ys.min() + 4, ys.max() - 4
        x0, x1 = xs.min() + 4, xs.max() - 4
        patch = g[y0:y1, x0:x1]
        out.append((float(patch.std()), float(np.median(patch))))
    return out


@pytest.mark.parametrize("shrink", [False, True], ids=["grown", "shrunk"])
def test_a_shallow_night_on_a_changed_canvas_is_not_drawn_cleaner(tmp_path, shrink):
    first, newest = _depth_pair(tmp_path, shrink=shrink)
    frames = render_deepening_frames([first, newest], max_width=256)
    (sd_first, med_first), (sd_new, med_new) = _panel_footprint_stats(frames)
    # Fail-before (grown): 25.3-ish vs 37.7-ish in the owner-scale probe — the
    # shallow night read *quieter*. It must read noisier, by roughly its depth.
    assert sd_first > sd_new * 1.2
    # One shared stretch: the sky is not lifted on the placed night.
    assert abs(med_first - med_new) <= 3.0
