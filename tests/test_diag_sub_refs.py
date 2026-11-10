"""The library diagnostics survey the library without holding its plate solutions.

Both diagnostics look at **every** sub of the library before they sample a few
hundred: `sensor_pattern_by_temperature` sorts every accepted sub into a
temperature range and holds that survey for the whole run, and
`filter_card_values` reads each target's subs to pick its nights. They did it
with `Project.iter_frames`, and a `FrameRow` is `SELECT *` — on a solved sub,
~2 kB of plate-solve header text. On the owner's library (tens of thousands of
subs, 35,894 on one target) that was hundreds of MB held for minutes by a job
that runs on its own after an update, on a box with an OOM history.

They now read four columns (`seestack.diag.SubRef`). What these tests pin is
the property itself (no `FrameRow` is built, and the survey's peak is a small
fraction of the row read's on the same subs) and that the answer is the one
the row read gave — same subs, same order, same seeded sample, so neither
diagnostic's `version` moves.
"""
from __future__ import annotations

import tracemalloc

import pytest

import seestack.io.project as project_module
from seestack.diag import SubRef, iter_sub_refs, sub_path
from seestack.diag import filter_card as fc
from seestack.diag import sensor_pattern as sp
from seestack.io.project import FrameRow

#: A solved sub's plate solution — the bulk of a row, and what the survey must
#: not hold. A fixture without one measures nothing.
WCS = "".join(f"CARD{c:02d}  = 1.2345678901E+02".ljust(80) for c in range(25))


def _rows_survey(proj, *, accepted_only=False):
    """The old survey: whole rows."""
    return proj.iter_frames(accepted_only=accepted_only)


@pytest.fixture
def deep_library(tmp_path):
    """Six targets of solved, accepted subs at two temperatures, no files on
    disk — the survey is what is measured, not the reading of pixels."""
    from seestack.io.library import Library

    lib = Library.open_or_create(tmp_path / "library")
    for t in range(6):
        _, proj = lib.create_target(f"NGC {7000 + t}", ra_deg=20.0 + 40 * t, dec_deg=10.0)
        try:
            proj.add_frames([FrameRow(
                source_path=f"/incoming/NGC {7000 + t}_sub/f{i:05d}.fit",
                wcs_json=WCS, accept=True,
                timestamp_utc=f"2026-01-{10 + i % 9:02d}T03:{i % 60:02d}:00",
                sensor_temp_c=-3.0 if i % 2 else 22.0,
            ) for i in range(600)])
        finally:
            proj.close()
        lib.refresh_target_stats(f"NGC {7000 + t}")
    yield lib
    lib.close()


def test_a_sub_ref_is_the_rows_own_values_in_the_rows_own_order(deep_library):
    entry = deep_library.list_targets()[0]
    proj = deep_library.open_target(entry.safe_name)
    try:
        for accepted_only in (False, True):
            rows = list(proj.iter_frames(accepted_only=accepted_only))
            refs = list(iter_sub_refs(proj, accepted_only=accepted_only))
            assert len(refs) == len(rows) > 0
            for r, f in zip(refs, rows, strict=True):
                assert r == SubRef(f.cached_path, f.source_path, f.timestamp_utc,
                                   f.sensor_temp_c)
    finally:
        proj.close()


def test_sub_path_is_the_apps_one_rule(tmp_path):
    src = tmp_path / "src.fit"
    src.write_bytes(b"x")
    cache = tmp_path / "cache.fit"
    ref = SubRef(str(cache), str(src), None, None)
    assert sub_path(ref) == str(src)          # a cleared cache falls through
    cache.write_bytes(b"x")
    assert sub_path(ref) == str(cache)        # a present cache is preferred
    assert sub_path(SubRef(None, str(tmp_path / "gone.fit"), None, None)) is None
    row = FrameRow(source_path=str(src))      # a FrameRow still answers too
    assert sub_path(row) == str(src)


@pytest.mark.parametrize("module", [sp, fc], ids=["sensor_pattern", "filter_card"])
def test_the_survey_builds_no_frame_rows(deep_library, module, monkeypatch):
    """Fail-before: both built a `FrameRow` per sub of the library."""
    built = 0
    real = project_module._row_to_frame

    def counting(row):
        nonlocal built
        built += 1
        return real(row)

    monkeypatch.setattr(project_module, "_row_to_frame", counting)
    module.run(deep_library)
    assert built == 0, f"built {built} FrameRow objects"


@pytest.mark.parametrize("module", [sp, fc], ids=["sensor_pattern", "filter_card"])
def test_the_answer_is_the_one_the_row_read_gave(deep_library, module, monkeypatch):
    """Same subs, same order, same seeded sample — so no `version` bump."""
    new = module.run(deep_library)
    monkeypatch.setattr(module, "iter_sub_refs", _rows_survey)
    old = module.run(deep_library)
    assert new == old


def test_holding_the_survey_costs_a_fraction_of_holding_the_rows(deep_library,
                                                                 monkeypatch):
    """The memory claim, measured against the row read on the same 3,600 subs.

    `sensor_pattern` holds its survey for the whole run, so its peak *is* the
    survey. Measured here: ~16 MB as rows against ~2 MB as `SubRef`s."""
    def peak() -> int:
        tracemalloc.start()
        try:
            sp.run(deep_library)
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    new = peak()
    monkeypatch.setattr(sp, "iter_sub_refs", _rows_survey)
    old = peak()
    assert new < old / 4, f"survey peak {new / 1e6:.1f} MB vs rows {old / 1e6:.1f} MB"
