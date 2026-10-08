"""``GET /api/incoming-lag`` — subs in the drop folder the library has no row for.

Run against the real fixture library (two ingested targets), so the ordinary
answer here is the one every healthy install gets: nothing waiting. The failing
shapes are made by adding files to ``incoming/`` *without* scanning them, which
is exactly what the observer measured on the owner's box.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.scanner import plan_incoming_units
from webapp.incominglag import LAG_MIN_AGE_S, SNAPSHOT_MAX_AGE_S
from webapp.watcher import Watcher

LONG_AGO_S = 11 * 24 * 3600.0


def _age_everything(root: Path, seconds: float) -> None:
    """Push every FITS under ``root`` into the past, so the folder has stopped
    moving as far as the age rule is concerned."""
    when = time.time() - seconds
    for p in root.rglob("*.fit"):
        import os
        os.utime(p, (when, when))


def _poll(client) -> None:
    """One watcher poll — the only thing that reads ``incoming/`` here."""
    client.app.state.watcher.poll_once()


def test_a_scanned_library_has_nothing_waiting(built_library, client):
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert body["n_waiting"] == 0
    assert body["n_folders"] == 0
    assert body["items"] == []
    assert body["checked_utc"]


def test_subs_that_never_reached_the_library_are_named(built_library, client):
    """The observer's shape: a night's subs on disk, in no ``frames`` table."""
    from tests.synth import write_seestar_fits

    d = built_library / "incoming" / "IC 360_sub"
    d.mkdir(parents=True)
    for i in range(4):
        write_seestar_fits(d / f"frame_{i:03d}.fit", width=48, height=32,
                           n_stars=3, seed=200 + i)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["n_waiting"] == 4
    assert body["n_folders"] == 1
    (item,) = body["items"]
    assert item["folder"] == "IC 360_sub"
    assert item["target_name"] == "IC 360"
    assert (item["n_on_disk"], item["n_imported"], item["n_waiting"]) == (4, 0, 4)
    assert item["still_hours"] >= LAG_MIN_AGE_S / 3600.0


def test_a_night_that_is_still_arriving_is_not_reported(built_library, client):
    """Fresh files are *supposed* to be ahead of the library — the import runs
    within minutes. Only a folder that has stopped moving speaks."""
    from tests.synth import write_seestar_fits

    _age_everything(built_library / "incoming", LONG_AGO_S)
    d = built_library / "incoming" / "IC 360_sub"
    d.mkdir(parents=True)
    write_seestar_fits(d / "frame_000.fit", width=48, height=32, n_stars=3, seed=9)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert body["n_waiting"] == 0


def test_the_convention_skips_are_not_reported_as_lag(built_library, client):
    """A Seestar's own picture beside its raw subs is skipped on purpose, so it
    is never "waiting to be imported" however long it sits there."""
    from tests.synth import write_seestar_fits

    incoming = built_library / "incoming"
    (incoming / "M_42_sub").mkdir(parents=True)
    write_seestar_fits(incoming / "M_42_sub" / "frame_000.fit",
                       width=48, height=32, n_stars=3, seed=11)
    (incoming / "Moon_video").mkdir(parents=True)
    write_seestar_fits(incoming / "Moon_video" / "frame_000.fit",
                       width=48, height=32, n_stars=3, seed=12)
    _age_everything(incoming, LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    folders = {i["folder"] for i in body["items"]}
    # "M_42/" is the fixture's own bare folder; it now has an "M_42_sub" sibling,
    # so the convention reads it as device output — and so must this note.
    assert "M_42" not in folders
    assert "Moon_video" not in folders
    assert folders == {"M_42_sub"}


def test_without_a_fresh_listing_it_declines_to_answer(built_library, client):
    """A stale snapshot would name folders that have since been imported, so the
    note says "nobody has looked" rather than repeating an old count. That is a
    different statement from "nothing is waiting", and the response carries it."""
    from tests.synth import write_seestar_fits

    d = built_library / "incoming" / "IC 360_sub"
    d.mkdir(parents=True)
    write_seestar_fits(d / "frame_000.fit", width=48, height=32, n_stars=3, seed=13)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)
    assert client.get("/api/incoming-lag").json()["n_waiting"] == 1

    watcher = client.app.state.watcher
    units, _ = watcher.incoming_units()
    watcher._incoming_reading = (units, time.time() - SNAPSHOT_MAX_AGE_S - 1)
    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is False
    assert body["n_waiting"] == 0
    assert body["checked_utc"] == ""


def test_a_missing_incoming_folder_clears_the_listing_rather_than_emptying_it(
        tmp_path, monkeypatch):
    """A folder that cannot be found has its own note. Answering "nothing is
    waiting" from a poll that could not look would be a claim it cannot make."""
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "M 42_sub").mkdir()
    (incoming / "M 42_sub" / "a.fit").write_bytes(b"x")

    class _S:
        resolved_incoming_dir = incoming
        watch_quiet_period_s = 0
        watcher_enabled = True

    w = Watcher(get_settings=lambda: _S(), on_batch_ready=lambda: True)
    w.poll_once()
    units, polled_at = w.incoming_units()
    assert polled_at > 0
    assert [u.folder for u in units] == ["M 42_sub"]

    (incoming / "M 42_sub" / "a.fit").unlink()
    (incoming / "M 42_sub").rmdir()
    incoming.rmdir()
    w.poll_once()
    assert w.incoming_units() == ([], 0.0)


