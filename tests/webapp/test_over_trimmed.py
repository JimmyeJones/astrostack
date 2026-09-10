"""``GET /api/over-trimmed-pictures`` — the library-wide half of "an older
version trimmed this picture too far".

The per-run verdict is tested in ``test_editor.py``; these pin the cross-target
scan the Dashboard note reads: that it finds the affected targets, that it stays
silent on a healthy library, that it judges the *newest* picture, that one broken
project cannot cost the whole answer, and — the rule that matters most — that it
can never name a different set of pictures from the editor's own note.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.webapp.test_editor import (
    _make_run,
    _ragged_border_coverage,
    _write_frame_coverage,
)

#: The rectangle the 2026-09-10 audit found in the owner's saved recipe, written
#: by v0.277.0 onto a 5089x2045 mosaic: 3.4 % of the canvas.
_AUDIT_SLIVER = {"x0": 0.6228, "y0": 0.0341, "x1": 0.6896, "y1": 0.5463}


def _save_crop(client, safe, rid, rect):
    r = client.put(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe",
                   json={"ops": [{"id": "geometry.crop", "enabled": True,
                                  "params": dict(rect)}]})
    assert r.status_code == 200, r.text


def _over_trimmed(client):
    r = client.get("/api/over-trimmed-pictures")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_library_with_nothing_saved_is_silent(client, solved_library):
    """Every healthy install, and every library on the very first render."""
    assert _over_trimmed(client) == {"count": 0, "items": []}


def test_it_names_the_target_whose_saved_edit_carries_the_sliver(client,
                                                                 solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=True)
    _write_frame_coverage(solved_library, safe, _ragged_border_coverage())
    _save_crop(client, safe, rid, _AUDIT_SLIVER)

    body = _over_trimmed(client)
    assert body["count"] == 1
    (item,) = body["items"]
    assert item["safe"] == safe and item["run_id"] == rid
    assert item["stored_keep_fraction"] == pytest.approx(0.034, abs=0.002)
    assert item["suggested_keep_fraction"] == pytest.approx(0.912, abs=0.01)


def test_the_dashboard_and_the_editor_can_never_name_different_pictures(
        client, solved_library):
    """One definition, two surfaces — the rule ``scan_new_subs_waiting`` was
    written to keep, here for a note whose whole credibility is that the picture
    it accuses is the picture on screen. Both targets get a run; only one gets
    the sliver; the two surfaces are asked independently and must agree on each."""
    targets = client.get("/api/targets").json()
    assert len(targets) >= 2, "the fixture library should have two targets"
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    rid_a = _make_run(solved_library, a, h=80, w=100, is_mosaic=True)
    rid_b = _make_run(solved_library, b, h=80, w=100, is_mosaic=True)
    for safe in (a, b):
        _write_frame_coverage(solved_library, safe, _ragged_border_coverage())
    _save_crop(client, a, rid_a, _AUDIT_SLIVER)
    _save_crop(client, b, rid_b, {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9})

    listed = {it["safe"] for it in _over_trimmed(client)["items"]}
    per_run = {
        safe for safe, rid in ((a, rid_a), (b, rid_b))
        if client.get(
            f"/api/targets/{safe}/stack-runs/{rid}/editor/crop-health"
        ).json()["stale"]
    }
    assert listed == per_run == {a}


def test_it_judges_the_newest_picture_not_a_superseded_one(client, solved_library):
    """The newest run is what the Library card, the hero and the share sheet
    show. Offering to re-seed a superseded run's recipe would be noise — so a
    target that has since been re-stacked and re-edited correctly is done, even
    though the bad recipe is still on disk under the older run."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    old = _make_run(solved_library, safe, basename="old", h=80, w=100,
                    is_mosaic=True, ts="2026-05-01T00:00:00Z")
    new = _make_run(solved_library, safe, basename="new", h=80, w=100,
                    is_mosaic=True, ts="2026-06-01T00:00:00Z")
    for base in ("old", "new"):
        _write_frame_coverage(solved_library, safe, _ragged_border_coverage(),
                              basename=base)
    _save_crop(client, safe, old, _AUDIT_SLIVER)
    trim = client.get(
        f"/api/targets/{safe}/stack-runs/{new}/editor/trim-suggestion").json()["crop"]
    _save_crop(client, safe, new, trim)

    assert _over_trimmed(client)["count"] == 0
    # …and the superseded run itself is still honestly reported when asked
    # directly, so nothing is being hidden — it is only not *nagged* about.
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{old}/editor/crop-health"
    ).json()["stale"] is True


