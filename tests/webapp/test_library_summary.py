"""GET /api/library/summary — the "Your sky, so far" whole-library roll-up."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def test_summary_empty(client):
    r = client.get("/api/library/summary")
    assert r.status_code == 200
    b = r.json()
    assert b["n_targets_imaged"] == 0
    assert b["n_subs_kept"] == 0
    assert b["total_integration_s"] == 0.0
    assert b["integration_hours"] == 0.0
    assert b["first_light_utc"] is None
    assert b["longest_target"] is None
    assert b["most_imaged_target"] is None
    assert b["heroes"] == []


def test_summary_rolls_up_library(client, solved_library):
    b = client.get("/api/library/summary").json()
    # The solved_library fixture ingests two targets with accepted light.
    assert b["n_targets_imaged"] == 2
    assert b["n_subs_kept"] > 0
    assert b["total_integration_s"] > 0.0
    assert b["integration_hours"] >= 0.0
    assert b["first_light_utc"] is not None
    assert b["longest_target"] is not None
    assert b["most_imaged_target"] is not None
    # No stacks registered yet → no finished pictures to show.
    assert b["heroes"] == []


def _register_preview(root, safe, preview="master_preview.png"):
    """Register a stack run with a preview file that exists on disk, so the
    library stamps ``last_stack_preview`` at a real path."""
    lib = Library.open_or_create(root / "library")
    try:
        entry = lib.find_target(safe)
        target_dir = lib.target_dir(entry)
        preview_path = target_dir / preview
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(b"\x89PNG\r\n")  # non-empty; existence is what matters
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
                options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_summary_lists_finished_pictures_as_heroes(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_preview(solved_library, safe)

    b = client.get("/api/library/summary").json()
    heroes = b["heroes"]
    assert len(heroes) == 1
    assert heroes[0]["safe"] == safe
    assert heroes[0]["thumbnail_url"] == f"/api/targets/{safe}/thumbnail"
    # And the thumbnail actually serves (the endpoint the URL points at).
    assert client.get(heroes[0]["thumbnail_url"]).status_code == 200


def test_first_light_is_the_oldest_sub_not_the_install_date(client, solved_library):
    """"First light" is a milestone — and the poster's "Since <date>" line — so it
    has to be when the owner first *captured*, not when AstroStack first heard
    about the target.

    The owner this app is built for arrives with a back catalogue: every target
    row is created on install day, so a creation-stamp answer tells someone who
    has been imaging for years that they started this week. The fixture's subs
    carry a 2024 ``DATE-OBS`` while their target rows were created just now, which
    is exactly that shape.
    """
    b = client.get("/api/library/summary").json()
    assert b["first_light_utc"] is not None
    assert b["first_light_utc"].startswith("2024-09-12")

    # …and it really is older than the rows themselves, i.e. this can't be
    # passing by accident on a fixture whose two dates happen to agree.
    lib = Library.open_or_create(solved_library / "library")
    try:
        created = [t.created_utc for t in lib.list_targets()]
    finally:
        lib.close()
    assert min(created) > b["first_light_utc"]


def test_first_light_falls_back_when_no_sub_is_dated(client, solved_library):
    """A target whose subs carry no capture time still contributes what it always
    did — its creation stamp — rather than dropping out of the milestone."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                proj._conn.execute("UPDATE frames SET timestamp_utc = NULL")
                proj._conn.commit()
                assert proj.earliest_frame_utc() is None
            finally:
                proj.close()
        created = min(t.created_utc for t in lib.list_targets())
    finally:
        lib.close()

    b = client.get("/api/library/summary").json()
    assert b["first_light_utc"] == created


def test_the_shared_poster_dates_itself_from_the_same_answer(client, solved_library):
    """`/api/recap`'s "Since <date>" footnote is the same fact on the picture the
    owner posts publicly, so the two must not be able to disagree."""
    summary = client.get("/api/library/summary").json()
    recap = client.get("/api/recap").json()
    assert recap["has_anything"] is True
    assert summary["first_light_utc"].startswith("2024-09-12")
    assert "2024" in recap["since"]