def test_a_grouping_failure_never_costs_a_poll(tmp_path, monkeypatch):
    """The watcher's job is to get frames in; this note is about frames that did
    not. A report that broke the import would be strictly worse than no report."""
    incoming = tmp_path / "incoming"
    (incoming / "M 42_sub").mkdir(parents=True)
    (incoming / "M 42_sub" / "a.fit").write_bytes(b"x")

    class _S:
        resolved_incoming_dir = incoming
        watch_quiet_period_s = 0
        watcher_enabled = True

    fired: list[bool] = []
    w = Watcher(get_settings=lambda: _S(),
                on_batch_ready=lambda: fired.append(True) or True)

    def _boom(*a, **kw):
        raise RuntimeError("nope")

    monkeypatch.setattr("webapp.watcher.plan_incoming_units", _boom)
    w.poll_once()                      # arms the file
    assert w.poll_once() == {str(incoming / "M 42_sub" / "a.fit")}
    assert fired == [True]
    assert w.incoming_units() == ([], 0.0)


def test_the_endpoint_and_the_plan_answer_from_the_same_listing(
        built_library, client):
    """One definition: the endpoint's on-disk counts are ``plan_incoming_units``
    over the watcher's listing, not a second reading of the folder."""
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    units, _ = client.app.state.watcher.incoming_units()
    incoming = built_library / "incoming"
    from seestack.io.ingest import find_fits_files
    direct = plan_incoming_units(
        incoming, {str(p): p.stat().st_mtime for p in find_fits_files(incoming)})
    assert sorted((u.folder, u.n_files) for u in units) == \
        sorted((u.folder, u.n_files) for u in direct)


# --- A file that cannot be read is not "waiting" ------------------------------
#
# This endpoint compares files on disk with frame rows, which is the right
# question and is blind to *why* a row is missing. A damaged or headerless FITS
# has no row **permanently**, so it counts as waiting forever and the Dashboard
# note has been saying "haven't been imported yet" over a **Scan incoming now**
# button that can never import it — on the owner's own library, about six files,
# since May. The scan is the only thing that opens these files, so the scan
# writes down what it found (``webapp/unreadablesubs.py``) and this reads it.

def _drop_unreadable(root: Path, folder: str, name: str) -> Path:
    """A non-empty file with no FITS header, the shape the owner's damaged subs
    have (right byte count, no ``SIMPLE`` card)."""
    d = root / "incoming" / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(b"\x00" * 8192)
    return p


def _scan(client) -> None:
    """A whole-library scan — the only thing that may write the record."""
    r = client.post("/api/scan", json={})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    end = time.monotonic() + 120
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            assert body["state"] == "done", body
            return
        time.sleep(0.1)
    raise AssertionError("scan did not finish")


def test_a_damaged_sub_is_reported_as_unreadable_not_merely_waiting(
        built_library, client):
    """Every waiting file in the folder is one nothing can import."""
    _drop_unreadable(built_library, "IC 360_sub", "frame_000.fit")
    _scan(client)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["n_waiting"] == 1
    # The fact the note needs to stop offering a scan it cannot deliver on.
    assert body["n_unreadable"] == 1
    (item,) = body["items"]
    assert item["folder"] == "IC 360_sub"
    assert (item["n_waiting"], item["n_unreadable"]) == (1, 1)


