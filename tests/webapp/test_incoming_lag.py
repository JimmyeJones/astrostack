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
