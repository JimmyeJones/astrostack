"""GET /api/stats dashboard aggregates."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def test_stats_empty(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    b = r.json()
    assert b["n_targets"] == 0
    assert b["n_stack_runs"] == 0
    assert b["recent_stacks"] == []
    assert b["acceptance_rate"] is None


def test_stats_rolls_up_library(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=3,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
                options_json=json.dumps({}),
            ))
        finally:
            proj.close()
    finally:
        lib.close()

    b = client.get("/api/stats").json()
    assert b["n_targets"] == 2
    assert b["n_frames"] > 0
    assert b["n_stack_runs"] == 1
    assert b["n_targets_with_stacks"] == 1
    assert 0.0 <= b["acceptance_rate"] <= 1.0
    assert len(b["recent_stacks"]) == 1
    assert b["recent_stacks"][0]["safe"] == safe
    # The run's own canvas travels, so the strip's download menu can say honestly
    # what its "Full-res PNG" contains — that render caps its long edge, so on a
    # canvas past the cap it must not claim native size (see fullres.ts).
    assert b["recent_stacks"][0]["canvas_w"] == 480
    assert b["recent_stacks"][0]["canvas_h"] == 320
    assert "integration_hours" in b


def _add_stack_run(root, safe, ts="2026-05-02T00:00:00Z", preview="master_preview.png"):
    lib = Library.open_or_create(root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename="master",
                fits_path=None, tiff_path=None, preview_path=preview,
                n_frames_used=3, canvas_h=320, canvas_w=480,
                coverage_min=1, coverage_max=3, options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        # Bumps last_activity_utc + last_stack_preview → cache signature changes.
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_recent_stack_reports_has_fits(client, solved_library, tmp_path):
    """``recent_stacks[].has_fits`` reflects whether the run's FITS exists — it
    gates the Dashboard's "Full-res PNG" download (rendered from the FITS)."""
    import numpy as np
    from astropy.io import fits as _fits

    from seestack.io.library import Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    # One run with a real FITS on disk and one without, so both has_fits states
    # appear in the same response.
    no_fits_id = _add_stack_run(solved_library, safe, ts="2026-05-01T00:00:00Z")
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fp = tdir / "with_fits.fits"
        _fits.PrimaryHDU(data=np.zeros((3, 8, 8), dtype=np.float32)).writeto(fp, overwrite=True)
        proj = lib.open_target(safe)
        try:
            with_fits_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-09T00:00:00Z", output_basename="master",
                fits_path=str(fp), tiff_path=None, preview_path=None,
                n_frames_used=3, canvas_h=8, canvas_w=8,
                coverage_min=1, coverage_max=3, options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()

    by_id = {r["run_id"]: r for r in client.get("/api/stats").json()["recent_stacks"]}
    assert by_id[with_fits_id]["has_fits"] is True
    assert by_id[no_fits_id]["has_fits"] is False