def test_a_folder_that_is_part_damaged_reports_both_numbers(built_library, client):
    """The mixed case, where the headline really is a delay and only some of it
    is damage — the note keeps its title and gains a sentence."""
    from tests.synth import write_seestar_fits

    _drop_unreadable(built_library, "IC 360_sub", "frame_000.fit")
    _scan(client)
    # Two good subs arriving *after* the scan: never imported, genuinely waiting.
    d = built_library / "incoming" / "IC 360_sub"
    for i in (1, 2):
        write_seestar_fits(d / f"frame_{i:03d}.fit", width=48, height=32,
                           n_stars=3, seed=300 + i)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["n_waiting"] == 3
    assert body["n_unreadable"] == 1
    (item,) = body["items"]
    assert (item["n_waiting"], item["n_unreadable"]) == (3, 1)


def test_a_healthy_library_reports_no_unreadable_files(built_library, client):
    """The silence guard: the ordinary answer is unchanged in every field."""
    _scan(client)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert (body["n_waiting"], body["n_unreadable"]) == (0, 0)


def test_a_repaired_sub_leaves_the_record_on_the_next_scan(built_library, client):
    """The record is replaced by each whole-library scan rather than merged, so a
    file that has been fixed or deleted stops being called unreadable."""
    bad = _drop_unreadable(built_library, "IC 360_sub", "frame_000.fit")
    _scan(client)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)
    assert client.get("/api/incoming-lag").json()["n_unreadable"] == 1

    # The owner re-copies the sub; now it reads, and the scan imports it.
    from tests.synth import write_seestar_fits
    bad.unlink()
    write_seestar_fits(bad, width=48, height=32, n_stars=3, seed=400)
    _scan(client)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["n_unreadable"] == 0
    assert body["n_waiting"] == 0


def test_darks_in_the_drop_folder_are_not_reported_as_waiting(built_library, client):
    """End to end, through the real endpoint: a folder of frames that declare
    themselves darks is calibration data the scan passes over on purpose
    (v0.455.0), so it is not a night that failed to land and this note must not
    say it is.

    The exclusion comes off the same ``incoming/`` walk the Calibration page's
    "shall I build the master?" offer is built from, so nothing extra is opened
    under a folder this app may only read (AGENTS.md §10)."""
    from webapp.sample_data import write_sample_calibration_frames

    write_sample_calibration_frames(
        built_library / "incoming" / "Darks 10s", "dark")
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    # The offer sees it — this is the set the note excludes, so a test that
    # asserted only silence would pass just as well if the walk found nothing.
    offer = client.get("/api/calibration/incoming").json()
    assert [f["name"] for f in offer["folders"]] == ["Darks 10s"]

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert body["n_waiting"] == 0
    assert body["items"] == []


# --- A folder two targets claim is counted once, not twice ---------------------
#
# Issue #878's mosaic double-registration left the same subs registered under two
# targets across 76 % of the owner's frames, and the tally this endpoint joins
# against used to *add* the two targets' counts. Such a folder therefore read as
# about twice as imported as it is, ``waiting`` went negative, and the guard
# dropped it — so the one signal built to catch subs that silently never imported
# (v0.442.0) was dark on 30 of his 54 drop folders, a combined 41,727 subs
# (v0.492.35). The counts are distinct now, and distinctly rather than by a
# ``max`` across targets, for the reason the disjoint test below pins.


