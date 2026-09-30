"""scripts/update_agent.py — the NAS-side helper behind Settings → App updates.

It runs as root and reads a file the web page wrote, so most of what is pinned
here is what it *refuses*: anything but the three actions, a request that names
its own ref, a stale ask, a data restore without RESTORE typed. The rest is the
contract with the page — status.json's fields — and that an update always
installs ``origin/stable`` through the same ``deploy.sh`` a person would run.

The clone here is a real git repo with a real ``origin`` (a local bare repo), so
fetch / rev-parse / show are exercised for real; only deploy.sh and rollback.sh
are stubs that record their arguments.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _load():
    spec = importlib.util.spec_from_file_location("update_agent", ROOT / "scripts" / "update_agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ua = _load()

STUB = """#!/usr/bin/env bash
echo "$0 $*" >> "{calls}"
echo "doing the thing"
exit $(cat "{rc}" 2>/dev/null || echo 0)
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit_version(clone: Path, version: str, schema: int, lib_schema: int) -> str:
    (clone / "webapp").mkdir(exist_ok=True)
    (clone / "seestack" / "io").mkdir(parents=True, exist_ok=True)
    (clone / "webapp" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    (clone / "seestack" / "io" / "project.py").write_text(f"SCHEMA_VERSION = {schema}\n")
    (clone / "seestack" / "io" / "library.py").write_text(f"LIBRARY_SCHEMA_VERSION = {lib_schema}\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", f"v{version}")
    return _git(clone, "rev-parse", "HEAD")


@pytest.fixture
def nas(tmp_path: Path):
    """A clone, its origin, a data folder, and the helper's own folders."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    clone = tmp_path / "astrostack-build"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True,
                   capture_output=True)
    _git(clone, "config", "user.email", "noreply@anthropic.com")
    _git(clone, "config", "user.name", "test")
    calls, rc = tmp_path / "calls.txt", tmp_path / "rc.txt"
    (clone / ".gitignore").write_text(".env\n")              # as the real repo does
    (clone / "scripts").mkdir()
    for name in ("deploy.sh", "rollback.sh"):
        s = clone / "scripts" / name
        s.write_text(STUB.format(calls=calls, rc=rc))
        s.chmod(0o755)
    old = _commit_version(clone, "0.1.0", 5, 3)
    _git(clone, "push", "-q", "origin", "HEAD:main")
    data = tmp_path / "astro"
    (data / "state").mkdir(parents=True)
    (clone / ".env").write_text(f"ASTRO_DATA={data}\n")      # untracked, as on the NAS
    home, deploy_state = tmp_path / "home", tmp_path / "deploy-state"
    home.mkdir()
    deploy_state.mkdir()

    class N:
        pass

    n = N()
    n.origin, n.clone, n.data, n.home, n.deploy_state = origin, clone, data, home, deploy_state
    n.calls, n.rc, n.old = calls, rc, old
    n.queue = data / "state" / "updater"
    n.agent = lambda: ua.Agent(clone, home, deploy_state=deploy_state)
    n.status = lambda: json.loads((n.queue / "status.json").read_text())

    def publish_stable(version: str, schema: int = 5, lib_schema: int = 3) -> str:
        sha = _commit_version(clone, version, schema, lib_schema)
        _git(clone, "push", "-q", "origin", "HEAD:main", "HEAD:stable")
        _git(clone, "checkout", "-q", "--detach", old)     # the NAS is still on the old one
        return sha

    def ask(action: str, **extra) -> None:
        n.queue.mkdir(exist_ok=True)
        body = {"id": "req-1", "action": action, "requested_at": time.time(), **extra}
        (n.queue / "request.json").write_text(json.dumps(body))

    n.publish_stable, n.ask = publish_stable, ask
    n.called = lambda: calls.read_text().splitlines() if calls.exists() else []
    return n


# ---- validation -------------------------------------------------------------------

@pytest.mark.parametrize("body, why", [
    (b"not json", "not readable"),
    (b"[1, 2]", "not readable"),
    (json.dumps({"id": "a", "action": "update; rm -rf /", "requested_at": 1e9}).encode(), "does not do"),
    (json.dumps({"id": "../x", "action": "check", "requested_at": 1e9}).encode(), "no valid id"),
    (json.dumps({"id": "a", "action": "check"}).encode(), "no time"),
    (json.dumps({"id": "a", "action": "check", "requested_at": True}).encode(), "no time"),
    (json.dumps({"id": "a", "action": "check", "requested_at": 1e9 - 7200}).encode(), "over an hour old"),
    (json.dumps({"id": "a", "action": "check", "requested_at": 1e9 + 3600}).encode(), "future"),
    (json.dumps({"id": "a", "action": "update", "requested_at": 1e9, "restore_data": True}).encode(), "not readable"),
    (json.dumps({"id": "a", "action": "rollback", "requested_at": 1e9, "restore_data": True}).encode(), "RESTORE"),
    (json.dumps({"id": "a", "action": "rollback", "requested_at": 1e9, "restore_data": "yes"}).encode(), "not readable"),
])
def test_validate_request_refuses(body: bytes, why: str) -> None:
    with pytest.raises(ua.Refused, match=why):
        ua.validate_request(body, now=1e9)


def test_validate_request_accepts_only_the_fields_it_knows() -> None:
    body = json.dumps({"id": "abc-1", "action": "update", "requested_at": 1e9,
                       "ref": "some-branch", "cmd": "anything"}).encode()
    assert ua.validate_request(body, now=1e9) == {"id": "abc-1", "action": "update", "restore_data": False}
    body = json.dumps({"id": "abc-1", "action": "rollback", "requested_at": 1e9,
                       "restore_data": True, "confirm": "RESTORE"}).encode()
    assert ua.validate_request(body, now=1e9)["restore_data"] is True


# ---- the tick -----------------------------------------------------------------------

def test_an_idle_tick_writes_a_heartbeat_and_touches_no_network(nas) -> None:
    before = time.time()
    nas.agent().tick()
    st = nas.status()
    assert st["agent_seen_at"] >= before and st["state"] == "idle"
    assert st["installed"]["version"] == "0.1.0"
    assert st["available"] is None                 # nothing fetched unasked
    assert st["rollback"] is None                  # no deploy recorded yet
    assert nas.called() == []


def test_check_fetches_and_reports_the_stable_version(nas) -> None:
    nas.publish_stable("0.2.0")
    _git(nas.clone, "update-ref", "-d", "refs/remotes/origin/stable")   # not fetched yet
    nas.ask("check")
    nas.agent().tick()
    st = nas.status()
    assert st["available"]["version"] == "0.2.0"
    assert st["last_result"]["ok"] is True and st["last_result"]["action"] == "check"
    assert st["last_result"]["id"] == "req-1"
    assert not (nas.queue / "request.json").exists()
    assert nas.called() == []                      # a check never deploys


def test_update_runs_deploy_on_origin_stable_and_nothing_the_page_named(nas) -> None:
    nas.publish_stable("0.2.0")
    nas.ask("update", ref="refs/heads/evil")
    nas.agent().tick()
    (call,) = nas.called()
    assert call.endswith("deploy.sh -y origin/stable")
    st = nas.status()
    assert st["last_result"]["ok"] is True
    assert st["last_result"]["message"] == "Updated to v0.2.0."
    assert "doing the thing" in st["last_result"]["log_tail"]
    assert st["state"] == "idle" and st["job"] is None


def test_a_failed_deploy_is_reported_with_its_log(nas) -> None:
    nas.publish_stable("0.2.0")
    nas.rc.write_text("1")
    nas.ask("update")
    nas.agent().tick()
    res = nas.status()["last_result"]
    assert res["ok"] is False and "did not finish" in res["message"]
    assert res["log_tail"]


def test_update_without_a_stable_branch_refuses(nas) -> None:
    nas.ask("update")
    nas.agent().tick()
    res = nas.status()["last_result"]
    assert res["ok"] is False and "no tested (stable) version" in res["message"]
    assert nas.called() == []


def test_a_refused_request_is_consumed_not_retried(nas) -> None:
    nas.queue.mkdir()
    (nas.queue / "request.json").write_text('{"id": "x", "action": "format-the-disk", "requested_at": 1}')
    nas.agent().tick()
    assert not (nas.queue / "request.json").exists()
    assert nas.status()["last_result"]["ok"] is False
    nas.agent().tick()
    assert nas.called() == []


def test_rollback_info_says_when_the_data_must_come_back_too(nas) -> None:
    nas.publish_stable("0.2.0", schema=6)
    _git(nas.clone, "checkout", "-q", "--detach", "origin/stable")    # as after a deploy
    (nas.deploy_state / "last-good").write_text(f"{nas.old} v0.1.0 20260930T0100Z\n")
    (nas.deploy_state / "last-backup").write_text("tank/astro@astrostack-pre-v0.2.0-20260930T0100Z\n")
    nas.agent().tick()
    assert nas.status()["rollback"] == {"to_version": "0.1.0", "needs_restore_data": True,
                                        "backup": "snapshot"}


def test_rollback_passes_yes_and_restore_only_when_confirmed(nas) -> None:
    (nas.deploy_state / "last-good").write_text(f"{nas.old} v0.1.0 x\n")
    nas.ask("rollback", restore_data=True)                      # no RESTORE typed
    nas.agent().tick()
    assert nas.called() == [] and "RESTORE" in nas.status()["last_result"]["message"]

    nas.ask("rollback", restore_data=True, confirm="RESTORE")
    nas.agent().tick()
    (call,) = nas.called()
    assert call.endswith("rollback.sh --yes --restore-data")
    assert nas.status()["last_result"]["message"] == "Rolled back to v0.1.0."


def test_rollback_with_nothing_recorded_refuses(nas) -> None:
    nas.ask("rollback")
    nas.agent().tick()
    assert "no earlier version" in nas.status()["last_result"]["message"]
    assert nas.called() == []


def test_a_successful_update_carries_the_installed_helper_forward(nas) -> None:
    (nas.home / "clone-path").write_text(str(nas.clone))
    (nas.home / "update_agent.py").write_text("# an older helper\n")
    nas.publish_stable("0.2.0")
    # What deploy.sh's checkout of the new version leaves in the clone.
    (nas.clone / "scripts" / "update_agent.py").write_text("# the helper this version ships\n")
    nas.ask("update")
    nas.agent().tick()
    assert (nas.home / "update_agent.py").read_text() == "# the helper this version ships\n"


# ---- install ------------------------------------------------------------------------

def test_install_refuses_a_clone_or_helper_inside_the_data_folder(tmp_path: Path) -> None:
    data = tmp_path / "astro"
    (data / "code").mkdir(parents=True)
    with pytest.raises(SystemExit, match="inside the app's data folder"):
        ua.check_install_paths(data / "code", tmp_path / "home", data)
    with pytest.raises(SystemExit, match="inside the app's data folder"):
        ua.check_install_paths(tmp_path / "clone", data / "state", data)
    ua.check_install_paths(tmp_path / "clone", tmp_path / "home", data)   # fine


# ---- the container is the adversary -------------------------------------------------
# Everything under ASTRO_DATA is writable by the container, and the helper runs as
# root on the host. Each test plants what a compromised container could, then checks
# the helper neither writes through it nor reads through it.

def _secret(tmp_path: Path, text: str = '{"id": "host-secret-1", "token": "s3cr3t"}') -> Path:
    s = tmp_path / "host" / "secret.json"
    s.parent.mkdir(parents=True, exist_ok=True)
    s.write_text(text)
    return s


def test_a_planted_last_log_link_is_not_written_through(nas, tmp_path) -> None:
    victim = _secret(tmp_path, "root-owned host file\n")
    nas.publish_stable("0.2.0")
    nas.queue.mkdir()
    (nas.queue / "last.log").symlink_to(victim)
    nas.ask("update")
    nas.agent().tick()
    assert victim.read_text() == "root-owned host file\n"
    log = nas.queue / "last.log"
    assert not log.is_symlink() and "doing the thing" in log.read_text()
    assert nas.status()["last_result"]["ok"] is True


def test_a_planted_status_link_does_not_leak_the_file_it_points_at(nas, tmp_path) -> None:
    secret = _secret(tmp_path)
    nas.queue.mkdir()
    (nas.queue / "status.json").symlink_to(secret)
    nas.agent().tick()
    status = nas.queue / "status.json"
    assert not status.is_symlink()
    assert "s3cr3t" not in status.read_text()
    assert secret.read_text() == '{"id": "host-secret-1", "token": "s3cr3t"}'


def test_a_request_that_is_a_link_is_refused_not_read(nas, tmp_path) -> None:
    nas.publish_stable("0.2.0")
    target = _secret(tmp_path, json.dumps({"id": "via-link", "action": "update",
                                           "requested_at": time.time()}))
    nas.queue.mkdir()
    (nas.queue / "request.json").symlink_to(target)
    nas.agent().tick()
    assert nas.called() == []                        # a valid request, but only behind a link
    assert nas.status()["last_result"]["ok"] is False
    assert target.exists()                           # moved/unlinked the link, not the target


def test_a_fifo_for_a_request_does_not_hang_the_helper(nas) -> None:
    import os
    nas.queue.mkdir()
    import threading
    os.mkfifo(nas.queue / "request.json")
    worker = threading.Thread(target=nas.agent().tick, daemon=True)
    worker.start()
    worker.join(timeout=20)                          # a plain open() blocks here forever
    assert not worker.is_alive(), "the helper hung on a FIFO planted as request.json"
    assert nas.status()["last_result"]["ok"] is False


@pytest.mark.parametrize("which", ["updater", "state"])
def test_a_linked_folder_is_refused_and_nothing_is_written_there(nas, tmp_path, which) -> None:
    elsewhere = tmp_path / "host" / "etc"
    elsewhere.mkdir(parents=True)
    if which == "updater":
        (nas.data / "state" / "updater").symlink_to(elsewhere)
    else:
        shutil.rmtree(nas.data / "state")
        (nas.data / "state").symlink_to(elsewhere)
        (elsewhere / "updater").mkdir()
    with pytest.raises(SystemExit, match="not links|does not exist"):
        nas.agent().tick()
    assert [p.name for p in elsewhere.rglob("*") if p.is_file()] == []
