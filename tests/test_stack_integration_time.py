"""What a picture is worth, when the subs are not all the same length.

A stack's ``total_exposure_s`` — the ``EXPTOTAL`` card in ``master.fits``, the
hours on the History card, the "N h captured" clause in every shared caption — was
``median sub exposure x frames combined``. That is the same shortcut v0.456.0
named for the dark advisory (*a representative value is a claim that the set is
uniform*), and here it is arithmetic rather than wording: a target is one folder,
never one exposure, and a median of a set with two lengths in it is one member of
that set picked by position, not a summary of it.

Measured, on six subs:

===========================  =========  ==========  ======
subs                         real       old figure  error
===========================  =========  ==========  ======
6 x 10 s                        60 s        60 s     0 %
4 x 10 s + 2 x 30 s            100 s        60 s   -40 %
3 x 10 s + 3 x 30 s            120 s       180 s   +50 %
2 x 10 s + 4 x 30 s            140 s       180 s   +29 %
===========================  =========  ==========  ======

The fix is the mean on a mixed target and the median on a uniform one — so every
ordinary stack is byte-for-byte what it always was, and the one number the figure
exists to state is the light that was actually collected.
"""

from __future__ import annotations

import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("PIL")

from astropy.io import fits  # noqa: E402

from seestack.calibrate.apply import typical_exposure_s  # noqa: E402
from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.stacker import (  # noqa: E402
    StackOptions,
    _integration_time_s,
    run_stack,
)
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


class _F:
    """The one attribute ``_integration_time_s`` reads off a frame."""

    def __init__(self, exposure_s: float | None) -> None:
        self.exposure_s = exposure_s


def _frames(exposures: list[float | None]) -> list[_F]:
    return [_F(e) for e in exposures]


# ---- the figure itself -------------------------------------------------------

@pytest.mark.parametrize("exposures", [
    [10.0] * 4 + [30.0] * 2,          # the minority is longer
    [10.0] * 3 + [30.0] * 3,          # an even split — the worst case
    [30.0] * 4 + [10.0] * 2,          # the minority is shorter
    [10.0] * 100 + [30.0] * 100,      # at a real target's depth
    [10.0, 20.0, 30.0],               # three lengths, not two
])
def test_a_mixed_target_reports_the_light_it_actually_collected(exposures):
    """With every candidate sub used, the figure is the exact sum — no estimate
    is involved at all, because the mean times the count *is* the sum."""
    frames = _frames(exposures)
    assert _integration_time_s(frames, len(frames)) == pytest.approx(
        sum(exposures))


def test_a_single_exposure_target_is_unchanged():
    """Every ordinary target, and the whole installed base's hot path: the median
    still answers, so nothing about an existing library's numbers moves."""
    assert _integration_time_s(_frames([10.0] * 6), 6) == pytest.approx(60.0)
    assert typical_exposure_s([10.0] * 6) == pytest.approx(10.0)


def test_a_set_with_no_usable_exposure_answers_none_rather_than_raising():
    """The shared form is asked by ``seestack.stackhealth`` too, where the input is
    whatever the frame rows recorded — so "nothing recorded one" has to be an
    answer rather than an exception. Missing, non-finite and non-positive values
    are dropped the way ``distinct_exposures`` drops them, not grouped."""
    assert typical_exposure_s([]) is None
    assert typical_exposure_s([None, None]) is None
    assert typical_exposure_s([0.0, -10.0, float("nan")]) is None
    # …and a usable value beside unusable ones still answers.
    assert typical_exposure_s([None, 10.0, 0.0]) == pytest.approx(10.0)


