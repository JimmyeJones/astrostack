"""Star-pattern registration — the rotation phase correlation cannot measure.

The bootstrap rescue placed every member by phase correlation, which measures a
**translation**. The Seestar is alt-az, so a long session turns the field, and
``phase_cross_correlation`` never declines: it returns its best peak whatever the
rotation, and its reported error is 1.0 either way. So a rotated sub was
propagated to a confidently wrong place — measured here as a *fail-before*, on
the same fixtures the fix is judged on.

Nothing is stubbed: astroalign really matches the synthetic star patterns, and
every placement is checked against sky truth (a star's position under the
reference sub's own WCS), not against the matcher's opinion of itself.
"""

import math

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("skimage")
pytest.importorskip("astroalign")

from seestack.align.starmatch import (  # noqa: E402
    DEFAULT_MAX_ROTATION_DEG,
    SEP_SUB_OBJECT_LIMIT,
    find_star_transform,
)
from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.io.wcs_io import (  # noqa: E402
    wcs_from_text,
    wcs_text_after_pixel_affine,
)
from seestack.solve.bootstrap import (  # noqa: E402
    bootstrap_solve,
    propagate_wcs,
    register_members,
    star_match_members,
)
from tests.synth import (  # noqa: E402
    make_rotated_star_field,
    make_synth_wcs_text,
    rotated_star_positions,
    write_seestar_fits,
)

W, H = 240, 160
PIXSCALE = 5.0
RA0, DEC0 = 83.6, -5.4
N_STARS = 25
SEED = 7

# A whole night of alt-az rotation, plus the small dither that rides on it. Two
# degrees is already past what a translation absorbs (see the fail-before
# assertions); the ladder goes up to where the corner of the frame has moved
# further than the frame's own centre ever does.
ROTATIONS = [2.0, 4.0, 7.0, 11.0, 16.0, 22.0, -5.0, -13.0]
DITHER = (2.0, -1.0)


def _gray(rotation_deg: float, *, shift=DITHER, noise_seed: int = 1,
          width: int = W, height: int = H, n_stars: int = N_STARS) -> np.ndarray:
    """A background-flattened luminance frame of the field, rotated by ``rotation_deg``.

    Mirrors ``starmatch.registration_gray``'s preparation (debayer → luminance →
    robust sky subtraction → clip) so these tests see the pixels the rescue sees.
    ``width``/``height``/``n_stars`` default to this module's small field; the
    extractor-overflow test needs a denser one.
    """
    from seestack.io.fits_loader import bilinear_debayer

    mosaic = make_rotated_star_field(
        width=width, height=height, n_stars=n_stars, seed=SEED,
        rotation_deg=rotation_deg, shift=shift, noise_seed=noise_seed,
    )
    rgb = bilinear_debayer(mosaic.astype(np.float32))
    gray = rgb.mean(axis=2)
    return np.clip(gray - float(np.median(gray)), 0.0, None).astype(np.float32)


def _ref_wcs_text() -> str:
    return make_synth_wcs_text(
        width=W, height=H, ra_center_deg=RA0, dec_center_deg=DEC0,
        pixscale_arcsec=PIXSCALE, crpix_shift=(0.0, 0.0),
    )


def _placement_errors_arcsec(frame_wcs_text: str, rotation_deg: float,
                             *, shift=DITHER) -> np.ndarray:
    """How far each star lands from where the reference's WCS says it is, in arcsec.

    The only honest measure of a propagated solution: take a star's true position
    in the rotated sub, ask that sub's WCS where it is on the sky, and compare with
    the sky the *reference* sub's WCS gives the same star. A correct placement is
    sub-pixel; a translation fitted to a rotated field is not.
    """
    ref = wcs_from_text(_ref_wcs_text())
    frame = wcs_from_text(frame_wcs_text)
    assert ref is not None and frame is not None
    out = []
    for cat_xy, frame_xy in rotated_star_positions(
        width=W, height=H, n_stars=N_STARS, seed=SEED,
        rotation_deg=rotation_deg, shift=shift,
    ):
        claimed = np.asarray(frame.all_pix2world([list(frame_xy)], 0)[0], dtype=float)
        truth = np.asarray(ref.all_pix2world([list(cat_xy)], 0)[0], dtype=float)
        d = claimed - truth
        d[0] *= math.cos(math.radians(truth[1]))  # RA degrees are shorter off the equator
        out.append(math.hypot(*d) * 3600.0)
    return np.asarray(out, dtype=float)


