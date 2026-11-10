"""seestack.diag.sky_falloff — measures a raw sub's centre-to-edge sky with the
camera's pedestal taken out (the slope over subs under different skies), reads
subs without writing anything, and publishes numbers only.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from seestack.diag import DiagnosticStopped, check_result_is_safe, registry
from seestack.diag import sky_falloff as sf

H, W = 240, 400


def _frame(rng, sky: float, vignette: float, pedestal: float = 500.0,
           gradient: float = 0.0) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W]
    ny = (yy - (H - 1) / 2) / ((H - 1) / 2)
    nx = (xx - (W - 1) / 2) / ((W - 1) / 2)
    r2 = (ny ** 2 + nx ** 2) / 2.0          # 0 at the centre, 1 in a corner
    img = pedestal + sky * (1.0 - vignette * r2) * (1.0 + gradient * nx)
    return img + rng.normal(0.0, 10.0, (H, W))


def _fits(rng, skies, vignette):
    ms = [sf.measure_frame(_frame(rng, s, vignette)) for s in skies]
    c = [m["centre"] for m in ms]
    return (sf._slope(c, [m["edge"] for m in ms]),
            sf._slope(c, [m["corner"] for m in ms]),
            float(np.median([m["edge"] / m["centre"] for m in ms])))


def test_no_vignette_reads_one():
    edge, corner, raw = _fits(np.random.default_rng(0), np.linspace(400, 3000, 25), 0.0)
    assert edge["slope"] == pytest.approx(1.0, abs=0.005)
    assert corner["slope"] == pytest.approx(1.0, abs=0.005)
    assert raw == pytest.approx(1.0, abs=0.005)


def test_a_vignette_is_measured_with_the_pedestal_taken_out():
    edge, corner, raw = _fits(np.random.default_rng(1), np.linspace(400, 3000, 25), 0.2)
    # Truth: the corner boxes average ~0.84 of the centre box, the side band
    # ~0.90. The raw ratio carries the 500-ADU pedestal and understates both.
    assert 0.87 < edge["slope"] < 0.92
    assert 0.82 < corner["slope"] < 0.87
    assert raw > edge["slope"] + 0.01
    assert edge["pedestal_over_median_centre"] == pytest.approx(500 / 2200, abs=0.03)


def test_a_sky_gradient_does_not_read_as_vignetting():
    rng = np.random.default_rng(2)
    ms = [sf.measure_frame(_frame(rng, s, 0.0, gradient=0.15))
          for s in np.linspace(400, 3000, 25)]
    c = [m["centre"] for m in ms]
    assert sf._slope(c, [m["edge"] for m in ms])["slope"] == pytest.approx(1.0, abs=0.01)
    # sky·0.3·0.95 / (pedestal + sky): 0.127 on the faintest sky here
    assert min(m["side_spread"] for m in ms) > 0.1


def _object_library(vignette: float, n_targets: int = 30, subs: int = 4, seed: int = 4):
    """``measure_frame`` results for a library whose every target puts its own
    nebula or galaxy — a different brightness and size each — in the middle
    of the frame, each target shot on nights of different sky."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    ny = (yy - (H - 1) / 2) / ((H - 1) / 2)
    nx = (xx - (W - 1) / 2) / ((W - 1) / 2)
    measured, groups = [], []
    for t in range(n_targets):
        bright, size = rng.uniform(100, 1500), rng.uniform(0.2, 0.5)
        blob = bright * np.exp(-(ny ** 2 + nx ** 2) / (2 * size ** 2))
        base = rng.uniform(800, 2500)
        for _ in range(subs):
            img = _frame(rng, base * rng.uniform(0.8, 1.25), vignette) + blob
            measured.append(sf.measure_frame(img))
            groups.append(t)
    return measured, groups


def test_a_central_object_on_every_target_does_not_read_as_vignetting():
    # v1 fitted one line through every target's subs, so each target's own
    # central light read as extra centre sky: this vignette-free library read
    # an edge slope of ~0.90 — a "10 % darker edge" that is not there.
    res = sf.summarise(*_object_library(0.0))
    assert res["edge_over_centre_slope"]["slope"] == pytest.approx(1.0, abs=0.01)
    assert res["corner_over_centre_slope"]["slope"] == pytest.approx(1.0, abs=0.01)
    assert res["edge_over_centre_slope"]["pairs"] >= sf.MIN_PAIRS
    assert res["edge_over_centre_slope"]["targets"] == res["targets_measured"] == 30
    # the pooled (v1) fit is still published beside it, and is what was biased
    assert res["edge_over_centre_pooled"]["slope"] < 0.97


