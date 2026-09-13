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
    stacking_coverage_max,
    stacking_field_fulls,
    stacking_samples_per_pixel,
    with_inherited_light_facts,
)

# Match the ``solved_library`` fixture's seeded frames (tests/webapp/conftest.py).
FRAME_W, FRAME_H = 480, 320


@dataclass
class _Row:
    """The three fields the resolver touches, plus the two it navigates by."""

    id: int
    options_json: str
    total_exposure_s: float | None = None
    calstat: str | None = None
    transparency_ratio: float | None = None
    noise_sigma: float | None = None
    canvas_w: int | None = None
    canvas_h: int | None = None
    n_frames_used: int | None = None


@dataclass
class _CoverageRow:
    """The two fields :func:`stacking_coverage_max` reads."""

    options_json: str
    coverage_max: int | None = None


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


# --- The one column a re-render is worse than silent about ------------------

def _cov(coverage_max, *, derived_from: int | None = None) -> _CoverageRow:
    options: dict = ({"editor_recipe": {"ops": []}, "derived_from": derived_from}
                     if derived_from is not None else {"sigma_clip": True})
    return _CoverageRow(options_json=json.dumps(options), coverage_max=coverage_max)


def test_a_stacks_own_coverage_is_reported_as_measured():
    assert stacking_coverage_max(_cov(180)) == 180


def test_a_re_renders_placeholder_coverage_reads_as_unrecorded():
    """``_apply_editor_to_run`` writes a literal 1, not a NULL — so without this
    the blend reads the finished picture as one sub deep at its deepest pixel."""
    assert stacking_coverage_max(_cov(1, derived_from=7)) == 0
    # ...and it is the *derivation* that decides, not the value: an export whose
    # row happens to carry a real-looking number is still not a measurement.
    assert stacking_coverage_max(_cov(180, derived_from=7)) == 0


def test_a_genuine_one_frame_stack_keeps_its_one():
    """The rule is keyed on the row being a re-render, never on the value —
    a single-sub stack really is one frame deep, and says so honestly."""
    assert stacking_coverage_max(_cov(1)) == 1


def test_an_unrecorded_coverage_stays_unrecorded():
    assert stacking_coverage_max(_cov(None)) == 0
    assert stacking_coverage_max(_cov(0)) == 0


def test_the_placeholder_is_what_the_export_writer_actually_records():
    """Drift guard, the same shape as the inherited-set one above: this rule
    exists because ``_apply_editor_to_run`` writes a literal 1 rather than
    leaving the column NULL. If that ever changes, this rule should be re-read
    rather than silently kept."""
    import inspect

    from webapp import pipeline

    src = inspect.getsource(pipeline._apply_editor_to_run)
    assert "coverage_min=1, coverage_max=1," in src


# --- The column that is true about the row and wrong as a divisor -----------
#
# ``canvas_w``/``canvas_h`` really are the export's pixels. What they are not is
# the sky the light was spread over: a crop shrinks them while
# ``total_exposure_s`` and ``n_frames_used`` come through whole, so every
# per-pixel figure divided by them rises by exactly the crop factor.

_SHAPE = (float(FRAME_W), float(FRAME_H))


def _sized(run_id: int, w: int, h: int, *, derived_from: int | None = None,
           n_frames_used: int | None = None, drizzle_scale: float | None = None,
           ) -> _Row:
    options: dict = ({"editor_recipe": {"ops": []}, "derived_from": derived_from}
                     if derived_from is not None else {"sigma_clip": True})
    if drizzle_scale is not None:
        options |= {"drizzle": True, "drizzle_scale": drizzle_scale}
    return _Row(id=run_id, options_json=json.dumps(options),
                canvas_w=w, canvas_h=h, n_frames_used=n_frames_used)


def test_a_stack_is_measured_against_its_own_canvas():
    stack = _sized(1, FRAME_W * 2, FRAME_H * 2)
    assert stacking_field_fulls(stack, {1: stack}, _SHAPE) == 4.0


def test_a_cropped_export_is_measured_against_the_canvas_it_was_stacked_on():
    """The bug. A 2x2 mosaic cropped back to one native frame is still a picture
    of four field-fulls' worth of subs — dividing its inherited light by 1.0
    would report a depth four times what any pixel holds."""
    stack = _sized(1, FRAME_W * 2, FRAME_H * 2)
    export = _sized(2, FRAME_W, FRAME_H, derived_from=1)
    assert stacking_field_fulls(export, {1: stack, 2: export}, _SHAPE) == 4.0