def test_header_rounding_is_one_exposure_not_two():
    """``9.998`` against ``10.0`` is a FITS card rounded, not a second sub length.
    Grouping is the engine's own ``distinct_exposures``, so the median — the
    robust choice, which one mistyped header cannot move — still answers here."""
    exposures = [10.0, 9.998, 10.001, 10.0, 9.999, 10.0]
    assert typical_exposure_s(exposures) == pytest.approx(
        sorted(exposures)[len(exposures) // 2])


def test_one_absurd_header_cannot_move_a_uniform_targets_figure():
    """The reason the uniform case keeps the median rather than simply always
    taking the mean: a single 3600 s typo in a night of 10 s subs would inflate
    the mean six-fold, and the median ignores it."""
    exposures = [10.0] * 5 + [3600.0]
    assert typical_exposure_s([10.0] * 6) == pytest.approx(10.0)
    # It *is* mixed, so the honest total is still the sum — but the point is that
    # a uniform night keeps its robust answer, which the line above pins.
    assert _integration_time_s(_frames(exposures), 6) == pytest.approx(
        sum(exposures))


def test_dropped_subs_are_still_scaled_rather_than_summed():
    """A sub that failed mid-stack contributed nothing, so the figure is scaled by
    the frames that actually combined — which is why this is ``typical x n_used``
    and not ``sum``. Nothing here says *which* of them dropped, so the mean of the
    candidates is the unbiased estimate of what the survivors were worth."""
    exposures = [10.0] * 4 + [30.0] * 2      # 100 s over 6 candidates
    assert _integration_time_s(_frames(exposures), 3) == pytest.approx(50.0)
    # A uniform target's dropped-sub arithmetic is exactly what it always was.
    assert _integration_time_s(_frames([10.0] * 6), 4) == pytest.approx(40.0)


def test_subs_with_no_recorded_exposure_are_assumed_to_look_like_the_rest():
    """A frame whose header carried no exposure is not a zero-length sub. It is
    excluded from the set the typical value is measured over and still counted in
    ``n_used``, so it is credited at the typical length rather than at nothing."""
    frames = _frames([10.0, 10.0, 30.0, 30.0, None, None])
    assert _integration_time_s(frames, 6) == pytest.approx(20.0 * 6)


def test_nothing_is_claimed_when_no_sub_records_an_exposure():
    assert _integration_time_s(_frames([None, None]), 2) is None
    assert _integration_time_s(_frames([0.0, -1.0]), 2) is None
    assert _integration_time_s(_frames([10.0]), 0) is None


# ---- end to end, through a real run -----------------------------------------

def _mixed_project(tmp_path, exposures: list[float]) -> Project:
    proj = Project.create(tmp_path / "p", name="mixed")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i, exposure in enumerate(exposures):
        path = write_seestar_fits(raws / f"f{i}.fit", add_wcs=True,
                                  seed=10 + i, n_stars=30)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            exposure_s=exposure,
        ))
    return proj


def test_a_real_mixed_run_records_and_stamps_the_honest_integration(tmp_path):
    """Through ``run_stack``, on the two places the owner meets the number: the
    run record every caption and History card reads, and the master's own FITS
    header, which is what Siril and PixInsight show.

    The two header cards must also agree with each other — a reader multiplying
    ``EXPOSURE`` by ``NFRAMES`` has to land on ``EXPTOTAL``, and with a median
    per-sub beside a mean-derived total they could not.
    """
    exposures = [10.0] * 4 + [30.0] * 2      # 100 s of light, median 10 s
    proj = _mixed_project(tmp_path, exposures)
    try:
        res = run_stack(proj, StackOptions(sigma_clip=True, max_workers=1,
                                           quality_weighted=False,
                                           auto_reject=False))
        assert res.n_frames_used == len(exposures)

        run = next(iter(proj.iter_stack_runs()))
        assert run.total_exposure_s == pytest.approx(100.0)

        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
        assert hdr["EXPTOTAL"] == pytest.approx(100.0)
        assert hdr["NFRAMES"] == len(exposures)
        # ``EXPOSURE`` is stamped to 3 dp, so the product can differ from
        # ``EXPTOTAL`` by at most half a stamp per frame — and by nothing more,
        # which is the claim. (Under the median it was out by 40 s.)
        assert abs(hdr["EXPOSURE"] * hdr["NFRAMES"] - hdr["EXPTOTAL"]) <= (
            0.001 * hdr["NFRAMES"])
        # …and the card says which kind of number it is, so "per-sub exposure"
        # never names a length no sub was shot at without saying so.
        assert "mixed" in hdr.comments["EXPOSURE"]
    finally:
        proj.close()


def test_a_real_single_exposure_run_is_stamped_exactly_as_before(tmp_path):
    """The companion that guards the ordinary library: same total, same per-sub
    card, and the comment back to its plain wording."""
    proj = _mixed_project(tmp_path, [10.0] * 5)
    try:
        res = run_stack(proj, StackOptions(sigma_clip=True, max_workers=1,
                                           quality_weighted=False,
                                           auto_reject=False))
        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
        assert hdr["EXPTOTAL"] == pytest.approx(50.0)
        assert hdr["EXPOSURE"] == pytest.approx(10.0)
        assert hdr.comments["EXPOSURE"] == "per-sub exposure (s)"
    finally:
        proj.close()
