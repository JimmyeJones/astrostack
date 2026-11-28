"""scripts/deploy.sh, run end to end against stub `docker`, `zfs`, `sudo` and `id`.

2026-10-04, the owner's first deploy: the script stopped the app and then
exited without a word. It looked up the data folder's ZFS dataset with
`zfs list | awk '... {print; exit}'`; on a TrueNAS box with hundreds of
datasets `zfs list` was still writing when awk quit, died of SIGPIPE, and
`set -o pipefail` + `set -e` ended the deploy — with zfs's stderr hidden, right
after `docker compose stop`. The same lines also deployed with **no backup** if
`zfs snapshot` failed. These tests run the real script over a fake NAS whose
`zfs list` prints 20,000 datasets.

2026-11-26 audit (backend.md §2): a failed build left the app stopped, and running
the update again recorded the never-started version as `last-good`, so
`rollback.sh` "restored" the broken one. The stub's `docker exec` reports the
version the container is running (``running`` file), which `up` advances.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None,
                                reason="needs git and bash")

STUBS = {
    "id": '#!/usr/bin/env bash\nif [ "${1:-}" = "-u" ]; then echo 0; else exec /usr/bin/id "$@"; fi\n',
    "sudo": '#!/usr/bin/env bash\nif [ "${1:-}" = "-u" ]; then shift 2; fi\nexec "$@"\n',
    "docker": """#!/usr/bin/env bash
echo "docker $*" >> "$STUB_LOG"
case "$1" in
  inspect) echo healthy ;;
  exec) cat "$STUB_DIR/running" 2>/dev/null || echo 0.1.0 ;;
  compose) for a in "$@"; do
      [ "$a" = build ] && exit "$(cat "$STUB_DIR/build_rc" 2>/dev/null || echo 0)"
      if [ "$a" = up ]; then
        rc="$(cat "$STUB_DIR/up_rc" 2>/dev/null || echo 0)"
        [ "$rc" = 0 ] && echo 0.2.0 > "$STUB_DIR/running"
        exit "$rc"
      fi
    done ;;
esac
exit 0
""",
    "zfs": """#!/usr/bin/env bash
echo "zfs $*" >> "$STUB_LOG"
if [ "$1" = list ] && [ "$3" = "-t" ] && [ "$4" = snapshot ]; then
  cat "$STUB_DIR/snapshots" 2>/dev/null; exit 0
fi
if [ "$1" = snapshot ]; then
  rc="$(cat "$STUB_DIR/snap_rc" 2>/dev/null || echo 0)"
  [ "$rc" = 0 ] && echo "$2" >> "$STUB_DIR/snapshots"
  exit "$rc"
fi
if [ "$1" = list ]; then
  for i in $(seq 1 4); do printf 'boot-pool/ROOT/%s\\t/sys%s\\n' "$i" "$i"; done
  printf 'tank/astro\\t%s\\n' "$STUB_DATA"
  for i in $(seq 1 20000); do printf 'tank/ix-apps/docker/%s\\t/mnt/.ix-apps/docker/%s\\n' "$i" "$i"; done
  exit 0