# --- the transform itself --------------------------------------------------

@pytest.mark.parametrize("rotation_deg", ROTATIONS)
def test_find_star_transform_recovers_a_known_rotation(rotation_deg):
    ref = _gray(0.0, shift=(0.0, 0.0), noise_seed=1)
    mov = _gray(rotation_deg, noise_seed=2)
    t = find_star_transform(ref, mov, max_shift_px=200.0)
    assert t is not None, f"no match at {rotation_deg}°"
    # The transform maps the *moving* frame onto the reference, so it undoes the
    # rotation the renderer applied.
    assert t.rotation_deg == pytest.approx(-rotation_deg, abs=0.25)
    # A star clipped by the frame edge at a large rotation biases its centroid
    # inward, so the fitted scale drifts a couple of parts in a thousand — well
    # inside the module's 1 % refusal, and a fixture artefact rather than a fit
    # problem (the residual below is what says the fit is good).
    assert t.scale == pytest.approx(1.0, abs=5e-3)
    assert t.n_matched >= 6
    assert t.residual_px < 1.5
    # And it really does carry the stars back: every catalog star maps to itself.
    a, b = t.affine()
    for cat_xy, frame_xy in rotated_star_positions(
        width=W, height=H, n_stars=N_STARS, seed=SEED,
        rotation_deg=rotation_deg, shift=DITHER,
    ):
        back = a @ np.asarray(frame_xy) + b
        assert np.allclose(back, np.asarray(cat_xy), atol=1.5)


def test_find_star_transform_declines_a_starless_frame():
    ref = _gray(0.0, shift=(0.0, 0.0))
    flat = np.random.default_rng(3).normal(0.0, 1.0, size=(H, W)).astype(np.float32)
    assert find_star_transform(ref, flat, max_shift_px=200.0) is None


def test_find_star_transform_declines_bad_input():
    ref = _gray(0.0, shift=(0.0, 0.0))
    assert find_star_transform(None, ref, max_shift_px=200.0) is None
    assert find_star_transform(ref, None, max_shift_px=200.0) is None
    assert find_star_transform(ref, np.zeros((0, 0), np.float32), max_shift_px=1.0) is None
    assert find_star_transform(ref, np.zeros((4, 4, 3), np.float32), max_shift_px=1.0) is None


def test_find_star_transform_declines_a_pointing_past_the_shift_cap():
    ref = _gray(0.0, shift=(0.0, 0.0))
    mov = _gray(0.0, shift=(18.0, 9.0), noise_seed=4)
    assert find_star_transform(ref, mov, max_shift_px=200.0) is not None
    # The same match, refused because the frame's centre moved further than the
    # caller allows — the guard against a lock onto a different pointing.
    assert find_star_transform(ref, mov, max_shift_px=3.0) is None


def test_find_star_transform_declines_a_rotation_past_the_cap():
    ref = _gray(0.0, shift=(0.0, 0.0))
    mov = _gray(16.0, noise_seed=5)
    assert find_star_transform(ref, mov, max_shift_px=200.0) is not None
    assert find_star_transform(
        ref, mov, max_shift_px=200.0, max_rotation_deg=5.0) is None


