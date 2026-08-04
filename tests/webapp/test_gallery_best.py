"""`GET /api/gallery/best`: the auto-curated *My best pictures* wall — cross-target
aggregation, quality ranking, self-hide, and the broken-project guard."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_preview_run(
    data_root, safe: str, *, basename: str,
    n_frames: int, exposure_s: float | None, noise_sigma: float | None,
    coverage_max: int, timestamp: str = "2026-05-02T00:00:00Z",
) -> int:
    """Register a finished stack whose preview file actually exists on disk (the
    ``/best`` wall only shows runs with a rendered picture)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        tdir = lib.target_dir(lib.find_target(safe))
        preview = tdir / f"{basename}.png"
        preview.write_bytes(b"\x89PNG\r\n\x1a\n")  # just needs to exist
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=timestamp,
                output_basename=basename, fits_path=None, tiff_path=None,
                preview_path=str(preview), n_frames_used=n_frames,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=coverage_max,
                options_json=json.dumps({"sigma_clip": True}),
                total_exposure_s=exposure_s, noise_sigma=noise_sigma,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_best_self_hides_with_fewer_than_two_pictures(client, solved_library):
    # No finished pictures yet → empty (self-hide), still 200.
    r = client.get("/api/gallery/best")
    assert r.status_code == 200
    assert r.json()["items"] == []

    # One finished picture is still not a curatable collection → self-hide.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_preview_run(solved_library, safe, basename="only",
                          n_frames=50, exposure_s=1500, noise_sigma=0.05,
                          coverage_max=50)
    assert client.get("/api/gallery/best").json()["items"] == []


def test_best_ranks_deeper_cleaner_stacks_first(client, solved_library):
    targets = client.get("/api/targets").json()
    assert len(targets) >= 2
    good = targets[0]["safe_name"]
    better = targets[1]["safe_name"]
    _register_preview_run(solved_library, good, basename="shallow",
                          n_frames=20, exposure_s=600, noise_sigma=0.09,
                          coverage_max=20)
    _register_preview_run(solved_library, better, basename="deep",
                          n_frames=500, exposure_s=15000, noise_sigma=0.01,
                          coverage_max=500)

    r = client.get("/api/gallery/best")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2  # one representative per target
    # The deep, clean stack ranks first with a full score; the shallow one trails.
    assert items[0]["safe"] == better
    assert items[0]["output_basename"] == "deep"
    assert items[0]["score"] == 1.0
    assert items[1]["safe"] == good
    assert items[1]["score"] < items[0]["score"]
    # It carries the fields the wall/lightbox need.
    assert items[0]["preview_url"].endswith("/preview")
    assert items[0]["has_preview"] is True
    assert items[0]["total_exposure_s"] == 15000
    assert items[0]["n_frames_used"] == 500


def test_best_uses_newest_finished_run_per_target(client, solved_library):
    """Each target contributes its newest preview-having run, not an older one."""
    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    _register_preview_run(solved_library, a, basename="old",
                          n_frames=100, exposure_s=3000, noise_sigma=0.05,
                          coverage_max=100, timestamp="2026-05-01T00:00:00Z")
    newest = _register_preview_run(solved_library, a, basename="new",
                                   n_frames=120, exposure_s=3600, noise_sigma=0.04,
                                   coverage_max=120, timestamp="2026-05-09T00:00:00Z")
    _register_preview_run(solved_library, b, basename="other",
                          n_frames=80, exposure_s=2400, noise_sigma=0.06,
                          coverage_max=80)

    items = client.get("/api/gallery/best").json()["items"]
    a_items = [it for it in items if it["safe"] == a]
    assert len(a_items) == 1
    assert a_items[0]["run_id"] == newest
    assert a_items[0]["output_basename"] == "new"


def test_best_limit_truncates(client, solved_library):
    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    _register_preview_run(solved_library, a, basename="a",
                          n_frames=200, exposure_s=6000, noise_sigma=0.03,
                          coverage_max=200)
    _register_preview_run(solved_library, b, basename="b",
                          n_frames=50, exposure_s=1500, noise_sigma=0.07,
                          coverage_max=50)
    items = client.get("/api/gallery/best?limit=1").json()["items"]
    assert len(items) == 1
    assert items[0]["safe"] == a  # the stronger one survives the cut


def _corrupt_project_schema(data_root, safe: str) -> None:
    import sqlite3

    lib = Library.open_or_create(data_root / "library")
    try:
        db = lib.target_dir(lib.find_target(safe)) / "project.sqlite"
    finally:
        lib.close()
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
    finally:
        conn.close()


def _create_target(data_root, name: str) -> str:
    """Register a fresh empty target and return its safe name."""
    lib = Library.open_or_create(data_root / "library")
    try:
        entry, proj = lib.create_target(name)
        proj.close()
        return entry.safe_name
    finally:
        lib.close()


def test_best_skips_a_broken_project_without_500ing(client, solved_library):
    """A newer-schema (rolled-back) project DB is skipped, not allowed to 500 the
    wall — same guard the gallery/stats/storage cross-target reads use. Two good
    pictures survive the skip, so the result still clears the self-hide floor."""
    targets = client.get("/api/targets").json()
    assert len(targets) >= 2
    good1, good2 = targets[0]["safe_name"], targets[1]["safe_name"]
    bad = _create_target(solved_library, "M13 Broken Cluster")
    _register_preview_run(solved_library, good1, basename="g1",
                          n_frames=100, exposure_s=3000, noise_sigma=0.05,
                          coverage_max=100)
    _register_preview_run(solved_library, good2, basename="g2",
                          n_frames=80, exposure_s=2400, noise_sigma=0.06,
                          coverage_max=80)
    _register_preview_run(solved_library, bad, basename="gb",
                          n_frames=90, exposure_s=2700, noise_sigma=0.055,
                          coverage_max=90)
    _corrupt_project_schema(solved_library, bad)

    r = client.get("/api/gallery/best")
    assert r.status_code == 200  # fail-before: the broken target 500s the wall
    safes = {it["safe"] for it in r.json()["items"]}
    assert good1 in safes and good2 in safes  # healthy targets still appear
    assert bad not in safes  # the broken one is skipped


