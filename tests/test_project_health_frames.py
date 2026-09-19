"""`Project.iter_health_frames` — how each sub turned out, without its header.

The Target page's "How's my stack?" card hands *every* sub of the target to
three functions — `stack_health`, `recommended_dark_spec` and the reference-sub
pick behind the noise yardstick — which between them read seven small fields and
one bit ("did ASTAP locate it?"). It was reading whole `FrameRow`s to do it, and
a `FrameRow` is `SELECT *`: on a solved sub the plate solution is a FITS header
text of ~25 eighty-character cards, i.e. almost all of what the read moves, for
a field nothing here does more than test for presence.

Measured on a synthetic project the size of the owner's deepest target (35,894
subs, ~2 kB of `wcs_json` each, best of 3): **1,180 ms / 144.0 MB peak** the old
way against **541 ms / 9.8 MB** this way, field-for-field identical. Memory is
the point rather than the milliseconds — AGENTS.md §10, this box has an OOM
history — and the card sits on the page the owner opens most.

So what these tests pin is **equivalence** (the same values, in the same order,
as reading the rows) plus the memory property itself, measured against the row
read on the same frames — that is the half that would silently regress if a
whole-row read came back.
"""

from __future__ import annotations

import pytest

from seestack.io.project import (
    _HEALTH_COLUMNS,
    FrameHealth,
    FrameRow,
    Project,
)

#: Every field of `FrameHealth`, and the `FrameRow` expression that must equal
#: it. Spelled out rather than derived, so a field quietly dropped from the read
#: goes red instead of simply not being compared.
FIELDS = {
    "id": lambda f: f.id,
    "accept": lambda f: f.accept,
    "solved": lambda f: f.solved,
    "reject_reason": lambda f: f.reject_reason,
    "fwhm_px": lambda f: f.fwhm_px,
    "eccentricity_median": lambda f: f.eccentricity_median,
    "exposure_s": lambda f: f.exposure_s,
    "gain": lambda f: f.gain,
}

#: A solved sub's WCS: the bulk of the row, and the whole reason this method
#: exists — a fixture has to carry one, or it is measuring nothing.
WCS = "".join(f"CARD{c:02d}  = 1.2345678901E+02".ljust(80) for c in range(25))


@pytest.fixture
def graded_project(tmp_path) -> Project:
    """A target whose subs turned out every way the card can grade.

    Deliberately awkward in each of them: subs QC set aside, subs ASTAP tried
    and failed to locate, subs it has not reached yet, one carrying a *blank*
    WCS rather than none, unmeasured star shapes, and two exposures so a median
    has something to choose between.
    """
    proj = Project.create(tmp_path / "t", "T")
    rows = []
    for i in range(120):
        tried_and_failed = i % 7 == 0
        rows.append(FrameRow(
            source_path=f"/incoming/T/sub_{i:04d}.fit",
            # A blank string is "not located" the same as NULL is — the one
            # value where "is the column there?" and "did it locate?" differ.
            wcs_json=("" if i == 3 else None) if (tried_and_failed or i % 9 == 0)
            else WCS,
            accept=i % 11 != 0,                     # ~1 in 11 set aside
            reject_reason=("solve_failed:no match" if tried_and_failed
                           else ("auto:grade:fwhm_px" if i % 11 == 0 else None)),
            fwhm_px=(2.5 + (i % 13) * 0.1) if i % 5 else None,
            eccentricity_median=(0.3 + (i % 7) * 0.05) if i % 4 else None,
            exposure_s=10.0 if i % 3 else 30.0,
            gain=80.0 if i % 5 else 200.0,
        ))
    proj.add_frames(rows)
    yield proj
    proj.close()


@pytest.mark.parametrize("accepted_only", [True, False])
def test_it_is_what_reading_the_rows_would_have_given(graded_project,
                                                      accepted_only):
    """The equivalence claim, field by field and in order."""
    rows = list(graded_project.iter_frames(accepted_only=accepted_only))
    health = list(graded_project.iter_health_frames(accepted_only=accepted_only))
    assert len(health) == len(rows) > 0
    for want, got in zip(rows, health, strict=True):
        for name, read in FIELDS.items():
            assert read(got) == read(want), f"{name} differs on frame {want.id}"


