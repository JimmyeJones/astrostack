"""Regression tests: the one-click update path must not follow container-planted
symlinks into writes OUTSIDE ASTRO_DATA (audit 2026-09-30, section A).

Threat model (AGENTS.md §10 + the updater's own docstring): everything under
ASTRO_DATA is writable by the container, which runs as root inside and has no
password by default. ``scripts/update_agent.py`` (cron, root) and
``scripts/lib/restore-data.sh`` (called by ``rollback.sh``, root) run on the HOST.
Nothing the container can plant under ASTRO_DATA may cause a root write OUTSIDE
ASTRO_DATA. A directory or file symlink planted under state/ or library/ is that
lever.

Each test FAILED on main @ 024babd (the writes followed the symlink). v0.492.5
made the writers *refuse* a symlinked queue folder or log — the queue is opened
with ``O_NOFOLLOW`` at every step and a planted link is a ``SystemExit`` — so the
first test expects the refusal rather than a quiet carry-on, and all three assert
that nothing landed outside ASTRO_DATA.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _load_agent():
    spec = importlib.util.spec_from_file_location("update_agent", ROOT / "scripts" / "update_agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ua = _load_agent()


def test_ensure_queue_refuses_a_symlinked_queue_dir(tmp_path: Path) -> None:
    """state/updater planted as a symlink would make every status write land at
    the symlink's target — outside ASTRO_DATA. The helper must refuse to use the
    queue at all (a loud SystemExit, so the cron log says why) and write nothing."""
    data = tmp_path / "astro"
    (data / "state").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (data / "state" / "updater").symlink_to(outside)     # what the container plants
    clone = tmp_path / "clone"
    (clone / "scripts").mkdir(parents=True)
    (clone / ".env").write_text(f"ASTRO_DATA={data}\n")
    agent = ua.Agent(clone, tmp_path / "home", deploy_state=tmp_path / "home")

    with pytest.raises(SystemExit, match="refusing to use"):
        agent.ensure_queue()
    # …and the status writer goes through the same door, so it refuses too rather
    # than opening the path some other way.
    with pytest.raises(SystemExit, match="refusing to use"):
        agent.update_status(state="idle")
    escaped = list(outside.iterdir())
    assert not escaped, f"status write escaped ASTRO_DATA via symlinked queue: {escaped}"
    # Nothing was created *inside* ASTRO_DATA either — the link itself is left as
    # evidence, not replaced with a folder behind the container's back.
    assert (data / "state" / "updater").is_symlink()
    assert not list(tmp_path.glob("**/status.json"))


def test_run_logged_refuses_a_symlinked_log(tmp_path: Path) -> None:
    """state/updater/last.log planted as a symlink would make run_logged truncate
    and overwrite the symlink's target (a host file) with deploy output, as root."""
    data = tmp_path / "astro"
    q = data / "state" / "updater"
    q.mkdir(parents=True)
    victim = tmp_path / "host_file"
    victim.write_text("PRECIOUS")
    (q / "last.log").symlink_to(victim)
    clone = tmp_path / "clone"
    (clone / "scripts").mkdir(parents=True)
    (clone / ".env").write_text(f"ASTRO_DATA={data}\n")
    stub = clone / "scripts" / "deploy.sh"
    stub.write_text("#!/usr/bin/env bash\necho deploy-output\n")
    stub.chmod(0o755)
    agent = ua.Agent(clone, tmp_path / "home", deploy_state=tmp_path / "home")

    agent.run_logged([str(stub)])
    assert victim.read_text() == "PRECIOUS", "run_logged overwrote a host file via symlinked last.log"


def test_restore_data_does_not_follow_a_symlinked_target_dir(tmp_path: Path) -> None:
    """library/targets/<name> planted as a directory symlink would make
    restore-data.sh cp the backed-up DB THROUGH the symlink, writing
    (attacker-influenced config.json content and DB blobs) as root outside
    ASTRO_DATA."""
    script = ROOT / "scripts" / "lib" / "restore-data.sh"
    data = tmp_path / "astro"
    snap = data / ".zfs" / "snapshot" / "pre"
    for base in (data, snap):
        (base / "library" / "targets" / "M_42").mkdir(parents=True)
        (base / "library" / "targets" / "M_42" / "project.sqlite").write_text("db-at-backup")
        (base / "state").mkdir(parents=True, exist_ok=True)
        (base / "state" / "config.json").write_text("{}")
    outside = tmp_path / "outside"
    outside.mkdir()
    # container swaps the real target dir for a symlink pointing outside ASTRO_DATA
    (data / "library" / "targets" / "M_42" / "project.sqlite").unlink()
    (data / "library" / "targets" / "M_42").rmdir()
    (data / "library" / "targets" / "M_42").symlink_to(outside)

    r = subprocess.run(["bash", str(script), str(data), "tank/astro@pre"],
                       capture_output=True, text=True)
    escaped = list(outside.iterdir())
    assert not escaped, f"restore wrote through a symlink to outside ASTRO_DATA: {escaped} (rc={r.returncode})"
    assert r.returncode != 0 and "is a link" in r.stderr