def test_an_edit_of_an_edit_is_measured_against_the_stack_underneath():
    """Second pass on a finished picture: the immediate source is another crop,
    so a one-hop lookup would still be reading a cropped canvas."""
    stack = _sized(1, FRAME_W * 3, FRAME_H * 3)
    first = _sized(2, FRAME_W * 2, FRAME_H * 2, derived_from=1)
    second = _sized(3, FRAME_W, FRAME_H, derived_from=2)
    by_id = {1: stack, 2: first, 3: second}
    assert stacking_field_fulls(second, by_id, _SHAPE) == 9.0


def test_a_pruned_source_falls_back_to_the_rows_own_canvas():
    """Not a guess but the only thing left: with the stack gone from History
    there is nothing else to measure against, which is what this read did for
    every row before the rule existed."""
    orphan = _sized(2, FRAME_W, FRAME_H, derived_from=99)
    assert stacking_field_fulls(orphan, {2: orphan}, _SHAPE) == 1.0


def test_the_drizzle_scale_travels_with_the_canvas():
    """It is the *stack* that drizzled; an export's options record no scale at
    all, so reading the export's own would divide a 2x drizzled 2x2 mosaic's
    pixels by nothing and call it a 16-field raster."""
    stack = _sized(1, FRAME_W * 4, FRAME_H * 4, drizzle_scale=2.0)
    export = _sized(2, FRAME_W * 4, FRAME_H * 4, derived_from=1)
    assert stacking_field_fulls(export, {1: stack, 2: export}, _SHAPE) == 4.0


def test_no_native_frame_shape_means_no_scaling():
    stack = _sized(1, FRAME_W * 2, FRAME_H * 2)
    assert stacking_field_fulls(stack, {1: stack}, None) is None


def test_samples_per_pixel_divides_the_inherited_count_by_the_stacks_canvas():
    """``_apply_editor_to_run`` carries ``n_frames_used`` forward whole, so the
    numerator needs no correction and the denominator is the whole bug: 200 subs
    over a 2x2 is 50 a pixel, cropped or not."""
    stack = _sized(1, FRAME_W * 2, FRAME_H * 2, n_frames_used=200)
    export = _sized(2, FRAME_W, FRAME_H, derived_from=1, n_frames_used=200)
    by_id = {1: stack, 2: export}
    assert stacking_samples_per_pixel(stack, by_id, _SHAPE) == 50.0
    assert stacking_samples_per_pixel(export, by_id, _SHAPE) == 50.0


def test_samples_per_pixel_declines_rather_than_guessing():
    stack = _sized(1, FRAME_W * 2, FRAME_H * 2, n_frames_used=None)
    assert stacking_samples_per_pixel(stack, {1: stack}, _SHAPE) is None
    assert stacking_samples_per_pixel(
        _sized(1, FRAME_W, FRAME_H, n_frames_used=200), {}, None) is None


# --- The surfaces -----------------------------------------------------------