def test_find_star_transform_declines_a_rescaled_field():
    """A fit that wants to resize the field has matched the wrong stars."""
    from scipy.ndimage import zoom

    ref = _gray(0.0, shift=(0.0, 0.0))
    # 4 % bigger, cropped back to the original shape: a real similarity, and one
    # no single telescope can produce between two subs.
    big = zoom(ref, 1.04, order=1)
    mov = np.ascontiguousarray(big[:H, :W]).astype(np.float32)
    assert find_star_transform(ref, mov, max_shift_px=400.0) is None
    loose = find_star_transform(
        ref, mov, max_shift_px=400.0, max_scale_deviation=0.10)
    assert loose is not None and loose.scale == pytest.approx(1 / 1.04, abs=0.01)


def test_a_rich_field_matches_instead_of_overflowing_the_extractor():
    """sep's **default** sub-object cap overflows on a dense field, and astroalign
    re-raises that as a generic "Input type for source not supported" — so the
    symptom is a matcher that quietly never matches, indistinguishable from having
    been handed something that is not an image.

    Measured on this fixture's shape (480x320, 30 stars, which is *sparser* than a
    real Seestar sub): 0 of 8 subs matched at sep's default and 8 of 8 once the cap
    is lifted. sep's limit is process-global, so this test puts it back to sep's own
    default first — otherwise any earlier match in the same worker has already
    lifted it and the test passes on the bug.
    """
    sep = pytest.importorskip("sep")
    dense_ref = _gray(0.0, shift=(0.0, 0.0), noise_seed=31, width=480, height=320,
                      n_stars=30)
    dense_mov = _gray(9.0, noise_seed=32, width=480, height=320, n_stars=30)
    sep.set_sub_object_limit(1024)  # sep's own default
    try:
        t = find_star_transform(dense_ref, dense_mov, max_shift_px=200.0)
    finally:
        sep.set_sub_object_limit(SEP_SUB_OBJECT_LIMIT)
    assert t is not None, "the rich field was not matched"
    assert t.rotation_deg == pytest.approx(-9.0, abs=0.25)


def test_star_transform_summary_is_json_safe():
    import json

    t = find_star_transform(_gray(0.0, shift=(0.0, 0.0)), _gray(7.0), max_shift_px=200.0)
    assert t is not None
    json.dumps(t.as_summary())  # must not raise — it rides a job summary
    assert DEFAULT_MAX_ROTATION_DEG > 0


# --- the WCS composition --------------------------------------------------

@pytest.mark.parametrize("rotation_deg", [0.0, 3.0, -11.0, 22.0])
def test_wcs_after_pixel_affine_places_every_star_exactly(rotation_deg):
    """The composition is exact: sky truth, not the matcher's own residual."""
    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    # The rotation the renderer applies, inverted: frame pixels → reference pixels.
    r_inv = np.array([[cos_t, sin_t], [-sin_t, cos_t]], dtype=float)
    centre = np.array([cx, cy], dtype=float)
    b = centre - r_inv @ (centre + np.asarray(DITHER, dtype=float))
    text = wcs_text_after_pixel_affine(
        _ref_wcs_text(), r_inv, b, width=W, height=H)
    assert text is not None
    errs = _placement_errors_arcsec(text, rotation_deg)
    # Sub-milliarcsecond: this is arithmetic, not a fit.
    assert errs.max() < 1e-3, errs.max()


def test_wcs_after_pixel_affine_identity_keeps_the_solution():
    text = wcs_text_after_pixel_affine(
        _ref_wcs_text(), np.eye(2), np.zeros(2), width=W, height=H)
    assert text is not None
    was, now = wcs_from_text(_ref_wcs_text()), wcs_from_text(text)
    assert np.allclose(now.wcs.crpix, was.wcs.crpix, atol=1e-9)
    assert np.allclose(now.wcs.crval, was.wcs.crval, atol=1e-12)


