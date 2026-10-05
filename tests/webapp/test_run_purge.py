"""Deleting a stack run takes *everything* it left on disk and in the DB with it.

A run is more than its ``stack_runs`` row: a whole set of output files (only
three of which are recorded as columns — the rest are resolved from the
basename, see ``RUN_ARTEFACT_SUFFIXES``), the editor's cached preview proxy,
and a handful of ``project_meta`` annotations. Both delete paths — the single-run endpoint and
"Prune old stacks" — go through one ``purge_stack_run``, because reclaiming
space is the whole point of either button.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _target_dir(data_root, safe):
    return data_root / "library" / "targets" / safe


def _open(data_root, safe):
    lib = Library.open_or_create(data_root / "library")
    return lib, lib.open_target(safe)


def _add_run_with_artifacts(data_root, safe, ts, basename):
    """A run with its full on-disk output set, an editor proxy and annotations —
    exactly the state a stacked-then-edited picture leaves behind."""
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES

    tdir = _target_dir(data_root, safe)
    out = tdir / "output"
    out.mkdir(parents=True, exist_ok=True)
    for suffix in RUN_ARTEFACT_SUFFIXES.values():
        (out / f"{basename}{suffix}").write_bytes(b"z" * 128)

    lib, proj = _open(data_root, safe)
    try:
        run_id = proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc=ts, output_basename=basename,
            fits_path=str(out / f"{basename}.fits"),
            tiff_path=str(out / f"{basename}.tif"),
            preview_path=str(out / f"{basename}_preview.png"),
            n_frames_used=1, canvas_h=10, canvas_w=10,
            coverage_min=1, coverage_max=1,
            options_json=json.dumps({}),
        ))
        from webapp.run_meta import per_run_meta_prefixes
        for prefix in per_run_meta_prefixes():
            proj.set_meta(f"{prefix}{run_id}", "something")
    finally:
        proj.close()
        lib.close()

    proxy = tdir / "cache" / "edit_proxies"
    proxy.mkdir(parents=True, exist_ok=True)
    (proxy / f"run_{run_id}.npy").write_bytes(b"p" * 4096)
    (proxy / f"run_{run_id}.json").write_text("{}")
    return run_id


def _leftovers(data_root, safe, basename, run_id):
    """Every file and meta row that should be gone once the run is deleted."""
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES
    from webapp.run_meta import per_run_meta_prefixes

    tdir = _target_dir(data_root, safe)
    files = [p for suffix in RUN_ARTEFACT_SUFFIXES.values()
             if (p := tdir / "output" / f"{basename}{suffix}").exists()]
    files += [p for name in (f"run_{run_id}.npy", f"run_{run_id}.json")
              if (p := tdir / "cache" / "edit_proxies" / name).exists()]
    lib, proj = _open(data_root, safe)
    try:
        meta = [prefix for prefix in per_run_meta_prefixes()
                if proj.get_meta(f"{prefix}{run_id}") is not None]
    finally:
        proj.close()
        lib.close()
    return files, meta


def _add_displaced_run(data_root, safe, ts, basename, run_id_of_writer):
    """A row that points at **another** run's output set and owns no files.

    The shape observer issue #1069 found 56 of on the owner's library: before the
    v0.81.7–0.81.8 overwrite guard a re-stack wrote the canonical ``master.*``
    straight over the previous run's output, and ``repoint_stack_runs`` only runs
    at re-stack time, so the older row was never moved aside and still names the
    file a *newer* run wrote. Its own picture is gone; the file at that path
    belongs to the live run.
    """
    tdir = _target_dir(data_root, safe)
    out = tdir / "output"
    lib, proj = _open(data_root, safe)
    try:
        return proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc=ts, output_basename=basename,
            fits_path=str(out / f"{basename}.fits"),
            tiff_path=str(out / f"{basename}.tif"),
            preview_path=str(out / f"{basename}_preview.png"),
            n_frames_used=1, canvas_h=10, canvas_w=10,
            coverage_min=1, coverage_max=1,
            options_json=json.dumps({}),
        ))
    finally:
        proj.close()
        lib.close()


def _whole_output_set(data_root, safe, basename):
    """Which of ``basename``'s output files are still on disk."""
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES

    out = _target_dir(data_root, safe) / "output"
    return sorted(p.name for suffix in RUN_ARTEFACT_SUFFIXES.values()
                  if (p := out / f"{basename}{suffix}").exists())