def _register_pair(
    data_root, safe: str,
    stack_canvas: tuple[int, int] = (FRAME_W, FRAME_H),
    edit_canvas: tuple[int, int] = (FRAME_W, FRAME_H),
) -> tuple[int, int]:
    """A stack and an editor export of it, shaped as a pre-v0.438.7 install has
    them: the export recorded with none of the light's facts."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            src_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="deepstack", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=180,
                canvas_w=stack_canvas[0], canvas_h=stack_canvas[1],
                coverage_min=1, coverage_max=180,
                options_json=json.dumps({"sigma_clip": True}),
                total_exposure_s=5400.0, calstat="dark+flat",
                transparency_ratio=0.91, noise_sigma=0.004,
            ))
            edit_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-09-13T10:00:00Z",
                output_basename="deepstack_edit", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=180,
                canvas_w=edit_canvas[0], canvas_h=edit_canvas[1],
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
    canvas: tuple[int, int] = (FRAME_W, FRAME_H),
) -> int:
    """A finished picture — the wall only shows runs whose preview file is on
    disk. ``derived_from`` makes it an editor export, recorded exactly the way
    ``_apply_editor_to_run`` records one on a pre-v0.438.7 install: no
    integration time of its own, and ``coverage_min``/``coverage_max`` at the
    placeholder **1** a re-render writes rather than a real stacking depth."""
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
                n_frames_used=180, canvas_w=canvas[0], canvas_h=canvas[1],
                coverage_min=1,
                coverage_max=1 if derived_from is not None else 180,
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


def test_the_wall_does_not_rank_a_finished_picture_down_for_never_stacking(
    client, solved_library,
):
    """The other half of the same row, and the one that is *worse* than silent.

    An export's ``coverage_max`` is not NULL, it is a placeholder **1** — so the
    blend, which is built to renormalise over the metrics an entry carries, had
    one present and reading "a single sub deep at the deepest pixel". Here the
    edited picture is the best in the collection on every metric it actually
    carries (most integration, same subs per pixel, grain unmeasured), against a
    rival stack that is identical but 10 % less exposed. It should score a clean
    1.0 and lead; before the fix the placeholder dragged it to 0.867 and the
    rival's 0.947 went first.
    """
    targets = client.get("/api/targets").json()
    edited, rival = targets[0]["safe_name"], targets[1]["safe_name"]
    src = _register_previewed(solved_library, edited, basename="deepstack",
                              timestamp="2026-05-02T00:00:00Z", exposure_s=18000.0)
    edit_id = _register_previewed(
        solved_library, edited, basename="deepstack_edit",
        timestamp="2026-09-13T10:00:00Z", exposure_s=None, derived_from=src)
    _register_previewed(solved_library, rival, basename="nearly",
                        timestamp="2026-05-02T00:00:00Z", exposure_s=16200.0)

    items = client.get("/api/gallery/best").json()["items"]
    assert items[0]["safe"] == edited
    assert items[0]["run_id"] == edit_id
    # Best on everything it carries → the top of the scale, not 0.867 of it.
    assert items[0]["score"] == 1.0


# --- …and the same row, on the four surfaces that divide by it --------------


def test_the_run_listing_measures_an_edit_against_the_stacks_canvas(
    client, solved_library,
):
    """History's noise-vs-time trend fits per-pixel integration across runs, so
    a 2x2 mosaic and the cropped picture made from it must not report two
    different amounts of sky for one set of subs."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    src_id, edit_id = _register_pair(
        solved_library, safe,
        stack_canvas=(FRAME_W * 2, FRAME_H * 2), edit_canvas=(FRAME_W, FRAME_H))

    runs = {r["id"]: r for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs[src_id]["field_fulls"] == 4.0
    # Its own canvas would say 1.0 — and the per-pixel integration the trend
    # fits would jump 4x between two rows describing one stack's light.
    assert runs[edit_id]["field_fulls"] == 4.0
    assert runs[edit_id]["canvas_w"] == FRAME_W  # the file itself is unchanged


def test_the_gallery_card_measures_an_edit_against_the_stacks_canvas(
    client, solved_library,
):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _src, edit_id = _register_pair(
        solved_library, safe,
        stack_canvas=(FRAME_W * 3, FRAME_H * 3), edit_canvas=(FRAME_W, FRAME_H))

    items = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert items[edit_id]["field_fulls"] == 9.0


def test_the_dashboard_strip_measures_an_edit_against_the_stacks_canvas(
    client, solved_library,
):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _src, edit_id = _register_pair(
        solved_library, safe,
        stack_canvas=(FRAME_W * 2, FRAME_H * 2), edit_canvas=(FRAME_W, FRAME_H))

    recent = {r["run_id"]: r
              for r in client.get("/api/stats").json()["recent_stacks"]}
    assert recent[edit_id]["field_fulls"] == 4.0


def test_the_wall_ranks_a_cropped_picture_on_the_sky_its_subs_covered(
    client, solved_library,
):
    """The surface with teeth again. "My best pictures" ranks on integration and
    frame count **per pixel**, and the representative of an edited target is the
    export — so a 2x2 mosaic finished and cropped back to one frame claimed four
    times the depth it has, and outranked a genuinely deeper single-field stack.

    Both targets here hold the same 180 subs and the same 5 h. The mosaic spread
    them over four field-fulls of sky, so per pixel it is a quarter as deep as
    the single field, and the single field must lead.
    """
    targets = client.get("/api/targets").json()
    mosaic, single = targets[0]["safe_name"], targets[1]["safe_name"]
    src = _register_previewed(
        solved_library, mosaic, basename="wide", timestamp="2026-05-02T00:00:00Z",
        exposure_s=18000.0, canvas=(FRAME_W * 2, FRAME_H * 2))
    edit_id = _register_previewed(
        solved_library, mosaic, basename="wide_edit",
        timestamp="2026-09-13T10:00:00Z", exposure_s=None, derived_from=src,
        canvas=(FRAME_W, FRAME_H))
    _register_previewed(
        solved_library, single, basename="deep", timestamp="2026-05-02T00:00:00Z",
        exposure_s=18000.0, canvas=(FRAME_W, FRAME_H))

    items = client.get("/api/gallery/best").json()["items"]
    shown = next(it for it in items if it["safe"] == mosaic)
    assert shown["run_id"] == edit_id
    # The cropped export is still a picture of a four-field raster's light…
    assert shown["field_fulls"] == 4.0
    # …so the single field, four times deeper per pixel, leads the wall.
    assert items[0]["safe"] == single
