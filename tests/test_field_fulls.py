"""Pure unit tests for the field-fulls-of-sky helper.

The one number every readiness verdict — the Target page's "Is it enough
yet?", the Dashboard's "Target progress" bar, and the Tonight planner's
"Plenty — try something new" — needs on a mosaic. See
``docs/IMPROVEMENTS.md`` → "the fourth wrong-denominator instance".
"""

from __future__ import annotations

import json

import pytest

from seestack.io.project import FrameRow, Project, StackRunRow
from webapp.field_fulls import (
    drizzle_scale_from_options,
    field_fulls_of_sky,
    native_frame_shape,
    samples_per_pixel_of_run,
    target_field_fulls,
)


class TestFieldFullsOfSky:
    def test_a_single_field_native_stack_reads_as_one(self):
        # Canvas equals the frame; no drizzle. This is the single-field case
        # the current code already gets right, so the scaling must leave it
        # bit-for-bit unchanged — the whole reason the readiness bug survived
        # is that the sums for a single field cancel.
        n = field_fulls_of_sky(1920, 1080, frame_w=1920, frame_h=1080)
        assert n == pytest.approx(1.0, abs=1e-9)

    def test_a_2x2_no_overlap_mosaic_reads_as_four(self):
        # This is the shape the readiness bug is filed against — a mosaic
        # owner told they have "plenty" of light for a target when each panel
        # is a quarter of the goal.
        n = field_fulls_of_sky(3840, 2160, frame_w=1920, frame_h=1080)
        assert n == pytest.approx(4.0, abs=1e-9)

    def test_a_50_percent_overlap_2x2_mosaic_reads_as_2_25(self):
        # 50 % overlap on each side → the canvas is 1.5 frames wide by 1.5
        # tall, i.e. 2.25 field-fulls. The verdict's fraction has to move
        # with the *sky covered*, not the panel *count*.
        n = field_fulls_of_sky(2880, 1620, frame_w=1920, frame_h=1080)
        assert n == pytest.approx(2.25, abs=1e-9)

    def test_a_2x_drizzled_single_field_is_not_four_fields(self):
        # 2× drizzle super-samples the pixels; the sky it covers is still
        # one native frame. Without the drizzle correction, a run with
        # ``drizzle_scale=2`` on one field would read as four and quietly
        # quadruple the goal on every single-field stack the owner ever
        # drizzled — the far side of the bug the fix is closing.
        n = field_fulls_of_sky(
            3840, 2160, frame_w=1920, frame_h=1080, drizzle_scale=2.0,
        )
        assert n == pytest.approx(1.0, abs=1e-9)

    def test_a_drizzled_2x2_mosaic_still_reads_as_four_fields(self):
        # 2× drizzle over a 2×2 mosaic: canvas 7680×4320. The sky covered
        # is still four fields — the fix undoes the drizzle before
        # comparing.
        n = field_fulls_of_sky(
            7680, 4320, frame_w=1920, frame_h=1080, drizzle_scale=2.0,
        )
        assert n == pytest.approx(4.0, abs=1e-9)

    def test_missing_canvas_dims_return_none(self):
        # A run predating the record, a stat that couldn't be read: caller
        # is expected to fall back to the un-scaled goal (today's
        # behaviour), so ``None`` is the right silence — not ``1.0``, which
        # would be a claim.
        assert field_fulls_of_sky(None, 1080, frame_w=1920, frame_h=1080) is None
        assert field_fulls_of_sky(1920, None, frame_w=1920, frame_h=1080) is None
        assert field_fulls_of_sky(0, 1080, frame_w=1920, frame_h=1080) is None

    def test_missing_frame_dims_return_none(self):
        assert field_fulls_of_sky(1920, 1080, frame_w=None, frame_h=1080) is None
        assert field_fulls_of_sky(1920, 1080, frame_w=1920, frame_h=None) is None
        assert field_fulls_of_sky(1920, 1080, frame_w=0, frame_h=1080) is None

    def test_a_canvas_smaller_than_one_frame_never_lowers_the_goal(self):
        # A cropped stack, or an older run whose canvas dim was recorded
        # partial, could compute below 1.0. The readiness verdict is a
        # beginner nudge — a value below 1.0 would *lower* what "plenty"
        # means, which would call a half-integrated target done. Clamped up.
        n = field_fulls_of_sky(960, 540, frame_w=1920, frame_h=1080)
        assert n == pytest.approx(1.0, abs=1e-9)

    def test_a_single_pointing_s_empty_corners_are_not_sky_it_covers(self):
        """The bug observer #1095 measured: one pointing read as 2.25 fields.

        A canvas is the bounding box of the accepted frames' footprints, so a
        night of pointing drift and field rotation leaves corners inside the box
        and outside every frame. On the owner's library that put 46 of his 50
        single-field pictures over the planner's 1.3 mosaic line — M 42 (119
        subs at one pointing, 43.8 % of its canvas empty) read as 2.22 fields of
        sky, so the planner withheld "shoot it in mosaic mode" from an 85'
        nebula on the grounds that it was already being shot wide.

        The run already recorded the share, so the area is correctable without a
        file read.
        """
        drifted = field_fulls_of_sky(2880, 1620, frame_w=1920, frame_h=1080)
        assert drifted == pytest.approx(2.25, abs=1e-9)   # what it used to say
        honest = field_fulls_of_sky(
            2880, 1620, frame_w=1920, frame_h=1080, uncovered_frac=0.56,
        )
        assert honest == pytest.approx(1.0, abs=1e-9)
        # …and specifically on the near side of the line the planner's mosaic
        # stand-down is keyed on (`_MOSAIC_CANVAS_FIELD_FULLS`), which is the
        # consequence the owner sees.
        assert honest < 1.3

    def test_a_real_mosaic_keeps_the_scale_it_needs(self):
        # The other direction, and the one that matters more: a 2x2 raster whose
        # bounding box is 10 % empty is still four fields of sky minus that
        # corner, nowhere near a single field. The correction must not talk a
        # genuine mosaic down into the single-field goal — the failure this
        # module was written to prevent.
        n = field_fulls_of_sky(3840, 2160, frame_w=1920, frame_h=1080,
                               uncovered_frac=0.10)
        assert n == pytest.approx(3.6, abs=1e-9)
        assert n > 1.3

    def test_an_absent_or_impossible_uncovered_share_changes_nothing(self):
        # Every run stacked before the column existed, every pre-stack estimate
        # (no coverage map yet), and any value that cannot be a share of a
        # canvas: all keep the plain area ratio, i.e. today's answer exactly.
        for bad in (None, "", "ragged", float("nan"), float("inf"), -0.1,
                    1.0, 1.5):
            n = field_fulls_of_sky(3840, 2160, frame_w=1920, frame_h=1080,
                                   uncovered_frac=bad)
            assert n == pytest.approx(4.0, abs=1e-9), bad

    def test_an_almost_entirely_empty_canvas_still_never_lowers_the_goal(self):
        # A 2x2 canvas recorded as 99 % empty computes to 0.04 fields. The
        # clamp that already protects a cropped canvas protects this too: a
        # scale below 1.0 would *lower* what "plenty" means and call a
        # half-integrated target done.
        n = field_fulls_of_sky(3840, 2160, frame_w=1920, frame_h=1080,
                               uncovered_frac=0.99)
        assert n == pytest.approx(1.0, abs=1e-9)

    def test_a_nonsense_drizzle_scale_is_treated_as_one(self):
        # A garbled or below-1.0 drizzle scale never *inflates* the field
        # count — the safe direction on an on-by-default readiness path.
        n = field_fulls_of_sky(
            1920, 1080, frame_w=1920, frame_h=1080, drizzle_scale=0.5,
        )
        assert n == pytest.approx(1.0, abs=1e-9)
        n = field_fulls_of_sky(
            1920, 1080, frame_w=1920, frame_h=1080, drizzle_scale=float("nan"),
        )
        assert n == pytest.approx(1.0, abs=1e-9)


