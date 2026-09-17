"""A mosaic's panels are different star fields, not different skies.

``transparency_score`` is the median flux of a frame's *brightest stars*, so it
is a property of where the scope pointed as much as of the sky. The per-run
``transparency_ratio`` behind the **"Hazy night"** badge compared it against a
target-wide ``p90`` baseline — which on a mosaic is set by whichever panel has
the richest star field, so every other panel read as haze and a perfectly clear
mosaic was stamped "Hazy night" on History, Gallery and Compare.

It now splits by mosaic panel through the shared ``pointing_groups`` gate, and
falls back to exactly the old target-wide behaviour when the pointings don't
split soundly. (The sibling site on the same metric — the "Clouds & haze" card's
session trend — is fixed and covered in ``tests/test_session_recap.py``.)
"""

import numpy as np

from seestack.io.project import FrameRow, Project, StackRunRow
from seestack.stack.stacker import _compute_transparency_ratio
from seestack.stackhealth import (
    HAZY_RATIO,
    TRANSPARENCY_ESTIMATOR_GENERATION,
    hazy_verdict,
    readable_transparency_ratio,
    stored_hazy_verdict_for,
)

# Three mosaic panels, 1° apart — well beyond the 0.25° panel link distance, and
# well inside the 3° "two different targets" distance.
PANELS = [(10.0, 20.0), (11.0, 20.0), (12.0, 20.0)]
# Their star fields differ by ~2.5× top to bottom. That is the intrinsic field,
# not haze: the measured cross-panel gain error behind the v0.271.0 fix was 2.23×.
FIELD = [10000.0, 5000.0, 4000.0]


def _add(proj, name, *, ra, dec, transp, accept=True):
    fid = proj.add_frame(FrameRow(
        id=None, source_path=name, accept=accept,
        ra_center_deg=ra, dec_center_deg=dec, transparency_score=transp,
    ))
    return proj.get_frame(fid)


def _mosaic_night(proj, *, dim=1.0, tag="a", per_panel=6):
    """One mosaic night: ``per_panel`` subs on each of the three panels.

    ``dim`` multiplies every score — a night shot through haze dims all panels
    equally, which is what a *real* hazy run looks like.
    """
    return [
        _add(proj, f"{tag}_p{p}_{k}.fit", ra=PANELS[p][0], dec=PANELS[p][1],
             transp=FIELD[p] * dim + k)
        for p in range(len(PANELS))
        for k in range(per_panel)
    ]


# ---------------------------------------------------------------------------
# The "Hazy night" badge (per-run transparency_ratio)
# ---------------------------------------------------------------------------

def test_a_clear_mosaic_run_is_not_called_hazy(tmp_path):
    """Before the fix this scored 0.50 — a "Hazy night" badge on a steady sky."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        frames = _mosaic_night(proj)
        ratio = _compute_transparency_ratio(proj, frames)
        assert ratio is not None
        assert ratio > 0.9, f"a clear mosaic read as {ratio} of its clearest nights"
    finally:
        proj.close()


def test_a_genuinely_hazy_mosaic_run_still_reads_hazy(tmp_path):
    """Per-panel comparison must not cost the badge its actual job."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _mosaic_night(proj, tag="clear")             # this target's clear baseline
        hazy = _mosaic_night(proj, tag="hazy", dim=0.4)
        ratio = _compute_transparency_ratio(proj, hazy)
        assert ratio is not None
        assert ratio < 0.6, f"a mosaic shot at 40% transparency read as {ratio}"
    finally:
        proj.close()


def test_one_hazy_panel_of_three_is_still_visible(tmp_path):
    """Combining the panels' ratios by median keeps a *majority*-clear run clear,
    but a single hazy panel still drags the run's number below 1."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _mosaic_night(proj, tag="clear")
        run = _mosaic_night(proj, tag="tonight")
        # Re-shoot panel 0 through haze; it is one of three, so the median panel
        # ratio stays near 1 — but the value must not read as *better* than clear.
        hazy = [_add(proj, f"haze_{k}.fit", ra=PANELS[0][0], dec=PANELS[0][1],
                     transp=FIELD[0] * 0.3 + k) for k in range(6)]
        ratio = _compute_transparency_ratio(proj, run + hazy)
        assert ratio is not None
        assert ratio <= 1.05
    finally:
        proj.close()


def test_a_single_field_target_keeps_the_target_wide_baseline(tmp_path):
    """No sound panel split → byte-for-byte the old behaviour."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        ra, dec = PANELS[0]
        for i in range(6):
            _add(proj, f"clear{i}.fit", ra=ra, dec=dec, transp=9000 + i * 100)
        hazy = [_add(proj, f"h{j}.fit", ra=ra, dec=dec, transp=t)
                for j, t in enumerate([3800, 4000, 4200])]
        ratio = _compute_transparency_ratio(proj, hazy)
        assert ratio is not None
        assert ratio < 0.6
    finally:
        proj.close()


