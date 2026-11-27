"""The 1.0 roadmap's real-data checks (R1, R2, R5, R6) and the one-file report.

Each check runs on a small synthetic library shaped like the owner's (several
targets of raw Seestar subs) and must (a) measure what it claims and (b) keep
its result to numbers and catalogue names.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from seestack.diag import check_result_is_safe, registry
from seestack.diag import hot_pixels as hp
from seestack.diag import library_inventory as inv
from seestack.diag import machine_speed as ms
from seestack.diag import registration_sharpness as rs
from tests.synth import make_star_field, write_seestar_fits

W, H = 384, 256
N_TARGETS = 6
SUBS = 10
# Photosites the "sensor" has stuck hot in every sub, whatever the target.
HOT = [(11, 20), (40, 101), (77, 300), (130, 31), (201, 222), (250, 377), (5, 5), (180, 60)]


def _build(tmp_path, *, hot: bool):
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    incoming = tmp_path / "incoming"
    for t in range(N_TARGETS):
        d = incoming / f"NGC {7000 + t}_sub"
        d.mkdir(parents=True)
        for i in range(SUBS):
            data = make_star_field(width=W, height=H, n_stars=60, seed=1000 * t + 17,
                                   noise_seed=1000 * t + i).astype(np.float64)
            if hot:
                for y, x in HOT:
                    data[y, x] += 20000.0
            write_seestar_fits(d / f"f{i:03d}.fit", width=W, height=H,
                               data=np.clip(data, 0, 65535).astype(np.uint16),
                               date_obs=f"2026-01-{10 + t:02d}T03:{i:02d}:00")
    lib = Library.open_or_create(tmp_path / "library")
    scan_and_organize(lib, incoming, copy_to_cache=False)
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            for k, f in enumerate(proj.iter_frames()):
                proj.update_frame(f.id, accept=1 if k else 0,
                                  reject_reason=None if k else "too few stars: 3",
                                  sensor_temp_c=12.0, fwhm_px=2.0, exposure_s=10.0)
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)
    return lib


@pytest.fixture
def library(tmp_path):
    lib = _build(tmp_path, hot=True)
    yield lib
    lib.close()


def test_registry_holds_the_new_checks_once():
    names = [d.name for d in registry()]
    for n in ("library_inventory", "machine_speed", "hot_pixel_census",
              "registration_sharpness"):
        assert names.count(n) == 1


def test_inventory_counts_the_library(library):
    r = inv.run(library)
    check_result_is_safe(r)
    assert r["totals"]["targets"] == N_TARGETS
    assert r["totals"]["subs"] == N_TARGETS * SUBS
    assert r["totals"]["accepted"] == N_TARGETS * (SUBS - 1)
    assert r["set_aside_reasons"] == {"too few stars": N_TARGETS}
    t = r["targets"][0]
    assert t["nights"] == 1 and t["hours"] == pytest.approx((SUBS - 1) * 10 / 3600, abs=0.01)
    assert t["latest_stack"] is None


def test_reason_categories_never_carry_a_path():
    assert inv._reason_category("unreadable: /data/incoming/x.fit") == "unreadable"
    assert inv._reason_category("/data/incoming/x.fit broke") == "other"
    assert inv._reason_category(None) is None


def test_machine_speed_times_real_subs(library):
    r = ms.run(library)
    check_result_is_safe(r)
    assert r["machine"]["cpu_count"] >= 1
    assert r["subs_timed"] >= 4
    assert set(r["seconds_per_sub_median"]) == {"read", "debayer", "sky_flatten", "qc"}


def test_hot_pixel_census_finds_planted_defects_and_agrees_across_targets(library):
    r = hp.run(library)
    check_result_is_safe(r)
    assert r["measured"]
    assert r["hot_in_both"] >= len(HOT) - 1, r
    assert r["hot_agreement_jaccard"] >= 0.6, r


def test_hot_pixel_census_finds_none_on_a_clean_sensor(tmp_path):
    lib = _build(tmp_path, hot=False)
    try:
        r = hp.run(lib)
    finally:
        lib.close()
    assert r["measured"]
    assert r["hot_in_both"] <= 2, r


def test_registration_sharpness_compares_a_stack_with_its_subs(library, tmp_path):
    from astropy.io import fits

    from seestack.io.project import StackRunRow

    yy, xx = np.mgrid[0:600, 0:600]
    img = np.full((600, 600), 100.0)
    rng = np.random.default_rng(1)
    sigma = 4.0 / 2.3548  # FWHM 4 full-res px = 2 half-res px, like the subs' fwhm_px
    for _ in range(80):
        y, x = rng.uniform(30, 570, 2)
        img += 3000 * np.exp(-((yy - y) ** 2 + (xx - x) ** 2) / (2 * sigma ** 2))
    img += rng.normal(0, 3, img.shape)
    cube = np.stack([img, img, img]).astype(np.float32)
    fp = tmp_path / "stack.fits"
    fits.PrimaryHDU(cube).writeto(fp)
    entry = library.list_targets()[0]
    proj = library.open_target(entry.safe_name)
    try:
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-01-20T00:00:00Z", output_basename="s",
            fits_path=str(fp), tiff_path=None, preview_path=None, n_frames_used=SUBS - 1,
            canvas_h=600, canvas_w=600, coverage_min=1, coverage_max=SUBS - 1,
            options_json=json.dumps({"drizzle": False}), is_mosaic=False))
    finally:
        proj.close()
    r = rs.run(library)
    check_result_is_safe(r)
    row = next(t for t in r["targets"] if t["name"] == entry.name)
    assert row["stack_fwhm"] == pytest.approx(2.0, rel=0.2), row
    assert row["ratio_stack_to_subs"] == pytest.approx(1.0, rel=0.2), row
    assert "ratio_stack_to_single_sub_same_method" in row


def test_the_report_checks_never_run_on_their_own_after_an_update(tmp_path):
    from webapp import diagnostics as wd
    from webapp.config import Settings

    s = Settings(data_root=str(tmp_path / "data"))
    s.ensure_dirs()
    on_demand = {d.name for d in registry() if d.on_demand}
    assert {"library_inventory", "machine_speed", "hot_pixel_census",
            "registration_sharpness"} <= on_demand
    assert not on_demand & {d.name for d in wd.ready_to_run(s)}