def test_a_real_vignette_is_still_measured_under_central_objects():
    res = sf.summarise(*_object_library(0.2))
    edge = res["edge_over_centre_slope"]
    assert 0.87 < edge["slope"] < 0.92
    assert edge["low"] <= edge["slope"] <= edge["high"]
    assert 0.82 < res["corner_over_centre_slope"]["slope"] < 0.87
    assert len(res["rings_over_centre_slope"]) == len(sf.RING_EDGES) - 1
    inner, outer = res["rings_over_centre_slope"][0], res["rings_over_centre_slope"][-1]
    assert inner["slope"] > outer["slope"]


def test_pairs_across_targets_or_with_alike_skies_are_not_used():
    # Two subs per target, each pair's skies 1 % apart: no usable pair at all,
    # however many targets — the slope is withheld, not guessed.
    rng = np.random.default_rng(5)
    measured, groups = [], []
    for t in range(40):
        for k in range(2):
            measured.append(sf.measure_frame(_frame(rng, 1000 + 500 * t + 10 * k, 0.2)))
            groups.append(t)
    res = sf.summarise(measured, groups)
    assert res["edge_over_centre_slope"] is None
    # ... while one line through every target (v1's) still finds one
    assert res["edge_over_centre_pooled"] is not None


def test_too_few_or_too_alike_skies_give_no_slope():
    rng = np.random.default_rng(3)
    edge, _, _ = _fits(rng, np.linspace(400, 3000, 10), 0.2)       # < 20 subs
    assert edge is None
    edge, _, _ = _fits(rng, np.linspace(1000, 1050, 25), 0.2)      # one sky
    assert edge is None


def test_a_tiny_or_empty_frame_is_skipped():
    assert sf.measure_frame(np.ones((20, 20))) is None
    assert sf.measure_frame(np.full((100, 100), np.nan)) is None


def test_spread_is_even_and_deterministic():
    assert sf._spread(list(range(10)), 4) == [0, 3, 6, 9]
    assert sf._spread([1, 2], 4) == [1, 2]


@pytest.fixture
def lib_and_incoming(tmp_path):
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize
    from tests.synth import write_seestar_fits

    inc = tmp_path / "incoming"
    for name in ("M 42", "M 31"):
        d = inc / f"{name}_sub"
        d.mkdir(parents=True)
        for i in range(6):
            write_seestar_fits(d / f"s{i}.fit", width=128, height=96, n_stars=5,
                               noise_seed=i, date_obs=f"2026-01-1{i}T03:00:00")
    lib = Library.open_or_create(tmp_path / "library")
    scan_and_organize(lib, inc, copy_to_cache=False)
    yield lib, inc
    lib.close()


def _digest(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def test_run_reads_subs_and_writes_nothing(lib_and_incoming):
    lib, inc = lib_and_incoming
    before = _digest(inc)
    seen = []
    res = sf.run(lib, progress=lambda *a: seen.append(a))
    assert _digest(inc) == before
    check_result_is_safe(res)
    text = json.dumps(res)
    assert "M 42" not in text and "incoming" not in text
    assert res["subs_sampled"] == 2 * sf.SUBS_PER_TARGET
    assert res["subs_measured"] == res["subs_sampled"]
    assert res["edge_over_centre_slope"] is None          # 8 subs: too few
    assert res["edge_over_centre_raw"]["median"] > 0
    assert seen and seen[-1][1] == seen[-1][2] == res["subs_sampled"]


def test_run_stops_when_asked(lib_and_incoming):
    lib, _ = lib_and_incoming
    with pytest.raises(DiagnosticStopped):
        sf.run(lib, should_stop=lambda: True)


def test_ready_and_registered(lib_and_incoming, tmp_path):
    from seestack.io.library import Library

    lib, _ = lib_and_incoming
    assert sf.ready(lib)
    empty = Library.open_or_create(tmp_path / "empty")
    try:
        assert not sf.ready(empty)
    finally:
        empty.close()
    assert ("sky_falloff", 2) in [(d.name, d.version) for d in registry()]
