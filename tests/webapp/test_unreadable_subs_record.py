"""``webapp/unreadablesubs.py`` — what the scan remembers about files it could
not read, so the lag note can tell "not imported yet" from "can never be".

Pure/near-pure: the encode/decode round trip, the folder keying, and the two
scan shapes' different rights to overwrite the record.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("astropy")

from webapp.unreadablesubs import (
    MAX_REMEMBERED_FOLDERS,
    UNREADABLE_SUBS_META_KEY,
    decode_unreadable,
    encode_unreadable,
    folders_from_scan,
)


def _scan(*dirs: dict[str, int]):
    return SimpleNamespace(
        targets=[SimpleNamespace(unreadable_dirs=d) for d in dirs])


def test_folders_are_keyed_relative_to_incoming(tmp_path):
    """The one spelling that matters: the same one ``PlannedUnit.folder`` and
    ``Project.source_folders_under`` use, so the reader joins them with no
    translation."""
    inc = tmp_path / "incoming"
    got = folders_from_scan(
        _scan({str(inc / "M 101_sub"): 2},
              {str(inc / "MyWorks" / "M 81_sub"): 1}),
        str(inc),
    )
    assert got == {"M 101_sub": 2, os.path.join("MyWorks", "M 81_sub"): 1}


def test_files_loose_in_the_drop_folder_key_as_the_root_unit(tmp_path):
    inc = tmp_path / "incoming"
    assert folders_from_scan(_scan({str(inc): 3}), str(inc)) == {"": 3}


def test_a_directory_outside_incoming_is_dropped_rather_than_guessed(tmp_path):
    inc = tmp_path / "incoming"
    got = folders_from_scan(
        _scan({str(tmp_path / "elsewhere" / "x"): 4, str(inc / "M 42_sub"): 1}),
        str(inc),
    )
    assert got == {"M 42_sub": 1}


def test_two_targets_in_one_folder_are_summed(tmp_path):
    """The mosaic double-registration shape (#878) reaches this side too: one
    folder can be ingested by two targets, and its damaged files must be counted
    once per file, not once per target."""
    inc = tmp_path / "incoming"
    got = folders_from_scan(
        _scan({str(inc / "M 42_mosaic_sub"): 1}, {str(inc / "M 42_mosaic_sub"): 2}),
        str(inc),
    )
    assert got == {"M 42_mosaic_sub": 3}


def test_the_round_trip_keeps_what_it_can_and_refuses_the_rest():
    assert decode_unreadable(encode_unreadable({"a": 2, "b": 1})) == {"a": 2, "b": 1}
    # A zero is not a finding and never reaches the record.
    assert decode_unreadable(encode_unreadable({"a": 0})) == {}
    # Anything a truncated write, a hand-edit or a future version could leave.
    for raw in (None, "", "not json", "[]", '{"folders": 7}',
                '{"folders": [["a"], ["a", "x"], [1, 2], "nope", null]}'):
        assert decode_unreadable(raw) == {}


def test_the_folder_list_is_capped_biggest_first():
    folders = {f"f{i:02d}": i + 1 for i in range(MAX_REMEMBERED_FOLDERS + 5)}
    got = decode_unreadable(encode_unreadable(folders))
    assert len(got) == MAX_REMEMBERED_FOLDERS
    # What survives is what matters most, not whatever happened to be first.
    assert min(got.values()) > min(folders.values())


def _run_scan(client, root: str | None = None) -> None:
    body = {} if root is None else {"root": root}
    job_id = client.post("/api/scan", json=body).json()["job_id"]
    end = time.monotonic() + 120
    while time.monotonic() < end:
        st = client.get(f"/api/jobs/{job_id}").json()
        if st["state"] in ("done", "error", "cancelled", "interrupted"):
            assert st["state"] == "done", st
            return
        time.sleep(0.1)
    raise AssertionError("scan did not finish")


def _drop_unreadable(root: Path, folder: str, name: str) -> Path:
    d = root / "incoming" / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(b"\x00" * 8192)
    return p


def test_a_whole_library_scan_writes_the_record(built_library, client):
    from seestack.io.library import Library

    _drop_unreadable(built_library, "IC 360_sub", "frame_000.fit")
    _run_scan(client)
    lib = Library.open_or_create(built_library / "library")
    try:
        assert decode_unreadable(lib.get_meta(UNREADABLE_SUBS_META_KEY)) \
            == {"IC 360_sub": 1}
    finally:
        lib.close()


def test_a_scoped_scan_leaves_the_record_alone(built_library, client):
    """A "bring this one folder in" scan has looked at one folder, so it cannot
    speak for the rest — overwriting would report every other folder as clean."""
    from seestack.io.library import Library

    _drop_unreadable(built_library, "IC 360_sub", "frame_000.fit")
    _run_scan(client)
    other = built_library / "incoming" / "NGC 6888_sub"
    other.mkdir(parents=True, exist_ok=True)
    from tests.synth import write_seestar_fits
    write_seestar_fits(other / "frame_000.fit", width=48, height=32,
                       n_stars=3, seed=11)
    _run_scan(client, root=str(other))

    lib = Library.open_or_create(built_library / "library")
    try:
        assert decode_unreadable(lib.get_meta(UNREADABLE_SUBS_META_KEY)) \
            == {"IC 360_sub": 1}
    finally:
        lib.close()