def _registered_paths(root: Path, folder: str) -> list[str]:
    """Every ``source_path`` the library already holds for ``folder``."""
    from seestack.io.library import Library

    out: list[str] = []
    lib = Library.open_or_create(root / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                out += [f.source_path for f in proj.iter_frames()
                        if Path(f.source_path).parent.name == folder]
            finally:
                proj.close()
    finally:
        lib.close()
    return out


def _register_under_a_new_target(root: Path, name: str, paths) -> None:
    """A second target carrying frame rows for ``paths`` — #878's shape.

    Nothing on disk moves: the duplicate is a second set of rows pointing at the
    one copy of each sub, which is exactly what the safe-name collision in
    ``Library._allocate_safe_name`` minted eleven times on the owner's library.
    """
    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    lib = Library.open_or_create(root / "library")
    try:
        _, twin = lib.create_target(name)
        try:
            twin.add_frames([FrameRow(source_path=str(p)) for p in paths])
        finally:
            twin.close()
    finally:
        lib.close()


def _drop_new_subs(root: Path, folder: str, *seeds: int) -> None:
    """Good subs arriving in a folder the library already has rows for: never
    imported, genuinely waiting."""
    from tests.synth import write_seestar_fits

    d = root / "incoming" / folder
    d.mkdir(parents=True, exist_ok=True)
    for s in seeds:
        write_seestar_fits(d / f"late_{s:03d}.fit", width=48, height=32,
                           n_stars=3, seed=s)


def test_a_folder_two_targets_claim_still_names_its_missing_subs(
        built_library, client):
    """The observer's measured shape: two never-imported subs in a folder whose
    rows exist twice over. Summed, the tally (3 + 3) exceeded the five files on
    disk and the folder never spoke at all."""
    _drop_new_subs(built_library, "M_42", 701, 702)
    paths = _registered_paths(built_library, "M_42")
    assert len(paths) == 3, paths
    _register_under_a_new_target(built_library, "M_42 twin", paths)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert body["n_waiting"] == 2
    item = next(i for i in body["items"] if i["folder"] == "M_42")
    assert (item["n_on_disk"], item["n_imported"], item["n_waiting"]) == (5, 3, 2)


def test_a_fully_imported_folder_two_targets_claim_stays_silent(
        built_library, client):
    """The other half of the same fix: de-duplicating must not *invent* lag on a
    folder whose subs are all in the library. The ordinary answer is unchanged."""
    _register_under_a_new_target(built_library, "M_42 twin",
                                 _registered_paths(built_library, "M_42"))
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert (body["n_waiting"], body["n_folders"], body["items"]) == (0, 0, [])


def test_two_targets_holding_disjoint_halves_of_one_folder_report_nothing(
        built_library, client):
    """Why the tally is a distinct count and not a ``max`` across targets.

    A ``max`` is exactly right for #878's frame-for-frame duplicates and wrong
    here: two targets each holding *part* of one folder's subs are between them
    holding all of them, so a ``max`` would call the rest of a fully-imported
    folder missing — this note crying wolf about subs that are in the library,
    which is the one direction it is designed never to go. (It passes under the
    old sum too: it is the guard on the fix, not the fix's own repro.)
    """
    _drop_new_subs(built_library, "M_42", 801, 802)
    later = sorted((built_library / "incoming" / "M_42").glob("late_*.fit"))
    assert len(later) == 2
    # The two late subs reach the library under a *different* target, so no file
    # is registered twice and the folder is in fact fully imported.
    _register_under_a_new_target(built_library, "M_42 panel 2", later)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert body["n_waiting"] == 0


def test_a_library_with_no_shared_folder_reads_not_one_extra_row(
        built_library, client, monkeypatch):
    """The de-duplication is paid only where targets actually overlap, so every
    other install reads exactly what it read before. Prove the spy is wired up by
    watching it fire once the duplicate exists."""
    from seestack.io.project import Project

    asked: list[str] = []
    real = Project.source_paths_in_folder

    def spy(self, prefix, folder, *a, **k):  # noqa: ANN001, ANN002, ANN003
        asked.append(folder)
        return real(self, prefix, folder, *a, **k)

    monkeypatch.setattr(Project, "source_paths_in_folder", spy)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    assert client.get("/api/incoming-lag").json()["checked"] is True
    assert asked == []

    _register_under_a_new_target(built_library, "M_42 twin",
                                 _registered_paths(built_library, "M_42"))
    assert client.get("/api/incoming-lag").json()["checked"] is True
    assert asked == ["M_42", "M_42"]      # one read per target that claims it


def test_a_dedupe_that_cannot_be_completed_keeps_the_quieter_summed_tally(
        built_library, client, monkeypatch):
    """An under-count is the direction that makes this note cry wolf, so a union
    that is missing a target's frames is never used: the folder falls back to the
    old, summed number — quieter, and wrong only in the way it was wrong before.
    A broken target must also not 500 the note."""
    from seestack.io.project import Project

    _drop_new_subs(built_library, "M_42", 901, 902)
    _register_under_a_new_target(built_library, "M_42 twin",
                                 _registered_paths(built_library, "M_42"))
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)
    assert client.get("/api/incoming-lag").json()["n_waiting"] == 2

    def boom(self, prefix, folder, *a, **k):  # noqa: ANN001, ANN002, ANN003
        raise RuntimeError("unreadable project")

    monkeypatch.setattr(Project, "source_paths_in_folder", boom)
    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert body["n_waiting"] == 0