def test_wcs_after_pixel_affine_refuses_what_it_cannot_rewrite():
    ref = _ref_wcs_text()
    assert wcs_text_after_pixel_affine(None, np.eye(2), np.zeros(2)) is None
    assert wcs_text_after_pixel_affine("", np.eye(2), np.zeros(2)) is None
    # Not a WCS at all.
    assert wcs_text_after_pixel_affine("END", np.eye(2), np.zeros(2)) is None
    # Singular: there is no CRPIX to move to.
    assert wcs_text_after_pixel_affine(ref, np.zeros((2, 2)), np.zeros(2)) is None
    # Malformed / non-finite inputs.
    assert wcs_text_after_pixel_affine(ref, np.eye(3), np.zeros(3)) is None
    assert wcs_text_after_pixel_affine(ref, np.eye(2), np.array([np.nan, 0.0])) is None
    # A legacy CROTA header is not rewritten — the same stand-down
    # ``wcs_text_after_pixel_steps`` makes, for the same reason.
    crota = ref.replace("CDELT1", "CROTA2")
    out = wcs_text_after_pixel_affine(crota, np.eye(2), np.zeros(2))
    assert out is None or "CROTA" not in out


# --- the rescue, end to end ------------------------------------------------

def _rotated_project(tmp_path, rotations, *, anchor: bool = True):
    """A project whose subs are one field at a ladder of rotations.

    With ``anchor``, one extra sub carries the reference's own true WCS — the
    ``anchored_on_solved_sub`` path, which is the one that needs no ASTAP at all,
    so the whole rescue runs for real in these tests.
    """
    proj = Project.create(tmp_path / "proj", name="Rotating")
    truth: dict[int, float] = {}
    if anchor:
        p = tmp_path / "anchor.fit"
        write_seestar_fits(
            p, width=W, height=H, data=make_rotated_star_field(
                width=W, height=H, n_stars=N_STARS, seed=SEED,
                rotation_deg=0.0, shift=(0.0, 0.0), noise_seed=1),
        )
        proj.add_frame(FrameRow(
            source_path=str(p), wcs_json=_ref_wcs_text(), star_count=N_STARS,
            fwhm_px=4.0,
        ))
    for i, rot in enumerate(rotations):
        p = tmp_path / f"sub_{i:03d}.fit"
        write_seestar_fits(
            p, width=W, height=H, data=make_rotated_star_field(
                width=W, height=H, n_stars=N_STARS, seed=SEED,
                rotation_deg=rot, shift=DITHER, noise_seed=10 + i),
        )
        fid = proj.add_frame(FrameRow(
            source_path=str(p), star_count=N_STARS, fwhm_px=4.0))
        truth[fid] = rot
    return proj, truth


def test_phase_correlation_alone_misplaces_a_rotated_sub():
    """FAIL-BEFORE: the translation-only propagation the rescue used to do.

    Numbers, not adjectives — a 4° sub lands several pixels out and a 16° one
    tens of pixels out, which on the canvas is a star smeared into an arc.
    """
    ref = _gray(0.0, shift=(0.0, 0.0), noise_seed=1)
    worst = {}
    for rot in (4.0, 16.0):
        mov = _gray(rot, noise_seed=20)
        shifts = register_members([ref, mov], 0)
        # Phase correlation never declines: it always returns a peak.
        assert shifts[1] is not None
        text = propagate_wcs(_ref_wcs_text(), shifts, 0)[1]
        assert text is not None
        worst[rot] = float(np.median(_placement_errors_arcsec(text, rot))) / PIXSCALE
    assert worst[4.0] > 2.0, worst
    assert worst[16.0] > 8.0, worst


@pytest.mark.parametrize("rotation_deg", ROTATIONS)
def test_a_star_matched_sub_lands_where_its_stars_are(rotation_deg):
    """AND-PASSES-AFTER: the same subs, placed by their star patterns."""
    ref = _gray(0.0, shift=(0.0, 0.0), noise_seed=1)
    mov = _gray(rotation_deg, noise_seed=21)
    shifts = register_members([ref, mov], 0)
    transforms = star_match_members([ref, mov], 0)
    assert transforms[1] is not None
    text = propagate_wcs(
        _ref_wcs_text(), shifts, 0,
        transforms=transforms, shapes=[(H, W), (H, W)],
    )[1]
    assert text is not None
    errs = _placement_errors_arcsec(text, rotation_deg)
    # Within a pixel — the matcher's own residual, carried through exactly.
    assert float(np.median(errs)) < PIXSCALE, float(np.median(errs))
    assert float(errs.max()) < 2.0 * PIXSCALE, float(errs.max())


