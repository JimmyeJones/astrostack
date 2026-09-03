"""Pure unit tests for the field-fulls-of-sky helper.

The one number every readiness verdict — the Target page's "Is it enough
yet?", the Dashboard's "Target progress" bar, and the Tonight planner's
"Plenty — try something new" — needs on a mosaic. See
``docs/IMPROVEMENTS.md`` → "the fourth wrong-denominator instance".
"""

from __future__ import annotations

import json

import pytest

from webapp.field_fulls import drizzle_scale_from_options, field_fulls_of_sky


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