# --- A calibration folder one level deep (observer issue #1088) ---------------
#
# The exclusion above reads the Calibration page's own ``incoming/`` walk, and
# v0.455.0 claimed that set was *identical* to the one the scan passes over: the
# scanner's skip carries ``discover.MIN_FRAMES``, so "a folder could not fall
# between them". It only ever was identical for darks sitting **directly** in a
# top-level folder. The scan plans a recursive *unit* (``Darks``) where discovery
# classifies an individual *directory* (``Darks/20s``) — and the Calibration
# page's own ``MAX_DEPTH = 2`` invites exactly that nesting — so the note named
# ``Darks`` over a **Scan incoming** button that will never import it. The scan
# knows the unit boundaries and has just read the headers, so the scan writes
# down what it skipped (``webapp/calibrationskips.py``) and this reads it too.


def test_darks_one_folder_deep_are_not_reported_as_waiting(built_library, client):
    """#1088, end to end through the real endpoint."""
    from webapp.sample_data import write_sample_calibration_frames

    write_sample_calibration_frames(
        built_library / "incoming" / "Darks" / "20s", "dark")
    _scan(client)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    # The granularity the bug lives in, asserted rather than assumed: discovery
    # names the directory one level down…
    offer = client.get("/api/calibration/incoming").json()
    assert [f["rel_path"] for f in offer["folders"]] == ["Darks/20s"]
    # …while the plan this note joins against names the unit above it, so the
    # two strings cannot match and a test that only asserted silence would pass
    # just as well if the nesting had never been planned as a unit at all.
    units, _ = client.app.state.watcher.incoming_units()
    assert "Darks" in {u.folder for u in units}

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert body["n_waiting"] == 0
    assert body["items"] == []


def test_two_half_full_dark_directories_are_not_reported_as_waiting(
        built_library, client):
    """The second half of #1088, which no amount of string matching could fix:
    ``MIN_FRAMES`` is the scan's floor on the whole **unit** and discovery's
    floor on each **directory**, so three darks in each of two directories is
    one skipped six-frame unit that the Calibration page does not offer at
    all — there is nothing in the discovery set to match against."""
    from seestack.calibrate.discover import MIN_FRAMES
    from webapp.sample_data import write_sample_calibration_frames

    half = MIN_FRAMES - 2
    for part in ("a", "b"):
        write_sample_calibration_frames(
            built_library / "incoming" / "Darks 20s" / part, "dark", n=half)
    _scan(client)
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    assert client.get("/api/calibration/incoming").json()["folders"] == []

    body = client.get("/api/incoming-lag").json()
    assert body["checked"] is True
    assert body["n_waiting"] == 0


def test_a_light_folder_holding_nested_darks_still_reports_its_lag(
        built_library, client):
    """Why the fix is not a prefix roll-up — which was the cheap repair and is
    wrong in this direction.

    Darks filed *inside* a light unit (``IC 360_sub/darks/``) are discovered as
    ``IC 360_sub/darks``, and rolling a skip up to its enclosing unit would
    silence the whole of ``IC 360_sub`` — four nights of real subs that the scan
    does ingest. Matching stays **exact**, which is what makes the record above
    safe: it is keyed by the unit the scan actually passed over."""
    from tests.synth import write_seestar_fits
    from webapp.sample_data import write_sample_calibration_frames

    d = built_library / "incoming" / "IC 360_sub"
    d.mkdir(parents=True)
    for i in range(4):
        write_seestar_fits(d / f"frame_{i:03d}.fit", width=48, height=32,
                           n_stars=3, seed=300 + i)
    n_darks = write_sample_calibration_frames(d / "darks", "dark")
    _age_everything(built_library / "incoming", LONG_AGO_S)
    _poll(client)

    offer = client.get("/api/calibration/incoming").json()
    assert [f["rel_path"] for f in offer["folders"]] == ["IC 360_sub/darks"]

    body = client.get("/api/incoming-lag").json()
    assert {i["folder"] for i in body["items"]} == {"IC 360_sub"}
    assert body["n_waiting"] == 4 + n_darks
