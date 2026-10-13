"""What an automatic drizzle will cost, said before it runs.

v0.494.0 let an unattended run drizzle itself when the subs can pay for it
("Auto, when worth it"); v0.494.2 then measured the price — about **×7 the
per-sub time of a plain stack**, which on the owner's 5,477-sub target turns
about an hour of stacking into most of a day's. Asked whether a hands-off run
should decline a long one, he chose **(c): tell me the estimate before it starts
and let it run** — explicitly not a refusal and not a threshold (sign-off item
19, answered 2026-10-13).

These pin the arithmetic behind that sentence (:mod:`webapp.drizzletime`) and the
one property that makes it trustworthy: it is **measured**, never modelled. The
preference order is the whole design — a comparable *drizzled* run of this target
answers directly, the measured ratio is only ever used to fill in a side that has
no runs of its own, and with nothing timed at all there is no number rather than
a guess. The copy that reads these numbers lives in
``frontend/src/autoDrizzleNote.ts`` and is pinned by its own vitest file.
"""

from __future__ import annotations

import json

import pytest

from seestack.io.project import StackRunRow
from seestack.stack.autodrizzle import DRIZZLE_COST_RATIO
from webapp.drizzletime import price_auto_drizzle

_CANVAS_W, _CANVAS_H = 1920, 1080
_CANVAS = _CANVAS_W * _CANVAS_H


def _row(cost_class_opts: dict, *, n: int, duration_s: float,
         engine_version: str | None = "0.494.6", run_id: int = 1) -> StackRunRow:
    """A timed ``stack_runs`` row on the owner's own frame size."""
    return StackRunRow(
        id=run_id, timestamp_utc="2026-10-01T00:00:00Z", output_basename="master",
        fits_path=None, tiff_path=None, preview_path=None,
        n_frames_used=n, canvas_h=_CANVAS_H, canvas_w=_CANVAS_W,
        coverage_min=1, coverage_max=n,
        options_json=json.dumps(cost_class_opts),
        duration_s=duration_s, engine_version=engine_version,
    )


def _plain(n: int, duration_s: float, **kw) -> StackRunRow:
    return _row({"sigma_clip": True}, n=n, duration_s=duration_s, **kw)


def _drizzled(n: int, duration_s: float, **kw) -> StackRunRow:
    return _row({"drizzle": True, "drizzle_reject": True},
                n=n, duration_s=duration_s, **kw)


def _price(runs, **kw):
    params = {
        "scale": 1.5, "n_frames": 1000, "canvas_px": _CANVAS,
        "cost_class": "drizzle+reject", "plain_cost_class": "sigma-clip",
        "engine_version": "0.494.6",
    }
    params.update(kw)
    return price_auto_drizzle(runs, **params)


# --- the ordinary case: only plain runs exist, so the ratio fills in ---------

def test_the_drizzle_estimate_is_the_plain_rate_times_the_measured_ratio():
    # 800 s over 100 subs = 8 s a sub; 1,000 subs at ×7.3 is the drizzled run.
    cost = _price([_plain(100, 800.0)])
    assert cost.plain_seconds == pytest.approx(8000.0)
    assert cost.drizzle_seconds == pytest.approx(8000.0 * DRIZZLE_COST_RATIO["drizzle+reject"])
    assert cost.measured is True
    assert cost.basis_runs == 1


def test_a_single_pass_drizzle_is_priced_at_its_own_ratio():
    """The second pass is about 2.5× again, so a run whose rejection pass was
    declined for memory must not be quoted the two-pass number — the engine
    hands over the class that will *actually* run for exactly this reason."""
    single = _price([_plain(100, 800.0)], cost_class="drizzle")
    both = _price([_plain(100, 800.0)], cost_class="drizzle+reject")
    assert single.drizzle_seconds == pytest.approx(8000.0 * DRIZZLE_COST_RATIO["drizzle"])
    assert both.drizzle_seconds > single.drizzle_seconds * 2


