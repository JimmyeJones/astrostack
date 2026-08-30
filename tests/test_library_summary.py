"""Pure aggregation behind the "Your sky, so far" personal-progress summary."""

from __future__ import annotations

from seestack.io.library import TargetEntry
from seestack.library_summary import summarize_library


def _entry(
    name, *, safe=None, created="2026-01-01T00:00:00Z", accepted=0,
    exposure=0.0, preview=None,
):
    return TargetEntry(
        id=1,
        name=name,
        safe_name=safe or name,
        ra_deg=10.0,
        dec_deg=20.0,
        created_utc=created,
        last_activity_utc=created,
        n_frames=accepted,
        n_frames_accepted=accepted,
        total_exposure_s=exposure,
        last_stack_preview=preview,
        notes=None,
    )


def test_empty_library_summary_is_all_zero():
    s = summarize_library([])
    assert s.n_targets_imaged == 0
    assert s.n_subs_kept == 0
    assert s.total_integration_s == 0.0
    assert s.first_light_utc is None
    assert s.longest_target is None
    assert s.most_imaged_target is None
    assert s.heroes == []


def test_freshly_created_empty_target_does_not_count_as_imaged():
    # A target created but with no accepted light yet should not appear as one of
    # "your pictures" — mirrors the Dashboard progress card's has-light gate.
    s = summarize_library([_entry("M42", accepted=0, exposure=0.0)])
    assert s.n_targets_imaged == 0
    assert s.longest_target is None


def test_tallies_and_standouts():
    targets = [
        _entry("M31", created="2026-02-01T00:00:00Z", accepted=50, exposure=3000.0),
        _entry("M42", created="2026-01-15T00:00:00Z", accepted=120, exposure=1800.0),
        _entry("NGC7000", created="2026-03-01T00:00:00Z", accepted=10, exposure=6000.0),
        _entry("Empty", created="2025-12-01T00:00:00Z", accepted=0, exposure=0.0),
    ]
    s = summarize_library(targets)

    assert s.n_targets_imaged == 3  # the empty one is excluded
    assert s.n_subs_kept == 50 + 120 + 10
    assert s.total_integration_s == 3000.0 + 1800.0 + 6000.0
    # First light is the earliest *imaged* target's creation (not the empty one).
    assert s.first_light_utc == "2026-01-15T00:00:00Z"
    # Longest integration → NGC7000 (6000 s); most subs kept → M42 (120).
    assert s.longest_target is not None and s.longest_target.name == "NGC7000"
    assert s.most_imaged_target is not None and s.most_imaged_target.name == "M42"


def test_heroes_ranked_by_integration_and_filtered_by_preview():
    targets = [
        _entry("A", accepted=5, exposure=1000.0, preview="a.png"),
        _entry("B", accepted=5, exposure=3000.0, preview="b.png"),
        _entry("C", accepted=5, exposure=2000.0, preview=None),  # no picture yet
    ]
    # Every listed preview "exists"; the default predicate treats a non-empty
    # path as present.
    s = summarize_library(targets)
    names = [h.name for h in s.heroes]
    assert names == ["B", "A"]  # C has no preview → excluded; ranked by exposure
    assert all(h.has_preview for h in s.heroes)


def test_hero_preview_existence_predicate_is_honoured():
    targets = [
        _entry("A", accepted=5, exposure=1000.0, preview="present.png"),
        _entry("B", accepted=5, exposure=3000.0, preview="missing.png"),
    ]
    s = summarize_library(targets, preview_exists=lambda p: p == "present.png")
    assert [h.name for h in s.heroes] == ["A"]
    # The standout still reports has_preview=False when its file is gone.
    assert s.longest_target is not None and s.longest_target.name == "B"
    assert s.longest_target.has_preview is False


def test_hero_limit_bounds_the_grid():
    targets = [
        _entry(f"T{i}", accepted=1, exposure=float(i + 1), preview=f"{i}.png")
        for i in range(10)
    ]
    s = summarize_library(targets, hero_limit=3)
    assert len(s.heroes) == 3
    # Highest-exposure first.
    assert [h.name for h in s.heroes] == ["T9", "T8", "T7"]