def test_the_records_come_back_in_id_order(graded_project):
    """`iter_frames`' own order, kept deliberately: every caller takes a median,
    and a median is one member of the set chosen by position."""
    ids = [f.id for f in graded_project.iter_health_frames()]
    assert ids == sorted(ids)
    assert ids == [f.id for f in graded_project.iter_frames()]


def test_reading_them_builds_no_frame_objects(graded_project, monkeypatch):
    """The claim the card is for. Fail-before: it built a `FrameRow` per sub —
    35,894 on the owner's deepest target, 144 MB of them — to read seven small
    fields and one bit."""
    import seestack.io.project as project_module

    built = 0
    real = project_module._row_to_frame

    def counting(row):
        nonlocal built
        built += 1
        return real(row)

    monkeypatch.setattr(project_module, "_row_to_frame", counting)
    got = list(graded_project.iter_health_frames())
    assert got and built == 0, f"built {built} FrameRow objects"


def test_holding_the_whole_target_costs_a_fraction_of_holding_the_rows(tmp_path):
    """The memory claim in its own right, measured rather than reasoned — and
    the half a caller most easily loses.

    The header is not skipped: the read streams, so one is alive at a time and
    testing it here costs about 5 % (269 ms against 256 ms for a SQL expression
    that never materialises it, same peak). What the old path could not do was
    **let it go** — every `FrameRow` held its own, all at once, and that is the
    whole 144 MB. So this pins the retained set, against the row read on the
    same frames, which is the comparison the endpoint actually made.
    """
    import tracemalloc

    n = 1000
    proj = Project.create(tmp_path / "deep", "D")
    try:
        proj.add_frames([
            FrameRow(source_path=f"/incoming/D/sub_{i:04d}.fit", wcs_json=WCS,
                     fwhm_px=3.0, eccentricity_median=0.4, exposure_s=10.0,
                     gain=80.0)
            for i in range(n)])

        def peak_of(read):
            tracemalloc.start()
            got = read()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert len(got) == n
            return peak

        rows = peak_of(lambda: list(proj.iter_frames()))
        health = peak_of(lambda: list(proj.iter_health_frames()))

        # Measured at ~1/15 on the owner's deepest target (144.0 MB → 9.8 MB)
        # and ~1/14 here. A quarter is a deliberately wide bar: the point is the
        # order of the cost, not a byte count that would drift with a field.
        assert health < rows / 4, (
            f"{n} health records peaked at {health / 1024:.0f} KiB against "
            f"{rows / 1024:.0f} KiB for the same frames as rows")
    finally:
        proj.close()


def test_an_empty_target_answers_empty_rather_than_raising(tmp_path):
    """A freshly created target has no frames, and the card reaches this on
    every target before anything has been ingested."""
    proj = Project.create(tmp_path / "empty", "E")
    try:
        assert list(proj.iter_health_frames()) == []
    finally:
        proj.close()


# ---------------------------------------------------------------------------
# `solved` — one bit, two spellings, one definition.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wcs,expected", [
    (None, False),
    ("", False),
    ("{}", True),
    (WCS, True),
])
def test_the_two_spellings_of_solved_agree(tmp_path, wcs, expected):
    """`FrameRow` keeps the header and answers over it on demand; `FrameHealth`
    answers once and lets the header go. The same `bool` of the same value, and
    pinned against each other rather than each against a copy of the rule —
    including on the empty string, which is the case where "is it there?" and
    "did it locate?" could part ways."""
    proj = Project.create(tmp_path / "s", "S")
    try:
        proj.add_frames([FrameRow(source_path="a.fit", wcs_json=wcs)])
        [row] = list(proj.iter_frames())
        [health] = list(proj.iter_health_frames())
        assert row.solved is health.solved is expected
    finally:
        proj.close()


def test_the_column_list_and_the_record_are_in_step(graded_project):
    """`iter_health_frames` unpacks the tuple positionally, so the two lists
    being in step is load-bearing and silent when it breaks — a swapped pair of
    same-typed fields (`exposure_s`/`gain`, both REAL) would raise nothing.

    They are not the *same* list: the record's last field is `solved`, read from
    the `wcs_json` column and kept as a bool. That one rename is the only
    difference allowed, and naming it here is what makes a second one go red.
    """
    from dataclasses import fields as dc_fields

    record = tuple(f.name for f in dc_fields(FrameHealth))
    assert record == _HEALTH_COLUMNS[:-1] + ("solved",)
    assert _HEALTH_COLUMNS[-1] == "wcs_json"
    assert set(record) == set(FIELDS)
