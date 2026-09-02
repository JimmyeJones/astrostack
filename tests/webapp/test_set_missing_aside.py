"""`POST …/frames/set-missing-aside` — "those subs are gone, carry on without them".

A8's owner-facing half. The walk-away readability hold told the owner his stack
was held back because subs weren't on disk, and offered him nothing to do about
it — which is the right answer while a drive is coming back and a dead end when
he deleted the session himself.

Guardrail these pin as hard as the behaviour: the endpoint is **database-only**.
`incoming/` is strictly read-only (AGENTS.md §10) and the owner's raws have no
backup, so a "the files are gone" action must never so much as consider removing
one — the tests below make the frames unreadable by repointing their recorded
paths, never by deleting anything, and assert the real files are all still there.
"""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import REJECT_REASON_FILE_MISSING


def _frames(client, safe: str = "M_42") -> list[dict]:
    return client.get(f"/api/targets/{safe}/frames").json()


def _unread(data_root: Path, safe: str, frame_ids: list[int]) -> None:
    """Make frames unreadable without touching a byte on disk — repoint their
    recorded paths, which is what the app sees when a folder is deleted."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for fid in frame_ids:
                f = proj.get_frame(fid)
                proj.update_frame(
                    fid,
                    source_path=f"{f.source_path}.__gone__",
                    cached_path=(f"{f.cached_path}.__gone__"
                                 if f.cached_path else None),
                )
        finally:
            proj.close()
    finally:
        lib.close()


def test_it_sets_aside_exactly_the_subs_whose_files_are_gone(client, solved_library):
    ids = [f["id"] for f in _frames(client)]
    assert len(ids) >= 3
    _unread(solved_library, "M_42", ids[:2])

    r = client.post("/api/targets/M_42/frames/set-missing-aside")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed"] == 2
    assert set(body["changed_ids"]) == set(ids[:2])

    by_id = {f["id"]: f for f in _frames(client)}
    for fid in ids[:2]:
        assert by_id[fid]["accept"] is False
        assert by_id[fid]["reject_reason"] == REJECT_REASON_FILE_MISSING
    for fid in ids[2:]:
        assert by_id[fid]["accept"] is True


def test_it_touches_no_file_on_disk(client, solved_library):
    """§10. The action is a database flag and nothing else."""
    incoming = solved_library / "incoming"
    before = sorted(p.relative_to(incoming) for p in incoming.rglob("*"))
    ids = [f["id"] for f in _frames(client)]
    _unread(solved_library, "M_42", ids[:2])

    assert client.post("/api/targets/M_42/frames/set-missing-aside").json()["changed"] == 2

    after = sorted(p.relative_to(incoming) for p in incoming.rglob("*"))
    assert after == before


def test_it_is_a_no_op_on_a_healthy_target(client, solved_library):
    """Every install with its subs on disk: nothing to do, and nothing done."""
    r = client.post("/api/targets/M_42/frames/set-missing-aside")
    assert r.status_code == 200
    assert r.json() == {"changed": 0, "changed_ids": []}
    assert all(f["accept"] for f in _frames(client))


def test_it_is_idempotent(client, solved_library):
    ids = [f["id"] for f in _frames(client)]
    _unread(solved_library, "M_42", ids[:1])
    assert client.post("/api/targets/M_42/frames/set-missing-aside").json()["changed"] == 1
    assert client.post("/api/targets/M_42/frames/set-missing-aside").json()["changed"] == 0


def test_the_returned_ids_undo_it_through_the_existing_bulk_accept(
        client, solved_library):
    """The UI's one-click undo, on the same endpoint every other bulk reject
    offers — no second undo path to keep in step."""
    ids = [f["id"] for f in _frames(client)]
    _unread(solved_library, "M_42", ids[:2])
    changed = client.post(
        "/api/targets/M_42/frames/set-missing-aside").json()["changed_ids"]

    r = client.post("/api/targets/M_42/frames/bulk",
                    json={"action": "accept", "ids": changed})
    assert r.status_code == 200
    assert all(f["accept"] for f in _frames(client))


def test_it_keeps_the_accepted_count_honest(client, solved_library):
    """The count every screen quotes stops claiming subs that do not exist."""
    ids = [f["id"] for f in _frames(client)]
    before = client.get("/api/targets/M_42").json()["n_frames_accepted"]
    _unread(solved_library, "M_42", ids[:2])
    client.post("/api/targets/M_42/frames/set-missing-aside")
    after = client.get("/api/targets/M_42").json()["n_frames_accepted"]
    assert after == before - 2


def test_an_unknown_target_is_a_404(client, solved_library):
    assert client.post("/api/targets/NOPE/frames/set-missing-aside").status_code == 404


def test_the_breakdown_names_the_bucket_and_reassures(client, solved_library):
    """"Left out for other reasons" is the wrong answer for something the owner
    just did — and this is the one bucket where "the app deleted nothing" is the
    whole point."""
    ids = [f["id"] for f in _frames(client)]
    _unread(solved_library, "M_42", ids[:2])
    client.post("/api/targets/M_42/frames/set-missing-aside")

    summary = client.get("/api/targets/M_42/frames/reject-summary").json()["summary"]
    bucket = next(b for b in summary["buckets"] if b["key"] == "missing")
    assert bucket["count"] == 2
    assert "aren't on your disk any more" in bucket["label"]
    assert "Nothing was deleted by the app" in bucket["note"]
