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
