"""Durable atomic writes for the app's small JSON state files.

The `fsync` itself isn't observable from a unit test — you'd need to pull the
power out mid-write — so these pin the parts that *are*: the file lands with the
right contents, the temp file never survives (success or failure), the previous
contents are still there after a failed write, and both real call sites go
through the helper.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from webapp import atomicio, calibration
from webapp.config import Settings, SettingsStore


def test_write_replaces_the_file_and_leaves_no_temp(tmp_path: Path):
    target = tmp_path / "config.json"
    atomicio.write_text_durably(target, "first")
    assert target.read_text(encoding="utf-8") == "first"

    atomicio.write_text_durably(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]


def test_a_failed_write_keeps_the_old_file_and_cleans_up(tmp_path: Path, monkeypatch):
    """A write that dies part-way must not publish, and must not litter.

    This is the whole point of writing to the side first: the previous settings
    are still the ones on disk.
    """
    target = tmp_path / "config.json"
    atomicio.write_text_durably(target, "good")

    def _boom(src, dst):  # noqa: ANN001, ANN202
        raise OSError("simulated failure just before publishing")

    monkeypatch.setattr(atomicio.os, "replace", _boom)
    with pytest.raises(OSError):
        atomicio.write_text_durably(target, "never published")

    assert target.read_text(encoding="utf-8") == "good"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]


def test_a_directory_that_refuses_fsync_is_not_fatal(tmp_path: Path, monkeypatch):
    """Some filesystems refuse to `fsync` a directory. The save still succeeds."""
    def _refuse(fd):  # noqa: ANN001, ANN202
        raise OSError("this filesystem does not fsync directories")

    monkeypatch.setattr(atomicio.os, "fsync", _refuse)
    target = tmp_path / "config.json"
    atomicio.write_text_durably(target, "still saved")
    assert target.read_text(encoding="utf-8") == "still saved"


def test_the_custom_suffix_reuses_the_existing_temp_name(tmp_path: Path, monkeypatch):
    """The call sites keep their historic temp names so an old one gets reused."""
    target = tmp_path / "config.json"
    seen: list[str] = []

    real_replace = os.replace

    def _spy(src, dst):  # noqa: ANN001, ANN202
        seen.append(Path(src).name)
        real_replace(src, dst)

    monkeypatch.setattr(atomicio.os, "replace", _spy)
    atomicio.write_text_durably(target, "x", suffix=".json.tmp")
    assert seen == ["config.json.tmp"]


def test_settings_still_round_trip_through_the_durable_save(tmp_path: Path):
    """The upgrade-safety contract: an existing config.json keeps loading."""
    store = SettingsStore(str(tmp_path))
    store.update({"astap_timeout_s": 42})
    path = store.get().config_path
    assert json.loads(path.read_text(encoding="utf-8"))["astap_timeout_s"] == 42
    # No stale temp beside it.
    assert not (path.with_suffix(".json.tmp")).exists()
    # And a fresh store reads it straight back.
    assert SettingsStore(str(tmp_path)).get().astap_timeout_s == 42


def test_the_calibration_registry_round_trips_through_the_durable_write(tmp_path: Path):
    entries = [{"id": 1, "filename": "dark_1.fits", "kind": "dark"}]
    calibration._write_registry(tmp_path, entries)
    assert calibration._read_registry(tmp_path) == entries

    calibration._write_id_high_water(tmp_path, 7)
    assert calibration._read_id_high_water(tmp_path) == 7
    # Neither write leaves a temp file for the next reader to trip over.
    names = sorted(p.name for p in calibration.calibration_dir(tmp_path).iterdir())
    assert names == sorted([calibration.NEXT_ID_NAME, calibration.REGISTRY_NAME])
