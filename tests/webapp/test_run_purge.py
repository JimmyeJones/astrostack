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


#: A ``project_meta`` key built from a prefix constant and a run id. Both
#: spellings — ``{run_id}`` and ``{run.id}``. The second was invisible to this
#: guard until 2026-10-05: the old pattern was ``\{(\w+)\}\{[\w.]*run_id\}``,
#: and ``[\w.]*`` cannot consume ``run.`` and then *also* match the literal
#: ``run_id``.
#:
#: Only ``UPPER_SNAKE`` names, deliberately. A lowercase one is a local or a
#: function parameter — ``webapp/routers/gallery.py`` takes ``recipe_prefix``,
#: ``exported_prefix`` and ``baked_look_prefix`` as *arguments* — so it is a
#: pass-through of a constant its caller supplies, with no definition here to
#: resolve and nothing of its own to register.
_META_SITE_RE = re.compile(r'f"\{([A-Z][A-Z0-9_]*)\}\{[\w.]*run(?:_id|\.id)\}"')

#: A module-level prefix constant: ``NAME = "literal"``.
_PREFIX_DEFN_RE = re.compile(
    r'^([A-Z][A-Z0-9_]*)\s*=\s*["\']([^"\']*)["\']\s*$', re.MULTILINE)

#: How many ``<prefix><run_id>`` sites the scan below must still find.
#:
#: A **floor, not an equality**: adding a per-run key is ordinary work and must
#: not require editing a number here. What it catches is the scan going *blind*,
#: which is the only failure this guard has ever actually had. Observer issue
#: `#1079 <https://github.com/JimmyeJones/astrostack/issues/1079>`_ measured the
#: previous version reaching **4** assertions against the 33 sites that exist —
#: it resolved each name with ``getattr`` on the module that *used* it and
#: ``continue``d when that returned ``None``, and ``webapp/pipeline.py``, which
#: holds most of the write sites, imports every one of those prefixes *inside*
#: the function that uses it (deliberately: ``webapp/run_meta.py`` documents the
#: cycle reason). Seven sites in that one file were skipped without a word.
#:
#: 30, against the 33 found when it was set: ``webapp/pipeline.py`` (14),
#: ``webapp/routers/stack.py`` (12), ``webapp/routers/editor.py`` (6) and
#: ``webapp/finishedpicture.py`` (1).
MIN_PER_RUN_META_SITES = 30


def test_every_per_run_meta_prefix_is_registered():
    """Drift guard: a new ``<prefix><run_id>`` key that isn't in
    ``per_run_meta_prefixes()`` would silently start orphaning rows again.

    Read off the **source** of every file under ``webapp/`` rather than off
    imported module attributes, which closes three holes at once and closes them
    by construction rather than by a longer hand-written list (all three measured
    in observer issue #1079):

    * a prefix is resolved from **where it is defined**, so the lazy in-function
      imports that keep ``webapp.pipeline`` cheap and cycle-free no longer hide a
      site — ``getattr(pipeline, "RECIPE_META_PREFIX", None)`` is ``None``, and
      the old version read that as "not a prefix" and moved on;
    * the file list is a **glob**, so a new module that keys meta by a run id is
      covered the day it is written. The old version named two modules by hand
      and ``webapp/routers/stack.py`` — 12 sites — was never among them; and
    * an ``UPPER_SNAKE`` name that resolves to no definition is a **failure**,
      not a skip. That was the shape of every one of those holes: the old
      guard's only answer to "I cannot tell what this is" was to carry on.
    """
    from webapp.run_meta import per_run_meta_prefixes

    webapp_root = Path(__file__).resolve().parents[2] / "webapp"
    defined: dict[str, str] = {}
    sites: list[tuple[str, str]] = []
    for path in sorted(webapp_root.rglob("*.py")):
        src = path.read_text()
        for m in _PREFIX_DEFN_RE.finditer(src):
            defined.setdefault(m.group(1), m.group(2))
        for m in _META_SITE_RE.finditer(src):
            sites.append((path.name, m.group(1)))

    registered = set(per_run_meta_prefixes())
    for filename, name in sites:
        assert name in defined, (
            f"{filename} keys project_meta by a run id with {name}, which is "
            "defined nowhere under webapp/ as a plain string literal — so this "
            'guard cannot check it. Define it as `NAME = "prefix:"` at module '
            "level, or this site is unpoliced.")
        assert defined[name] in registered, (
            f"{filename}: {name} = {defined[name]!r} is keyed by a run id but is "
            "not listed in webapp/run_meta.py::per_run_meta_prefixes, so "
            "delete_run_meta leaves its rows behind when a run is deleted")

    # The guard's own self-check. It has been blind once; silence is not a pass.
    assert len(sites) >= MIN_PER_RUN_META_SITES, (
        f"only {len(sites)} per-run meta sites found, below the "
        f"{MIN_PER_RUN_META_SITES} that existed when this floor was set — the "
        "scan has probably stopped matching (a renamed spelling, a moved file), "
        "which is how this guard lost 7 of its 9 sites in silence before")


