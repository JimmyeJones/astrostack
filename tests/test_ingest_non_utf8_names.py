"""A sub whose *file name* is not valid UTF-8 is one unreadable sub, never a
failed scan.

Python holds such a name with surrogate escapes (``os.fsdecode``). SQLite
refuses to store one, so before this ``Project.add_frame`` raised
``UnicodeEncodeError`` out of ``ingest_files``, out of ``scan_and_organize``'s
per-unit loop and out of the pipeline's scan step: every target sorted after the
file never ingested, and nothing was QC'd, solved or stacked — on every scan,
until the file was renamed, which the app must never do (Scout 2026-11-11, QA
sweep (3)). Nothing here writes to ``incoming/`` (AGENTS.md §10).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io import scanner
from seestack.io.ingest import (
    NAME_NOT_TEXT_ERROR,
    name_is_valid_text,
    printable_name,
)
from seestack.io.library import Library
from seestack.io.scanner import scan_and_organize
from tests.synth import write_seestar_fits
from webapp.unreadablesubs import encode_unreadable, folders_from_scan

_BAD_FILE = os.fsdecode(b"Light_M42_caf\xe9.fit")
_BAD_DIR = os.fsdecode(b"NGC 7000 r\xe9gion")


def _fits(path: Path, seed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_seestar_fits(path, width=48, height=32, n_stars=3, seed=seed)


def _snapshot(root: Path) -> dict[bytes, tuple[int, float]]:
    out = {}
    for dirpath, _dirs, files in os.walk(os.fsencode(root)):
        for f in files:
            p = os.path.join(dirpath, f)
            st = os.stat(p)
            out[p] = (st.st_size, st.st_mtime)
    return out


def _tree(root: Path) -> None:
    """``A_1`` (2), ``M_42`` (3 good + 1 bad name), ``Z_9`` (2)."""
    seed = 1
    for folder, n in (("A_1", 2), ("M_42", 3), ("Z_9", 2)):
        for i in range(n):
            _fits(root / folder / f"Light_{folder}_{i}.fit", seed)
            seed += 1
    _fits(root / "M_42" / _BAD_FILE, seed)


@pytest.fixture
def incoming(tmp_path: Path) -> Path:
    root = tmp_path / "incoming"
    root.mkdir()
    try:
        (root / _BAD_FILE).write_bytes(b"")
    except (OSError, UnicodeEncodeError):
        pytest.skip("this filesystem refuses non-UTF-8 names")
    (root / _BAD_FILE).unlink()
    return root


def _json_safe(obj) -> None:
    json.dumps(obj, ensure_ascii=False).encode("utf-8")


def test_the_helpers():
    assert name_is_valid_text("Light_M 42_10.0s.fit")
    assert not name_is_valid_text(_BAD_FILE)
    assert printable_name(_BAD_FILE) == "Light_M42_caf�.fit"
    assert printable_name("Light_ok.fit") == "Light_ok.fit"


def test_one_bad_name_no_longer_stops_the_scan(incoming: Path, tmp_path: Path):
    _tree(incoming)
    before = _snapshot(incoming)
    lib = Library.open_or_create(tmp_path / "library")
    try:
        result = scan_and_organize(lib, incoming)
        by_name = {t.target_name: t for t in result.targets}
        assert len(by_name) == 3, sorted(by_name)
        added = sorted(t.n_frames_added for t in result.targets)
        assert added == [2, 2, 3]
        m42 = next(t for t in result.targets if t.n_frames_found == 4)
        assert m42.n_errors == 1
        assert m42.unreadable_examples == ["Light_M42_caf�.fit"]
        _json_safe([t.unreadable_examples for t in result.targets])
        folders = folders_from_scan(result, str(incoming))
        assert folders == {"M_42": 1}
        _json_safe(folders)

        # And the next scan is still a clean dedup pass, reporting it again.
        again = scan_and_organize(lib, incoming)
        assert sum(t.n_frames_added for t in again.targets) == 0
        assert sum(t.n_errors for t in again.targets) == 1
    finally:
        lib.close()
    assert _snapshot(incoming) == before


def test_a_folder_with_a_bad_name_is_reported_not_registered(
    incoming: Path, tmp_path: Path,
):
    _fits(incoming / "A_1" / "Light_a.fit", 1)
    _fits(incoming / _BAD_DIR / "Light_b.fit", 2)
    _fits(incoming / _BAD_DIR / "Light_c.fit", 3)
    _fits(incoming / "Z_9" / "Light_z.fit", 4)
    before = _snapshot(incoming)
    lib = Library.open_or_create(tmp_path / "library")
    try:
        result = scan_and_organize(lib, incoming)
        added = {t.target_name: t.n_frames_added for t in result.targets}
        assert sum(added.values()) == 2, added
        held = [t for t in result.targets if t.n_errors]
        assert len(held) == 1
        assert held[0].safe_name == ""
        assert held[0].n_errors == 2
        assert "�" in held[0].target_name
        payload = [{"target": t.target_name, "examples": t.unreadable_examples,
                    "dirs": t.unreadable_dirs} for t in result.targets]
        _json_safe(payload)
        _json_safe(encode_unreadable(folders_from_scan(result, str(incoming))))
        # No target row was minted for it.
        assert len(lib.list_targets()) == 2
    finally:
        lib.close()
    assert _snapshot(incoming) == before


def test_ingest_files_reports_the_reason_in_plain_words(incoming: Path, tmp_path: Path):
    _tree(incoming)
    lib = Library.open_or_create(tmp_path / "library")
    try:
        result = scan_and_organize(lib, incoming / "M_42", single_target=True)
    finally:
        lib.close()
    (t,) = result.targets
    assert (t.n_frames_added, t.n_errors) == (3, 1)
    assert "rename it" in NAME_NOT_TEXT_ERROR


def test_one_targets_failure_does_not_stop_the_others(
    incoming: Path, tmp_path: Path, monkeypatch,
):
    """Belt and braces: any exception organising one unit lets the rest ingest
    and is still raised afterwards, so a real fault fails the step loudly."""
    _tree(incoming)
    real = scanner._ingest_into_target

    def flaky(library, target_name, files, **kw):
        if "A" in target_name and "1" in target_name:
            raise RuntimeError("disk on fire")
        return real(library, target_name, files, **kw)

    monkeypatch.setattr(scanner, "_ingest_into_target", flaky)
    lib = Library.open_or_create(tmp_path / "library")
    try:
        with pytest.raises(RuntimeError, match="disk on fire"):
            scan_and_organize(lib, incoming)
        names = {t.name for t in lib.list_targets()}
    finally:
        lib.close()
    assert len(names) == 2, names
