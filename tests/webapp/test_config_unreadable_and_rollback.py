"""``config.json`` survives a damaged file and a rollback.

Full audit 2026-11-26 (backend.md §10, §11), filed as a 🟠 Bugs entry:

(b) a truncated or garbled ``config.json`` booted on defaults — auto-stack on,
    the password off, the folders reset — and ``SettingsStore.__init__``
    overwrote it at once, so nothing of the owner's settings could be recovered;
(c) a top-level key the running build did not know (a setting a newer version
    added, seen after a rollback) was dropped by the next save, so rolling back
    and forward again lost every setting added in between.
"""

from __future__ import annotations

import json

from webapp import config as config_mod
from webapp.config import Settings, SettingsStore


def _cfg(tmp_path):
    return tmp_path / "state" / config_mod.CONFIG_FILENAME


def _owner_config(tmp_path) -> str:
    """A config the way the owner's looks: automation off, a password set."""
    SettingsStore(str(tmp_path))
    cfg = _cfg(tmp_path)
    data = json.loads(cfg.read_text())
    data.update(auto_stack=False, auto_edit_on_autostack=False,
                auth_password_hash="pbkdf2_sha256$1$salt$hash")
    text = json.dumps(data, indent=2)
    cfg.write_text(text)
    return text


def test_a_truncated_config_is_kept_and_not_overwritten(tmp_path):
    text = _owner_config(tmp_path)
    cfg = _cfg(tmp_path)
    damaged = text[: len(text) // 2]  # a crash mid-copy
    cfg.write_text(damaged)

    store = SettingsStore(str(tmp_path))

    # The damaged file is left exactly as it was …
    assert cfg.read_text() == damaged
    # … and a copy of it is kept beside it for recovery by hand.
    copies = sorted(cfg.parent.glob("config.json.unreadable-*"))
    assert len(copies) == 1 and copies[0].read_text() == damaged
    assert store.unreadable_copy == copies[0]

    # Nothing unattended runs on settings the owner never chose.
    s = store.get()
    assert s.watcher_enabled is False
    assert s.auto_stack is False
    assert s.auto_edit_on_autostack is False
    assert s.data_root == str(tmp_path)


def test_a_restart_loop_on_the_same_damaged_file_keeps_one_copy(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"auto_stack": fal')
    SettingsStore(str(tmp_path))
    SettingsStore(str(tmp_path))
    SettingsStore(str(tmp_path))
    assert len(list(cfg.parent.glob("config.json.unreadable-*"))) == 1


def test_an_empty_or_non_object_config_counts_as_unreadable(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.parent.mkdir(parents=True)
    for body in ("", "[1, 2, 3]", "null"):
        cfg.write_text(body)
        store = SettingsStore(str(tmp_path))
        assert cfg.read_text() == body
        assert store.get().auto_stack is False


def test_the_first_saved_change_after_a_damaged_boot_writes_a_fresh_file(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{ not json")
    store = SettingsStore(str(tmp_path))
    store.update({"watcher_enabled": True})
    data = json.loads(cfg.read_text())
    assert data["watcher_enabled"] is True
    assert data["auto_stack"] is False  # what the owner was shown, not the default
    # The kept copy is untouched by the save.
    (copy,) = cfg.parent.glob("config.json.unreadable-*")
    assert copy.read_text() == "{ not json"


def test_a_setting_this_build_does_not_know_survives_boot_and_save(tmp_path):
    SettingsStore(str(tmp_path))
    cfg = _cfg(tmp_path)
    data = json.loads(cfg.read_text())
    data["auto_qc"] = False
    data["a_setting_from_a_newer_version"] = {"nested": [1, 2]}
    data["another_newer_flag"] = True
    cfg.write_text(json.dumps(data, indent=2))

    store = SettingsStore(str(tmp_path))  # the rolled-back build boots
    assert "a_setting_from_a_newer_version" not in store.get().model_dump()
    on_disk = json.loads(cfg.read_text())
    assert on_disk["a_setting_from_a_newer_version"] == {"nested": [1, 2]}
    assert on_disk["another_newer_flag"] is True

    store.update({"cpu_workers": 3})  # a settings change on the old build
    on_disk = json.loads(cfg.read_text())
    assert on_disk["cpu_workers"] == 3 and on_disk["auto_qc"] is False
    assert on_disk["a_setting_from_a_newer_version"] == {"nested": [1, 2]}
    assert on_disk["another_newer_flag"] is True

    # Rolling forward: the newer build reads its key back.
    assert json.loads(cfg.read_text())["another_newer_flag"] is True


def test_a_config_with_unknown_keys_is_not_rewritten_on_boot(tmp_path, monkeypatch):
    SettingsStore(str(tmp_path))
    cfg = _cfg(tmp_path)
    data = json.loads(cfg.read_text())
    data["a_setting_from_a_newer_version"] = 7
    cfg.write_text(json.dumps(data, indent=2))
    SettingsStore(str(tmp_path))  # first boot may normalise the layout once
    calls = []
    monkeypatch.setattr(config_mod, "write_text_durably",
                        lambda *a, **kw: calls.append(a))
    SettingsStore(str(tmp_path))
    assert calls == []


def test_a_valid_config_with_one_bad_field_is_still_repaired_in_place(tmp_path):
    """The per-field safety net is unchanged: a readable file with one invalid
    value drops just that value and is saved — no ``unreadable`` copy."""
    SettingsStore(str(tmp_path))
    cfg = _cfg(tmp_path)
    data = json.loads(cfg.read_text())
    data.update(auto_stack=False, cpu_workers=-3)
    cfg.write_text(json.dumps(data))
    s = SettingsStore(str(tmp_path)).get()
    assert s.auto_stack is False and s.cpu_workers == Settings().cpu_workers
    assert not list(cfg.parent.glob("config.json.unreadable-*"))
    assert json.loads(cfg.read_text())["cpu_workers"] == Settings().cpu_workers