class TestSamplesPerPixelOfRun:
    """The finished-run companion: how many subs landed on *one pixel*.

    Same correction as ``frontend/src/samplesPerPixel.ts`` makes before a stack,
    applied after one — a run's ``n_frames_used`` is the total that went in, and
    on a mosaic that flatters the picture by the number of fields it spans.
    """

    FRAME = {"frame_w": 480, "frame_h": 320}

    def test_a_single_field_run_reports_its_own_frame_count(self):
        # Canvas is one field, so the total *is* the depth — this is the case
        # every caller already answered correctly, and it must not move.
        assert samples_per_pixel_of_run(
            480, 320, n_frames_used=200, **self.FRAME) == pytest.approx(200.0)

    def test_a_mosaic_reports_the_depth_not_the_total(self):
        # A 2x2 no-overlap raster: 120 subs in total is ~30 on any one pixel.
        assert samples_per_pixel_of_run(
            960, 640, n_frames_used=120, **self.FRAME) == pytest.approx(30.0)

    def test_drizzle_is_divided_out_before_the_canvas_is_counted(self):
        # A 2x drizzled single field has 4x the pixels of a frame and still
        # covers one field of sky, so every sub is on every pixel.
        opts = json.dumps({"drizzle": True, "drizzle_scale": 2.0})
        assert samples_per_pixel_of_run(
            960, 640, n_frames_used=200, options_json=opts,
            **self.FRAME) == pytest.approx(200.0)

    def test_a_cropped_canvas_never_reports_more_subs_than_went_in(self):
        # field_fulls_of_sky clamps below 1.0 rather than shrinking the goal;
        # the same clamp is what stops a cropped run claiming extra depth.
        assert samples_per_pixel_of_run(
            240, 160, n_frames_used=50, **self.FRAME) == pytest.approx(50.0)

    def test_anything_unknowable_declines_rather_than_guessing(self):
        # Each caller then keeps its depth-unaware wording, which is exactly the
        # behaviour it had before this function existed.
        assert samples_per_pixel_of_run(
            0, 320, n_frames_used=100, **self.FRAME) is None
        assert samples_per_pixel_of_run(
            480, 320, n_frames_used=100, frame_w=None, frame_h=320) is None
        assert samples_per_pixel_of_run(
            480, 320, n_frames_used=0, **self.FRAME) is None
        assert samples_per_pixel_of_run(
            480, 320, n_frames_used=None, **self.FRAME) is None
        assert samples_per_pixel_of_run(
            480, 320, n_frames_used="five", **self.FRAME) is None