def test_deleting_a_run_takes_the_auto_edit_highlight_reading_with_it(
        client, solved_library):
    """FAIL-BEFORE: ``editor_auto_highlight:`` was not in
    ``per_run_meta_prefixes()``, so ``delete_run_meta`` left its row behind for
    good — observer issue #1079.

    Stamped from the prefix **constant**, deliberately never from
    ``per_run_meta_prefixes()``. The helpers at the top of this file walk the
    registry to *write* the rows they then check, so they stamp exactly the keys
    that are registered and cannot notice a missing one — the same blindness as
    the guard's, wearing the end-to-end test's clothes.
    """
    from webapp.routers.editor import AUTO_EDIT_HIGHLIGHT_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run_with_artifacts(solved_library, safe,
                                     "2026-05-01T00:00:00Z", "master")
    lib, proj = _open(solved_library, safe)
    try:
        proj.set_meta(f"{AUTO_EDIT_HIGHLIGHT_PREFIX}{run_id}",
                      json.dumps({"strength": 0.4, "flat_fraction": 0.02,
                                  "core_px": 118}))
    finally:
        proj.close()
        lib.close()

    assert client.delete(
        f"/api/targets/{safe}/stack-runs/{run_id}").status_code == 200

    lib, proj = _open(solved_library, safe)
    try:
        left = proj.get_meta(f"{AUTO_EDIT_HIGHLIGHT_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()
    assert left is None, (
        "the unattended auto-edit's highlight reading outlived the run it "
        "describes, where nothing will ever read it again")


def test_the_guard_sees_a_prefix_its_module_only_imports_lazily():
    """The property the rewrite is *for*, asserted rather than argued.

    ``RECIPE_META_PREFIX`` is used with a run id in ``webapp/pipeline.py`` and
    defined in ``webapp/routers/editor.py``, reaching ``pipeline`` only through
    an import inside the function that uses it. So the module attribute the old
    guard asked for does not exist, and the site was skipped in silence.
    """
    from webapp import pipeline

    assert getattr(pipeline, "RECIPE_META_PREFIX", None) is None, (
        "pipeline now imports this at module level, so this test no longer "
        "pins the lazy-import case — point it at another lazily-imported prefix")

    src = Path(pipeline.__file__).read_text()
    names = {m.group(1) for m in _META_SITE_RE.finditer(src)}
    assert "RECIPE_META_PREFIX" in names
    # ...and the scan resolves it anyway, from where it is defined.
    webapp_root = Path(__file__).resolve().parents[2] / "webapp"
    defined = {m.group(1): m.group(2)
               for path in sorted(webapp_root.rglob("*.py"))
               for m in _PREFIX_DEFN_RE.finditer(path.read_text())}
    assert defined.get("RECIPE_META_PREFIX") == "editor_recipe:"


def test_an_unresolvable_prefix_name_fails_rather_than_being_skipped():
    """"I cannot tell what this is" must not read as "nothing to check" — that
    one ``continue`` is what let seven sites through."""
    src = '    proj.set_meta(f"{A_PREFIX_DEFINED_NOWHERE}{run_id}", "x")\n'
    names = {m.group(1) for m in _META_SITE_RE.finditer(src)}
    assert names == {"A_PREFIX_DEFINED_NOWHERE"}
    assert not _PREFIX_DEFN_RE.findall(src)


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
