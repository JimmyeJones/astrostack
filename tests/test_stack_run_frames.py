"""Which subs a picture was *offered* — recorded, carried by a Combine, and read.

The 2026-09-30 audit's C-F1: "Bring my pictures up to date" measured a target's
new light against the *newest* genuine run by capture time. After a Combine the
newest genuine run is the one-night stack carried in, with its own recent
timestamp and a subset of the target's subs — so the deep target the Combine
existed to deepen answered "nothing missing", and the Dashboard note stayed
silent about the one target it should have named. The same reading was wrong for
any run that is a subset of the target: a carried night, a set-aside night, a
pinned older cover.

The fix is membership: ``stack_run_frames`` records which subs each run was
offered, the stacker writes it, a merge re-keys it, and a run that has it is
measured by set difference rather than by a clock. These pin the table, its
upgrade path (no ``SCHEMA_VERSION`` bump — the rollback guard), the freeze that
makes a legacy run measurable before a merge changes the frame set, and the
Combine itself: two nights combined, and each night's picture is missing exactly
the other night's subs.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from seestack.io.project import SCHEMA_VERSION, FrameRow, Project, StackRunRow

BEFORE = "2024-09-01T00:00:00+00:00"
NIGHT_1 = "2024-09-12T03:00:00+00:00"
STACK_1 = "2024-09-13T12:00:00+00:00"
NIGHT_2 = "2024-10-12T03:00:00+00:00"
STACK_2 = "2024-10-13T12:00:00+00:00"
# The deep target re-stacked *after* the second night was shot but before the
# two were combined — the shape in which every sub of the other night predates
# every picture, so the capture-time rule can see none of it.
STACK_1_AGAIN = "2024-10-20T12:00:00+00:00"
LATER = "2026-06-01T00:00:00+00:00"


def _run(ts: str, *, basename: str = "master", n: int = 3,
         options: dict | None = None, preview: str | None = None) -> StackRunRow:
    return StackRunRow(
        id=None, timestamp_utc=ts, output_basename=basename,
        fits_path=None, tiff_path=None, preview_path=preview,
        n_frames_used=n, canvas_h=8, canvas_w=8, coverage_min=1, coverage_max=1,
        options_json=json.dumps(options if options is not None
                                else {"sigma_clip": True}),
    )


def _frame(path: str, *, shot: str = NIGHT_1, solved: bool = True,
           accept: bool = True) -> FrameRow:
    return FrameRow(source_path=path, timestamp_utc=shot,
                    wcs_json="SIMPLE  =  T" if solved else None,
                    width_px=8, height_px=8, bayer_pattern="RGGB", accept=accept)


# ------------------------------------------------------------ the table -------


def test_the_record_round_trips_and_a_deleted_run_takes_its_record_with_it(tmp_path):
    proj = Project.create(tmp_path / "t", name="T")
    try:
        ids = [proj.add_frame(_frame(f"s{i}.fit")) for i in range(3)]
        run_id = proj.add_stack_run(_run(STACK_1))
        assert proj.stack_run_has_frame_record(run_id) is False
        assert proj.stack_run_frame_ids(run_id) is None

        # Recorded, de-duplicated, ordered; ``None`` ids are dropped.
        assert proj.set_stack_run_frames(run_id, [ids[2], ids[0], ids[0], None]) == 2
        assert proj.stack_run_frame_ids(run_id) == sorted([ids[0], ids[2]])
        assert proj.stack_run_has_frame_record(run_id) is True

        # A second write replaces the first rather than accumulating.
        proj.set_stack_run_frames(run_id, [ids[1]])
        assert proj.stack_run_frame_ids(run_id) == [ids[1]]

        proj.delete_stack_run(run_id)
        assert proj.stack_run_frame_ids(run_id) is None
    finally:
        proj.close()


def test_an_older_project_gains_the_table_on_open_without_a_version_bump(tmp_path):
    """§9, and specifically *rollback*: the table arrives through
    ``_AUX_TABLES_SQL`` on every open, never through a ``SCHEMA_VERSION`` bump
    — a bump makes the previous Docker image refuse to open every project this
    one has touched. So a project stamped current but written by a build that
    never heard of the table gains it, keeps its rows, and stays readable by
    the old build afterwards (it never asks about the table)."""
    proj_dir = tmp_path / "old"
    proj = Project.create(proj_dir, name="old")
    try:
        fid = proj.add_frame(_frame("sub.fit"))
        run_id = proj.add_stack_run(_run(STACK_1))
    finally:
        proj.close()
    conn = sqlite3.connect(proj_dir / "project.sqlite")
    try:
        conn.execute("DROP TABLE stack_run_frames")
        conn.commit()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()

    proj = Project.open(proj_dir)
    try:
        # Nothing recorded for the legacy run — and that is an answer, not an
        # error: it is measured by the capture-time rule.
        assert proj.stack_run_has_frame_record(run_id) is False
        assert proj.get_frame(fid) is not None
        proj.set_stack_run_frames(run_id, [fid])
        assert proj.stack_run_frame_ids(run_id) == [fid]
    finally:
        proj.close()
    assert SCHEMA_VERSION == 22, (
        "stack_run_frames is an unversioned aux table so the upgrade stays "
        "rollable; do not bump SCHEMA_VERSION for it")


# ---------------------------------------------------- the count, by membership --


def test_a_run_with_a_record_is_measured_by_membership_not_by_the_clock(tmp_path):
    """The whole point: a sub shot *before* the run and never restored is
    invisible to the capture-time rule, and missing from the picture all the
    same when the run never saw it."""
    proj = Project.create(tmp_path / "t", name="T")
    try:
        seen = [proj.add_frame(_frame(f"n1_{i}.fit", shot=NIGHT_1)) for i in range(3)]
        unseen = [proj.add_frame(_frame(f"n0_{i}.fit", shot=BEFORE)) for i in range(2)]
        run_id = proj.add_stack_run(_run(STACK_1))
        run = next(r for r in proj.iter_stack_runs() if r.id == run_id)

        # No record: the clock says nothing is missing (every sub predates it).
        assert proj.count_light_missing_from_stack(STACK_1) == 0
        assert proj.count_light_missing_from_run(run) == 0

        # With a record: the two subs the run never saw are missing from it —
        # fails before the fix, where no membership existed to consult.
        proj.set_stack_run_frames(run_id, seen)
        assert proj.count_light_missing_from_run(run) == 2

        # Same bar as the clock rule: a set-aside or un-located sub is not light
        # a re-stack could use, so it is not counted as waiting.
        proj.update_frame(unseen[0], accept=0)
        assert proj.count_light_missing_from_run(run) == 1
        proj.update_frame(unseen[1], wcs_json=None)
        assert proj.count_light_missing_from_run(run) == 0

        # And a sub the run *was* offered but shot later is not missing either —
        # membership, not time, is the test now.
        proj.update_frame(seen[0], timestamp_utc=LATER)
        assert proj.count_light_missing_from_run(run) == 0
        # A new sub, shot after, is missing on both readings.
        proj.add_frame(_frame("new.fit", shot=LATER))
        assert proj.count_light_missing_from_run(run) == 1
    finally:
        proj.close()


def test_freezing_a_legacy_run_records_exactly_what_the_clock_rule_still_calls_present(
        tmp_path):
    """Before a merge changes the frame set, a run with no record is given the
    capture-time rule's own answer — so the two readings agree at the moment of
    the freeze and diverge only for subs that arrive afterwards."""
    proj = Project.create(tmp_path / "t", name="T")
    try:
        present = proj.add_frame(_frame("a.fit", shot=NIGHT_1))
        shot_after = proj.add_frame(_frame("b.fit", shot=LATER))
        unsolved = proj.add_frame(_frame("c.fit", shot=NIGHT_1, solved=False))
        set_aside_before = proj.add_frame(_frame("d.fit", shot=NIGHT_1, accept=False))
        # Set aside *after* the run: it was in the picture, and a restoration
        # later would not make it new light.
        aside_after = proj.add_frame(_frame("e.fit", shot=NIGHT_1))
        # Restored after the run, set aside before it: genuinely missing.
        came_back = proj.add_frame(_frame("f.fit", shot=NIGHT_1))
        proj.update_frame(came_back, rejected_utc=BEFORE, restored_utc=LATER)
        run_id = proj.add_stack_run(_run(STACK_1))
        proj.update_frame(aside_after, accept=0, reject_reason="auto:grade:fwhm_px")
        assert (proj.get_frame(aside_after).rejected_utc or "") > STACK_1

        assert proj.freeze_unrecorded_stack_run_frames() == 1
        assert proj.stack_run_frame_ids(run_id) == sorted([present, aside_after])
        # Freezing twice changes nothing: the first answer stands.
        assert proj.freeze_unrecorded_stack_run_frames() == 0
        assert proj.stack_run_frame_ids(run_id) == sorted([present, aside_after])

        run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        # The clock rule and the membership rule agree on this frame set…
        assert proj.count_light_missing_from_stack(STACK_1) == 2   # b, f
        assert proj.count_light_missing_from_run(run) == 2
        # …and only membership sees a sub that arrives with an old timestamp.
        proj.add_frame(_frame("merged_in.fit", shot=BEFORE))
        assert proj.count_light_missing_from_stack(STACK_1) == 2
        assert proj.count_light_missing_from_run(run) == 3
        assert unsolved and set_aside_before and shot_after  # fixture rows, named
    finally:
        proj.close()


# ------------------------------------------------ the stacker writes it -------


def test_a_real_stack_records_the_subs_it_was_offered(tmp_path):
    """The stacker's own answer, including a sub it dropped itself: with a lucky
    fraction the run *combines* fewer subs than it was offered, and the ones it
    set aside are still recorded — a re-stack would set them aside again, so
    they are not light the owner is missing."""
    pytest.importorskip("astropy")
    pytest.importorskip("photutils")
    pytest.importorskip("scipy")
    from seestack.stack.stacker import StackOptions, run_stack
    from tests.synth import make_synth_wcs_text, write_seestar_fits

    proj = Project.create(tmp_path / "p", name="offered")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    ids = []
    for i in range(4):
        path = write_seestar_fits(raws / f"f{i}.fit", add_wcs=True, seed=i, n_stars=20)
        ids.append(proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            fwhm_px=2.0 + i,
        )))
    # A fifth sub the run must not be offered: set aside before the stack.
    aside = proj.add_frame(FrameRow(
        source_path=str(raws / "f0.fit") + ".copy", cached_path=str(raws / "f0.fit"),
        width_px=480, height_px=320, bayer_pattern="RGGB",
        wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4, accept=False,
    ))
    try:
        res = run_stack(proj, StackOptions(sigma_clip=False, background_flatten=False,
                                           max_workers=2, output_name="offered",
                                           lucky_fraction=0.5))
        assert res.run_id is not None
        assert res.n_frames_used == 2
        assert proj.stack_run_frame_ids(res.run_id) == sorted(ids)
        run = next(r for r in proj.iter_stack_runs() if r.id == res.run_id)
        assert proj.count_light_missing_from_run(run) == 0
        # The set-aside sub comes back: missing, because the run never saw it.
        proj.update_frame(aside, accept=1)
        assert proj.count_light_missing_from_run(run) == 1
    finally:
        proj.close()


# ---------------------------------------- a Combine carries and re-keys it ----


def _night(tmp_path: Path, name: str, *, shot: str, stacked: str, n: int) -> Project:
    """One night's project: ``n`` solved subs shot at ``shot`` and one finished
    picture of them stacked at ``stacked`` — with its files on disk, so the
    merge carries it (a run whose files are gone is deliberately not carried)."""
    proj = Project.create(tmp_path / name, name=name)
    for i in range(n):
        proj.add_frame(_frame(str(tmp_path / f"{name}_{i}.fit"), shot=shot))
    out = tmp_path / name / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "master.fits").write_bytes(name.encode())
    (out / "master_preview.png").write_bytes(b"png:" + name.encode())
    proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc=stacked, output_basename="master",
        fits_path=str(out / "master.fits"), tiff_path=None,
        preview_path=str(out / "master_preview.png"),
        n_frames_used=n, canvas_h=8, canvas_w=8, coverage_min=1, coverage_max=1,
        options_json=json.dumps({"sigma_clip": True}),
    ))
    return proj


def test_combining_two_nights_leaves_each_picture_missing_the_other_night(tmp_path):
    """The audit's repro. Neither run recorded its offered subs (both predate
    the table), so the freeze is what makes them measurable: the deep night's
    own picture is missing exactly the second night's subs, and the carried
    picture is missing exactly the first night's — by the clock, both read 0."""
    from seestack.io.merge import merge_projects

    deep = _night(tmp_path, "deep", shot=NIGHT_1, stacked=STACK_1_AGAIN, n=3)
    second = _night(tmp_path, "second", shot=NIGHT_2, stacked=STACK_2, n=2)
    second.close()
    try:
        (result,) = merge_projects(deep, [second.project_dir], copy_stack_runs=True)
        assert result.n_added == 2 and result.n_runs_copied == 1
        runs = list(deep.iter_stack_runs())            # newest first
        own, carried = runs[0], runs[1]
        assert own.timestamp_utc == STACK_1_AGAIN and carried.timestamp_utc == STACK_2

        # Fails before the fix: both counts were the clock's 0.
        assert deep.count_light_missing_from_stack(own.timestamp_utc) == 0
        assert deep.count_light_missing_from_stack(carried.timestamp_utc) == 0
        assert deep.count_light_missing_from_run(own) == 2
        assert deep.count_light_missing_from_run(carried) == 3

        # And the records are the destination's own ids, disjoint and complete.
        by_path = {Path(f.source_path).name: f.id for f in deep.iter_frames()}
        assert deep.stack_run_frame_ids(own.id) == sorted(
            by_path[f"deep_{i}.fit"] for i in range(3))
        assert deep.stack_run_frame_ids(carried.id) == sorted(
            by_path[f"second_{i}.fit"] for i in range(2))
    finally:
        deep.close()