# --- the better case: this target has been drizzled before -------------------

def test_a_comparable_drizzled_run_is_read_directly_not_scaled():
    """A measurement of the job in hand beats a measurement of a different job
    times a constant — so with drizzled runs of its own, the ratio is unused."""
    cost = _price([_drizzled(100, 5000.0), _plain(100, 800.0)])
    assert cost.drizzle_seconds == pytest.approx(50000.0)   # 50 s a sub × 1,000
    assert cost.plain_seconds == pytest.approx(8000.0)      # its own plain runs
    assert cost.measured is True


def test_with_only_drizzled_runs_the_plain_comparison_is_derived():
    # The sentence's second half is the fact the owner asked for, so it is filled
    # in from the ratio rather than dropped (which would leave a bare "14 h").
    cost = _price([_drizzled(100, 5000.0)])
    assert cost.drizzle_seconds == pytest.approx(50000.0)
    assert cost.plain_seconds == pytest.approx(
        50000.0 / DRIZZLE_COST_RATIO["drizzle+reject"])


# --- the refusals ------------------------------------------------------------

def test_nothing_timed_means_no_number_at_all():
    """A fresh install, or a target stacked for the first time. Both halves are
    None together — half a comparison reads as a promise about the other half —
    and the surface then says "several times longer than a normal stack", which
    the measurement supports with no history."""
    cost = _price([])
    assert cost.drizzle_seconds is None
    assert cost.plain_seconds is None
    assert cost.measured is False
    assert cost.basis_runs == 0
    # The scale is still known and still said: it came from the decision itself.
    assert cost.scale == 1.5


def test_a_run_too_small_to_generalise_from_is_not_evidence():
    # MIN_BASIS_FRAMES: a three-frame run is mostly start-up cost.
    assert _price([_plain(3, 30.0)]).drizzle_seconds is None


def test_a_wildly_different_canvas_is_not_evidence():
    row = _plain(100, 800.0)
    row = StackRunRow(**{**row.__dict__, "canvas_w": 200, "canvas_h": 150})
    assert _price([row]).drizzle_seconds is None


def test_a_rate_from_another_build_is_used_but_flagged():
    """The same caveat the Stack form's own estimate carries: across one real
    upgrade the owner's identical restacks came back 8–36 % slower (observer
    issue #933), so the number is still shown and still says where it is from."""
    cost = _price([_plain(100, 800.0, engine_version="0.400.0")])
    assert cost.drizzle_seconds == pytest.approx(
        8000.0 * DRIZZLE_COST_RATIO["drizzle+reject"])
    assert cost.same_engine is False


def test_this_build_s_own_timings_win_and_are_not_flagged():
    cost = _price([_plain(100, 800.0), _plain(100, 1600.0, engine_version="0.400.0")])
    assert cost.plain_seconds == pytest.approx(8000.0)
    assert cost.same_engine is True


# --- the shape the job row carries ------------------------------------------

def test_the_payload_is_flat_and_always_holds_every_key():
    keys = {"scale", "drizzle_seconds", "plain_seconds", "basis_runs", "same_engine"}
    assert set(_price([]).as_dict()) == keys
    assert set(_price([_plain(100, 800.0)]).as_dict()) == keys


def test_the_measured_ratio_matches_what_the_engine_published():
    """One owner for the number. ``scripts/measure_drizzle_cost.py`` measured
    0.78 s a plain sub against 5.68 s for a ×1.5 drizzle with two-pass
    rejection, which is the ×7.3 the note multiplies by — if that measurement is
    ever re-run, this is the single place the ratio changes."""
    assert DRIZZLE_COST_RATIO["drizzle+reject"] == pytest.approx(5.68 / 0.78, rel=0.02)
    assert DRIZZLE_COST_RATIO["drizzle"] == pytest.approx(2.23 / 0.78, rel=0.02)
