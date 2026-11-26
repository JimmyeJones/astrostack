"""The app must boot when the data disk is full or read-only.

Full audit 2026-11-26 (backend.md finding 6): ``SettingsStore.__init__`` re-saved
``config.json`` on every boot and let the ``OSError`` escape the lifespan, so a
pool or quota that filled during a big stack left the container restart-looping
with the Storage page — the friendly way to free space — unreachable.
"""

from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from webapp import config as config_mod
from webapp.config import SettingsStore


def _full_disk(*_a, **_kw):
    raise OSError(errno.ENOSPC, "No space left on device")


def test_boot_survives_a_config_save_that_hits_a_full_disk(tmp_path, monkeypatch):
    SettingsStore(str(tmp_path))  # a normal first boot writes config.json
    cfg = tmp_path / "state" / config_mod.CONFIG_FILENAME
    data = json.loads(cfg.read_text())
    data["auto_stack"] = False  # the owner's own value (default is on), to prove it loads
    cfg.write_text(json.dumps(data))  # not byte-identical to what save() writes
    before = cfg.read_bytes()

    monkeypatch.setattr(config_mod, "write_text_durably", _full_disk)
    store = SettingsStore(str(tmp_path))  # used to raise OSError
    assert store.get().auto_stack is False
    assert cfg.read_bytes() == before  # the owner's file is untouched

    # A later real settings change still reports the failure — only boot is lenient.
    with pytest.raises(OSError):
        store.update({"auto_stack": True})


def test_boot_does_not_rewrite_an_identical_config(tmp_path, monkeypatch):
    SettingsStore(str(tmp_path))
    calls = []
    monkeypatch.setattr(config_mod, "write_text_durably",
                        lambda *a, **kw: calls.append(a))
    SettingsStore(str(tmp_path))
    assert calls == []


def test_boot_still_writes_a_config_that_needs_it(tmp_path):
    # Fresh install: no file yet → written.
    SettingsStore(str(tmp_path))
    cfg = tmp_path / "state" / config_mod.CONFIG_FILENAME
    assert cfg.exists()
    # A file with an invalid field is repaired on disk, as before.
    data = json.loads(cfg.read_text())
    data["auto_stack"] = "not-a-bool-at-all"
    cfg.write_text(json.dumps(data))
    SettingsStore(str(tmp_path))
    assert json.loads(cfg.read_text())["auto_stack"] in (True, False)


def test_the_app_answers_health_on_a_full_disk(data_root: Path, monkeypatch):
    """End to end: the lifespan completes and the API answers."""
    from fastapi.testclient import TestClient

    from tests.webapp.conftest import disable_watcher_before_boot
    from webapp.main import create_app

    monkeypatch.setenv("ASTROSTACK_DATA", str(data_root))
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    disable_watcher_before_boot(data_root)
    cfg = data_root / "state" / config_mod.CONFIG_FILENAME
    if cfg.exists():  # make the boot-time save non-trivial
        cfg.write_text(json.dumps(json.loads(cfg.read_text())))
    monkeypatch.setattr(config_mod, "write_text_durably", _full_disk)
    app = create_app()
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/settings").status_code == 200