def test_a_sub_both_nights_already_held_is_in_both_pictures(tmp_path):
    """A duplicate is not added twice, and the carried run's record lands on
    the row the destination already has for it."""
    from seestack.io.merge import merge_projects

    deep = _night(tmp_path, "deep", shot=NIGHT_1, stacked=STACK_1, n=2)
    second = _night(tmp_path, "second", shot=NIGHT_2, stacked=STACK_2, n=1)
    shared = str(tmp_path / "deep_0.fit")
    second.add_frame(_frame(shared, shot=NIGHT_1))
    second.close()
    try:
        (result,) = merge_projects(deep, [second.project_dir], copy_stack_runs=True)
        assert result.n_skipped_duplicate == 1
        carried = list(deep.iter_stack_runs())[0]
        shared_id = next(f.id for f in deep.iter_frames() if f.source_path == shared)
        assert shared_id in (deep.stack_run_frame_ids(carried.id) or [])
        # Missing from the carried picture: only deep_1.
        assert deep.count_light_missing_from_run(carried) == 1
    finally:
        deep.close()


def test_a_run_the_stacker_recorded_travels_as_recorded_not_re_derived(tmp_path):
    """The stacker's answer beats a reconstruction: a source run whose record
    says it was offered one of its two subs is carried with that one sub."""
    from seestack.io.merge import merge_projects

    deep = _night(tmp_path, "deep", shot=NIGHT_1, stacked=STACK_1, n=1)
    second = _night(tmp_path, "second", shot=NIGHT_2, stacked=STACK_2, n=2)
    src_run = next(iter(second.iter_stack_runs()))
    offered_path = str(tmp_path / "second_1.fit")
    offered_id = next(f.id for f in second.iter_frames() if f.source_path == offered_path)
    second.set_stack_run_frames(src_run.id, [offered_id])
    second.close()
    try:
        list(merge_projects(deep, [second.project_dir], copy_stack_runs=True))
        carried = list(deep.iter_stack_runs())[0]
        dest_id = next(f.id for f in deep.iter_frames() if f.source_path == offered_path)
        assert deep.stack_run_frame_ids(carried.id) == [dest_id]
        # deep_0 and second_0 are both light it never saw.
        assert deep.count_light_missing_from_run(carried) == 2
    finally:
        deep.close()


def test_an_older_caller_that_carries_without_the_map_records_nothing(tmp_path):
    """``carry_stack_runs`` on its own keeps its old contract: no map, no
    record, the carried run is measured by the clock exactly as before."""
    from seestack.io.merge import carry_stack_runs

    deep = _night(tmp_path, "deep", shot=NIGHT_1, stacked=STACK_1, n=1)
    second = _night(tmp_path, "second", shot=NIGHT_2, stacked=STACK_2, n=1)
    try:
        assert carry_stack_runs(deep, second).copied == 1
        carried = list(deep.iter_stack_runs())[0]
        assert deep.stack_run_has_frame_record(carried.id) is False
    finally:
        deep.close()
        second.close()
