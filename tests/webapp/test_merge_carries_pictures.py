"""Combining folders of the same object keeps the pictures, not only the subs.

``POST /api/targets/merge`` ends in an ``rmtree`` of every source target's
folder, so anything :func:`seestack.io.merge.merge_projects` does not carry out
first is destroyed — and the Library nudge that fires it says, in the product,
*"keeps every sub — and every picture you've already made of it. Nothing is
deleted."* These are that sentence read as a test.

The second test is the drift guard. The engine cannot import ``webapp``
(AGENTS.md §6), so :data:`seestack.io.merge._RUN_META_KEY` identifies a per-run
annotation by *shape* (a trailing ``:<run id>``) rather than by the vocabulary
``webapp.run_meta`` owns. That only stays true while every registered prefix has
that shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow, Project, StackRunRow


def _target_dir(data_root: Path, safe: str) -> Path:
    return data_root / "library" / "targets" / safe


def _second_folder_of_the_same_object(data_root: Path, first_safe: str) -> str:
    """A second target at the same sky position, carrying one finished picture.

    Shaped like the case the nudge detects: the Seestar writes a new folder every
    night, ``auto_stack`` stacks each one by itself, and the two end up as two
    shallow targets of one object — one of which is about to be deleted.
    """
    lib = Library.open_or_create(data_root / "library")
    try:
        first = lib.open_target(first_safe)
        try:
            sample = next(iter(first.iter_frames()))
        finally:
            first.close()
        entry, proj = lib.create_target("Second night")
        try:
            proj.add_frame(FrameRow(
                source_path=str(Path(sample.source_path).with_name("second_night.fit")),
                width_px=sample.width_px, height_px=sample.height_px,
                bayer_pattern=sample.bayer_pattern,
                ra_center_deg=sample.ra_center_deg,
                dec_center_deg=sample.dec_center_deg,
                exposure_s=sample.exposure_s,
            ))
            out = Path(proj.project_dir) / "output"
            out.mkdir(parents=True, exist_ok=True)
            (out / "master.fits").write_bytes(b"the-second-nights-pixels")
            (out / "master_preview.png").write_bytes(b"the-second-nights-preview")
            (out / "master_coverage.fits").write_bytes(b"the-second-nights-coverage")
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-09-02T04:00:00Z",
                output_basename="master",
                fits_path=str(out / "master.fits"), tiff_path=None,
                preview_path=str(out / "master_preview.png"),
                n_frames_used=31, canvas_h=10, canvas_w=10,
                coverage_min=1, coverage_max=31, options_json=json.dumps({}),
                notes="second night",
            ))
            proj.set_meta(f"editor_recipe:{run_id}", json.dumps({"ops": []}))
        finally:
            proj.close()
        return entry.safe_name
    finally:
        lib.close()


def test_merging_keeps_the_picture_the_source_folder_had(client, solved_library):
    keeper = client.get("/api/targets").json()[0]["safe_name"]
    doomed = _second_folder_of_the_same_object(solved_library, keeper)

    r = client.post("/api/targets/merge",
                    json={"into": keeper, "sources": [doomed]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["frames_added"] == 1
    # The field the confirmation reads, so it can say what survived.
    assert body["pictures_kept"] == 1

    # The folder really was deleted — the picture moved out ahead of it.
    assert not _target_dir(solved_library, doomed).exists()

    proj = Project.open(_target_dir(solved_library, keeper))
    try:
        runs = [r for r in proj.iter_stack_runs() if r.notes == "second night"]
        assert len(runs) == 1
        run = runs[0]
        assert run.n_frames_used == 31
        assert Path(run.fits_path).read_bytes() == b"the-second-nights-pixels"
        assert Path(run.preview_path).read_bytes() == b"the-second-nights-preview"
        # The sibling that resolves off the basename rather than off a column.
        stem = Path(run.fits_path).stem
        assert (Path(run.fits_path).parent / f"{stem}_coverage.fits").read_bytes() \
            == b"the-second-nights-coverage"
        # The user's saved edit followed its picture, re-keyed to the new run id.
        assert proj.get_meta(f"editor_recipe:{run.id}") == json.dumps({"ops": []})
    finally:
        proj.close()


def test_every_registered_per_run_meta_prefix_is_one_the_merge_carries():
    from seestack.io.merge import _RUN_META_KEY
    from webapp.run_meta import per_run_meta_prefixes

    prefixes = per_run_meta_prefixes()
    assert prefixes, "the registry is empty — this guard would vacuously pass"
    for prefix in prefixes:
        m = _RUN_META_KEY.match(f"{prefix}7")
        assert m is not None, f"{prefix!r} is not shaped like a per-run key"
        assert m.group("prefix") == prefix
        assert m.group("run_id") == "7"