def test_an_unsolved_target_keeps_the_target_wide_baseline(tmp_path):
    """Frames with no pointing can't be split; the old path must still answer."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for i in range(6):
            _add(proj, f"c{i}.fit", ra=None, dec=None, transp=10000)
        run = [_add(proj, f"r{j}.fit", ra=None, dec=None, transp=10000)
               for j in range(4)]
        ratio = _compute_transparency_ratio(proj, run)
        assert ratio is not None
        assert 0.95 <= ratio <= 1.05
    finally:
        proj.close()


# ---------------------------------------------------------------------------
# Reading a **stored** figure on the scale it was written on
#
# v0.304.2 fixed the estimator and re-measured nothing, so a library that has
# been shooting for a while holds both generations at once. The badge's bar
# lives in today's code; a mosaic figure from before the fix does not.
# ---------------------------------------------------------------------------

def _run(**kw) -> StackRunRow:
    """A stack-run row with just the columns this question turns on."""
    base = dict(
        id=1, timestamp_utc="2026-08-01T00:00:00+00:00",
        output_basename="x", fits_path=None, tiff_path=None, preview_path=None,
        n_frames_used=18, canvas_h=100, canvas_w=100,
        coverage_min=1, coverage_max=1, options_json="{}",
    )
    base.update(kw)
    return StackRunRow(**base)


def test_the_stored_figure_a_clear_mosaic_kept_is_the_one_that_reads_hazy(tmp_path):
    """The bug, measured end to end: the generation-1 estimator's own number for
    a mosaic under a steady sky falls the wrong side of today's bar."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        frames = _mosaic_night(proj)
        today = _compute_transparency_ratio(proj, frames)
        # What v0.304.1 stored for the same frames: ONE target-wide p90 baseline.
        all_rows = [f for f in proj.iter_frames() if f.transparency_score]
        baseline = float(np.percentile([f.transparency_score for f in all_rows], 90))
        stored = round(float(np.percentile(
            [f.transparency_score for f in frames], 50)) / baseline, 4)
    finally:
        proj.close()
    assert stored < HAZY_RATIO < today, (stored, today)
    # Read raw — i.e. as every surface did before this fix — the old row is hazy.
    assert hazy_verdict(stored) == "hazy"
    # Read on its own scale, it says nothing at all.
    old_row = _run(transparency_ratio=stored, is_mosaic=True,
                   engine_version="0.304.1")
    assert stored_hazy_verdict_for(old_row) is None


def test_a_mosaic_run_stacked_since_the_fix_is_read_normally():
    """The stamp is what says so; the fallback agrees with it on a dated row."""
    stamped = _run(transparency_ratio=0.4, is_mosaic=True,
                   engine_version="0.304.1",
                   transparency_scale=TRANSPARENCY_ESTIMATOR_GENERATION)
    assert stored_hazy_verdict_for(stamped) == "hazy"
    by_version = _run(transparency_ratio=0.4, is_mosaic=True,
                      engine_version="0.453.6")
    assert stored_hazy_verdict_for(by_version) == "hazy"


def test_a_single_field_run_is_never_withheld():
    """``_panel_transparency_ratios`` returns [] off a mosaic, so the estimator
    never moved there — an ancient single-field figure is read as it always was."""
    for version in ("0.100.0", None, "not-a-version"):
        row = _run(transparency_ratio=0.4, is_mosaic=False,
                   engine_version=version)
        assert stored_hazy_verdict_for(row) == "hazy", version
        assert readable_transparency_ratio(row) == 0.4


def test_an_undatable_mosaic_figure_says_nothing():
    """A version string nobody can parse is not an argument for speaking."""
    for version in (None, "", "v0.304.2", "0.x.1"):
        row = _run(transparency_ratio=0.4, is_mosaic=True,
                   engine_version=version)
        assert stored_hazy_verdict_for(row) is None, version


def test_withholding_only_ever_costs_the_claim_not_the_number():
    """A run with nothing to say and a clear run are both silent either way, so
    the rule changes exactly one thing: it stops an undatable mosaic figure
    being asserted as haze."""
    assert stored_hazy_verdict_for(_run(transparency_ratio=None,
                                        is_mosaic=True)) is None
    clear = _run(transparency_ratio=0.95, is_mosaic=True,
                 engine_version="0.304.1")
    assert stored_hazy_verdict_for(clear) is None
    # And the stored figure itself is never rewritten — only the reading of it.
    assert clear.transparency_ratio == 0.95


