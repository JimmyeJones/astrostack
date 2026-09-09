"""The upload form's destination advice and the scanner's own folder rules must
not drift apart.

``frontend/src/uploadDestination.ts`` tells a beginner what the folder name they
typed will do — which target it joins, and the two ways a plausible-looking name
silently costs them subs. Every one of those sentences is a claim about
:mod:`seestack.io.scanner`: which suffix marks raw subs, which folders are
skipped outright, and what a ``<T>_mosaic_sub`` folder is called once ingested.
TypeScript cannot import those constants, so they are mirrored by hand — the
same arrangement as ``fullres.ts`` / ``test_fullres_cap_mirror.py``, and guarded
here for the same reason: a stale copy would keep saying "adds to M 31" about an
upload the scanner walks straight past, with nothing failing.
"""

from __future__ import annotations

import re
from pathlib import Path

from seestack.io.scanner import (
    _CAPTURE_SUFFIXES,
    _MOSAIC_SUB_SUFFIX,
    _MOSAIC_TARGET_SUFFIX,
    _SUB_SUFFIX,
    _TEMP_FOLDER_NAMES,
    target_name_for_folder,
)

TS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "uploadDestination.ts"


def _src() -> str:
    return TS.read_text(encoding="utf-8")


def _ts_string(name: str) -> str:
    """The value of a top-level ``const <name> = "…";`` in the mirror module.

    Fails loudly when the declaration can't be found — a renamed or relocated
    constant *is* the drift this guard exists to catch, and a check that quietly
    passes when it cannot find its subject enforces nothing."""
    m = re.search(rf'^const {name}\s*=\s*"([^"]*)"\s*;', _src(), re.M)
    assert m is not None, (
        f"Could not find `const {name}` in {TS.name}. If it was renamed or "
        "moved, update this guard and check the wording still agrees with "
        "seestack/io/scanner.py — otherwise the upload form goes back to "
        "describing rules the scanner does not follow."
    )
    return m.group(1)


def _ts_string_list(name: str) -> list[str]:
    m = re.search(rf"^const {name}\s*=\s*\[([^\]]*)\]\s*;", _src(), re.M)
    assert m is not None, f"Could not find `const {name}` in {TS.name}."
    return re.findall(r'"([^"]*)"', m.group(1))


def test_the_raw_subs_suffixes_match_the_scanner():
    assert _ts_string("SUB_SUFFIX") == _SUB_SUFFIX
    assert _ts_string("MOSAIC_SUB_SUFFIX") == _MOSAIC_SUB_SUFFIX


def test_the_skipped_folder_names_match_the_scanner():
    assert _ts_string_list("CAPTURE_SUFFIXES") == list(_CAPTURE_SUFFIXES)
    assert sorted(_ts_string_list("TEMP_FOLDER_NAMES")) == sorted(_TEMP_FOLDER_NAMES)


def test_the_mosaic_target_naming_matches_the_scanner():
    """``M 31_mosaic_sub/`` becomes the target *M 31 (mosaic)*. The mirror spells
    that suffix inside a template literal, so pin it against the real one."""
    assert _MOSAIC_TARGET_SUFFIX in _src(), (
        f"{TS.name} no longer spells the mosaic target suffix "
        f"{_MOSAIC_TARGET_SUFFIX!r} that scanner.mosaic_target_name appends."
    )
    assert target_name_for_folder("M 31_mosaic_sub") == "M 31 (mosaic)"
    assert target_name_for_folder("M 31_sub") == "M 31"
