"""The "build the night-by-night reel" offer — the missing affordance on a
target that holds the reel's subs but was stacked once.

Two layers: the pure decision (:mod:`webapp.reeloffer`) and the one endpoint
that carries it (``/deepening-reel/info``'s unavailable branch).
"""

from __future__ import annotations

import json

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp.capture_nights import capture_night_count
from webapp.reeloffer import MIN_REEL_NIGHTS, night_reel_offer

# Three ordinary nights of Seestar hours — the shape the offer exists for.
THREE_NIGHTS = [
    "2026-05-01T22:00:00Z", "2026-05-01T23:00:00Z",
    "2026-05-02T21:00:00Z", "2026-05-02T22:00:00Z",
    "2026-05-03T22:00:00Z",
]
THREE_NIGHTS_JSON = json.dumps(THREE_NIGHTS)


class _Run:
    """The handful of run-row attributes the decision reads."""

    def __init__(self, *, id=7, n_frames_used=900, options_json="{}",
                 capture_hours_json=THREE_NIGHTS_JSON, duration_s=1500.0):
        self.id = id
        self.n_frames_used = n_frames_used
        self.options_json = options_json
        self.capture_hours_json = capture_hours_json
        self.duration_s = duration_s


# --- the pure decision -------------------------------------------------------

def test_one_stack_of_three_nights_is_offered_the_reel():
    offer = night_reel_offer(_Run(), n_stacks=1)
    assert offer == {"run_id": 7, "nights": 3, "subs": 900,
                     "last_duration_s": 1500.0}


def test_a_target_with_a_cross_run_reel_is_not_offered_one():
    # Two steps already animate as "night after night" — there is nothing to
    # offer, and the card is showing the reel rather than this.
    assert night_reel_offer(_Run(), n_stacks=2) is None
    # And a target with no stack at all has nothing to repeat.
    assert night_reel_offer(None, n_stacks=0) is None


def test_a_run_that_already_has_its_own_reel_is_not_offered_another():
    assert night_reel_offer(_Run(), n_stacks=1, has_reel=True) is None


def test_two_nights_is_not_a_progression():
    two = json.dumps(["2026-05-01T22:00:00Z", "2026-05-02T22:00:00Z"])
    assert night_reel_offer(_Run(capture_hours_json=two), n_stacks=1) is None
    assert MIN_REEL_NIGHTS == 3


def test_a_run_that_never_recorded_its_hours_says_nothing():
    # Pre-schema-19: the nights cannot be *shown*, and a guess is worse than
    # silence.
    assert night_reel_offer(_Run(capture_hours_json=None), n_stacks=1) is None
    assert night_reel_offer(_Run(capture_hours_json="not json"), n_stacks=1) is None


def test_lucky_imaging_declines_because_it_reorders_the_frames():
    # `plan_capture_nights` refuses a frame list sorted by FWHM, so the reel
    # would fall back to evenly-spaced snapshots — not what the card promises.
    lucky = json.dumps({"lucky_fraction": 0.5})
    assert night_reel_offer(_Run(options_json=lucky), n_stacks=1) is None
    # The full-frame default is not a re-order.
    keeps_all = json.dumps({"lucky_fraction": 1.0})
    assert night_reel_offer(_Run(options_json=keeps_all), n_stacks=1) is not None


def test_the_night_count_must_hold_under_both_bucketings():
    """The card's number is the owner's (local noon); the stacker's is UTC noon.

    A run straddling that boundary can be three nights to one and two to the
    other, and the offer only speaks where both agree — otherwise it promises a
    night-by-night clip that `plan_capture_nights` would decline to label.
    """
    hours = ["2026-05-01T18:00:00Z", "2026-05-02T06:00:00Z",
             "2026-05-03T06:00:00Z"]
    # The premise, asserted rather than assumed.
    assert capture_night_count(json.dumps(hours), 180.0) == 3
    assert capture_night_count(json.dumps(hours), None) == 2
    run = _Run(capture_hours_json=json.dumps(hours))
    assert night_reel_offer(run, n_stacks=1, lon_deg=180.0) is None
    # The same run without a site is simply two nights, and declines for that.
    assert night_reel_offer(run, n_stacks=1) is None


def test_an_untimed_run_drops_the_duration_rather_than_guessing():
    for bad in (None, 0.0, -3.0):
        offer = night_reel_offer(_Run(duration_s=bad), n_stacks=1)
        assert offer is not None
        assert offer["last_duration_s"] is None


# --- the endpoint ------------------------------------------------------------

def _add_stack(root, safe: str, name: str, *, subs: int, when: str,
               hours: list[str] | None, duration_s: float | None = None,
               options_json: str = "{}", seed: int = 1) -> int:
    """Write a synthetic linear stack FITS and register a run for it."""
    lib = Library.open_or_create(root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        h = w = 48
        rng = np.random.default_rng(seed)
        chan = (0.1 + 0.04 * rng.standard_normal((h, w))).astype(np.float32)
        cube = np.stack([chan, chan * 0.7, chan * 0.5]).astype(np.float32)
        fp = tdir / f"{name}.fits"
        fits.PrimaryHDU(data=cube).writeto(fp, overwrite=True)
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=when, output_basename=name,
                fits_path=str(fp), tiff_path=None, preview_path=None,
                n_frames_used=subs, canvas_h=h, canvas_w=w,
                coverage_min=1, coverage_max=3, options_json=options_json,
                capture_start_utc=(hours[0] if hours else None),
                capture_end_utc=(hours[-1] if hours else None),
                capture_hours_json=(json.dumps(hours) if hours else None),
                duration_s=duration_s,
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def test_info_offers_the_reel_on_a_single_multi_night_stack(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_stack(solved_library, safe, "master", subs=900,
                        when="2026-05-04T00:00:00Z", hours=THREE_NIGHTS,
                        duration_s=1500.0)
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is False
    assert body["n_stacks"] == 1
    assert body["reel_offer"] == {"run_id": run_id, "nights": 3, "subs": 900,
                                  "last_duration_s": 1500.0}


def test_info_offers_nothing_on_a_single_stack_of_one_night(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "master", subs=120,
               when="2026-05-04T00:00:00Z",
               hours=["2026-05-01T22:00:00Z", "2026-05-01T23:00:00Z"])
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is False
    assert body["reel_offer"] is None


def test_info_offers_nothing_once_the_run_has_its_own_reel(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "master", subs=900,
               when="2026-05-04T00:00:00Z", hours=THREE_NIGHTS)
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
    finally:
        lib.close()
    (tdir / "master_progress.webp").write_bytes(b"not really a reel")
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["reel_offer"] is None


def test_the_offer_disappears_once_a_second_stack_makes_a_real_reel(
        client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "master", subs=300,
               when="2026-05-02T00:00:00Z",
               hours=THREE_NIGHTS[:3], seed=1)
    _add_stack(solved_library, safe, "master2", subs=900,
               when="2026-05-04T00:00:00Z", hours=THREE_NIGHTS, seed=2)
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is True
    # The unavailable branch is the only one that carries an offer.
    assert "reel_offer" not in body
