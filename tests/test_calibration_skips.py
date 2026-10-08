"""``webapp.calibrationskips`` — the record of what a scan passed over.

The lag note may not open anything under ``incoming/`` (AGENTS.md §10), so it
cannot ask the frames whether a folder is calibration data; it has always asked
:func:`seestack.calibrate.discover.find_calibration_folders` instead, and
v0.455.0 claimed that set was *identical* to the one the scan skips. Observer
issue #1088 is where that claim is false — see the module docstring for the two
granularities — so the scan now writes down the unit folders it actually passed
over and the note reads that too.

These are the record's own rules: it survives a round trip, it is byte-stable
between two scans that found the same thing, and anything else in the registry
degrades to "nothing known", which is the behaviour before it existed.
"""

from __future__ import annotations

from webapp.calibrationskips import (
    MAX_REMEMBERED_FOLDERS,
    SKIPPED_CALIBRATION_META_KEY,
    decode_calibration_skips,
    encode_calibration_skips,
    folders_from_scan,
    recall_calibration_skips,
    remember_calibration_skips,
)


class _Skip:
    def __init__(self, folder: str | None) -> None:
        self.folder = folder


class _Scan:
    def __init__(self, *folders: str | None) -> None:
        self.skipped_calibration_folders = [_Skip(f) for f in folders]


class _Lib:
    """The two methods of ``Library`` this record uses."""

    def __init__(self) -> None:
        self.meta: dict[str, str] = {}

    def set_meta(self, key: str, value: str) -> None:
        self.meta[key] = value

    def get_meta(self, key: str) -> str | None:
        return self.meta.get(key)


def test_a_scans_answer_survives_the_round_trip() -> None:
    lib = _Lib()
    remember_calibration_skips(lib, folders_from_scan(
        _Scan("Darks", "Flats", "")))

    assert recall_calibration_skips(lib) == {"Darks", "Flats", ""}
    assert SKIPPED_CALIBRATION_META_KEY in lib.meta


def test_the_root_unit_is_a_real_answer_and_unknown_is_not() -> None:
    """Darks loose in the drop folder are the ``Unsorted`` unit, whose folder is
    the empty string — so ``""`` cannot double as "the scan did not say". A
    record with no folder (an older engine) is dropped instead of guessed at."""
    assert folders_from_scan(_Scan("")) == [""]
    assert folders_from_scan(_Scan(None)) == []
    assert folders_from_scan(_Scan(None, "Darks")) == ["Darks"]


def test_the_same_finding_twice_writes_the_same_bytes() -> None:
    """A poll-driven scan runs often. A record that churned would rewrite the
    registry every time for no reason, so the order is the record's, not the
    scan's."""
    assert encode_calibration_skips(["Flats", "Darks"]) \
        == encode_calibration_skips(["Darks", "Flats", "Darks"])


def test_a_pathological_tree_is_capped_and_the_cap_lets_the_note_speak() -> None:
    """Dropping a folder from the record makes the note *name* it — the same
    direction the bug this record fixes already erred in, and the safe one for a
    value whose whole job is silencing."""
    many = [f"Darks {i:03d}" for i in range(MAX_REMEMBERED_FOLDERS + 20)]

    kept = decode_calibration_skips(encode_calibration_skips(many))

    assert len(kept) == MAX_REMEMBERED_FOLDERS
    assert kept <= set(many)


def test_anything_else_in_the_registry_reads_as_nothing_known() -> None:
    """Read on a poll: a truncated write or a shape from some future version
    must degrade to the pre-record behaviour, never 500 the Dashboard."""
    for raw in (None, "", "not json", "[]", "{}", '{"folders": 7}',
                '{"folders": [1, null, {"a": 1}]}'):
        assert decode_calibration_skips(raw) == set()

    # A newer writer that adds keys is still readable.
    assert decode_calibration_skips('{"folders": ["Darks"], "v": 2}') == {"Darks"}


def test_a_library_that_has_never_scanned_knows_nothing() -> None:
    assert recall_calibration_skips(_Lib()) == set()
