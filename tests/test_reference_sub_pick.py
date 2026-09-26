"""Which sub stands in for "one raw frame" — sharpest, among a typical sky.

The reveal card's "stacking cut your noise ~N×" badge is a ratio of background
σ, and the σ on its numerator comes from whichever sub
:func:`webapp.routers.stack.reference_sub_from_frames` hands back. Sky **shot
noise** is the dominant term in that σ and is uncorrelated with FWHM, so picking
purely on sharpness let a frame that happened to be shot under a bright sky —
moon up, a passing cloud lit from below, twilight — stand in for a typical one
and inflate the badge by however much brighter its sky was.

Each test here also asserts what the *old* rule (``min`` FWHM over the whole
accepted pool) would have picked, so a fixture that could not exhibit the bug
goes red rather than green.
"""

from __future__ import annotations

import pytest

from seestack.io.project import FrameHealth, FrameRow
from webapp.routers.stack import _REF_SKY_MIN_SAMPLE, reference_sub_from_frames


def _rows(specs: list[tuple[float | None, float | None]], *,
          exposures: list[float] | None = None) -> list[FrameRow]:
    """One accepted sub per ``(fwhm_px, sky_adu_median)`` pair, id 1…n."""
    return [
        FrameRow(source_path=f"s{i}.fit", id=i + 1, fwhm_px=fwhm,
                 sky_adu_median=sky, accept=True,
                 exposure_s=(exposures[i] if exposures else 10.0))
        for i, (fwhm, sky) in enumerate(specs)
    ]


def _as_health(rows: list[FrameRow]) -> list[FrameHealth]:
    """The narrow record the Target page's health card reads — which has to make
    the *same* choice, or the noise stamp it fingerprints never hits."""
    return [FrameHealth(
        id=r.id, accept=r.accept, reject_reason=r.reject_reason,
        fwhm_px=r.fwhm_px, eccentricity_median=r.eccentricity_median,
        exposure_s=r.exposure_s, gain=r.gain,
        sky_adu_median=r.sky_adu_median, solved=r.solved,
    ) for r in rows]


def _sharpest_id(rows: list[FrameRow]) -> int:
    """What the pick was before v0.475.1: lowest FWHM over the whole pool."""
    return min((r for r in rows if r.fwhm_px is not None),
               key=lambda r: (r.fwhm_px, r.id or 0)).id


@pytest.fixture
def moonlit() -> list[FrameRow]:
    """Twenty subs of one target. Nineteen were shot under a sky within a few
    percent of 1000 ADU; the twentieth caught the moon at 6000 ADU — and is also
    the sharpest frame of the night, which is exactly the coincidence that made
    this a bug rather than a curiosity."""
    specs: list[tuple[float | None, float | None]] = [
        (3.0 + (i % 7) * 0.05, 990.0 + (i % 11) * 4.0) for i in range(19)
    ]
    specs.append((2.4, 6000.0))
    return _rows(specs)


def test_a_bright_sky_frame_does_not_stand_in_for_a_typical_one(moonlit):
    chosen = reference_sub_from_frames(moonlit)
    assert chosen is not None
    assert chosen.sky_adu_median == pytest.approx(1000.0, abs=60.0)
    # …and the fixture really would have fooled the old rule.
    assert _sharpest_id(moonlit) == 20
    assert chosen.id != 20


def test_the_health_record_makes_the_same_choice(moonlit):
    """Two records, one pick — the reveal endpoint reads whole rows and the
    health card reads :class:`FrameHealth`, and a disagreement between them
    would make every stamped measurement a miss."""
    assert (reference_sub_from_frames(moonlit).id
            == reference_sub_from_frames(_as_health(moonlit)).id)


def test_it_is_still_the_sharpest_of_the_typical_ones(moonlit):
    """Narrowing the pool must not stop it being a *sharpness* pick."""
    chosen = reference_sub_from_frames(moonlit)
    typical = [r for r in moonlit if r.sky_adu_median < 2000.0]
    assert chosen.fwhm_px == min(r.fwhm_px for r in typical)


def test_a_longer_exposure_minority_is_left_out():
    """Sky level scales with exposure, so a mostly-10 s target's few 30 s subs
    sit outside the band on their own — and a sub that integrated three times as
    long carries √3 the sky noise, which is the same inflation in a different
    costume (the class `run_stack`'s reference-frame exposure taught in
    v0.456.0)."""
    specs = [(3.0 + (i % 5) * 0.05, 1000.0 + (i % 7) * 3.0) for i in range(16)]
    exposures = [10.0] * 16
    specs += [(2.5, 3000.0), (2.6, 3010.0), (2.7, 2990.0), (2.8, 3020.0)]
    exposures += [30.0] * 4
    rows = _rows(specs, exposures=exposures)
    chosen = reference_sub_from_frames(rows)
    assert chosen.exposure_s == 10.0
    assert _sharpest_id(rows) == 17          # a 30 s sub, before the fix


def test_too_few_measured_skies_leaves_the_old_choice_alone():
    """Under :data:`_REF_SKY_MIN_SAMPLE` measurements there is no "typical" to
    speak of — a quartile of four numbers is an opinion — so the pick stays on
    sharpness and nothing about a small target changes."""
    specs = [(3.0 + i * 0.1, 1000.0) for i in range(_REF_SKY_MIN_SAMPLE - 1)]
    specs[-1] = (2.0, 9000.0)
    rows = _rows(specs)
    assert reference_sub_from_frames(rows).id == _sharpest_id(rows)


def test_no_sky_measurements_at_all_is_unchanged():
    """An unQC'd or legacy target carries no ``sky_adu_median``; the pick must
    degrade to what it always was rather than returning nothing."""
    rows = _rows([(3.0 + i * 0.1, None) for i in range(20)])
    assert reference_sub_from_frames(rows).id == _sharpest_id(rows)


def test_a_uniform_sky_keeps_every_frame_eligible():
    """When every sub reads the same sky the quartiles collapse onto it, and an
    inclusive band must still contain all of them — otherwise the sharpest frame
    of a perfectly consistent target would be excluded for being typical."""
    rows = _rows([(3.0 + i * 0.1, 1234.0) for i in range(20)])
    assert reference_sub_from_frames(rows).id == _sharpest_id(rows)


def test_rejected_frames_are_still_skipped_first():
    """Acceptance outranks both: a set-aside sub is not a candidate however
    sharp or however typical its sky."""
    rows = _rows([(3.0 + (i % 6) * 0.05, 1000.0 + (i % 5) * 2.0)
                  for i in range(20)])
    rows[0].fwhm_px = 1.0
    rows[0].accept = False
    chosen = reference_sub_from_frames(rows)
    assert chosen.id != 1
    assert chosen.accept