def test_deleting_a_displaced_row_does_not_delete_the_live_picture(
        client, solved_library):
    """FAIL-BEFORE: deleting an old History entry destroyed a *current* picture.

    ``delete_run_artifacts`` unlinks the three recorded columns plus every
    sibling it resolves from the FITS basename, and checked nothing about whether
    another row still names those files. On the owner's library 71 rows sit on 15
    shared paths (observer issue #1069), so "delete this old stack" on any of the
    56 displaced ones unlinked the master, TIFF, preview, coverage maps and reel
    of the live run that shares the name — hours of stacking, and the target's
    cover image, gone without being asked for.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    live = _add_run_with_artifacts(
        solved_library, safe, "2026-04-01T00:00:00Z", "master")
    displaced = _add_displaced_run(
        solved_library, safe, "2026-01-01T00:00:00Z", "master", live)
    before = _whole_output_set(solved_library, safe, "master")
    assert before, "fixture wrote no files"

    r = client.delete(f"/api/targets/{safe}/stack-runs/{displaced}")
    assert r.status_code == 200

    # The row goes — it is a real history row and the owner asked for it…
    ids = [x["id"] for x in client.get(f"/api/targets/{safe}/stack-runs").json()]
    assert displaced not in ids
    assert live in ids
    # …but not one byte of the picture it was only *pointing* at.
    assert _whole_output_set(solved_library, safe, "master") == before


def test_pruning_old_stacks_does_not_delete_the_newest_picture(
        client, solved_library):
    """The same hazard through the button it is most likely to be met on.
    ``iter_stack_runs`` is newest-first and prune deletes ``runs[keep:]``, so
    "keep the newest N" targets the **oldest** rows — which is exactly what the
    56 displaced rows are (all pre-v0.81.7). Pruning a target that holds one took
    its current master with it.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    live = _add_run_with_artifacts(
        solved_library, safe, "2026-04-01T00:00:00Z", "master")
    displaced = _add_displaced_run(
        solved_library, safe, "2026-01-01T00:00:00Z", "master", live)
    before = _whole_output_set(solved_library, safe, "master")

    r = client.post(f"/api/targets/{safe}/stack-runs/prune", json={"keep": 1})
    assert r.status_code == 200
    assert r.json()["deleted"] == [displaced]

    assert _whole_output_set(solved_library, safe, "master") == before


def test_pruning_every_run_still_reclaims_the_shared_file_set(
        client, solved_library):
    """The guard must not leak disk: it withholds a file only while a row that
    still names it survives, so deleting the **last** of a shared group frees the
    whole set. Reclaiming space is the entire point of the button."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    live = _add_run_with_artifacts(
        solved_library, safe, "2026-04-01T00:00:00Z", "master")
    _add_displaced_run(
        solved_library, safe, "2026-01-01T00:00:00Z", "master", live)
    assert _whole_output_set(solved_library, safe, "master")

    r = client.post(f"/api/targets/{safe}/stack-runs/prune", json={"keep": 0})
    assert r.status_code == 200

    assert _whole_output_set(solved_library, safe, "master") == []


def test_deleting_the_live_row_keeps_the_files_its_displaced_sibling_serves(
        client, solved_library):
    """The other order, and the one that says the rule is about the *files* rather
    than about which row is the writer: with the live row gone the displaced row
    is the only one left naming those files, and it is now the one serving that
    picture — so they stay."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    live = _add_run_with_artifacts(
        solved_library, safe, "2026-04-01T00:00:00Z", "master")
    _add_displaced_run(
        solved_library, safe, "2026-01-01T00:00:00Z", "master", live)
    before = _whole_output_set(solved_library, safe, "master")

    assert client.delete(
        f"/api/targets/{safe}/stack-runs/{live}").status_code == 200

    assert _whole_output_set(solved_library, safe, "master") == before


