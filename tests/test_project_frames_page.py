"""`Project.iter_frames_page` — the frames endpoint's sort and slice, in SQLite.

The endpoint used to read every row of the target, build a `FrameRow` for each,
sort in Python and throw all but the page away. The frames table fetches 2,000
at a time until a short page, so on the owner's deepest target (35,894 subs)
one visit meant eighteen full reads. Measured on a synthetic project of that
size: **9.09 s / 163.6 MB peak** for the full paged read the old way against
**2.42 s / 83.5 MB** this way.

Speed is the visible half; the one that matters on this box is that a page now
costs `limit` objects instead of `n` (AGENTS.md §10, "never break the ingest/
stack hot path's memory bounds" — the OOM history is why).

So what these tests pin is **equivalence**: the same rows, in the same order,
as the Python sort they replace, on every sortable column, both directions and
every interesting window — plus the memory property itself, which is the thing
that would silently regress if somebody re-introduced a whole-table read.
"""

from __future__ import annotations

import random

import pytest

from seestack.io.project import FrameRow, Project

# The user-facing sort vocabulary (`webapp.routers.frames._SORTABLE`), pinned
# here as the set the engine has to answer identically for. `id` is the default
# the endpoint falls back to for anything it doesn't recognise.
SORTABLE = (
    "id", "timestamp_utc", "exposure_s", "fwhm_px", "star_count",
    "sky_adu_median", "eccentricity_median", "transparency_score",
)


def _python_page(proj: Project, *, accepted_only: bool, sort: str,
                 descending: bool, offset: int, limit: int) -> list[FrameRow]:
    """The exact sort/slice `list_frames` did in Python, kept as the oracle."""
    frames = list(proj.iter_frames(accepted_only=accepted_only))
    measured = [f for f in frames if getattr(f, sort) is not None]
    unmeasured = [f for f in frames if getattr(f, sort) is None]
    measured.sort(key=lambda f: getattr(f, sort), reverse=descending)
    return (measured + unmeasured)[offset: offset + limit]


@pytest.fixture
def deep_project(tmp_path) -> Project:
    """A target with ties, unmeasured subs, rejected subs and every metric.

    Ties and nulls are the whole difficulty: Python's sort is stable and
    `iter_frames` yields in id order, so a tie has to come back in id order, and
    SQLite will not do that unless asked.
    """
    proj = Project.create(tmp_path / "t", "T")
    rng = random.Random(1234)
    rows = []
    for i in range(240):
        measured = i % 7 != 0          # ~1 in 7 never measured
        rows.append(FrameRow(
            source_path=f"/incoming/T/sub_{i:04d}.fit",
            # Deliberately coarse, so many frames share a timestamp.
            timestamp_utc=f"2026-01-{1 + i % 5:02d}T0{i % 6}:00:00",
            # Only three distinct exposures across 240 frames: nothing but the
            # id tie-break can separate them.
            exposure_s=[10.0, 20.0, 30.0][i % 3],
            fwhm_px=round(rng.uniform(2, 8), 1) if measured else None,
            star_count=rng.randint(10, 60) if measured else None,
            sky_adu_median=float(rng.randint(100, 130)) if measured else None,
            eccentricity_median=round(rng.uniform(0, 0.9), 2) if measured else None,
            transparency_score=round(rng.uniform(0, 1), 2) if measured else None,
            accept=i % 13 != 0,
        ))
    proj.add_frames(rows)
    yield proj
    proj.close()


@pytest.mark.parametrize("sort", SORTABLE)
@pytest.mark.parametrize("descending", [False, True])
def test_a_page_is_what_the_python_sort_would_have_given(
        deep_project, sort, descending):
    for offset in (0, 1, 17, 100, 239, 240, 10_000):
        for limit in (0, 1, 50, 500):
            got = list(deep_project.iter_frames_page(
                sort=sort, descending=descending, offset=offset, limit=limit))
            want = _python_page(deep_project, accepted_only=False, sort=sort,
                                descending=descending, offset=offset, limit=limit)
            assert [f.id for f in got] == [f.id for f in want], (
                f"{sort} descending={descending} offset={offset} limit={limit}")


@pytest.mark.parametrize("sort", SORTABLE)
def test_accepted_only_filters_the_same_rows_it_always_did(deep_project, sort):
    got = list(deep_project.iter_frames_page(
        accepted_only=True, sort=sort, limit=500))
    want = _python_page(deep_project, accepted_only=True, sort=sort,
                        descending=False, offset=0, limit=500)
    assert [f.id for f in got] == [f.id for f in want]
    assert got and all(f.accept for f in got)
    # …and it is genuinely a filter, not a no-op on this fixture.
    assert len(got) < deep_project.count()


