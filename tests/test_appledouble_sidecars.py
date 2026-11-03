"""macOS AppleDouble sidecars (``._<name>.fit``) in ``incoming/`` are not subs.

A Mac that copies onto a share without native resource-fork support writes a
4 KB ``._<name>`` twin beside every file it copies. It ends in ``.fit`` like its
twin, so before this every walker of ``incoming/`` took it for a sub: the scan
registered one unreadable "sub" per real one, ``unreadablesubs`` listed them on
the Jobs page, and the incoming-lag note counted them as waiting forever (Scout
2026-11-03, QA sweep (3)). The skip is one shared, name-only predicate
(:func:`seestack.io.ingest.is_appledouble_sidecar`) so the plan — which may not
open files — and the scan cannot disagree. Nothing here writes to ``incoming/``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.ingest import find_fits_files, is_appledouble_sidecar
from seestack.io.library import UNSORTED_TARGET_NAME, Library
from seestack.io.scanner import plan_incoming_units, scan_and_organize
from tests.synth import write_seestar_fits

# The AppleDouble header: magic 0x00051607, version 0x00020000, 16 filler bytes.
_APPLEDOUBLE = (b"\x00\x05\x16\x07\x00\x02\x00\x00" + b"Mac OS X        "
                + b"\x00" * 4070)


def _fits(path: Path, seed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_seestar_fits(path, width=48, height=32, n_stars=3, seed=seed)


def _twin(path: Path) -> Path:
    side = path.with_name("._" + path.name)
    side.write_bytes(_APPLEDOUBLE)
    return side


def _mac_copied_tree(root: Path) -> list[Path]:
    """Four subs in a ``_sub`` folder and two loose, each with its sidecar."""
    sidecars: list[Path] = []
    for i in range(4):
        p = root / "M 42_sub" / f"Light_M 42_10.0s_IRCUT_2026110{i}-220000.fit"
        _fits(p, seed=i + 1)
        sidecars.append(_twin(p))
    for i in range(2):
        p = root / f"Light_loose_{i}.fits"
        _fits(p, seed=10 + i)
        sidecars.append(_twin(p))
    (root / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    return sidecars


def _snapshot(root: Path) -> dict[str, tuple[int, float, int]]:
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            st = os.stat(os.path.join(dirpath, name))
            out[os.path.join(dirpath, name)] = (st.st_size, st.st_mtime, st.st_mode)
    return out


@pytest.mark.parametrize("name, expected", [
    ("._Light_M 42_10.0s.fit", True),
    ("._x.FITS", True),
    ("._", True),
    ("Light_M 42_10.0s.fit", False),
    ("_Light.fit", False),
    (".hidden.fit", False),  # a dot-name, but not AppleDouble's — part (b)'s question
    ("a._b.fit", False),
])
def test_the_predicate_keys_on_the_appledouble_prefix_only(
        name: str, expected: bool) -> None:
    assert is_appledouble_sidecar(name) is expected
    assert is_appledouble_sidecar(Path("/data/incoming/M 42_sub") / name) is expected


def test_find_fits_files_does_not_list_a_sidecar(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    sidecars = _mac_copied_tree(incoming)
    found = find_fits_files(incoming)
    assert len(found) == 6
    assert not set(found) & set(sidecars)
    assert find_fits_files(sidecars[0]) == []
    assert len(find_fits_files(incoming, recursive=False)) == 2


def test_the_plan_ignores_a_sidecar_it_is_handed(tmp_path: Path) -> None:
    """The plan takes a listing, not a walk — a caller's listing that still
    carries a sidecar must not grow a folder's count."""
    incoming = tmp_path / "incoming"
    sidecars = _mac_copied_tree(incoming)
    listing = {str(p): p.stat().st_mtime for p in find_fits_files(incoming)}
    listing.update({str(p): p.stat().st_mtime for p in sidecars})
    planned = {u.folder: (u.target_name, u.n_files)
               for u in plan_incoming_units(incoming, listing)}
    assert planned == {"M 42_sub": ("M 42", 4), "": (UNSORTED_TARGET_NAME, 2)}


def test_the_scan_neither_ingests_nor_reports_a_sidecar(tmp_path: Path) -> None:
    """The repro: before, ``M 42`` found 8, added 4 and reported four ``._``
    names as unreadable subs; loose sidecars did the same in Unsorted."""
    incoming = tmp_path / "incoming"
    _mac_copied_tree(incoming)
    before = _snapshot(incoming)

    planned = plan_incoming_units(
        incoming, {str(p): p.stat().st_mtime for p in find_fits_files(incoming)})
    lib = Library.open_or_create(tmp_path / "library")
    try:
        result = scan_and_organize(lib, incoming, copy_to_cache=False)
    finally:
        lib.close()

    by_name = {t.target_name: t for t in result.targets}
    assert set(by_name) == {"M 42", UNSORTED_TARGET_NAME}
    for name, n in (("M 42", 4), (UNSORTED_TARGET_NAME, 2)):
        t = by_name[name]
        assert (t.n_frames_found, t.n_frames_added, t.n_errors) == (n, n, 0), name
        assert not any(os.path.basename(str(e)).startswith("._")
                       for e in t.unreadable_examples), name
    # The plan and the scan still agree, sidecars and all.
    assert (sorted((u.target_name, u.n_files) for u in planned)
            == sorted((t.target_name, t.n_frames_found) for t in result.targets))
    # AGENTS.md §10: the scan read incoming/ and changed nothing in it.
    assert _snapshot(incoming) == before