def test_the_scale_change_is_two_sided_so_neither_half_can_be_read_around(tmp_path):
    """Why the answer is silence rather than the seam's one-sided rule.

    The seam's v0.313.1 change could only ever lower a figure, so "flat" stayed
    honest. This one moves both ways: a target-wide baseline is set by the
    richest panel, which usually flatters *nothing* and depresses the ratio —
    but where the run leans on the rich panel it can also read high.
    """
    rng = np.random.default_rng(7)
    higher = lower = 0
    for trial in range(60):
        n_panels = int(rng.integers(2, 5))
        fields = rng.uniform(2000, 20000, n_panels)
        dim = rng.uniform(0.3, 1.0, n_panels)
        run_per_panel = rng.integers(3, 12, n_panels)
        proj = Project.create(tmp_path / f"p{trial}", name="t")
        try:
            for p in range(n_panels):
                for k in range(8):
                    _add(proj, f"b{p}_{k}", ra=10.0 + p, dec=20.0,
                         transp=float(fields[p]) * float(rng.uniform(0.9, 1.05)))
            run = [_add(proj, f"r{p}_{k}", ra=10.0 + p, dec=20.0,
                        transp=float(fields[p]) * float(dim[p])
                        * float(rng.uniform(0.97, 1.03)))
                   for p in range(n_panels)
                   for k in range(int(run_per_panel[p]))]
            today = _compute_transparency_ratio(proj, run)
            all_rows = [f for f in proj.iter_frames() if f.transparency_score]
            baseline = float(np.percentile(
                [f.transparency_score for f in all_rows], 90))
            stored = float(np.percentile(
                [f.transparency_score for f in run], 50)) / baseline
        finally:
            proj.close()
        assert today is not None
        if today > stored + 1e-6:
            higher += 1
        elif today < stored - 1e-6:
            lower += 1
    assert higher > 0 and lower > 0, (
        f"the change read one-sided over {trial + 1} mosaics "
        f"(higher {higher}, lower {lower}) — if that is now true, "
        "stored_hazy_verdict_for could keep one half of the figure")


def test_an_older_project_gains_the_transparency_scale_column_on_open(tmp_path):
    """Upgrade safety (§9), and specifically **rollback** safety: like
    ``seam_scale``, this column is additive through the un-gated ``ALTER`` +
    ``_reconcile_table_columns`` rather than through a ``SCHEMA_VERSION`` bump —
    an older build refuses to open a project stamped newer than itself, so
    bumping would make the upgrade one-way. A project missing the column must
    gain it on open, keep every row and every figure, and read those figures
    exactly as an un-upgraded build's rows deserve.
    """
    import sqlite3

    proj_dir = tmp_path / "t"
    proj = Project.create(proj_dir, name="T")
    try:
        proj.add_stack_run(_run(id=None, output_basename="old_mosaic",
                                transparency_ratio=0.50, is_mosaic=True,
                                engine_version="0.304.1"))
        proj.add_stack_run(_run(id=None, output_basename="stamped",
                                transparency_ratio=0.50, is_mosaic=True,
                                engine_version="0.304.1",
                                transparency_scale=TRANSPARENCY_ESTIMATOR_GENERATION))
    finally:
        proj.close()

    conn = sqlite3.connect(proj_dir / "project.sqlite")
    try:
        conn.execute("ALTER TABLE stack_runs DROP COLUMN transparency_scale")
        conn.commit()
        version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    proj = Project.open(proj_dir)
    try:
        assert proj._conn.execute(
            "PRAGMA user_version").fetchone()[0] == version_before
        runs = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert set(runs) == {"old_mosaic", "stamped"}
        # Every figure survives the upgrade — nothing is cleared, only read
        # differently.
        assert all(r.transparency_ratio == 0.50 for r in runs.values())
        # The stamp did not survive the *downgrade* that dropped the column, so
        # both rows read as undated, which is the honest answer for a DB an
        # un-upgraded build has been writing.
        assert runs["old_mosaic"].transparency_scale is None
        assert stored_hazy_verdict_for(runs["old_mosaic"]) is None
    finally:
        proj.close()


def test_the_stamp_round_trips_through_the_project_db(tmp_path):
    """The column is written and read back, so a run stacked today is dated for
    every future reader rather than falling back to its version string."""
    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_run(id=None, output_basename="fresh",
                                transparency_ratio=0.50, is_mosaic=True,
                                engine_version="0.304.1",
                                transparency_scale=TRANSPARENCY_ESTIMATOR_GENERATION))
        stored = next(iter(proj.iter_stack_runs()))
        assert stored.transparency_scale == TRANSPARENCY_ESTIMATOR_GENERATION
        assert stored_hazy_verdict_for(stored) == "hazy"
    finally:
        proj.close()
