"""Worked examples beside the reject counts — "show me one you threw away".

Two layers: the pure picker (:mod:`webapp.rejectexamples`) and the
``/frames/reject-summary`` field that carries it.
"""

from __future__ import annotations

import pytest

from webapp.rejectexamples import (
    EXAMPLE_BUCKETS,
    MAX_EXAMPLES_PER_BUCKET,
    pick_reject_examples,
)
from webapp.rejection_summary import bucket_for

#: Every path exists — the ranking tests are about ranking.
ALL_READABLE = lambda cached, source: source or cached  # noqa: E731


def _row(frame_id, reason, *, fwhm=3.0, stars=200, source=None):
    return (frame_id, reason, fwhm, stars, None,
            source or f"/subs/light_{frame_id:04d}.fit")


# --- the pure picker ---------------------------------------------------------

def test_soft_offers_the_fattest_stars_first():
    rows = [_row(1, "auto:grade:fwhm", fwhm=3.1),
            _row(2, "auto:grade:fwhm", fwhm=9.4),
            _row(3, "auto:grade:fwhm", fwhm=6.0)]
    got = pick_reject_examples(rows, readable=ALL_READABLE)
    assert [e["frame_id"] for e in got["soft"]] == [2, 3, 1]
    assert got["soft"][0]["name"] == "light_0002.fit"


def test_clouds_offers_the_thinnest_star_field_first():
    rows = [_row(1, "auto:grade:star_count", stars=180),
            _row(2, "auto:grade:star_count", stars=12),
            _row(3, "auto:grade:star_count", stars=95)]
    got = pick_reject_examples(rows, readable=ALL_READABLE)
    assert [e["frame_id"] for e in got["clouds"]] == [2, 3, 1]


def test_an_unmeasured_frame_can_only_ever_be_a_filler():
    # No number means no claim about how instructive it is, so it sorts last —
    # it must never displace a frame the metric actually ranked.
    rows = [_row(1, "auto:grade:fwhm", fwhm=None),
            _row(2, "auto:grade:fwhm", fwhm=4.0)]
    got = pick_reject_examples(rows, readable=ALL_READABLE)
    assert [e["frame_id"] for e in got["soft"]] == [2, 1]


def test_trailed_has_no_metric_so_it_stays_in_id_order():
    # A satellite crossing is detected, not scored; ranking it by a number it is
    # not about would pick a frame for the wrong reason.
    rows = [_row(5, "auto:streak", fwhm=8.0, stars=10),
            _row(2, "bulk:trailed", fwhm=2.0, stars=900),
            _row(9, "bulk:streaked")]
    got = pick_reject_examples(rows, readable=ALL_READABLE)
    assert [e["frame_id"] for e in got["trailed"]] == [2, 5, 9]


def test_only_the_buckets_whose_cause_you_can_see_get_examples():
    rows = [_row(1, "user"), _row(2, "seestar_output_frame"),
            _row(3, "qc_error:boom"), _row(4, "solve_failed:whatever"),
            _row(5, "auto:streak")]
    got = pick_reject_examples(rows, readable=ALL_READABLE)
    assert set(got) == {"trailed"}
    # The gate is stated once, and it is the summary's own vocabulary.
    assert set(EXAMPLE_BUCKETS) == {"trailed", "clouds", "soft"}
    assert bucket_for("auto:streak") == "trailed"


def test_the_strip_is_capped():
    rows = [_row(i, "auto:grade:fwhm", fwhm=float(i)) for i in range(1, 40)]
    got = pick_reject_examples(rows, readable=ALL_READABLE)
    assert len(got["soft"]) == MAX_EXAMPLES_PER_BUCKET == 3


def test_a_frame_whose_file_has_gone_is_skipped_not_shown_broken():
    rows = [_row(1, "auto:grade:fwhm", fwhm=9.0, source="/gone/a.fit"),
            _row(2, "auto:grade:fwhm", fwhm=8.0, source="/here/b.fit"),
            _row(3, "auto:grade:fwhm", fwhm=7.0, source="/here/c.fit")]
    got = pick_reject_examples(
        rows, max_per_bucket=2,
        readable=lambda cached, source: (
            None if str(source).startswith("/gone/") else source))
    assert [e["frame_id"] for e in got["soft"]] == [2, 3]