class TestDrizzleScaleFromOptions:
    def test_a_drizzled_run_returns_its_scale(self):
        opts = json.dumps({"drizzle": True, "drizzle_scale": 2.0})
        assert drizzle_scale_from_options(opts) == 2.0

    def test_the_flag_off_returns_none_even_when_the_scale_is_set(self):
        # ``drizzle_scale`` has a non-1.0 default (1.5) on ``StackOptions``,
        # so a κ-σ or plain-mean run stores the field but did not drizzle.
        # The corrector must not divide the canvas by 1.5 there.
        opts = json.dumps({"drizzle": False, "drizzle_scale": 1.5})
        assert drizzle_scale_from_options(opts) is None

    def test_an_empty_or_garbled_options_returns_none(self):
        assert drizzle_scale_from_options(None) is None
        assert drizzle_scale_from_options("") is None
        assert drizzle_scale_from_options("{not: json}") is None
        assert drizzle_scale_from_options("[]") is None
        assert drizzle_scale_from_options(
            json.dumps({"drizzle": True, "drizzle_scale": "big"})
        ) is None
        assert drizzle_scale_from_options(
            json.dumps({"drizzle": True, "drizzle_scale": 0})
        ) is None


class TestNativeFrameShape:
    """The one ``LIMIT 1`` read the History listing hoists out of its per-run
    loop. Every degraded shape must answer ``None`` rather than raise: the
    callers fall back to the un-scaled behaviour, and a broken project DB must
    never cost a page its picture list."""

    class _Row(dict):
        """A stand-in for ``sqlite3.Row`` — ``keys()`` plus ``__getitem__``."""

    class _Conn:
        def __init__(self, row):
            self._row = row

        def execute(self, *_args, **_kwargs):
            if isinstance(self._row, Exception):
                raise self._row
            return self

        def fetchone(self):
            return self._row

    class _Proj:
        def __init__(self, conn):
            self._conn = conn

    def _proj(self, row):
        return self._Proj(self._Conn(row))

    def test_a_measured_frame_gives_its_shape(self):
        proj = self._proj(self._Row(width_px=1920, height_px=1080))
        assert native_frame_shape(proj) == (1920.0, 1080.0)

    def test_a_project_with_no_connection_declines(self):
        class Bare:
            pass

        assert native_frame_shape(Bare()) is None

    def test_no_frame_has_ever_recorded_its_shape(self):
        assert native_frame_shape(self._proj(None)) is None

    def test_a_broken_db_declines_rather_than_raising(self):
        assert native_frame_shape(self._proj(RuntimeError("no such table"))) is None

    def test_a_non_positive_or_missing_dimension_declines(self):
        # A half-written row must not become a zero-area "native frame", which
        # would make every canvas an infinite number of field-fulls.
        assert native_frame_shape(self._proj(self._Row(width_px=0, height_px=1080))) is None
        assert native_frame_shape(self._proj(self._Row(width_px=1920, height_px=None))) is None
        assert native_frame_shape(self._proj(self._Row())) is None