def test_deleting_a_run_removes_its_whole_file_set_proxy_and_notes(
        client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run_with_artifacts(
        solved_library, safe, "2026-03-01T00:00:00Z", "master")

    r = client.delete(f"/api/targets/{safe}/stack-runs/{run_id}")
    assert r.status_code == 200

    files, meta = _leftovers(solved_library, safe, "master", run_id)
    assert files == [], f"left behind: {[p.name for p in files]}"
    assert meta == [], f"orphan meta keys: {meta}"


def test_pruning_reclaims_as_much_as_deleting_one_run(client, solved_library):
    """"Prune old stacks" is the *disk-space* feature — it used to leave the
    coverage map, the progress reel and a ~27 MB editor proxy behind."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    old = _add_run_with_artifacts(
        solved_library, safe, "2026-01-01T00:00:00Z", "old")
    keep = _add_run_with_artifacts(
        solved_library, safe, "2026-04-01T00:00:00Z", "newest")

    r = client.post(f"/api/targets/{safe}/stack-runs/prune", json={"keep": 1})
    assert r.status_code == 200
    assert r.json()["deleted"] == [old]

    files, meta = _leftovers(solved_library, safe, "old", old)
    assert files == [], f"left behind: {[p.name for p in files]}"
    assert meta == [], f"orphan meta keys: {meta}"

    # The kept run is untouched — nothing derived a sibling name too eagerly.
    # Its annotation count is read off the registry rather than hard-coded, so
    # registering a new per-run prefix (as it should be) doesn't fail this for
    # the wrong reason — the assertion is "every one of them survived".
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES
    from webapp.run_meta import per_run_meta_prefixes

    kept_files, kept_meta = _leftovers(solved_library, safe, "newest", keep)
    # Counted off the artefact registry for the same reason the annotations are:
    # adding a new per-run output file (as this should be free to do) must not
    # fail this for the wrong reason — the assertion is "every one of them
    # survived", which is the whole output set plus the two proxy files.
    assert len(kept_files) == len(RUN_ARTEFACT_SUFFIXES) + 2
    assert kept_meta == list(per_run_meta_prefixes())


def test_storage_counts_and_clears_the_editor_proxy_cache(client, solved_library):
    """The proxies live under ``cache/`` but were in no cache figure and no
    clear stage, so an install that pruned before the fix could never get the
    orphaned ones back."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    pdir = _target_dir(solved_library, safe) / "cache" / "edit_proxies"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "run_99.npy").write_bytes(b"q" * 5000)

    row = next(t for t in client.get("/api/storage").json()["targets"]
               if t["safe"] == safe)
    assert row["proxies_bytes"] == 5000
    assert row["cache_bytes"] >= 5000

    c = client.post(f"/api/targets/{safe}/cache/clear", params={"stage": "proxies"})
    assert c.status_code == 200
    assert "proxies" in c.json()["cleared"]
    assert not (pdir / "run_99.npy").exists()


def test_clear_all_includes_the_proxies(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    pdir = _target_dir(solved_library, safe) / "cache" / "edit_proxies"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "run_5.npy").write_bytes(b"q" * 64)

    c = client.post(f"/api/targets/{safe}/cache/clear", params={"stage": "all"})
    assert "proxies" in c.json()["cleared"]
    assert not (pdir / "run_5.npy").exists()


def test_deleting_a_missing_run_still_answers(client, solved_library):
    """An id with no row (a half-finished earlier delete) must not 500."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.delete(f"/api/targets/{safe}/stack-runs/4242")
    assert r.status_code == 200


def test_every_per_run_meta_prefix_is_registered():
    """Drift guard: a new ``<prefix><run_id>`` key that isn't in
    ``per_run_meta_prefixes()`` would silently start orphaning rows again."""
    from webapp import pipeline
    from webapp.routers import editor
    from webapp.run_meta import per_run_meta_prefixes

    registered = set(per_run_meta_prefixes())
    used = re.compile(r'f"\{(\w+)\}\{[\w.]*run_id\}"')
    for module in (pipeline, editor):
        src = Path(module.__file__).read_text()
        names = {m.group(1) for m in used.finditer(src)}
        for name in names:
            value = getattr(module, name, None)
            if not isinstance(value, str):
                continue
            assert value in registered, (
                f"{module.__name__}.{name} = {value!r} is keyed by a run id but "
                "is not listed in webapp/run_meta.py::per_run_meta_prefixes")


def test_a_real_stack_write_leaves_nothing_the_delete_path_cannot_find(tmp_path):
    """The delete path derives a run's *unrecorded* siblings from
    ``RUN_ARTEFACT_SUFFIXES``, so run the actual writer and check that every file
    it produced is one of them — otherwise a future output would leak again."""
    import numpy as np

    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES, write_stack_outputs
    from webapp.routers.storage import delete_run_artifacts

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    written = write_stack_outputs(
        project_dir=project_dir,
        rgb=np.full((8, 8, 3), 0.2, dtype=np.float32),
        coverage=np.ones((8, 8), dtype=np.float32),
        wcs_text=None, out_basename="master",
    )
    out_dir = project_dir / "output"
    produced = sorted(p.name for p in out_dir.iterdir() if p.is_file())
    assert produced, "the writer produced nothing to check"
    assert all(any(name == f"master{sfx}" for sfx in RUN_ARTEFACT_SUFFIXES.values())
               for name in produced), produced

    # And deleting the run really does clear the directory.
    delete_run_artifacts(StackRunRow(
        id=1, timestamp_utc="2026-05-01T00:00:00Z", output_basename="master",
        fits_path=str(written["fits"]), tiff_path=str(written["tiff"]),
        preview_path=str(written["preview"]), n_frames_used=1,
        canvas_h=8, canvas_w=8, coverage_min=0, coverage_max=1, options_json="{}",
    ))
    assert list(out_dir.iterdir()) == []


def test_deleting_a_run_takes_its_deepening_reel_with_it(tmp_path):
    """The cross-run "night after night" reel is cached beside the *newest* run's
    basename, and it was not a registered artefact — so deleting that run left the
    reel and its signature on disk for good, where nothing would ever look at them
    again. Reproduced before the fix at 2.0 MB on one synthetic run; a real reel is
    a 1024 px animation of every stack a target has.

    Sits beside ``test_a_real_stack_write_leaves_nothing_the_delete_path_cannot_find``
    because that guard runs the *writer*, and this file is written later, by the
    webapp, on demand."""
    import numpy as np

    from seestack.render.deepening import write_deepening_reel
    from seestack.stack.output import write_stack_outputs
    from webapp.routers.storage import delete_run_artifacts

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    written = write_stack_outputs(
        project_dir=project_dir,
        rgb=np.full((8, 8, 3), 0.2, dtype=np.float32),
        coverage=np.ones((8, 8), dtype=np.float32),
        wcs_text=None, out_basename="master",
    )
    out_dir = project_dir / "output"

    # Write the reel with its *own* writer, so the test cannot be wrong about the
    # names, plus the signature the resolver keeps beside it.
    from PIL import Image
    frames = [Image.new("RGB", (8, 8), (10 * i, 10 * i, 10 * i)) for i in (1, 2, 3)]
    reel = write_deepening_reel(frames, out_dir, "master")
    assert reel is not None and reel.exists()
    # Spelled out rather than read from RUN_ARTEFACT_SUFFIXES on purpose, so this
    # test states the failure in the terms the bug had: these were files on disk
    # that the table did not know about. `test_run_artefact_coverage.py` is what
    # pins the name against the table.
    (out_dir / "master_deepening.sig").write_text("some-series-signature")

    delete_run_artifacts(StackRunRow(
        id=1, timestamp_utc="2026-05-01T00:00:00Z", output_basename="master",
        fits_path=str(written["fits"]), tiff_path=str(written["tiff"]),
        preview_path=str(written["preview"]), n_frames_used=1,
        canvas_h=8, canvas_w=8, coverage_min=0, coverage_max=1, options_json="{}",
    ))

    left = sorted(p.name for p in out_dir.iterdir())
    assert left == [], f"deleting the run left files behind: {left}"