def test_star_match_members_skips_the_reference_and_unreadable_members():
    ref = _gray(0.0, shift=(0.0, 0.0), noise_seed=1)
    mov = _gray(9.0, noise_seed=22)
    out = star_match_members([ref, None, mov], 0)
    assert out[0] is None  # the reference is never matched against itself
    assert out[1] is None  # unreadable
    assert out[2] is not None
    # A reference that didn't load means nothing can be matched.
    assert star_match_members([None, mov], 0) == [None, None]
    assert star_match_members([ref, mov], 5) == [None, None]  # no such reference


def test_the_rescue_places_a_rotating_night_and_says_how(tmp_path):
    proj, truth = _rotated_project(tmp_path, ROTATIONS)
    try:
        res = bootstrap_solve(proj, min_frames=4)
        assert res.engaged and res.anchored_on_solved_sub
        assert res.n_propagated >= 6, res.reason
        assert res.n_star_matched >= 6, res.reason
        assert "star-pattern" in res.reason
        assert res.as_summary()["n_star_matched"] == res.n_star_matched
        placed = 0
        for f in proj.iter_frames():
            if f.id not in truth or not f.wcs_json:
                continue
            errs = _placement_errors_arcsec(f.wcs_json, truth[f.id])
            assert float(np.median(errs)) < PIXSCALE, (truth[f.id], float(np.median(errs)))
            assert f.ra_center_deg is not None and f.dec_center_deg is not None
            placed += 1
        assert placed >= 6
    finally:
        proj.close()


def test_the_rescue_without_star_matching_misplaces_the_same_night(tmp_path):
    """The other half of the fail-before, through the real rescue."""
    proj, truth = _rotated_project(tmp_path, ROTATIONS)
    try:
        res = bootstrap_solve(proj, min_frames=4, star_match=False)
        assert res.engaged and res.n_propagated >= 6
        assert res.n_star_matched == 0
        assert "star-pattern" not in res.reason
        worst = 0.0
        for f in proj.iter_frames():
            if f.id not in truth or not f.wcs_json:
                continue
            worst = max(worst, float(np.median(
                _placement_errors_arcsec(f.wcs_json, truth[f.id]))))
        assert worst > 2.0 * PIXSCALE, worst
    finally:
        proj.close()


@pytest.mark.parametrize("star_match", [True, False])
def test_an_ordinary_dithered_burst_is_placed_either_way(tmp_path, star_match):
    """No regression on the case the bootstrap was built and measured for.

    A pure dither is a rotation of zero, so both registrars answer it and both
    answers are right — this pins that turning star matching on did not disturb
    the burst the rescue already handled, in the only terms that matter (where
    each sub's stars end up).
    """
    proj, truth = _rotated_project(tmp_path, [0.0] * 8)
    try:
        res = bootstrap_solve(proj, min_frames=4, star_match=star_match)
        assert res.engaged and res.anchored_on_solved_sub
        assert res.n_propagated >= 6
        assert (res.n_star_matched > 0) is star_match
        for f in proj.iter_frames():
            if f.id not in truth or not f.wcs_json:
                continue
            errs = _placement_errors_arcsec(f.wcs_json, 0.0)
            assert float(np.median(errs)) < 1.5 * PIXSCALE, float(np.median(errs))
    finally:
        proj.close()


def test_the_scan_summary_carries_the_star_match_count(tmp_path):
    from seestack.io.scanner import run_qc_and_solve

    proj, _ = _rotated_project(tmp_path, ROTATIONS)
    try:
        summary = run_qc_and_solve(
            proj, run_qc=False, run_solve=False, serial=True, bootstrap_solve=True,
        )
        assert summary["bootstrap_engaged"] is True
        assert summary["bootstrap_propagated"] >= 6
        assert summary["bootstrap_star_matched"] >= 6
    finally:
        proj.close()