def test_a_bucket_with_nothing_usable_is_absent_rather_than_empty():
    got = pick_reject_examples(
        [_row(1, "auto:streak")], readable=lambda cached, source: None)
    assert got == {}
    assert pick_reject_examples([], readable=ALL_READABLE) == {}


def test_a_hand_reject_with_no_stated_reason_is_not_an_example():
    # NULL reads as "user", exactly as `reject_reason_counts` reads it.
    assert pick_reject_examples([_row(1, None)], readable=ALL_READABLE) == {}


def test_the_readable_check_is_asked_of_candidates_not_of_every_reject():
    asked: list = []

    def counting(cached, source):
        asked.append(source)
        return source

    rows = [_row(i, "auto:grade:fwhm", fwhm=float(i)) for i in range(1, 500)]
    got = pick_reject_examples(rows, readable=counting)
    assert len(got["soft"]) == 3
    # Three examples off 499 rejects: the file question is asked a handful of
    # times, never once per rejected sub.
    assert len(asked) <= 3 * MAX_EXAMPLES_PER_BUCKET


# --- the projection this rests on -------------------------------------------

def test_iter_frame_columns_can_stream_the_rejected_rows(solved_library, client):
    from seestack.io.library import Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            ids = [f.id for f in proj.iter_frames()]
            proj.update_frame(ids[0], accept=False, reject_reason="auto:streak")
            rejected = list(proj.iter_frame_columns(
                "id", "reject_reason", rejected_only=True))
            accepted = list(proj.iter_frame_columns("id", rejected_only=False,
                                                    accepted_only=True))
            assert rejected == [(ids[0], "auto:streak")]
            assert ids[0] not in [r[0] for r in accepted]
            with pytest.raises(ValueError):
                list(proj.iter_frame_columns("id", accepted_only=True,
                                             rejected_only=True))
        finally:
            proj.close()
    finally:
        lib.close()


# --- the endpoint ------------------------------------------------------------

def test_reject_summary_carries_examples_for_the_visible_causes(
        client, solved_library):
    from seestack.io.library import Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            ids = [f.id for f in proj.iter_frames()]
            assert len(ids) >= 3
            proj.update_frame(ids[0], accept=False, reject_reason="auto:streak")
            proj.update_frame(ids[1], accept=False,
                              reject_reason="auto:grade:fwhm", fwhm_px=9.5)
            proj.update_frame(ids[2], accept=False,
                              reject_reason="auto:grade:fwhm", fwhm_px=4.0)
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/frames/reject-summary").json()
    examples = body["examples"]
    assert set(examples) == {"trailed", "soft"}
    assert [e["frame_id"] for e in examples["trailed"]] == [ids[0]]
    # Worst first — the fattest stars are the clearest teaching case.
    assert [e["frame_id"] for e in examples["soft"]] == [ids[1], ids[2]]
    assert all(e["name"] for e in examples["soft"])
    # The strips are keyed by the same buckets the counts are.
    assert set(examples) <= {b["key"] for b in body["summary"]["buckets"]}


def test_a_cause_you_cannot_see_is_counted_but_never_illustrated(
        client, solved_library):
    # "You removed these" is a real bucket with a real count, and a thumbnail of
    # one teaches nothing — the frame looks like any other.
    from seestack.io.library import Library

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for fid in [f.id for f in proj.iter_frames()]:
                proj.update_frame(fid, accept=False, reject_reason="user")
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/frames/reject-summary").json()
    assert {b["key"] for b in body["summary"]["buckets"]} >= {"removed"}
    assert body["examples"] == {}


def test_reject_summary_examples_are_empty_when_nothing_was_dropped(
        client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    body = client.get(f"/api/targets/{safe}/frames/reject-summary").json()
    assert body["examples"] == {}