def test_a_correctly_trimmed_mosaic_never_appears(client, solved_library):
    """The picture today's Auto produces. If this ever fires, the note starts
    nagging about every mosaic on the owner's install."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=True)
    _write_frame_coverage(solved_library, safe, _ragged_border_coverage())
    trim = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/trim-suggestion").json()["crop"]
    _save_crop(client, safe, rid, trim)

    assert _over_trimmed(client)["count"] == 0


def test_one_unreadable_project_does_not_cost_the_whole_answer(client,
                                                               solved_library,
                                                               monkeypatch):
    """The same resilience every other cross-target read has: a corrupt target is
    skipped, not 500'd, so the note still speaks for the rest of the library."""
    targets = client.get("/api/targets").json()
    safe, other = targets[0]["safe_name"], targets[1]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=True)
    _write_frame_coverage(solved_library, safe, _ragged_border_coverage())
    _save_crop(client, safe, rid, _AUDIT_SLIVER)
    # The other target needs a run and a saved crop of its own, or the scan skips
    # it before the health check and the simulated corruption never happens.
    rid_other = _make_run(solved_library, other, h=80, w=100, is_mosaic=True)
    _write_frame_coverage(solved_library, other, _ragged_border_coverage())
    _save_crop(client, other, rid_other, _AUDIT_SLIVER)

    import webapp.routers.editor as editor_mod

    real = editor_mod.crop_health_for_run
    raised: list[str] = []

    def flaky(proj, run):  # noqa: ANN001
        # Every target *except* the affected one blows up — not "the first one",
        # which would pass vacuously whenever the scan happens to reach `safe`
        # first. The fixture library has two targets, so this always fires.
        if safe not in str(proj.project_dir):
            raised.append(str(proj.project_dir))
            raise RuntimeError("simulated corrupt project DB")
        return real(proj, run)

    monkeypatch.setattr(editor_mod, "crop_health_for_run", flaky)
    body = _over_trimmed(client)
    assert raised, "no other target was scanned — the failure never happened"
    assert body["count"] == 1 and body["items"][0]["safe"] == safe


def test_the_worst_picture_is_listed_first(client, solved_library):
    """Worst first — the picture that lost the most — so the three the Dashboard
    names outright are the three worth opening."""
    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    rid_a = _make_run(solved_library, a, h=80, w=100, is_mosaic=True)
    rid_b = _make_run(solved_library, b, h=80, w=100, is_mosaic=True)
    for safe in (a, b):
        _write_frame_coverage(solved_library, safe, _ragged_border_coverage())
    _save_crop(client, a, rid_a, {"x0": 0.0, "y0": 0.0, "x1": 0.3, "y1": 0.3})  # 9 %
    _save_crop(client, b, rid_b, _AUDIT_SLIVER)                                 # 3.4 %

    items = _over_trimmed(client)["items"]
    assert [it["safe"] for it in items] == [b, a]


def test_a_run_with_no_coverage_sibling_is_never_listed(client, solved_library):
    """Unmeasurable is not wrong. The oldest runs in the owner's library have no
    coverage map beside them; a note that fired on "I can't check" would name
    most of them."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=True)
    _save_crop(client, safe, rid, _AUDIT_SLIVER)

    assert _over_trimmed(client)["count"] == 0


def test_the_weighted_map_still_answers_for_a_run_without_a_frame_count(
        client, solved_library):
    """Runs recorded before ``_framecov.fits`` existed fall back to the weighted
    coverage map — the same precedence the border trim itself uses. They are the
    population most likely to carry a pre-D1 recipe, so they must be judged, not
    skipped."""
    from tests.webapp.test_editor import _output_dir, _write_coverage

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=True)
    _write_coverage(solved_library, safe, _ragged_border_coverage())
    assert not (_output_dir(solved_library, safe) / "master_framecov.fits").exists()
    _save_crop(client, safe, rid, _AUDIT_SLIVER)

    body = _over_trimmed(client)
    assert body["count"] == 1
    assert body["items"][0]["suggested_keep_fraction"] == pytest.approx(0.912,
                                                                        abs=0.01)


def test_a_single_field_run_with_nothing_to_trim_is_left_alone(client,
                                                               solved_library):
    """The over-trim only ever happened on a mosaic canvas, and a single field
    with uniform coverage gives the border rule nothing to propose — so there is
    no measured share to weigh a crop against and this says nothing, matching the
    editor's note exactly (which is gated on the same suggestion).

    Not gated on ``is_mosaic`` itself, though: the thing judged is a saved crop
    against a coverage map, and gating on that flag would also skip every legacy
    run recorded before it existed."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=False)
    _write_frame_coverage(solved_library, safe,
                          np.full((80, 100), 5.0, dtype="float32"))
    _save_crop(client, safe, rid, _AUDIT_SLIVER)

    assert _over_trimmed(client)["count"] == 0
