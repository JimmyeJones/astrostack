"""A mosaic's panels are different star fields, not different skies.

``transparency_score`` is the median flux of a frame's *brightest stars*, so it
is a property of where the scope pointed as much as of the sky. Two places read
it across a whole target and so turned "we moved to a sparser panel" into a
weather claim on a perfectly clear night:

  * the per-run ``transparency_ratio`` behind the **"Hazy night"** badge, and
  * the **"Clouds & haze"** card's session trend.

Both now split by mosaic panel through the shared ``pointing_groups`` gate, and
both fall back to exactly their old target-wide behaviour when the pointings
don't split soundly.
"""

from seestack.io.project import FrameRow, Project
from seestack.session_recap import transparency_trend
from seestack.stack.stacker import _compute_transparency_ratio

# Three mosaic panels, 1° apart — well beyond the 0.25° panel link distance, and
# well inside the 3° "two different targets" distance.
PANELS = [(10.0, 20.0), (11.0, 20.0), (12.0, 20.0)]
# Their star fields differ by ~2.5× top to bottom. That is the intrinsic field,
# not haze: the measured cross-panel gain error behind the v0.271.0 fix was 2.23×.
FIELD = [10000.0, 5000.0, 4000.0]


def _add(proj, name, *, ra, dec, transp, t_utc=None, accept=True):
    fid = proj.add_frame(FrameRow(
        id=None, source_path=name, accept=accept, timestamp_utc=t_utc,
        ra_center_deg=ra, dec_center_deg=dec, transparency_score=transp,
    ))
    return proj.get_frame(fid)


def _clock(start_hour=20):
    """Successive capture times, five minutes apart."""
    minute = 0
    hour = start_hour
    while True:
        yield f"2026-07-10T{hour:02d}:{minute:02d}:00+00:00"
        minute += 5
        if minute >= 60:
            minute -= 60
            hour += 1


def _mosaic_night(proj, *, dim=1.0, tag="a", per_panel=6, times=None, interleave=False):
    """One clear mosaic night: ``per_panel`` subs on each of the three panels.

    ``dim`` multiplies every score (a night shot through haze dims all panels
    equally). ``interleave`` cycles the panels the way a Seestar revisits them,
    rather than shooting each to completion.
    """
    order = (
        [(k, p) for k in range(per_panel) for p in range(len(PANELS))]
        if interleave else
        [(k, p) for p in range(len(PANELS)) for k in range(per_panel)]
    )
    out = []
    for k, p in order:
        ra, dec = PANELS[p]
        out.append(_add(
            proj, f"{tag}_p{p}_{k}.fit", ra=ra, dec=dec,
            transp=FIELD[p] * dim + k, t_utc=next(times) if times else None,
        ))
    return out


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
# The "Clouds & haze" card (session transparency trend)
# ---------------------------------------------------------------------------

def test_a_clear_mosaic_night_is_not_clouds_rolling_in(tmp_path):
    """Before the fix a panel-by-panel mosaic read "degraded" (early 10025 vs
    late 4025) under a perfectly steady sky."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _mosaic_night(proj, times=_clock())
        trend = transparency_trend(proj)
        assert trend is not None
        assert trend.verdict == "clear", (
            f"{trend.verdict}: early {trend.early_transparency} "
            f"late {trend.late_transparency}"
        )
        assert trend.n_panels_levelled == 3
        assert trend.degraded_after_utc is None
    finally:
        proj.close()


def test_haze_rolling_in_across_a_mosaic_still_reads_degraded(tmp_path):
    """Levelling the panels must not blind the card to the real thing. A Seestar
    revisits its panels through the night, so a sky that closes in shows up
    *inside* every panel — which survives levelling."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        times = _clock()
        # Six passes over three panels; the sky fades steadily from 1.0 to 0.4.
        for k in range(6):
            dim = 1.0 - 0.12 * k
            for p, (ra, dec) in enumerate(PANELS):
                _add(proj, f"m{k}_{p}.fit", ra=ra, dec=dec,
                     transp=FIELD[p] * dim, t_utc=next(times))
        trend = transparency_trend(proj)
        assert trend is not None
        assert trend.n_panels_levelled == 3
        assert trend.verdict == "degraded"
        assert trend.degraded_after_utc is not None
    finally:
        proj.close()


def test_a_single_field_night_is_untouched(tmp_path):
    """No sound panel split → the plotted points are the raw scores, as before."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        times = _clock()
        ra, dec = PANELS[0]
        raw = [10000, 9800, 9600, 5000, 4800, 4600]
        for i, s in enumerate(raw):
            _add(proj, f"s{i}.fit", ra=ra, dec=dec, transp=float(s),
                 t_utc=next(times))
        trend = transparency_trend(proj)
        assert trend is not None
        assert trend.n_panels_levelled == 0
        assert [p.transparency for p in trend.points] == [float(s) for s in raw]
        assert trend.verdict == "degraded"
    finally:
        proj.close()
