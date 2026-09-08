"""The folder a scan walked past, remembered where the owner will see it.

A bare ``<T>/`` beside ``<T>_sub/`` is skipped as the Seestar's own finished
picture. When its files are *not* named like the device's output the scan says
so — but only in that one job's result, on the Jobs page, and on a walk-away
install the scan that finds it is the watcher's. So the finding is true,
actionable, and unseen; it renews itself next scan and scrolls away again.

These tests pin the standing half: the scan **remembers** what it walked past
(``webapp/skipped_folders.py``), ``GET /api/targets/skipped-folders`` serves it
for the Library's card, and — the part that decides whether a standing card is a
help or a nag — it goes quiet again the moment the folder has been brought in.
"""

from __future__ import annotations

import time
from pathlib import Path

from tests.synth import write_seestar_fits
from webapp.skipped_folders import (
    SKIPPED_FOLDERS_META_KEY,
    SkippedFolder,
    decode_skipped_folders,
    encode_skipped_folders,
)


def _wait_job(client, job_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def _scan(client, root=None):
    payload = {"root": str(root)} if root is not None else {}
    r = client.post("/api/scan", json=payload)
    assert r.status_code == 200, r.text
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body
    return body["result"]


def _remembered(client):
    r = client.get("/api/targets/skipped-folders")
    assert r.status_code == 200, r.text
    return r.json()


def _drop_unvouched_pair(data_root: Path, name: str = "NGC_6888") -> Path:
    """The owner's own shape: a ``<T>_sub`` of one sub, and a bare ``<T>`` of two
    real subs plus one of the device's own pictures."""
    incoming = Path(data_root) / "incoming"
    (incoming / f"{name}_sub").mkdir(parents=True)
    write_seestar_fits(incoming / f"{name}_sub" / "Light_0001.fit",
                       width=480, height=320, n_stars=10, seed=1)
    bare = incoming / name
    bare.mkdir()
    for i in range(2):
        write_seestar_fits(bare / f"Light_{i:04d}.fit",
                           width=480, height=320, n_stars=10, seed=10 + i)
    write_seestar_fits(bare / "Stacked.fit", width=480, height=320,
                       n_stars=10, seed=99)
    return bare


# --- the remembered form -----------------------------------------------------

def test_the_remembered_form_round_trips_biggest_shortfall_first():
    records = [
        SkippedFolder(name="M 13", path="/i/M 13", n_files=3, n_unvouched=1),
        SkippedFolder(name="NGC 6888", path="/i/NGC 6888",
                      n_files=4815, n_unvouched=4815),
    ]
    back = decode_skipped_folders(encode_skipped_folders(records))
    assert [r.name for r in back] == ["NGC 6888", "M 13"]
    assert back[0] == records[1]


def test_a_value_this_version_cannot_read_means_nothing_to_say():
    """It is read on a poll, so anything unreadable must degrade to silence
    rather than 500 the Library page."""
    assert decode_skipped_folders(None) == []
    assert decode_skipped_folders("") == []
    assert decode_skipped_folders("not json") == []
    assert decode_skipped_folders('{"name": "M 13"}') == []
    assert decode_skipped_folders('[null, 7, {"name": "M 13"}]') == []
    # A folder with nothing unaccounted for is not a finding, however it got in.
    assert decode_skipped_folders(
        '[{"name": "M 13", "path": "/i/M 13", "n_files": 3, "n_unvouched": 0}]') == []


def test_only_a_handful_are_ever_remembered():
    from webapp.skipped_folders import MAX_REMEMBERED

    many = [
        SkippedFolder(name=f"T{i}", path=f"/i/T{i}", n_files=i, n_unvouched=i)
        for i in range(1, MAX_REMEMBERED + 5)
    ]
    back = decode_skipped_folders(encode_skipped_folders(many))
    assert len(back) == MAX_REMEMBERED
    # …and the ones kept are the ones that matter most.
    assert back[0].n_unvouched == max(r.n_unvouched for r in many)


# --- the standing report -----------------------------------------------------

def test_a_scan_remembers_the_folder_it_could_not_account_for(client, data_root):
    """Fail-before: the finding existed only in the job result, so the Library
    had nothing to show once that job scrolled away."""
    bare = _drop_unvouched_pair(data_root)
    result = _scan(client)
    assert [s["name"] for s in result["skipped_folders"]] == ["NGC_6888"]

    assert _remembered(client) == [{
        "name": "NGC_6888", "path": str(bare),
        "n_files": 3, "n_unrecognised": 2, "reason": "device_output",
    }]


def test_an_ordinary_seestar_library_is_told_nothing(client, data_root):
    """The half that keeps this quiet: a skipped folder of the device's own
    pictures is the convention working, and the card never appears."""
    incoming = Path(data_root) / "incoming"
    (incoming / "M 81_sub").mkdir(parents=True)
    write_seestar_fits(incoming / "M 81_sub" / "Light_0001.fit",
                       width=480, height=320, n_stars=10, seed=3)
    (incoming / "M 81").mkdir()
    write_seestar_fits(incoming / "M 81" / "Stacked.fit",
                       width=480, height=320, n_stars=10, seed=4)

    _scan(client)
    assert _remembered(client) == []


def test_another_programs_working_folder_is_reported_with_its_own_reason(
        client, data_root):
    """The scan-time half of the owner's 2026-09-08 "yes, skip it": the folder is
    no longer ingested as a junk target, and — because a silent skip could never
    be undone from the UI — it is reported with the rule that skipped it, so the
    card can say what it really is instead of calling another program's scratch
    directory "your Seestar's own finished picture"."""
    incoming = Path(data_root) / "incoming"
    scratch = incoming / "batch_stack_tmp"
    scratch.mkdir(parents=True)
    for i in range(2):
        write_seestar_fits(scratch / f"Light_{i:04d}.fit",
                           width=480, height=320, n_stars=10, seed=20 + i)

    result = _scan(client)
    # Fail-before: it ingested, so the scratch folder became a target of its own
    # and nothing was reported as skipped.
    assert "batch_stack_tmp" not in result.get("targets", [])
    assert [s["reason"] for s in result["skipped_folders"]] == ["temp_folder"]
    assert _remembered(client) == [{
        "name": "batch_stack_tmp", "path": str(scratch),
        "n_files": 2, "n_unrecognised": 2, "reason": "temp_folder",
    }]


def test_the_working_folder_can_still_be_brought_in_by_hand(client, data_root):
    """The owner's condition on the skip: *"the owner must be able to ingest it
    anyway if a future folder happens to share the name"*. The card's own
    "bring it in" is a scoped ``POST /api/scan`` at that path — which is exactly
    what this does — and once its frames have landed the card goes quiet."""
    incoming = Path(data_root) / "incoming"
    scratch = incoming / "batch_stack_tmp"
    scratch.mkdir(parents=True)
    for i in range(2):
        write_seestar_fits(scratch / f"Light_{i:04d}.fit",
                           width=480, height=320, n_stars=10, seed=30 + i)
    _scan(client)
    assert [f["name"] for f in _remembered(client)] == ["batch_stack_tmp"]

    result = _scan(client, root=scratch)
    assert result["scanned"] == 2
    assert _remembered(client) == []


def test_a_remembered_working_folder_survives_a_backend_that_never_wrote_one(
):
    """Upgrade-safety, both ways. A record written by an older build carries no
    ``reason``, and must read back as the only case that build could produce —
    never be dropped, and never claim to be a temp folder."""
    old = '[{"name": "M 13", "path": "/i/M 13", "n_files": 3, "n_unvouched": 1}]'
    back = decode_skipped_folders(old)
    assert [r.reason for r in back] == ["device_output"]
    # …and an unknown future value degrades the same way rather than reaching
    # the card as a reason no copy exists for.
    weird = '[{"name": "M 13", "path": "/i/M 13", "n_files": 3, ' \
            '"n_unvouched": 1, "reason": "something_new"}]'
    assert [r.reason for r in decode_skipped_folders(weird)] == ["device_output"]


def test_a_working_folder_is_remembered_even_with_nothing_unvouched():
    """A device-output skip earns its line by holding files the device's naming
    cannot vouch for, so ``n_unvouched == 0`` drops it. A temp folder must not be
    dropped by that same filter — being reported is what makes it recoverable."""
    raw = encode_skipped_folders([
        SkippedFolder(name="batch_stack_tmp", path="/i/batch_stack_tmp",
                      n_files=4, n_unvouched=0, reason="temp_folder"),
        SkippedFolder(name="M 13", path="/i/M 13", n_files=4, n_unvouched=0),
    ])
    assert [r.name for r in decode_skipped_folders(raw)] == ["batch_stack_tmp"]


def test_a_library_that_never_scanned_says_nothing_rather_than_erroring(client):
    """Upgrade-safety: the registry of an install that predates this key has no
    value to read, and the endpoint must answer normally."""
    assert _remembered(client) == []


def test_bringing_the_folder_in_stops_the_card_nagging(client, data_root):
    """The whole reason this is a *standing* report and not just a repeat of the
    scan's own: the convention keeps skipping the folder, so a card that simply
    mirrored the newest scan would still be shouting after the owner acted."""
    bare = _drop_unvouched_pair(data_root)
    _scan(client)
    assert len(_remembered(client)) == 1

    # …the card's own button, which scans exactly that folder.
    result = _scan(client, bare)
    assert result["scanned"] == 2
    assert _remembered(client) == []

    # And a later whole-incoming scan — which still walks past the folder, and
    # still reports it in its own job summary — does not bring the card back.
    later = _scan(client)
    assert [s["name"] for s in later["skipped_folders"]] == ["NGC_6888"]
    assert _remembered(client) == []


def test_a_folder_that_has_left_incoming_is_forgotten(client, data_root):
    """The owner's other recovery is to rename or move the folder on the NAS.
    Nothing here writes to ``incoming/`` (AGENTS.md §10) — but when the folder
    is gone the report about it must go too."""
    bare = _drop_unvouched_pair(data_root)
    _scan(client)
    assert len(_remembered(client)) == 1

    bare.rename(bare.parent / "NGC_6888_extra_sub")
    assert _remembered(client) == []


def test_a_later_clean_scan_clears_what_an_earlier_one_remembered(
        client, data_root):
    """The remembered list is the last whole scan's answer, not a growing pile:
    a folder that is no longer a finding stops being mentioned."""
    bare = _drop_unvouched_pair(data_root)
    _scan(client)
    assert len(_remembered(client)) == 1

    for p in bare.iterdir():
        p.unlink()
    bare.rmdir()
    _scan(client)
    assert _remembered(client) == []


def test_a_scoped_scan_of_another_folder_leaves_the_report_alone(
        client, data_root):
    """A scoped scan has looked at one folder, so it may not overwrite an answer
    about the whole tree — only prune what it has just disproved."""
    _drop_unvouched_pair(data_root)
    _scan(client)
    assert len(_remembered(client)) == 1

    _scan(client, Path(data_root) / "incoming" / "M_42")
    assert len(_remembered(client)) == 1


def test_remembering_is_never_what_fails_a_scan(client, data_root, monkeypatch):
    """It is a side note on a job that has just ingested the owner's frames —
    a registry it cannot write must not turn that job red."""
    import webapp.skipped_folders as sf

    _drop_unvouched_pair(data_root)

    def boom(*_a, **_k):
        raise RuntimeError("registry is having a day")

    monkeypatch.setattr(sf, "still_missing", boom)
    result = _scan(client)
    assert result["scanned"] >= 2
    assert [s["name"] for s in result["skipped_folders"]] == ["NGC_6888"]


def test_the_report_reads_the_registry_and_not_the_incoming_tree(
        client, data_root, monkeypatch):
    """Polling must not walk ``incoming/``. Pinned by making a walk fatal: the
    endpoint answers from what the scan wrote down."""
    _drop_unvouched_pair(data_root)
    _scan(client)

    from seestack.io import scanner

    def boom(*_a, **_k):
        raise AssertionError("the poll walked incoming/")

    monkeypatch.setattr(scanner, "find_fits_files", boom)
    monkeypatch.setattr(scanner, "scan_and_organize", boom)
    assert len(_remembered(client)) == 1


def test_the_key_is_additive_and_leaves_the_rest_of_the_registry_alone(
        client, data_root):
    """Upgrade-safety (§9): one new ``library_meta`` row, no schema change, and
    every other target fact untouched."""
    from seestack.io.library import Library

    before = {t["safe_name"] for t in client.get("/api/targets").json()}
    _drop_unvouched_pair(data_root)
    _scan(client)

    lib = Library.open_or_create(Path(data_root) / "library")
    try:
        assert lib.get_meta(SKIPPED_FOLDERS_META_KEY)
        assert lib.get_meta("schema_version")
    finally:
        lib.close()
    after = {t["safe_name"] for t in client.get("/api/targets").json()}
    assert before <= after
