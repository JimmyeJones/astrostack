"""seestack.diag.twin_overcount — sets the registry's sums (what the Dashboard
headline shows) against each sub counted once by its source file, separates a
stale registry column from a double registration, lists sharing pairs without
names, and reads the record only.
"""
from __future__ import annotations

import json

import pytest

from seestack.diag import DiagnosticStopped, check_result_is_safe, registry
from seestack.diag import twin_overcount as tw
from seestack.io.project import FrameRow


def _add(lib, name, paths, *, exposure=30.0, rejected=()):
    _, proj = lib.create_target(name)
    try:
        for i, p in enumerate(paths):
            fid = proj.add_frame(FrameRow(source_path=p, exposure_s=exposure))
            if i in rejected:
                proj.update_frame(fid, accept=False)
    finally:
        proj.close()
    lib.refresh_target_stats(name)


def _paths(folder, n):
    return [f"/data/incoming/{folder}/s{i}.fit" for i in range(n)]


@pytest.fixture
def lib(tmp_path):
    from seestack.io.library import Library

    lib = Library.open_or_create(tmp_path / "library")
    yield lib
    lib.close()


def test_a_twin_pair_reads_as_double_counted(lib):
    # #878's shape: one folder's subs registered in two targets.
    _add(lib, "NGC 7000", _paths("NGC 7000_mosaic_sub", 3))
    _add(lib, "NGC 7000 (mosaic)", _paths("NGC 7000_mosaic_sub", 3))
    _add(lib, "My secret backyard", _paths("M 42_sub", 4))
    res = tw.run(lib)
    assert res["registry"] == {"n_frames": 10, "n_frames_accepted": 10,
                               "total_exposure_h": round(300 / 3600, 2)}
    assert res["distinct"]["n_frames"] == 7
    assert res["distinct"]["n_frames_accepted"] == 7
    assert res["distinct"]["total_exposure_h"] == round(210 / 3600, 2)
    assert res["record_sum"] == res["registry"]
    assert res["overcount"] == {"n_frames": round(10 / 7, 3),
                                "n_frames_accepted": round(10 / 7, 3),
                                "total_exposure": round(300 / 210, 3)}
    assert res["subs_in_two_or_more_targets"] == 3
    assert res["subs_in_three_or_more_targets"] == 0
    assert res["targets_sharing_subs"] == 2 and res["sharing_pairs"] == 1
    assert res["pairs"] == [{"shared_subs": 3, "subs_in_first": 3, "subs_in_second": 3,
                             "first_is_mosaic_name": False,
                             "second_is_mosaic_name": True}]


def test_a_library_without_twins_reads_honest(lib):
    _add(lib, "M 31", _paths("M 31_sub", 5), rejected={1})
    _add(lib, "M 42", _paths("M 42_sub", 4))
    res = tw.run(lib)
    assert res["overcount"] == {"n_frames": 1.0, "n_frames_accepted": 1.0,
                                "total_exposure": 1.0}
    assert res["distinct"]["n_frames"] == 9 and res["distinct"]["n_frames_accepted"] == 8
    assert res["sharing_pairs"] == 0 and res["pairs"] == []


def test_a_sub_rejected_in_one_twin_and_kept_in_the_other_counts_once_as_kept(lib):
    _add(lib, "A", _paths("f", 2), rejected={0})
    _add(lib, "B", _paths("f", 2))
    res = tw.run(lib)
    assert res["distinct"]["n_frames"] == 2
    assert res["distinct"]["n_frames_accepted"] == 2
    assert res["distinct"]["total_exposure_h"] == round(60 / 3600, 2)
    # registry: A has 1 accepted, B has 2
    assert res["registry"]["n_frames_accepted"] == 3


def test_a_sub_in_three_targets_is_counted_once(lib):
    for name in ("A", "B", "C"):
        _add(lib, name, _paths("f", 2))
    res = tw.run(lib)
    assert res["distinct"]["n_frames"] == 2
    assert res["subs_in_two_or_more_targets"] == 2
    assert res["subs_in_three_or_more_targets"] == 2
    assert res["overcount"]["n_frames"] == 3.0
    assert res["targets_sharing_subs"] == 3


def test_a_stale_registry_column_is_told_apart_from_a_duplicate(lib):
    _add(lib, "A", _paths("f", 3))
    _add(lib, "B", _paths("g", 2))
    # A sub lands in A's record without the registry being refreshed.
    proj = lib.open_target("A")
    try:
        proj.add_frame(FrameRow(source_path="/data/incoming/f/late.fit", exposure_s=30.0))
    finally:
        proj.close()
    res = tw.run(lib)
    assert res["registry"]["n_frames"] == 5
    assert res["record_sum"]["n_frames"] == 6
    assert res["distinct"]["n_frames"] == 6
    assert res["subs_in_two_or_more_targets"] == 0


def test_run_publishes_numbers_only(lib):
    _add(lib, "My secret backyard", _paths("M 42_sub", 2))
    _add(lib, "M 42 (mosaic)", _paths("M 42_sub", 2))
    seen = []
    res = tw.run(lib, progress=lambda *a: seen.append(a))
    check_result_is_safe(res)
    text = json.dumps(res)
    assert "secret" not in text and "incoming" not in text and "M 42" not in text
    assert seen and seen[-1][1] == seen[-1][2] == 2


def test_an_unopenable_target_is_counted_not_fatal(lib, monkeypatch):
    _add(lib, "A", _paths("f", 2))
    _add(lib, "B", _paths("f", 2))
    real = lib.open_target

    def flaky(safe):
        if safe == "B":
            raise OSError("locked")
        return real(safe)

    monkeypatch.setattr(lib, "open_target", flaky)
    res = tw.run(lib)
    assert res["unreadable_targets"] == 1
    assert res["distinct"]["n_frames"] == 2


def test_run_stops_when_asked(lib):
    _add(lib, "A", _paths("f", 2))
    with pytest.raises(DiagnosticStopped):
        tw.run(lib, should_stop=lambda: True)


def test_ready_needs_two_targets_with_subs_and_is_registered(lib):
    assert not tw.ready(lib)
    _add(lib, "A", _paths("f", 2))
    assert not tw.ready(lib)
    _add(lib, "B", _paths("g", 1))
    assert tw.ready(lib)
    assert ("twin_target_overcount", 1) in [(d.name, d.version) for d in registry()]
