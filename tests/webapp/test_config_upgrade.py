"""Upgrade safety: an existing config.json must keep working after an upgrade.

These guard the "my NAS upgrades without trouble" contract — a deployed
config.json written by an older version must still load, keep its values, pick
up new fields at their defaults, and never silently reset everything just
because one field is now out of range or auth was added.
"""

from __future__ import annotations

import json
from pathlib import Path

from webapp.config import Settings, SettingsStore, _load_resilient


def _write_cfg(root: Path, cfg: dict) -> None:
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "config.json").write_text(json.dumps(cfg))


def test_old_config_loads_keeps_values_and_defaults_new_fields(tmp_path):
    _write_cfg(tmp_path, {
        "auto_stack": True, "cpu_workers": 6, "astap_fov_deg": 1.3,
        "watch_poll_interval_s": 300,
    })
    s = SettingsStore(str(tmp_path)).get()
    assert s.auto_stack is True and s.cpu_workers == 6      # existing values kept
    assert s.auth_password_hash == "" and s.auth_username == "admin"  # auth OFF
    assert s.astap_use_solve_hints is True                 # new field defaulted
    # New streak-keep flag defaults off → streaks still fully rejected as before.
    assert s.keep_streaked_frames is False
    # Auto-grade defaults off → an upgrade never starts rejecting frames on its
    # own; the sensitivity default is the balanced middle.
    assert s.auto_grade_frames is False
    assert s.auto_grade_sensitivity == "balanced"
    # New auto-edit-on-autostack flag defaults off → an upgrade never starts
    # seeding editor recipes on unattended stacks on its own.
    assert s.auto_edit_on_autostack is False
    # New auto-bind-calibration flag defaults off → an upgrade never starts
    # binding master darks/flats to unattended stacks on its own (a live
    # install's autonomous output is unchanged until the user opts in).
    assert s.auto_bind_calibration is False
    # New mixed-pointing guard defaults off → an upgrade never starts skipping an
    # unattended stack on its own; a bimodal batch stacks exactly as before until
    # the user opts in.
    assert s.mixed_pointing_guard is False
    # New walk-away minimum-frames floor defaults to 3 → an unattended auto-stack
    # holds a 1-2 frame target back (the single-frame speckle the owner reported)
    # instead of publishing it, while a real stack still goes through. Loads
    # cleanly from an old config that never wrote the field.
    assert s.auto_stack_min_frames == 3
    # New job-history cap defaults to the long-standing hard-coded value, so an
    # upgraded install keeps exactly as much job history as before.
    assert s.job_history_limit == 200
    # New observing-site fields default to "unset" so the Tonight planner is
    # inert on upgrade (it falls back to reading a frame header) and never
    # changes existing behaviour.
    assert s.site_lat is None and s.site_lon is None
    assert s.site_elevation_m == 0.0
    assert s.min_target_altitude_deg == 30


def test_observing_site_config_round_trips(tmp_path):
    # A config that sets a site location must load it back unchanged.
    _write_cfg(tmp_path, {
        "site_lat": 48.2, "site_lon": 11.6, "site_elevation_m": 520.0,
        "min_target_altitude_deg": 40,
    })
    s = SettingsStore(str(tmp_path)).get()
    assert s.site_lat == 48.2 and s.site_lon == 11.6
    assert s.site_elevation_m == 520.0 and s.min_target_altitude_deg == 40


def test_horizon_profile_defaults_empty_and_round_trips(tmp_path):
    # An old config without the field defaults to an empty (inert) horizon mask.
    _write_cfg(tmp_path, {"site_lat": 48.2, "site_lon": 11.6})
    s = SettingsStore(str(tmp_path)).get()
    assert s.horizon_profile == []
    # A config that sets one loads it back cleaned + ordered (never a whole reset).
    _write_cfg(tmp_path, {"horizon_profile": [[180, 25], [0, 15]]})
    s2 = SettingsStore(str(tmp_path)).get()
    assert s2.horizon_profile == [[0.0, 15.0], [180.0, 25.0]]


def test_malformed_horizon_profile_is_sanitised_not_wiped(tmp_path):
    # A hand-edited profile with a couple of bad points keeps the good ones (the
    # validator drops the junk) rather than resetting the whole config.
    _write_cfg(tmp_path, {"auto_stack": True, "horizon_profile": [
        [45, 30], ["junk"], [400, 50],
    ]})
    s = SettingsStore(str(tmp_path)).get()
    assert s.auto_stack is True  # untouched
    assert s.horizon_profile == [[40.0, 50.0], [45.0, 30.0]]  # cleaned + wrapped


def test_bad_site_lat_resets_only_that_field(tmp_path):
    # An out-of-range latitude must reset just that field, not wipe the config.
    _write_cfg(tmp_path, {"auto_stack": True, "site_lat": 200.0, "site_lon": 11.6})
    s = SettingsStore(str(tmp_path)).get()
    assert s.auto_stack is True and s.site_lon == 11.6  # untouched
    assert s.site_lat is None  # bad value reset to the "unset" default


def test_bad_auto_grade_sensitivity_resets_only_that_field(tmp_path):
    # A hand-edited/corrupt sensitivity must not wipe the rest of the config.
    _write_cfg(tmp_path, {"auto_stack": True, "auto_grade_frames": True,
                          "auto_grade_sensitivity": "extreme"})
    s = SettingsStore(str(tmp_path)).get()
    assert s.auto_stack is True and s.auto_grade_frames is True
    assert s.auto_grade_sensitivity == "balanced"  # only the bad field reset


def test_one_bad_field_does_not_wipe_the_rest(tmp_path):
    # watch_poll_interval_s below the new lower bound must reset ONLY that field.
    _write_cfg(tmp_path, {"auto_stack": True, "cpu_workers": 6,
                          "watch_poll_interval_s": 0})
    s = SettingsStore(str(tmp_path)).get()
    assert s.auto_stack is True and s.cpu_workers == 6     # untouched
    assert s.watch_poll_interval_s == Settings().watch_poll_interval_s  # reset to default


def test_malformed_json_falls_back_to_defaults(tmp_path):
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "config.json").write_text("{ not json")
    s = SettingsStore(str(tmp_path)).get()
    assert s.auth_password_hash == ""  # clean defaults, no crash


def test_load_resilient_keeps_valid_fields():
    txt = json.dumps({"auto_qc": False, "cpu_workers": -3})  # cpu_workers invalid
    s = _load_resilient(txt, "/tmp/x")
    assert s.auto_qc is False                       # valid field preserved
    assert s.cpu_workers == Settings().cpu_workers  # invalid one reset


def test_pre_drizzle_reject_stack_options_still_coerce(tmp_path):
    """A config (or saved per-target defaults / old run record) written before
    drizzle_reject existed must coerce cleanly, with the new knob defaulting
    to off — an in-place upgrade must not change what an old drizzle run does."""
    from webapp.schemas import coerce_stack_options

    old_payload = {"drizzle": True, "drizzle_scale": 2.0, "sigma_clip": True}
    opts = coerce_stack_options(old_payload)
    assert opts.drizzle is True and opts.drizzle_scale == 2.0
    assert opts.drizzle_reject is False  # new behaviour stays opt-in

    _write_cfg(tmp_path, {"default_stack_options": old_payload})
    s = SettingsStore(str(tmp_path)).get()
    assert s.default_stack_options == old_payload  # survives verbatim