# ---------------------------------------------------------------------------
# The user's own pick: a target's pinned cover represents it on the wall.
# ---------------------------------------------------------------------------

def _set_cover(data_root, safe: str, run_id: int | None) -> None:
    """Pin (or clear) a target's cover run, exactly as ``PUT /targets/{safe}/cover``
    does — the same library-level field the Library/Dashboard tile already reads."""
    lib = Library.open_or_create(data_root / "library")
    try:
        lib.set_target_cover(safe, run_id)
    finally:
        lib.close()


def test_a_pinned_cover_represents_its_target_instead_of_the_newest_stack(
        client, solved_library):
    """"Set as cover" says "this picture represents this target". The wall used to
    ignore that and show the newest stack regardless."""
    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    favourite = _register_preview_run(
        solved_library, a, basename="favourite", n_frames=100, exposure_s=3000,
        noise_sigma=0.05, coverage_max=100, timestamp="2026-05-01T00:00:00Z")
    _register_preview_run(
        solved_library, a, basename="newer", n_frames=120, exposure_s=3600,
        noise_sigma=0.04, coverage_max=120, timestamp="2026-05-09T00:00:00Z")
    _register_preview_run(solved_library, b, basename="other", n_frames=80,
                          exposure_s=2400, noise_sigma=0.06, coverage_max=80)
    _set_cover(solved_library, a, favourite)

    items = client.get("/api/gallery/best").json()["items"]
    a_items = [it for it in items if it["safe"] == a]
    assert len(a_items) == 1  # still exactly one representative per target
    assert a_items[0]["run_id"] == favourite
    assert a_items[0]["output_basename"] == "favourite"
    assert a_items[0]["pinned"] is True
    # An unpinned target is unaffected and says so.
    assert [it for it in items if it["safe"] == b][0]["pinned"] is False


def test_a_pinned_favourite_is_never_cut_by_the_ranking(client, solved_library):
    """The pin's whole job: a modest favourite outranks a much deeper stack and
    survives the wall's limit."""
    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    modest = _register_preview_run(solved_library, a, basename="modest",
                                   n_frames=20, exposure_s=600, noise_sigma=0.09,
                                   coverage_max=20)
    _register_preview_run(solved_library, b, basename="deep", n_frames=500,
                          exposure_s=15000, noise_sigma=0.01, coverage_max=500)
    # Unpinned, the deep stack wins the single slot.
    assert client.get("/api/gallery/best?limit=1").json()["items"][0]["safe"] == b

    _set_cover(solved_library, a, modest)
    top = client.get("/api/gallery/best?limit=1").json()["items"]
    assert len(top) == 1
    assert top[0]["safe"] == a and top[0]["run_id"] == modest
    # Floating it never inflates the transparent score the caption shows.
    assert top[0]["score"] < 1.0


def test_a_cover_whose_preview_is_gone_falls_back_to_the_newest_picture(
        client, solved_library):
    """A pruned/edited-away cover must degrade to the newest stack, not drop the
    target off the wall or serve a broken image."""
    from pathlib import Path

    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    gone = _register_preview_run(
        solved_library, a, basename="gone", n_frames=100, exposure_s=3000,
        noise_sigma=0.05, coverage_max=100, timestamp="2026-05-01T00:00:00Z")
    _register_preview_run(
        solved_library, a, basename="newer", n_frames=120, exposure_s=3600,
        noise_sigma=0.04, coverage_max=120, timestamp="2026-05-09T00:00:00Z")
    _register_preview_run(solved_library, b, basename="other", n_frames=80,
                          exposure_s=2400, noise_sigma=0.06, coverage_max=80)
    _set_cover(solved_library, a, gone)
    lib = Library.open_or_create(solved_library / "library")
    try:
        Path(lib.target_dir(lib.find_target(a)) / "gone.png").unlink()
    finally:
        lib.close()

    a_items = [it for it in client.get("/api/gallery/best").json()["items"]
               if it["safe"] == a]
    assert len(a_items) == 1
    assert a_items[0]["output_basename"] == "newer"
    assert a_items[0]["pinned"] is False


def test_a_cover_pointing_at_a_deleted_run_falls_back_to_the_newest_picture(
        client, solved_library):
    """A cover id that no longer matches any run (the run was deleted) degrades
    the same way rather than leaving the target unrepresented."""
    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    _register_preview_run(solved_library, a, basename="only", n_frames=120,
                          exposure_s=3600, noise_sigma=0.04, coverage_max=120)
    _register_preview_run(solved_library, b, basename="other", n_frames=80,
                          exposure_s=2400, noise_sigma=0.06, coverage_max=80)
    _set_cover(solved_library, a, 987654)  # no such run

    a_items = [it for it in client.get("/api/gallery/best").json()["items"]
               if it["safe"] == a]
    assert len(a_items) == 1
    assert a_items[0]["output_basename"] == "only"
    assert a_items[0]["pinned"] is False
