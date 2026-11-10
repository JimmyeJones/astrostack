"""seestack.diag.mosaic_hints — tells a per-panel pointing hint from a
mosaic-centre one by comparing each solved sub's hint with its own solved
centre, counts the panels a fix would find missing, reads the record only,
and publishes numbers without target names.
"""
from __future__ import annotations

import json

import pytest

from seestack.diag import DiagnosticStopped, check_result_is_safe, registry
from seestack.diag import mosaic_hints as mh
from seestack.io.project import FrameRow

# A 2×2 mosaic, panels 1° apart, around (150, 30).
PANELS = [(149.5, 29.5), (150.5, 29.5), (149.5, 30.5), (150.5, 30.5)]
MIDDLE = (150.0, 30.0)


def _row(hint, centre, reason=None):
    return (hint[0] if hint else None, hint[1] if hint else None,
            centre[0] if centre else None, centre[1] if centre else None, reason)


def _mosaic_rows(*, hint_is_panel: bool, lost_panel: int | None = None, per=10):
    rows = []
    for p, (ra, dec) in enumerate(PANELS):
        for k in range(per):
            centre = (ra + 0.002 * k, dec)            # a dither
            hint = (ra, dec) if hint_is_panel else MIDDLE
            if p == lost_panel:
                rows.append(_row(hint, None, "solve_failed:no solution"))
            else:
                rows.append(_row(hint, centre))
    return rows


def test_a_per_panel_hint_reads_per_panel():
    m = mh.measure_target(_mosaic_rows(hint_is_panel=True), is_mosaic_name=True)
    assert m["verdict"] == "per_panel"
    assert m["located_panels"] == 4 and m["hint_groups"] == 4
    assert m["share_hint_on_own_panel"] == 1.0
    assert m["unlocated_only_hint_groups"] == 0


def test_a_mosaic_centre_hint_reads_mosaic_centre():
    m = mh.measure_target(_mosaic_rows(hint_is_panel=False), is_mosaic_name=True)
    assert m["verdict"] == "mosaic_centre"
    assert m["located_panels"] == 4 and m["hint_groups"] == 1
    assert m["median_hint_to_own_centre_deg"] > 0.5
    assert m["median_hint_to_mosaic_middle_deg"] < 0.01


def test_a_panel_that_never_located_is_counted_under_per_panel_hints():
    m = mh.measure_target(_mosaic_rows(hint_is_panel=True, lost_panel=2),
                          is_mosaic_name=True)
    assert m["verdict"] == "per_panel"
    assert m["located_panels"] == 3
    assert m["unlocated"] == m["unlocated_solve_failed"] == 10
    assert m["unlocated_only_hint_groups"] == 1
    assert m["subs_in_unlocated_only_hint_groups"] == 10


def test_unlocated_subs_on_a_located_panel_are_not_a_missing_panel():
    rows = _mosaic_rows(hint_is_panel=True)
    rows += [_row(PANELS[0], None, "solve_failed:x")] * 8
    m = mh.measure_target(rows, is_mosaic_name=True)
    assert m["unlocated"] == 8
    assert m["unlocated_only_hint_groups"] == 0


def test_a_single_field_is_skipped_unless_named_a_mosaic():
    rows = [_row(MIDDLE, (150.0 + 0.002 * k, 30.0)) for k in range(30)]
    assert mh.measure_target(rows, is_mosaic_name=False) is None
    m = mh.measure_target(rows, is_mosaic_name=True)
    assert m["verdict"] == "cannot_tell" and m["located_panels"] == 1


def test_an_unnamed_target_whose_centres_split_is_measured():
    m = mh.measure_target(_mosaic_rows(hint_is_panel=True), is_mosaic_name=False)
    assert m is not None and m["mosaic_by_name"] is False


def test_hints_wrap_across_ra_zero():
    # Two panels straddling RA 0/360; per-panel hints must not read as far away.
    rows = []
    for ra in (359.6, 0.4):
        for k in range(8):
            rows.append(_row((ra, 10.0), ((ra + 0.002 * k) % 360.0, 10.0)))
    m = mh.measure_target(rows, is_mosaic_name=True)
    assert m["verdict"] == "per_panel"
    assert m["median_hint_to_mosaic_middle_deg"] < 0.5


@pytest.fixture
def library(tmp_path):
    from seestack.io.library import Library

    lib = Library.open_or_create(tmp_path / "library")

    def add(name, rows):
        _, proj = lib.create_target(name)
        try:
            for i, r in enumerate(rows):
                fid = proj.add_frame(FrameRow(
                    source_path=f"/data/incoming/{name}/s{i}.fit",
                    ra_hint_deg=r[0], dec_hint_deg=r[1]))
                if r[2] is not None:
                    proj.update_frame(fid, ra_center_deg=r[2], dec_center_deg=r[3])
                elif r[4]:
                    proj.update_frame(fid, reject_reason=r[4])
        finally:
            proj.close()
        lib.refresh_target_stats(name)

    add("NGC 7000 (mosaic)", _mosaic_rows(hint_is_panel=True, lost_panel=1))
    add("M 31 (mosaic)", _mosaic_rows(hint_is_panel=True, per=20))
    add("My secret backyard", [_row(MIDDLE, (150.0, 30.0))] * 12)
    yield lib
    lib.close()


def test_run_reads_the_record_and_publishes_numbers_only(library):
    seen = []
    res = mh.run(library, progress=lambda *a: seen.append(a))
    check_result_is_safe(res)
    text = json.dumps(res)
    assert "NGC" not in text and "secret" not in text and "incoming" not in text
    assert res["mosaic_targets"] == 2 and res["single_field_targets"] == 1
    assert res["verdicts"] == {"per_panel": 2}
    assert res["mosaics_with_an_unlocated_only_hint_group"] == 1
    assert [m["subs"] for m in res["mosaics"]] == [80, 40]     # largest first
    assert seen and seen[-1][1] == seen[-1][2] == 3


def test_run_stops_when_asked(library):
    with pytest.raises(DiagnosticStopped):
        mh.run(library, should_stop=lambda: True)


def test_ready_and_registered(library, tmp_path):
    from seestack.io.library import Library

    assert mh.ready(library)
    empty = Library.open_or_create(tmp_path / "empty")
    try:
        assert not mh.ready(empty)
    finally:
        empty.close()
    assert ("mosaic_panel_hints", 1) in [(d.name, d.version) for d in registry()]
