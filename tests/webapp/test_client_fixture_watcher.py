"""The webapp ``client`` fixture must boot with the watcher **already off**.

Not a product test — a test of the harness every other webapp test runs on, and
it exists because the ordering was wrong and cost a run. The fixture used to turn
the watcher off one request *after* ``TestClient(app)`` had run the lifespan,
which left a window: ``Watcher._run`` polls immediately on startup, every webapp
test's ``incoming/`` holds two drop folders, and a startup poll could enqueue a
scan *while a test body was running*. That scan's ``refresh_target_stats``
recomputes ``last_stack_preview`` from the project's run list — read before the
test's own registered run existed and written after it — so the stamp landed
NULL and ``current_picture_path`` fell through to the ``open_target`` that
``test_a_healthy_library_never_opens_a_project_for_the_fallback`` forbids
(``assert ['NGC_7000'] == []``). Under ``-n 4`` the window is CPU contention, so
it surfaced as "that one flaky webapp test" rather than as a wrong ordering.

Pinned deterministically — the race itself is not reproducible on demand, but
"what does the app boot with?" is a fact about the state folder, and that is what
the fix changes. Both halves matter: the write has to happen, and it must not
trample a config a test supplied for itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from webapp_boot import CONFIG_BASENAME, disable_watcher_before_boot


def _booted_settings(root: Path):
    """What an app rooted here would load at startup — the real loader, so this
    cannot pass on a config file the app would have ignored or reset."""
    from webapp.config import SettingsStore

    return SettingsStore(str(root)).get()


def test_the_app_boots_with_the_watcher_off(tmp_path):
    assert disable_watcher_before_boot(tmp_path) is True
    assert _booted_settings(tmp_path).watcher_enabled is False


def test_without_it_the_app_would_boot_with_the_watcher_on(tmp_path):
    """The premise: ``watcher_enabled`` defaults to **on**, so the pre-boot write
    is doing real work and this file is not asserting a default."""
    assert _booted_settings(tmp_path).watcher_enabled is True


def test_it_changes_only_that_one_setting(tmp_path):
    """Every other field still comes from the model's defaults, so booting from
    this file is not a second source of truth for settings."""
    from webapp.config import Settings

    disable_watcher_before_boot(tmp_path)
    booted = _booted_settings(tmp_path)
    defaults = Settings(data_root=str(tmp_path))
    differing = {
        name for name in Settings.model_fields
        if getattr(booted, name) != getattr(defaults, name)
    }
    assert differing == {"watcher_enabled"}, differing


def test_it_never_overwrites_a_config_the_test_supplied(tmp_path):
    """The upgrade-safety tests hand the app a hand-written ``config.json`` on
    purpose; silently rewriting it would make those tests measure this fixture
    instead of the loader."""
    cfg = tmp_path / "state" / CONFIG_BASENAME
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"watcher_enabled": True, "auto_stack": True}))

    assert disable_watcher_before_boot(tmp_path) is False
    assert json.loads(cfg.read_text()) == {"watcher_enabled": True,
                                           "auto_stack": True}


def test_the_client_fixture_uses_it(client):
    """The link between the helper above and the fixture every other file gets:
    the app the fixture yields reports the watcher off."""
    assert client.get("/api/settings").json()["watcher_enabled"] is False
