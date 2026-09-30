"""scripts/lib/restore-data.sh — what `rollback.sh --restore-data` may put back.

The rule it exists for is AGENTS.md §10: `incoming/` holds the only copy of the
owner's raw subs. The first version of `rollback.sh` restored a ZFS backup with
`zfs rollback` on the dataset mounted at ASTRO_DATA — the dataset `incoming/` lives
in — so every sub copied in after the update would have been deleted by the very
command whose comment promised incoming/ is "never touched". These tests pin the
replacement: only library/ and state/ databases and config come back, from the
snapshot's read-only `.zfs/snapshot/<name>/` view or from the tar archive.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lib" / "restore-data.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _state_at_backup(root: Path) -> None:
    """What the data folder held when deploy.sh took its backup."""
    _write(root / "library" / "library.sqlite", "library v1")
    _write(root / "library" / "targets" / "M_42" / "project.sqlite", "m42 v1")
    _write(root / "state" / "config.json", '{"auto_stack": false}')
    _write(root / "state" / "jobs.sqlite", "jobs v1")
    _write(root / "incoming" / "M 42_sub" / "old.fit", "old sub")


def _after_update(data: Path) -> None:
    """What happened after the update: the newer app rewrote its databases, left a
    write-ahead log behind, and — the case that matters — the owner copied a new
    night of subs into incoming/."""
    _write(data / "library" / "library.sqlite", "library v2")
    _write(data / "library" / "library.sqlite-wal", "newer wal")
    _write(data / "library" / "targets" / "M_42" / "project.sqlite", "m42 v2")
    _write(data / "state" / "config.json", '{"auto_stack": true}')
    _write(data / "incoming" / "M 42_sub" / "new.fit", "the only copy of tonight")


def _run(data: Path, backup: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), str(data), backup],
                          capture_output=True, text=True)


def _assert_restored(data: Path) -> None:
    assert (data / "library" / "library.sqlite").read_text() == "library v1"
    assert (data / "library" / "targets" / "M_42" / "project.sqlite").read_text() == "m42 v1"
    assert (data / "state" / "config.json").read_text() == '{"auto_stack": false}'
    assert not (data / "library" / "library.sqlite-wal").exists()
    # incoming/ is exactly as the owner left it — including what arrived since.
    assert (data / "incoming" / "M 42_sub" / "new.fit").read_text() == "the only copy of tonight"
    assert (data / "incoming" / "M 42_sub" / "old.fit").read_text() == "old sub"


def test_zfs_backup_restores_databases_and_never_touches_incoming(tmp_path: Path) -> None:
    data = tmp_path / "astro"
    _state_at_backup(data)
    snap = data / ".zfs" / "snapshot" / "astrostack-pre-v0.490.0-20260930T0100Z"
    _state_at_backup(snap)
    _after_update(data)

    r = _run(data, "tank/astro@astrostack-pre-v0.490.0-20260930T0100Z")

    assert r.returncode == 0, r.stderr
    _assert_restored(data)
    assert "incoming/ untouched" in r.stdout


def test_tar_backup_restores_databases_and_never_touches_incoming(tmp_path: Path) -> None:
    src = tmp_path / "at-backup"
    _state_at_backup(src)
    archive = tmp_path / "backup-pre-v0.490.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for rel in ("library/library.sqlite", "library/targets/M_42/project.sqlite",
                    "state/config.json", "state/jobs.sqlite"):
            tf.add(src / rel, arcname=rel)
    data = tmp_path / "astro"
    _state_at_backup(data)
    _after_update(data)

    r = _run(data, str(archive))

    assert r.returncode == 0, r.stderr
    _assert_restored(data)


def test_an_archive_that_carries_incoming_still_cannot_write_there(tmp_path: Path) -> None:
    """The file list is filtered to library/ and state/, not trusted from the archive."""
    src = tmp_path / "at-backup"
    _state_at_backup(src)
    _write(src / "incoming" / "M 42_sub" / "new.fit", "stale copy")
    archive = tmp_path / "b.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for rel in ("library/library.sqlite", "incoming/M 42_sub/new.fit"):
            tf.add(src / rel, arcname=rel)
    data = tmp_path / "astro"
    _state_at_backup(data)
    _after_update(data)

    assert _run(data, str(archive)).returncode == 0
    assert (data / "incoming" / "M 42_sub" / "new.fit").read_text() == "the only copy of tonight"


def test_missing_snapshot_or_empty_backup_restores_nothing(tmp_path: Path) -> None:
    data = tmp_path / "astro"
    _state_at_backup(data)
    _after_update(data)

    r = _run(data, "tank/astro@does-not-exist")
    assert r.returncode != 0 and "not readable" in r.stderr

    empty = tmp_path / "empty.tar.gz"
    with tarfile.open(empty, "w:gz"):
        pass
    r = _run(data, str(empty))
    assert r.returncode != 0 and "no databases" in r.stderr
    # A refused restore changed nothing, WAL included.
    assert (data / "library" / "library.sqlite").read_text() == "library v2"
    assert (data / "library" / "library.sqlite-wal").exists()


def test_rollback_script_no_longer_rolls_the_dataset_back() -> None:
    """The one command that would take incoming/ with it stays out of rollback.sh."""
    text = (SCRIPT.parents[1] / "rollback.sh").read_text()
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "zfs rollback" not in code
    assert "scripts/lib/restore-data.sh" in code
    assert os.access(SCRIPT, os.X_OK)
