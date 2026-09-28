"""The cross-run "night after night" deepening reel (engine side).

Covers the fair-comparison contract that makes the reel honest: every frame is
tone-mapped with one shared stretch (so only the noise/detail changes, never the
brightness), frames are unified to the deepest frame's size, and the whole thing
degrades gracefully below two usable stacks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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
