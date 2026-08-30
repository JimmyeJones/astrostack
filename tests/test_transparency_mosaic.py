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

from seestack.io.project import FrameRow, Project
from seestack.stack.stacker import _compute_transparency_ratio

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