def test_stats_recent_limit_is_clamped(client, solved_library):
    """A negative/zero recent_limit must not silently drop the newest stacks.

    ``recent`` is sorted newest-first, so an unclamped ``recent[:recent_limit]``
    with a negative limit would return the wrong slice and 0 an empty strip.
    The endpoint clamps to a sane range like the other int query params do.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    for k in range(3):
        _add_stack_run(solved_library, safe, ts=f"2026-05-0{k + 1}T00:00:00Z")

    # 0 and negative both fall back to at least one recent stack, not an empty
    # or reversed slice; a huge value is capped but still returns everything.
    assert len(client.get("/api/stats", params={"recent_limit": 0}).json()["recent_stacks"]) == 1
    assert len(client.get("/api/stats", params={"recent_limit": -5}).json()["recent_stacks"]) == 1
    assert len(client.get("/api/stats", params={"recent_limit": 999}).json()["recent_stacks"]) == 3


def test_stats_caches_rollup_until_activity_changes(client, solved_library, monkeypatch):
    import webapp.routers.stats as stats_mod

    calls = {"n": 0}
    real = stats_mod._rollup_stacks

    def counting(lib, targets, lon_deg=None):
        calls["n"] += 1
        return real(lib, targets, lon_deg)

    monkeypatch.setattr(stats_mod, "_rollup_stacks", counting)

    # First hit does the expensive roll-up; a second hit with nothing changed
    # is served from cache (no extra project opens).
    assert client.get("/api/stats").json()["n_stack_runs"] == 0
    assert calls["n"] == 1
    assert client.get("/api/stats").json()["n_stack_runs"] == 0
    assert calls["n"] == 1

    # A completed stack bumps last_activity_utc, which changes the cache
    # signature — the next call re-rolls up and reflects the new run.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack_run(solved_library, safe)
    body = client.get("/api/stats").json()
    assert calls["n"] == 2
    assert body["n_stack_runs"] == 1


def test_stats_counts_finished_moon_sun_stills(client, data_root):
    """A video still is a picture the deep-sky counters cannot see.

    The Dashboard's "Your first image" checklist ticks itself off these numbers,
    and a Moon capture ingests no FITS, solves nothing and creates no stack run —
    so without its own count the app tells someone holding a finished Moon
    picture that they haven't made one.
    """
    assert client.get("/api/stats").json()["n_video_stills"] == 0

    video = data_root / "video"
    (video / "Lunar_video").mkdir(parents=True)
    (video / "Lunar_video" / "stack.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    # A folder that hasn't finished writing its picture isn't a picture yet.
    (video / "Solar_video").mkdir(parents=True)
    (video / "Solar_video" / "meta.json").write_text("{}", encoding="utf-8")

    assert client.get("/api/stats").json()["n_video_stills"] == 1


def _set_run_meta(root, safe, key: str, value: str = "{}") -> None:
    """Write one ``project_meta`` row on a target's project."""
    lib = Library.open_or_create(root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_meta(key, value)
        finally:
            proj.close()
    finally:
        lib.close()


def _uncache_stats(client) -> None:
    """Drop the roll-up cache.

    Saving an editor recipe writes only a ``project_meta`` row: it bumps neither
    ``last_activity_utc`` nor ``last_stack_preview``, so the cache signature is
    unchanged and the 30 s TTL is what refreshes the counters in the running app.
    The tests want the answer now, not in 30 s.
    """
    client.app.state.stats_cache = None


def test_stats_counts_finished_and_saved_pictures(client, solved_library):
    """The two counters the "Your first image" checklist reads for the *end* of
    the journey — finished in the editor, then exported as its own picture.

    Both are per-run ``project_meta`` markers (``editor_recipe:<id>`` /
    ``editor_exported:<id>``) that nothing cheap reported before, which is why
    the card could only ever *mention* the last two steps in its congratulation.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_stack_run(solved_library, safe)

    body = client.get("/api/stats").json()
    assert body["n_stack_runs"] == 1
    # A stack nobody has opened in the editor yet: both steps still to do.
    assert body["n_edited_runs"] == 0
    assert body["n_finished_pictures"] == 0

    _set_run_meta(solved_library, safe, f"editor_recipe:{run_id}", "{\"ops\": []}")
    _uncache_stats(client)
    body = client.get("/api/stats").json()
    assert body["n_edited_runs"] == 1
    assert body["n_finished_pictures"] == 0

    _set_run_meta(solved_library, safe, f"editor_exported:{run_id}", "{\"ops\": []}")
    _uncache_stats(client)
    body = client.get("/api/stats").json()
    assert body["n_edited_runs"] == 1
    assert body["n_finished_pictures"] == 1


def test_stats_counts_an_in_place_auto_edit_as_finished(client, solved_library):
    """A hands-off "Process this target" finishes the picture *in place*: it saves
    the recipe **and** bakes it into the run's stored preview
    (``preview_display_space``), with no export anywhere.

    Counting only the export marker would have the checklist tell a walk-away
    owner to go and finish a picture the app already finished — and would
    contradict the un-exported-edit nudge, which reads this same marker and stays
    silent for exactly this run.
    """
    from seestack.io.library import Library as _Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_stack_run(solved_library, safe)
    _set_run_meta(solved_library, safe, f"editor_recipe:{run_id}", "{\"ops\": []}")
    lib = _Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_run_preview_display_space(run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    _uncache_stats(client)

    body = client.get("/api/stats").json()
    assert body["n_edited_runs"] == 1
    assert body["n_finished_pictures"] == 1


def test_stats_finished_pictures_dont_double_count_one_run(client, solved_library):
    """A run that was auto-edited in place and *then* exported is one finished
    picture, not two — the two markers are unioned by run id."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_stack_run(solved_library, safe)
    _set_run_meta(solved_library, safe, f"editor_exported:{run_id}", "{\"ops\": []}")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_run_preview_display_space(run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    _uncache_stats(client)

    assert client.get("/api/stats").json()["n_finished_pictures"] == 1


def test_stats_edit_counters_ignore_meta_that_isnt_a_run(client, solved_library):
    """Only ``<prefix><run_id>`` keys count.

    ``project_meta`` is a shared key space — the stack defaults, the target's
    integration goal and every per-run annotation live in it — so a counter that
    took any key starting with the prefix would drift the moment a neighbouring
    feature borrowed it.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_stack_run(solved_library, safe)
    _set_run_meta(solved_library, safe, f"editor_recipe:{run_id}")
    # Not a run id: a hand-edited row, or a future key sharing the prefix.
    _set_run_meta(solved_library, safe, "editor_recipe:default")
    _set_run_meta(solved_library, safe, "editor_recipes_seen", "3")
    _uncache_stats(client)

    assert client.get("/api/stats").json()["n_edited_runs"] == 1


def test_stats_edit_counters_dont_read_an_unstacked_target(client, solved_library,
                                                           monkeypatch):
    """The care note on this feature: it must ride along on a walk that already
    happens, never add a read of its own.

    A target with no stack runs cannot carry either marker, so it must not be
    asked — otherwise every library poll pays two extra prefix scans per target
    for an answer that is structurally zero.
    """
    from seestack.io.project import Project

    scans: list[str] = []
    real = Project.iter_meta_prefix

    def spying(self, prefix):
        scans.append(prefix)
        return real(self, prefix)

    monkeypatch.setattr(Project, "iter_meta_prefix", spying)

    # Nothing stacked anywhere in this library yet.
    assert client.get("/api/stats").json()["n_edited_runs"] == 0
    assert scans == []

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack_run(solved_library, safe)
    client.get("/api/stats")
    # Exactly the two prefixes, and only for the one target that has a run —
    # the library's *other* target is still never opened for them.
    assert scans == ["editor_recipe:", "editor_exported:"]


def test_stats_edit_counters_survive_a_broken_project(client, solved_library):
    """One unreadable project must not cost the whole answer — the same
    degrade-don't-500 rule the rest of the roll-up already follows."""
    from seestack.io.library import Library as _Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_stack_run(solved_library, safe)
    _set_run_meta(solved_library, safe, f"editor_recipe:{run_id}")

    lib = _Library.open_or_create(solved_library / "library")
    try:
        others = [t for t in lib.list_targets() if t.safe_name != safe]
        assert others, "fixture should carry a second target"
        (lib.target_dir(others[0]) / "project.sqlite").write_bytes(b"not a database")
    finally:
        lib.close()
    _uncache_stats(client)

    body = client.get("/api/stats").json()
    assert body["n_edited_runs"] == 1
