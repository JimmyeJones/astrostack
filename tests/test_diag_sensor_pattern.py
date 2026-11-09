"""seestack.diag.sensor_pattern — finds a camera-fixed colour pattern, per
sensor temperature, from subs of different targets, without aligning them.

The fixture plants a smooth colour blotch on the red photosites of every
*cold* sub of eight unrelated targets; the warm subs carry none. The
diagnostic must report the pattern in the cold range and not in the warm one,
and its result must hold nothing but numbers and labels.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from seestack.diag import check_result_is_safe, registry
from seestack.diag import sensor_pattern as sp
from tests.synth import make_star_field, write_seestar_fits

W, H = 384, 256
N_TARGETS = 8
SUBS = 12  # per target: 6 cold, 6 warm


def _blotch() -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    return (np.exp(-(((xx - 0.3 * W) / (0.18 * W)) ** 2 + ((yy - 0.4 * H) / (0.25 * H)) ** 2))
            - np.exp(-(((xx - 0.72 * W) / (0.15 * W)) ** 2 + ((yy - 0.6 * H) / (0.2 * H)) ** 2)))


@pytest.fixture
def library(tmp_path):
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    incoming = tmp_path / "incoming"
    blotch = _blotch()
    for t in range(N_TARGETS):
        d = incoming / f"NGC {7000 + t}_sub"
        d.mkdir(parents=True)
        for i in range(SUBS):
            data = make_star_field(width=W, height=H, n_stars=60, seed=1000 * t + 17,
                                   noise_seed=1000 * t + i).astype(np.float64)
            if i % 2 == 0:  # cold: the camera adds a colour blotch on red sites
                data[0::2, 0::2] += 120.0 * blotch[0::2, 0::2]
            write_seestar_fits(d / f"f{i:03d}.fit", width=W, height=H,
                               data=np.clip(data, 0, 65535).astype(np.uint16),
                               date_obs=f"2026-01-{10 + t:02d}T03:{i:02d}:00")
    lib = Library.open_or_create(tmp_path / "library")
    scan_and_organize(lib, incoming, copy_to_cache=False)
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            for f in proj.iter_frames():
                cold = int(Path(f.source_path).stem[1:]) % 2 == 0
                proj.update_frame(f.id, accept=1, sensor_temp_c=-3.0 if cold else 27.0)
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)
    yield lib
    lib.close()


def _row(result, label):
    return next(r for r in result["by_temperature"] if r["range"] == label)


def test_finds_the_pattern_only_where_it_was_planted(library):
    result = sp.run(library)
    cold, warm = _row(result, "below 0 C"), _row(result, "25 C and up")
    assert cold["measured"] and warm["measured"]
    assert cold["targets"] == N_TARGETS and warm["targets"] == N_TARGETS
    assert cold["repeat_r"] > 0.8 and cold["ratio"] > 3, cold
    # No pattern planted: ratio about 1 (what is left is noise) and the two
    # halves do not agree. A uniform colour cast must not count as a pattern.
    assert warm["ratio"] < 1.5 and abs(warm["repeat_r"]) < 0.3, warm
    # Empty ranges say so instead of inventing a number.
    assert _row(result, "5 to 10 C") == {
        "range": "5 to 10 C", "subs_available": 0, "targets_available": 0,
        "nights": 0, "measured": False}


def test_result_is_json_numbers_and_labels_only(library):
    result = sp.run(library)
    check_result_is_safe(result)
    text = json.dumps(result)
    assert "incoming" not in text and "/" not in text.replace("n/a", "")


def test_too_few_targets_declines_rather_than_guessing(library):
    keep = {e.safe_name for e in library.list_targets()[:sp.MIN_TARGETS - 1]}
    by_target = {}
    for e in library.list_targets():
        if e.safe_name in keep:
            proj = library.open_target(e.safe_name)
            by_target[e.safe_name] = list(proj.iter_frames(accepted_only=True))
            proj.close()
    assert sp._measure(by_target, np.random.default_rng(0), lambda: None, None) is None


def test_it_stops_when_asked(library):
    from seestack.diag import DiagnosticStopped

    with pytest.raises(DiagnosticStopped):
        sp.run(library, should_stop=lambda: True)


def test_ready_needs_subs_from_enough_targets(library, tmp_path):
    from seestack.io.library import Library

    assert sp.ready(library)
    empty = Library.open_or_create(tmp_path / "empty-library")
    try:
        assert not sp.ready(empty)
    finally:
        empty.close()


def test_registry_names_are_unique_and_versioned():
    names = [(d.name, d.version) for d in registry()]
    assert len(names) == len(set(names))
    assert all(v >= 1 for _, v in names)


@pytest.mark.parametrize("bad", [
    {"x": "/mnt/tank/astro/incoming/M 31_sub/a.fit"},
    {"x": ["fine", "C:\\Users\\someone\\a.fit"]},
    {"SITELAT": 1.0},
    {"note": "site_lon was 12.3"},
])
def test_safety_check_refuses_paths_and_locations(bad):
    with pytest.raises(ValueError):
        check_result_is_safe(bad)