class TestTargetFieldFulls:
    """The target-level read behind the three readiness surfaces — and the one
    thing it must not take its canvas from.

    A re-render records the canvas it *wrote*, so a crop shrinks it — and the
    editor seeds Auto (with its border trim) on first open, so a cropped export
    is the ordinary shape of a finished picture, not an unusual one. It is also
    the newest row. Reading the scale off it moves every goal on this target
    toward "plenty", which is the failure this module exists to prevent.
    """

    # A 2x2 mosaic of 480x320 subs: canvas is four field-fulls of sky.
    FRAME_W, FRAME_H = 480, 320
    CANVAS_W, CANVAS_H = 960, 640

    def _project(self, tmp_path) -> Project:
        proj = Project.create(tmp_path / "target", "M 42")
        proj.add_frame(FrameRow(
            source_path="sub0001.fits", width_px=self.FRAME_W,
            height_px=self.FRAME_H,
        ))
        return proj

    def _add_run(self, proj, *, timestamp: str, canvas_w: int, canvas_h: int,
                 derived_from: int | None = None,
                 uncovered_frac: float | None = None) -> int:
        options: dict = ({"editor_recipe": {"ops": []},
                          "derived_from": derived_from}
                         if derived_from is not None else {"sigma_clip": True})
        return proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc=timestamp, output_basename=f"run_{timestamp}",
            fits_path=None, tiff_path=None, preview_path=None,
            n_frames_used=180, canvas_h=canvas_h, canvas_w=canvas_w,
            coverage_min=1, coverage_max=1 if derived_from is not None else 180,
            options_json=json.dumps(options), uncovered_frac=uncovered_frac,
        ))

    def test_a_plain_mosaic_stack_gives_its_canvas(self, tmp_path):
        proj = self._project(tmp_path)
        try:
            self._add_run(proj, timestamp="2026-05-02T00:00:00Z",
                          canvas_w=self.CANVAS_W, canvas_h=self.CANVAS_H)
            assert target_field_fulls(proj) == pytest.approx(4.0)
        finally:
            proj.close()

    def test_a_drifted_single_field_is_not_read_as_a_mosaic(self, tmp_path):
        """Observer #1095, through the read the three surfaces actually make.

        One pointing, a canvas 1.5x the frame on each axis because the night
        drifted, and the run's own record that 56 % of that box is empty. The
        figure behind the goal chip, the Dashboard bar and the planner's mosaic
        stand-down has to be the sky with data on it.
        """
        proj = self._project(tmp_path)
        try:
            self._add_run(proj, timestamp="2026-05-02T00:00:00Z",
                          canvas_w=720, canvas_h=480, uncovered_frac=0.56)
            assert target_field_fulls(proj) == pytest.approx(1.0, abs=1e-9)
        finally:
            proj.close()

    def test_a_run_with_no_recorded_share_answers_exactly_as_before(
            self, tmp_path):
        # 668 of the owner's 756 stack-run rows carry no `uncovered_frac` (they
        # predate the column, and only a surface that grades them backfills it).
        # Those keep the area ratio they have always had — the upgrade is
        # invisible until a row has something to say.
        proj = self._project(tmp_path)
        try:
            self._add_run(proj, timestamp="2026-05-02T00:00:00Z",
                          canvas_w=self.CANVAS_W, canvas_h=self.CANVAS_H)
            assert target_field_fulls(proj) == pytest.approx(4.0)
        finally:
            proj.close()

    def test_a_cropped_export_takes_the_stack_s_own_emptiness_too(
            self, tmp_path):
        """The export's canvas is not read, so neither is its emptiness.

        A crop changes both terms — it removes the ragged border *and* shrinks
        the box — so pairing the stack's area with the export's share (or the
        reverse) would be two halves of two pictures. The stacking run answers
        with both of its own numbers.
        """
        proj = self._project(tmp_path)
        try:
            src = self._add_run(proj, timestamp="2026-05-02T00:00:00Z",
                                canvas_w=self.CANVAS_W, canvas_h=self.CANVAS_H,
                                uncovered_frac=0.25)
            self._add_run(proj, timestamp="2026-09-13T10:00:00Z",
                          canvas_w=920, canvas_h=614, derived_from=src,
                          uncovered_frac=0.0)
            assert target_field_fulls(proj) == pytest.approx(3.0, abs=1e-9)
        finally:
            proj.close()

    def test_a_cropped_export_does_not_shrink_the_target_s_goal(self, tmp_path):
        """The bug: Auto's border trim keeps ~92 % of a mosaic canvas, and the
        export is the newest row — so the target's scale, and with it the goal
        behind "Is it enough yet?", fell by the crop factor."""
        proj = self._project(tmp_path)
        try:
            src = self._add_run(proj, timestamp="2026-05-02T00:00:00Z",
                                canvas_w=self.CANVAS_W, canvas_h=self.CANVAS_H)
            # An Auto-trimmed re-render of that stack, written later.
            self._add_run(proj, timestamp="2026-09-13T10:00:00Z",
                          canvas_w=920, canvas_h=614, derived_from=src)
            assert target_field_fulls(proj) == pytest.approx(4.0)
        finally:
            proj.close()

    def test_a_hard_crop_cannot_hand_a_mosaic_the_single_field_goal(self, tmp_path):
        """The severe end of the same edit. A crop past one native frame's area
        lands on ``field_fulls_of_sky``'s ``max(1.0, …)`` clamp, so the scale
        would collapse to 1.0 — a four-panel mosaic told it needs a quarter of
        the light it does."""
        proj = self._project(tmp_path)
        try:
            src = self._add_run(proj, timestamp="2026-05-02T00:00:00Z",
                                canvas_w=self.CANVAS_W, canvas_h=self.CANVAS_H)
            self._add_run(proj, timestamp="2026-09-13T10:00:00Z",
                          canvas_w=300, canvas_h=200, derived_from=src)
            assert target_field_fulls(proj) == pytest.approx(4.0)
        finally:
            proj.close()

    def test_the_newest_stack_still_wins_over_an_older_one(self, tmp_path):
        """The scan skips re-renders; it does not otherwise change the order. A
        mosaic's canvas grows as its panels are shot, and the newest *stack* is
        still the one that describes the sky it now spans."""
        proj = self._project(tmp_path)
        try:
            self._add_run(proj, timestamp="2026-05-02T00:00:00Z",
                          canvas_w=self.FRAME_W, canvas_h=self.FRAME_H)
            self._add_run(proj, timestamp="2026-06-02T00:00:00Z",
                          canvas_w=self.CANVAS_W, canvas_h=self.CANVAS_H)
            assert target_field_fulls(proj) == pytest.approx(4.0)
        finally:
            proj.close()

    def test_a_target_whose_only_picture_is_an_export_keeps_its_old_answer(
        self, tmp_path,
    ):
        """Its source was pruned from History, so there is nothing else to read.
        Falling back to the newest row of any kind is what this always did —
        better a scale off a re-render than no scale at all."""
        proj = self._project(tmp_path)
        try:
            self._add_run(proj, timestamp="2026-09-13T10:00:00Z",
                          canvas_w=self.CANVAS_W, canvas_h=self.CANVAS_H,
                          derived_from=9999)
            assert target_field_fulls(proj) == pytest.approx(4.0)
        finally:
            proj.close()

    def test_a_target_with_no_stack_yet_declines(self, tmp_path):
        proj = self._project(tmp_path)
        try:
            assert target_field_fulls(proj) is None
        finally:
            proj.close()

    def test_a_project_with_no_connection_declines(self):
        class Bare:
            pass

        assert target_field_fulls(Bare()) is None