fi
[ "$1" = snapshot ] && exit "$(cat "$STUB_DIR/snap_rc" 2>/dev/null || echo 0)"
exit 0
""",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(clone: Path, version: str) -> None:
    (clone / "webapp" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", f"v{version}")


@pytest.fixture
def nas(tmp_path: Path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    clone = tmp_path / "astrostack-build"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, capture_output=True)
    _git(clone, "config", "user.email", "noreply@anthropic.com")
    _git(clone, "config", "user.name", "test")
    (clone / ".gitignore").write_text(".env\n")
    for rel in ("scripts/deploy.sh", "scripts/lib/zfs-dataset.sh"):
        (clone / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, clone / rel)
    (clone / "docker").mkdir()
    (clone / "docker" / "docker-compose.yml").write_text("services: {}\n")
    (clone / "webapp").mkdir()
    (clone / "seestack" / "io").mkdir(parents=True)
    (clone / "seestack" / "io" / "project.py").write_text("SCHEMA_VERSION = 22\n")
    (clone / "seestack" / "io" / "library.py").write_text("LIBRARY_SCHEMA_VERSION = 5\n")
    _commit(clone, "0.1.0")
    old = _git(clone, "rev-parse", "HEAD")
    _git(clone, "tag", "v0.1.0")
    _commit(clone, "0.2.0")
    _git(clone, "tag", "v0.2.0")
    _git(clone, "push", "-q", "origin", "HEAD:main", "--tags")
    _git(clone, "checkout", "-q", "--detach", old)

    data = tmp_path / "astro"
    for rel, text in (("library/library.sqlite", "lib"), ("state/config.json", "{}"),
                      ("incoming/M 42_sub/a.fit", "sub")):
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / rel).write_text(text)
    (clone / ".env").write_text(f"ASTRO_DATA={data}\n")

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in STUBS.items():
        (stubs / name).write_text(body)
        (stubs / name).chmod(0o755)

    class N:
        pass

    n = N()
    n.clone, n.data, n.stubs, n.tmp = clone, data, stubs, tmp_path
    n.state = tmp_path / "deploy-state"
    n.log = tmp_path / "stub.log"
    n.v020 = _git(clone, "rev-parse", "v0.2.0")
    n.v010 = old

    def run(*, zfs: bool = True) -> subprocess.CompletedProcess:
        if not zfs:
            (stubs / "zfs").unlink(missing_ok=True)
        env = {k: v for k, v in os.environ.items() if k != "SUDO_USER"}
        env.update(PATH=f"{stubs}:{env['PATH']}", STUB_LOG=str(n.log), STUB_DIR=str(stubs),
                   STUB_DATA=str(data), ASTROSTACK_DEPLOY_STATE=str(n.state))
        return subprocess.run(["bash", str(clone / "scripts" / "deploy.sh"), "-y", "v0.2.0"],
                              cwd=clone, env=env, capture_output=True, text=True, timeout=120)

    n.run = run
    n.calls = lambda: n.log.read_text().splitlines() if n.log.exists() else []
    return n


def test_a_nas_with_thousands_of_datasets_deploys_with_a_snapshot(nas) -> None:
    r = nas.run()
    assert r.returncode == 0, r.stdout + r.stderr
    snap = (nas.state / "last-backup").read_text().strip()
    assert snap.startswith("tank/astro@astrostack-pre-v0.2.0-")
    assert f"Snapshot: {snap}" in r.stdout
    assert f"zfs snapshot {snap}" in nas.calls()
    assert _git(nas.clone, "rev-parse", "HEAD") == nas.v020
    assert any("compose" in c and " up -d" in c for c in nas.calls())
    assert (nas.state / "last-good").read_text().split()[:2] == [nas.v010, "v0.1.0"]


def test_a_failed_snapshot_falls_back_to_a_copy_instead_of_no_backup(nas) -> None:
    (nas.stubs / "snap_rc").write_text("1")
    r = nas.run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "snapshot failed" in r.stdout
    backup = Path((nas.state / "last-backup").read_text().strip())
    assert backup.name.endswith(".tar.gz") and backup.exists()
    with tarfile.open(backup) as tf:
        names = tf.getnames()
    assert "library/library.sqlite" in names and "state/config.json" in names
    assert not any(n.startswith("incoming") for n in names)


def test_without_zfs_the_backup_is_a_copy(nas) -> None:
    r = nas.run(zfs=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (nas.state / "last-backup").read_text().strip().endswith(".tar.gz")


def _index(calls: list[str], needle: str) -> int:
    return next(i for i, c in enumerate(calls) if needle in c)


def test_the_new_version_is_built_before_the_app_is_stopped(nas) -> None:
    r = nas.run()
    assert r.returncode == 0, r.stdout + r.stderr
    calls = nas.calls()
    assert _index(calls, " build") < _index(calls, " stop") < _index(calls, " up -d")
    assert not any(c.startswith("docker start") for c in calls)


def test_a_failed_build_leaves_the_old_version_running_and_the_checkout_alone(nas) -> None:
    (nas.stubs / "build_rc").write_text("1")
    r = nas.run()
    assert r.returncode != 0
    assert "building v0.2.0 failed" in r.stderr
    assert "still running" in r.stderr
    calls = nas.calls()
    assert not any(" stop" in c or " up " in c for c in calls)     # never stopped
    assert _git(nas.clone, "rev-parse", "HEAD") == nas.v010
    assert not (nas.state / "last-good").exists()
    assert not (nas.state / "last-backup").exists()


def test_a_failure_after_stopping_the_app_starts_the_old_one_again(nas) -> None:
    (nas.stubs / "up_rc").write_text("3")
    r = nas.run()
    assert r.returncode != 0
    assert "stopped unexpectedly" in r.stderr
    calls = nas.calls()
    assert _index(calls, " up -d") < _index(calls, "docker start astrostack")
    assert "Started again: 0.1.0" in r.stderr
    assert _git(nas.clone, "rev-parse", "HEAD") == nas.v010   # checkout matches what runs
    assert (nas.state / "last-backup").exists()          # the backup was taken first


def test_a_retry_after_a_failed_deploy_keeps_the_real_rollback_point(nas) -> None:
    """The audit's sequence: the first deploy got v0.2.0 started but unhealthy (or the
    old script left the checkout on it); the owner runs the update again. `last-good`
    must still name v0.1.0, or rollback.sh "restores" the broken version."""
    (nas.stubs / "up_rc").write_text("3")
    assert nas.run().returncode != 0
    assert (nas.state / "last-good").read_text().split()[:2] == [nas.v010, "v0.1.0"]
    # As the old script left it: checkout on the new version, new version reported running.
    _git(nas.clone, "checkout", "-q", "--detach", nas.v020)
    (nas.stubs / "running").write_text("0.2.0\n")
    (nas.stubs / "up_rc").write_text("0")
    r = nas.run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "keeping the recorded rollback point (v0.1.0)" in r.stdout
    assert (nas.state / "last-good").read_text().split()[:2] == [nas.v010, "v0.1.0"]


def test_the_rollback_point_is_the_running_version_not_the_checkout(nas) -> None:
    """The old script's other leftover: checkout already on the target while the
    owner restarted the old container by hand. The running version wins."""
    _git(nas.clone, "checkout", "-q", "--detach", nas.v020)
    r = nas.run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert (nas.state / "last-good").read_text().split()[:2] == [nas.v010, "v0.1.0"]


def test_incoming_is_never_touched(nas) -> None:
    before = (nas.data / "incoming" / "M 42_sub" / "a.fit").read_text()
    assert nas.run().returncode == 0
    assert (nas.data / "incoming" / "M 42_sub" / "a.fit").read_text() == before


@pytest.mark.parametrize("path, expect", [
    (None, "tank/astro"),
    ("/trailing/", ""),
])
def test_zfs_dataset_helper_reads_the_whole_listing(nas, path, expect) -> None:
    env = dict(os.environ, PATH=f"{nas.stubs}:{os.environ['PATH']}", STUB_LOG=str(nas.log),
               STUB_DIR=str(nas.stubs), STUB_DATA=str(nas.data))
    want = str(nas.data) + "/" if path is None else path
    r = subprocess.run(["bash", "-c", 'set -euo pipefail; d="$(bash "$0" "$1")"; echo "[$d]"',
                        str(ROOT / "scripts" / "lib" / "zfs-dataset.sh"), want],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"[{expect}]"


# ---- keeping only the newest backups (owner's decision 2026-11-28) ---------
#
# Every update used to add a snapshot (or a tar of the databases) and nothing
# ever removed one. After a healthy update the script now keeps the newest
# three of its OWN backups, and touches nothing else.

def test_only_the_three_newest_update_snapshots_are_kept(nas) -> None:
    old = [f"tank/astro@astrostack-pre-v0.0.{i}-2026010{i}T0000Z" for i in range(1, 6)]
    others = ["tank/astro@my-own-snapshot", "tank/astro@auto-2026-11-01_00-00"]
    (nas.stubs / "snapshots").write_text("\n".join(old[:2] + others + old[2:]) + "\n")
    r = nas.run()
    assert r.returncode == 0, r.stdout + r.stderr
    new = (nas.state / "last-backup").read_text().strip()
    destroyed = [c.split(" ", 2)[2] for c in nas.calls() if c.startswith("zfs destroy")]
    # 5 old + the new one = 6 of ours: the 3 oldest go, the newest 3 stay.
    assert destroyed == old[:3]
    assert new not in destroyed
    assert not any(o in destroyed for o in others)
    assert not any("-r" in c.split() for c in nas.calls() if c.startswith("zfs destroy"))


def test_three_or_fewer_update_snapshots_are_all_kept(nas) -> None:
    (nas.stubs / "snapshots").write_text(
        "tank/astro@astrostack-pre-v0.0.1-20260101T0000Z\n")
    r = nas.run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert not [c for c in nas.calls() if c.startswith("zfs destroy")]


def test_only_the_three_newest_backup_copies_are_kept(nas) -> None:
    nas.state.mkdir(parents=True, exist_ok=True)
    olds = []
    for i in range(1, 5):
        f = nas.state / f"backup-pre-v0.0.{i}-2026010{i}T0000Z.tar.gz"
        f.write_bytes(b"old")
        os.utime(f, (1_700_000_000 + i, 1_700_000_000 + i))
        olds.append(f)
    keep_me = nas.state / "notes.tar.gz"
    keep_me.write_bytes(b"not ours")
    os.utime(keep_me, (1_600_000_000, 1_600_000_000))
    r = nas.run(zfs=False)
    assert r.returncode == 0, r.stdout + r.stderr
    new = Path((nas.state / "last-backup").read_text().strip())
    assert new.exists()
    # 4 old + the new one = 5: the 2 oldest go.
    assert [f.exists() for f in olds] == [False, False, True, True]
    assert keep_me.exists()
    assert (nas.data / "incoming" / "M 42_sub" / "a.fit").read_text() == "sub"
