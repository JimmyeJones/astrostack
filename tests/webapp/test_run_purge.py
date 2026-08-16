"""Deleting a stack run takes *everything* it left on disk and in the DB with it.

A run is more than its ``stack_runs`` row: six output files (only three of which
are recorded as columns), the editor's cached preview proxy, and up to six
``project_meta`` annotations. Both delete paths — the single-run endpoint and
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
    kept_files, kept_meta = _leftovers(solved_library, safe, "newest", keep)
    assert len(kept_files) == 8   # six outputs + two proxy files
    assert len(kept_meta) == 6


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