def test_imaged_ranked_names_every_imaged_target_even_without_a_picture():
    """"What did I shoot?" must include a target that's collected light but hasn't
    been stacked into a picture yet — `heroes` can't answer that, because it's
    narrowed to targets with a preview on disk."""
    targets = [
        _entry("A", accepted=5, exposure=1000.0, preview="a.png"),
        _entry("B", accepted=5, exposure=3000.0, preview=None),   # no picture yet
        _entry("C", accepted=5, exposure=2000.0, preview="c.png"),
        _entry("Empty", accepted=0, exposure=0.0),                # never imaged
    ]
    s = summarize_library(targets)
    assert [t.name for t in s.imaged_ranked] == ["B", "C", "A"]  # by integration
    assert [t.name for t in s.heroes] == ["C", "A"]              # unchanged
    # has_preview still reports honestly per target.
    assert [t.has_preview for t in s.imaged_ranked] == [False, True, True]


def test_imaged_ranked_respects_the_same_cap_as_the_hero_grid():
    targets = [
        _entry(f"T{i}", accepted=1, exposure=float(i + 1)) for i in range(10)
    ]
    s = summarize_library(targets, hero_limit=3)
    assert [t.name for t in s.imaged_ranked] == ["T9", "T8", "T7"]


def test_imaged_ranked_is_empty_on_an_untouched_library():
    assert summarize_library([]).imaged_ranked == []


# "First light" is a milestone stat *and* the poster's "Since <date>" line, and
# it used to be the earliest target-*creation* stamp — when the row was made in
# AstroStack. For the owner this app is built for (a Seestar user dropping in a
# back catalogue of subs) every target is created on install day, so it claimed
# they started astrophotography the week they installed the app.
def test_first_light_is_when_the_oldest_sub_was_captured():
    targets = [
        _entry("M31", created="2026-08-30T09:00:00Z", accepted=50, exposure=3000.0),
        _entry("M42", created="2026-08-30T09:01:00Z", accepted=120, exposure=1800.0),
    ]
    captures = {"M31": "2024-11-15T22:12:00Z", "M42": "2023-02-03T20:00:00Z"}
    s = summarize_library(targets, first_capture=captures.get)
    assert s.first_light_utc == "2023-02-03T20:00:00Z"


def test_first_light_falls_back_to_creation_for_an_undated_target():
    # A target whose subs carry no DATE-OBS contributes exactly what it always
    # did, so nothing regresses on a library the lookup can't answer for.
    targets = [
        _entry("M31", created="2026-01-05T00:00:00Z", accepted=50, exposure=3000.0),
        _entry("M42", created="2026-01-02T00:00:00Z", accepted=120, exposure=1800.0),
    ]
    s = summarize_library(targets, first_capture=lambda _s: None)
    assert s.first_light_utc == "2026-01-02T00:00:00Z"
    # …and one dated target still wins over the other's creation stamp.
    s2 = summarize_library(
        targets, first_capture={"M31": "2025-06-01T00:00:00Z"}.get)
    assert s2.first_light_utc == "2025-06-01T00:00:00Z"


def test_first_light_ignores_a_target_with_no_light_yet():
    # The gate that already applied to creation stamps applies to captures too:
    # an empty target is not one of "your pictures", however old its subs claim
    # to be.
    targets = [
        _entry("M31", created="2026-01-05T00:00:00Z", accepted=50, exposure=3000.0),
        _entry("Empty", created="2025-12-01T00:00:00Z", accepted=0, exposure=0.0),
    ]
    s = summarize_library(
        targets,
        first_capture={"Empty": "2019-01-01T00:00:00Z",
                       "M31": "2025-11-02T00:00:00Z"}.get,
    )
    assert s.first_light_utc == "2025-11-02T00:00:00Z"


def test_first_light_compares_stamps_by_time_not_by_string():
    # The two kinds of stamp now mixed are written in different shapes — the
    # registry's `…Z` and a frame's DATE-OBS as ingest recorded it — so a
    # lexicographic minimum would pick whichever *spelling* sorts first.
    # "2024-03-01T00:00:00+00:00" < "2024-03-01T01:00:00Z" as text and as time;
    # the pair below disagree, which is the case that matters.
    targets = [
        _entry("A", created="2026-01-01T00:00:00Z", accepted=1, exposure=1.0),
        _entry("B", created="2026-01-01T00:00:00Z", accepted=1, exposure=1.0),
    ]
    s = summarize_library(
        targets,
        first_capture={"A": "2024-03-01T05:00:00+02:00",   # 03:00 UTC — earlier
                       "B": "2024-03-01T04:00:00Z"}.get,   # 04:00 UTC — sorts first
    )
    assert s.first_light_utc == "2024-03-01T05:00:00+02:00"


def test_first_light_survives_an_unparseable_stamp():
    targets = [_entry("M31", created="not-a-date", accepted=1, exposure=1.0)]
    s = summarize_library(targets, first_capture=lambda _s: None)
    assert s.first_light_utc == "not-a-date"   # something beats nothing
