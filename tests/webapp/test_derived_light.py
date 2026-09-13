"""The exports already on disk answer about the light they were made from.

``_apply_editor_to_run`` now records an export's ``total_exposure_s``,
``calstat`` and ``transparency_ratio`` from the stack it re-rendered — but no
change at write time can reach the pictures a live install has *already*
finished, and a NAS holding three years of edits will not re-export them. So the
listings heal a derived row from the sibling row they already hold
(:mod:`webapp.derived_light`), which is the read-side twin of
``seestack.coverage_backfill``.

These tests cover the pure resolver and then the three surfaces that show a
finished picture: the History/Target run listing, the Gallery, and the "My best
pictures" wall — whose ranking reads integration directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp.derived_light import (
    INHERITED_LIGHT_FACTS,
    with_inherited_light_facts,
)


@dataclass
class _Row:
    """The three fields the resolver touches, plus the two it navigates by."""

    id: int
    options_json: str
    total_exposure_s: float | None = None
    calstat: str | None = None
    transparency_ratio: float | None = None
    noise_sigma: float | None = None


def _edit(run_id: int, source_id: int | None, **kw) -> _Row:
    options: dict = {"editor_recipe": {"ops": []}}
    if source_id is not None:
        options["derived_from"] = source_id
    return _Row(id=run_id, options_json=json.dumps(options), **kw)


def _stack(run_id: int, **kw) -> _Row:
    return _Row(id=run_id, options_json=json.dumps({"sigma_clip": True}), **kw)


def test_a_re_render_answers_with_its_stacks_light():
    src = _stack(1, total_exposure_s=5400.0, calstat="dark+flat",
                 transparency_ratio=0.91, noise_sigma=0.004)
    out = with_inherited_light_facts([_edit(2, 1), src])
    healed = next(r for r in out if r.id == 2)
    assert healed.total_exposure_s == 5400.0
    assert healed.calstat == "dark+flat"
    assert healed.transparency_ratio == 0.91
    # Not a measurement of these pixels — it stays unanswered.
    assert healed.noise_sigma is None


def test_an_ordinary_stack_is_returned_untouched():
    """Identity, not equality: the common case must cost nothing and change
    nothing, so a plain library is byte-for-byte what it was."""
    src = _stack(1, total_exposure_s=5400.0)
    other = _stack(2, total_exposure_s=60.0)
    out = with_inherited_light_facts([src, other])
    assert out[0] is src and out[1] is other


def test_a_value_the_export_already_carries_is_never_overwritten():
    """Every export written from v0.438.7 on records its own (inherited) values.
    If one is ever recorded from a different source, the row wins over the walk."""
    src = _stack(1, total_exposure_s=5400.0, calstat="dark+flat")
    edit = _edit(2, 1, total_exposure_s=1234.0)
    healed = next(r for r in with_inherited_light_facts([edit, src]) if r.id == 2)
    assert healed.total_exposure_s == 1234.0
    assert healed.calstat == "dark+flat"  # ...the one it *didn't* carry still fills


def test_an_edit_of_an_edit_reaches_the_stack_underneath():
    """The ordinary shape of a second pass: open the finished picture, adjust,
    save again. The immediate source is another export and just as empty, so a
    one-hop lookup would answer nothing."""
    src = _stack(1, total_exposure_s=5400.0, calstat="dark+flat")
    out = with_inherited_light_facts([_edit(3, 2), _edit(2, 1), src])
    assert next(r for r in out if r.id == 3).total_exposure_s == 5400.0
    assert next(r for r in out if r.id == 2).total_exposure_s == 5400.0


def test_a_pruned_source_leaves_the_row_exactly_as_it_was():
    orphan = _edit(2, 99)
    out = with_inherited_light_facts([orphan])
    assert out[0] is orphan


def test_a_self_referential_or_looped_chain_terminates():
    """``options_json`` is stored user-adjacent data; a cycle must not hang a
    page load. Neither row can answer, so neither is changed."""
    a = _edit(1, 2)
    b = _edit(2, 1)
    out = with_inherited_light_facts([a, b])
    assert out[0] is a and out[1] is b
    assert with_inherited_light_facts([_edit(1, 1)])[0].total_exposure_s is None


def test_the_inherited_set_is_the_one_the_export_writes():
    """Drift guard: the write-time list in ``_apply_editor_to_run`` and this
    read-time one are the same set by construction, and a new column added to
    one and not the other is exactly how the two would start disagreeing."""
    import inspect

    from webapp import pipeline

    src = inspect.getsource(pipeline._apply_editor_to_run)
    written = {f for f in INHERITED_LIGHT_FACTS if f"{f}=run.{f}," in src}
    assert written == set(INHERITED_LIGHT_FACTS), (
        f"the export does not carry {set(INHERITED_LIGHT_FACTS) - written}")


# --- The surfaces -----------------------------------------------------------

def _register_pair(data_root, safe: str) -> tuple[int, int]:
    """A stack and an editor export of it, shaped as a pre-v0.438.7 install has
    them: the export recorded with none of the light's facts."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            src_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="deepstack", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=180, canvas_h=320, canvas_w=480,
                coverage_min=1, coverage_max=180,
                options_json=json.dumps({"sigma_clip": True}),
                total_exposure_s=5400.0, calstat="dark+flat",
                transparency_ratio=0.91, noise_sigma=0.004,
            ))
            edit_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-09-13T10:00:00Z",
                output_basename="deepstack_edit", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=180, canvas_h=320, canvas_w=480,
                coverage_min=1, coverage_max=1,
                options_json=json.dumps({"editor_recipe": {"ops": []},
                                         "derived_from": src_id}),
                notes="edited",
            ))
            return src_id, edit_id
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_the_run_listing_names_an_old_edits_integration(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _src, edit_id = _register_pair(solved_library, safe)

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    row = next(r for r in runs if r["id"] == edit_id)
    assert row["total_exposure_s"] == 5400.0
    assert row["calstat"] == "dark+flat"
    assert row["transparency_ratio"] == 0.91
    # The picture's own grain is still unmeasured, and still says so.
    assert row["noise_sigma"] is None


def test_the_gallery_card_of_an_old_edit_names_its_integration(
    client, solved_library,
):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _src, edit_id = _register_pair(solved_library, safe)

    items = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert items[edit_id]["total_exposure_s"] == 5400.0
    assert items[edit_id]["calstat"] == "dark+flat"


def _register_previewed(
    data_root, safe: str, *, basename: str, timestamp: str,
    exposure_s: float | None, derived_from: int | None = None,
) -> int:
    """A finished picture — the wall only shows runs whose preview file is on
    disk. ``derived_from`` makes it an editor export, recorded the pre-v0.438.7
    way: no integration time of its own."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        preview = lib.target_dir(lib.find_target(safe)) / f"{basename}.png"
        preview.write_bytes(b"\x89PNG\r\n\x1a\n")
        options: dict = ({"editor_recipe": {"ops": []},
                          "derived_from": derived_from}
                         if derived_from is not None else {"sigma_clip": True})
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=timestamp, output_basename=basename,
                fits_path=None, tiff_path=None, preview_path=str(preview),
                n_frames_used=180, canvas_h=320, canvas_w=480,
                coverage_min=1, coverage_max=180,
                options_json=json.dumps(options),
                total_exposure_s=exposure_s,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_the_wall_ranks_a_finished_picture_on_the_light_it_holds(
    client, solved_library,
):
    """The surface with teeth: "My best pictures" blends integration into its
    score and breaks ties on it, and an export is the *newest* run with a
    preview — so the wall's representative for every target the owner has
    edited was the one row that reported no integration at all.
    """
    targets = client.get("/api/targets").json()
    edited, plain = targets[0]["safe_name"], targets[1]["safe_name"]
    src = _register_previewed(solved_library, edited, basename="deepstack",
                              timestamp="2026-05-02T00:00:00Z", exposure_s=18000.0)
    edit_id = _register_previewed(
        solved_library, edited, basename="deepstack_edit",
        timestamp="2026-09-13T10:00:00Z", exposure_s=None, derived_from=src)
    _register_previewed(solved_library, plain, basename="shallow",
                        timestamp="2026-05-02T00:00:00Z", exposure_s=600.0)

    items = client.get("/api/gallery/best").json()["items"]
    shown = next(it for it in items if it["safe"] == edited)
    # It really is the edit that represents the target (newest with a preview).
    assert shown["run_id"] == edit_id
    assert shown["total_exposure_s"] == 18000.0
    # ...and the five-hour picture now outranks the ten-minute one, which it did
    # not while its integration read as unknown.
    assert items[0]["safe"] == edited