class TestCanvasSupersampling:
    """How many canvas pixels there are per native camera pixel — the factor a
    caller converting canvas pixels to sky with a *frame's* plate scale has to
    divide out (``webapp.routers.sky``'s no-canvas-WCS fallback)."""

    def test_a_drizzled_run_reports_its_scale(self):
        from webapp.field_fulls import canvas_supersampling

        assert canvas_supersampling(
            '{"drizzle": true, "drizzle_scale": 2.0}') == pytest.approx(2.0)
        assert canvas_supersampling(
            '{"drizzle": true, "drizzle_scale": 1.4}') == pytest.approx(1.4)

    def test_everything_else_changes_nothing(self):
        """1.0 — not None — for every shape that isn't a drizzled run, so the
        caller's arithmetic needs no branch: missing options, malformed JSON, the
        drizzle switch off (which is how ``StackOptions`` ships), a nonsense
        scale, and a sub-unity one — clamped because that is what the engine did
        with it (``stacker`` takes ``max(1.0, drizzle_scale)``), so the canvas was
        never written finer-than-native however the number reads."""
        from webapp.field_fulls import canvas_supersampling

        for options in (None, "", "not json{", "{}", '{"drizzle": false}',
                        '{"drizzle": true}',
                        '{"drizzle": true, "drizzle_scale": "x"}',
                        '{"drizzle": true, "drizzle_scale": 0.5}',
                        '{"drizzle": true, "drizzle_scale": 0}'):
            assert canvas_supersampling(options) == 1.0, options
