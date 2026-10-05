"""How the webapp tests' app is brought up, factored out of their conftest.

Lives beside ``synth.py`` — in ``tests/``, which the webapp conftest puts on
``sys.path`` — because ``tests/webapp/`` is not importable, and a boot rule this
load-bearing should be testable rather than only readable
(``tests/webapp/test_client_fixture_watcher.py``).
"""

from __future__ import annotations

import json
from pathlib import Path

#: The app's config filename, mirrored rather than imported so this module stays
#: importable without pulling the webapp in at collection time.
CONFIG_BASENAME = "config.json"


def disable_watcher_before_boot(data_root: Path) -> bool:
    """Write ``watcher_enabled: false`` into the state folder an app rooted at
    ``data_root`` will boot from. ``True`` when it wrote, ``False`` when the
    caller had already supplied a config of its own.

    **Why before the boot and not after.** Turning the watcher off one request
    *after* ``TestClient(app)`` has run the lifespan left a real race, and it
    failed a pre-merge suite: ``Watcher._run`` polls immediately on startup, and
    every webapp test's ``incoming/`` holds the two folders ``_make_incoming``
    writes, so a startup poll could enqueue a batch *while a test body was
    running*. The scan it triggered called ``refresh_target_stats``, which
    recomputes ``last_stack_preview`` from the project's run list — read before
    the test's own registered run existed and written after it, so the stamp
    landed NULL, became unreadable, and ``current_picture_path`` fell through to
    a third-step ``open_target`` that one test explicitly forbids
    (``test_a_healthy_library_never_opens_a_project_for_the_fallback``,
    ``assert ['NGC_7000'] == []``). Under ``-n 4`` the window is a function of
    CPU contention, which is why adding unrelated tests was enough to open it
    once, and why it read as "that one flaky webapp test" rather than as a wrong
    ordering. Boot with the watcher already off and there is no startup poll to
    race with.

    ``SettingsStore`` fills every other field from the model's defaults, so this
    changes exactly the one setting the fixture was already setting. It never
    overwrites an existing ``config.json``, so the upgrade-safety tests that hand
    the app a hand-written config still do.
    """
    cfg_path = Path(data_root) / "state" / CONFIG_BASENAME
    if cfg_path.exists():
        return False
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"watcher_enabled": False}))
    return True