@pytest.mark.parametrize("descending", [False, True])
def test_unmeasured_frames_stay_last_in_both_directions(deep_project, descending):
    # The ordering rule the endpoint exists to keep: an unmeasured sub is not a
    # bad one, and a reader who asked for "blurriest first" wants the worst
    # *measured* frames, not a block of subs nothing has looked at.
    page = list(deep_project.iter_frames_page(
        sort="fwhm_px", descending=descending, offset=0, limit=1000))
    values = [f.fwhm_px for f in page]
    measured = [v for v in values if v is not None]
    assert values[:len(measured)] == measured          # no null before a value
    assert measured == sorted(measured, reverse=descending)
    assert len(values) - len(measured) > 0             # the fixture has some


def test_ties_come_back_in_id_order_so_a_page_boundary_cannot_drop_a_row(
        deep_project):
    # 240 frames over three exposures, so ~80 share every sort key: paging is
    # only coherent if the order within a tie group is fixed, or two requests
    # for adjacent windows can repeat one row and never return another.
    #
    # **This asserts a contract, and it does not fail without the `id ASC`
    # term** — checked by deleting that term and re-running the file, which
    # still passes. This SQLite's sorter happens to preserve the scan order for
    # equal keys, and the scan happens to be in rowid order, so the tie-break is
    # insurance against an accident rather than a fix for a live bug: a spilled
    # sort, a later SQLite, or an index added to one of these columns could each
    # end that coincidence silently. Recorded rather than dressed up as a
    # fail-before test (AGENTS.md §8) — what *is* pinned here is that the
    # endpoint's paging and its single-request answer agree, which is the thing
    # a reader of the frames table would actually notice.
    whole = [f.id for f in deep_project.iter_frames_page(
        sort="exposure_s", limit=1000)]
    paged: list[int] = []
    for offset in range(0, 300, 25):
        paged += [f.id for f in deep_project.iter_frames_page(
            sort="exposure_s", offset=offset, limit=25)]
    assert paged == whole
    assert sorted(paged) == sorted(f.id for f in deep_project.iter_frames())
    # And the contract itself: inside every run of equal keys, ids ascend.
    rows = list(deep_project.iter_frames_page(sort="exposure_s", limit=1000))
    for i in range(1, len(rows)):
        if rows[i].exposure_s == rows[i - 1].exposure_s:
            assert rows[i].id > rows[i - 1].id


def test_a_page_builds_only_the_pages_rows(deep_project, monkeypatch):
    # The memory claim, in test form. This is what the change is *for*: the old
    # path built a FrameRow for all 240 (35,894 on the owner's deepest target)
    # to return 25 of them, and nothing would have noticed it coming back.
    import seestack.io.project as project_module

    built = 0
    real = project_module._row_to_frame

    def counting(row):
        nonlocal built
        built += 1
        return real(row)

    monkeypatch.setattr(project_module, "_row_to_frame", counting)
    page = list(deep_project.iter_frames_page(sort="fwhm_px", limit=25))
    assert len(page) == 25
    assert built == 25, f"built {built} FrameRow objects to return 25"


def test_a_sort_column_that_is_not_a_column_is_refused_not_interpolated(
        deep_project):
    # `sort` arrives from a query string. The endpoint has its own allow-list,
    # but the engine cannot rely on its caller having one.
    for bad in ("id; DROP TABLE frames", "1=1", "", "fwhm", "FWHM_PX",
                "rowid", "(SELECT 1)"):
        with pytest.raises(ValueError):
            list(deep_project.iter_frames_page(sort=bad))
    # The table is still there, which is the half a raised exception alone
    # wouldn't prove.
    assert deep_project.count() == 240


def test_negative_offset_and_limit_are_clamped_not_wrapped(deep_project):
    # SQLite reads a negative LIMIT as "no limit", which is the opposite of what
    # a caller passing -1 means — and exactly the whole-table read this method
    # exists to avoid. (The endpoint clamps too; this is the engine's own floor.)
    assert list(deep_project.iter_frames_page(limit=-1)) == []
    first = [f.id for f in deep_project.iter_frames_page(offset=0, limit=5)]
    assert [f.id for f in deep_project.iter_frames_page(offset=-7, limit=5)] == first


def test_the_endpoints_sort_vocabulary_is_all_real_columns(deep_project):
    # A drift guard: `webapp.routers.frames._SORTABLE` is the user-facing list,
    # and every entry in it has to be something this method will accept —
    # otherwise the endpoint's fall-back to `id` would silently swallow a typo
    # and serve the wrong order.
    from webapp.routers.frames import _SORTABLE

    assert set(_SORTABLE) == set(SORTABLE)
    for col in _SORTABLE:
        list(deep_project.iter_frames_page(sort=col, limit=1))
