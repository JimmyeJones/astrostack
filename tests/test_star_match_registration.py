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
    StarField,
    extract_star_field,
    find_star_transform,
    registration_gray,
)
from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.io.wcs_io import (  # noqa: E402
    wcs_from_text,
    wcs_text_after_pixel_affine,
)
from seestack.solve.bootstrap import (  # noqa: E402
    bootstrap_solve,
    integrate_deep_image,
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
# The anchor's own ASTAP ``CROTA2``. A real solved sub carries one, and it is
# what every rescued member used to inherit wholesale — so the fixture has to
# carry a non-zero one for "did this member get its *own* rotation?" to be a
# question with an answer. The value is arbitrary and deliberately not 0.
ANCHOR_ROTATION_DEG = 12.5

# A **real** Seestar sub's shape, for the tests that cannot be written at this
# module's 240x160. ``sep`` — the extractor astroalign detects stars with —
# refuses once more than this many pixels sit over its detection threshold, and
# re-raises that as a generic error astroalign reports as "input type not
# supported", i.e. indistinguishable from never having matched. A 240x160 frame
# holds 38,400 pixels in total, so it cannot reach the buffer however wrong the
# threshold is: the whole class of "the threshold is in the noise" bug is
# invisible at this module's size and needs a fixture with more pixels than the
# buffer has slots. (v0.483.3 was exactly that bug.)
SEP_EXTRACT_PIXSTACK_DEFAULT = 300_000
REAL_W, REAL_H = 1920, 1080
REAL_N_STARS = 120


def _gray(rotation_deg: float, *, shift=DITHER, noise_seed: int = 1,
          width: int = W, height: int = H, n_stars: int = N_STARS) -> np.ndarray:
    """A background-flattened luminance frame of the field, rotated by ``rotation_deg``.

    Mirrors ``starmatch.registration_gray``'s preparation (debayer → luminance →
    robust sky subtraction, **negatives kept**) so these tests see the pixels the
    rescue sees. ``width``/``height``/``n_stars`` default to this module's small
    field; the extractor tests need a denser or a bigger one.
    """
    from seestack.io.fits_loader import bilinear_debayer

    mosaic = make_rotated_star_field(
        width=width, height=height, n_stars=n_stars, seed=SEED,
        rotation_deg=rotation_deg, shift=shift, noise_seed=noise_seed,
    )
    rgb = bilinear_debayer(mosaic.astype(np.float32))
    gray = rgb.mean(axis=2)
    return (gray - float(np.median(gray))).astype(np.float32)


def _ref_wcs_text(*, width: int = W, height: int = H) -> str:
    return make_synth_wcs_text(
        width=width, height=height, ra_center_deg=RA0, dec_center_deg=DEC0,
        pixscale_arcsec=PIXSCALE, crpix_shift=(0.0, 0.0),
    )


def _placement_errors_arcsec(frame_wcs_text: str, rotation_deg: float,
                             *, shift=DITHER, width: int = W, height: int = H,
                             n_stars: int = N_STARS) -> np.ndarray:
    """How far each star lands from where the reference's WCS says it is, in arcsec.

    The only honest measure of a propagated solution: take a star's true position
    in the rotated sub, ask that sub's WCS where it is on the sky, and compare with
    the sky the *reference* sub's WCS gives the same star. A correct placement is
    sub-pixel; a translation fitted to a rotated field is not.
    """
    ref = wcs_from_text(_ref_wcs_text(width=width, height=height))
    frame = wcs_from_text(frame_wcs_text)
    assert ref is not None and frame is not None
    out = []
    for cat_xy, frame_xy in rotated_star_positions(
        width=width, height=height, n_stars=n_stars, seed=SEED,
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
    """A dense field matches — and, since v0.483.3, it does so whether or not sep's
    sub-object cap is raised. **Coverage of the raise, not of a bug.**

    This test was written for v0.482.0's :data:`SEP_SUB_OBJECT_LIMIT`, whose
    measurement was "0 of 8 subs matched at sep's default, 8 of 8 once the cap is
    lifted" on this fixture. That overflow turned out to be downstream of something
    else: :func:`registration_gray` used to clip the sky noise's negative half
    away, which collapsed sep's own noise estimate and put its detection threshold
    *inside* the noise, so a sparse 30-star field deblended like a crowded one.
    With the negatives kept (v0.483.3) this fixture matches **8 of 8 at sep's own
    default**, and so do 1,200 stars on 480x320 and 3,000 on 1920x1080 — all
    measured. So the fail-before this test once had is gone, and it is kept as
    coverage that the raised cap changes nothing rather than as a demonstration of
    the cap's necessity; the cap stays because it only sizes an internal buffer and
    a real crowded sky is not a synthetic one.

    sep's limit is process-global, so the default is re-asserted here — which is
    now the interesting half: it is what makes the test say "the raise is not what
    makes this work".
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


# --- stars extracted once, matched many times ------------------------------

def test_a_pre_extracted_star_field_matches_exactly_like_the_image():
    """A ``StarField`` must be a cost saving and nothing else.

    It exists so one sub can be offered to several mosaic panels for the price of one
    extraction — so it has to detect exactly what handing the image over detects, or
    the caller's choice between them would change the *answer*.
    """
    ref = _gray(0.0, shift=(0.0, 0.0), noise_seed=1)
    mov = _gray(9.0, noise_seed=2)
    from_images = find_star_transform(ref, mov, max_shift_px=200.0)
    ref_field, mov_field = extract_star_field(ref), extract_star_field(mov)
    assert ref_field is not None and mov_field is not None
    assert ref_field.n_stars >= 6 and ref_field.shape == ref.shape
    from_fields = find_star_transform(ref_field, mov_field, max_shift_px=200.0)
    assert from_images is not None and from_fields is not None
    assert from_fields == from_images
    # And the two may be mixed, which is what a caller falling back for one side does.
    mixed = find_star_transform(ref_field, mov, max_shift_px=200.0)
    assert mixed == from_images


def test_a_malformed_star_field_declines_rather_than_matching_anything():
    ref = _gray(0.0, shift=(0.0, 0.0), noise_seed=1)
    field = extract_star_field(ref)
    assert field is not None
    empty = StarField(points=np.zeros((0, 2)), shape=ref.shape)
    two = StarField(points=field.points[:2], shape=ref.shape)
    wrong = StarField(points=field.points[:, :1], shape=ref.shape)
    for bad in (empty, two, wrong):
        assert find_star_transform(bad, field, max_shift_px=200.0) is None
        assert find_star_transform(field, bad, max_shift_px=200.0) is None
    assert extract_star_field(None) is None
    assert extract_star_field(np.zeros((4, 4, 3), dtype=np.float32)) is None
    # A starless frame has nothing to extract.
    assert extract_star_field(np.zeros((64, 64), dtype=np.float32)) is None


# --- the frame size and the noise the threshold is derived from ------------
#
# Every fixture above is 240x160 or 480x320. A real Seestar sub is 1920x1080, and
# the two tests below are the ones that shape can carry and this module's cannot.

def test_the_prepared_frame_keeps_the_sky_noise_its_threshold_is_derived_from(tmp_path):
    """FAIL-BEFORE: ``registration_gray`` used to clip the sky noise's negative half.

    Every star extractor sets its detection threshold from a noise estimate, and a
    frame whose negatives have been clipped to exactly 0.0 has half its pixels
    parked on one value — a spike a sigma-clipped estimator converges onto, so the
    estimate collapses and the threshold lands *inside* the noise. This asserts the
    property that stops happening, on the production function, at a real sub's size:
    the negative half of the sky noise is still there, and the noise ``sep``
    measures agrees with a robust estimate of the frame's own.
    """
    sep = pytest.importorskip("sep")
    path = write_seestar_fits(
        tmp_path / "real.fit", width=REAL_W, height=REAL_H,
        data=make_rotated_star_field(width=REAL_W, height=REAL_H,
                                     n_stars=REAL_N_STARS, seed=SEED,
                                     rotation_deg=0.0, noise_seed=1),
    )
    flat = registration_gray(str(path))
    assert flat is not None
    # The sky noise straddles zero, roughly half either side. Before: 0.0.
    below = float((flat < 0.0).mean())
    assert 0.25 < below < 0.75, below
    # And sep's own global RMS agrees with a robust sigma of the same pixels
    # (MAD-scaled, so the stars don't inflate it). Before: 0.0022 against ~21.
    mad = float(np.median(np.abs(flat - np.median(flat))))
    robust_sigma = 1.4826 * mad
    rms = float(sep.Background(np.ascontiguousarray(flat, dtype=np.float32)).globalrms)
    assert 0.5 < rms / robust_sigma < 2.0, (rms, robust_sigma)
    # The fixture's own claim: it has more pixels than sep's buffer has slots, so
    # it *can* exhibit the refusal. The small fixtures above cannot.
    assert flat.size > SEP_EXTRACT_PIXSTACK_DEFAULT


@pytest.mark.parametrize("rotation_deg", [4.0, -13.0])
def test_a_real_sized_night_is_placed_by_its_stars(tmp_path, rotation_deg):
    """FAIL-BEFORE at this size only: on a 1920x1080 sub the matcher placed nothing.

    The bootstrap rescue prefers a star transform and falls back to a phase
    correlation shift, so a matcher that silently never matches did not read as
    broken — it read as the *old* behaviour, which is the confident mis-placement of
    a rotated night v0.481.0 exists to prevent. Checked against sky truth, not
    against the matcher's opinion of itself, exactly like its 240x160 sibling.
    """
    def gray(rot: float, *, shift, noise_seed: int) -> np.ndarray:
        path = write_seestar_fits(
            tmp_path / f"s{noise_seed}.fit", width=REAL_W, height=REAL_H,
            data=make_rotated_star_field(width=REAL_W, height=REAL_H,
                                         n_stars=REAL_N_STARS, seed=SEED,
                                         rotation_deg=rot, shift=shift,
                                         noise_seed=noise_seed),
        )
        out = registration_gray(str(path))
        assert out is not None
        return out

    ref = gray(0.0, shift=(0.0, 0.0), noise_seed=1)
    mov = gray(rotation_deg, shift=DITHER, noise_seed=2)
    transforms = star_match_members([ref, mov], 0)
    assert transforms[1] is not None, "a real-sized sub was not placed by its stars"
    # The transform maps the moving sub onto the reference, so it *undoes* the
    # field's rotation — the same sign convention the ladder above asserts.
    assert transforms[1].rotation_deg == pytest.approx(-rotation_deg, abs=0.25)
    text = propagate_wcs(
        _ref_wcs_text(width=REAL_W, height=REAL_H),
        register_members([ref, mov], 0), 0,
        transforms=transforms, shapes=[(REAL_H, REAL_W), (REAL_H, REAL_W)],
    )[1]
    assert text is not None
    errs = _placement_errors_arcsec(
        text, rotation_deg, width=REAL_W, height=REAL_H, n_stars=REAL_N_STARS)
    assert float(np.median(errs)) < PIXSCALE, float(np.median(errs))
    assert float(errs.max()) < 2.0 * PIXSCALE, float(errs.max())


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
            fwhm_px=4.0, rotation_deg=ANCHOR_ROTATION_DEG,
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


# --- the image the rescue asks a solver to solve ---------------------------

def _deep_star_peak_snr(deep: np.ndarray) -> float:
    """Median star peak over the sky noise, at the *reference*'s own star positions.

    Ground truth from the fixture's catalogue, not from a detector's opinion: a
    star integrated on the wrong registration does not vanish, it spreads into an
    arc, and the honest measure of that is how far its peak has fallen into the
    noise at the place the reference says the star is.
    """
    sky = float(np.std(deep[deep < np.percentile(deep, 80)]))
    peaks = []
    for cat_xy, _ in rotated_star_positions(
        width=W, height=H, n_stars=N_STARS, seed=SEED,
        rotation_deg=0.0, shift=(0.0, 0.0),
    ):
        x, y = int(round(cat_xy[0])), int(round(cat_xy[1]))
        if 4 <= x < W - 4 and 4 <= y < H - 4:
            peaks.append(float(deep[y - 3:y + 4, x - 3:x + 4].max()))
    assert peaks
    return float(np.median(peaks)) / sky


def _deep_pair(rotations):
    """``(shift_integrated, warp_integrated, star_matched)`` for one night."""
    ref = _gray(0.0, shift=(0.0, 0.0), noise_seed=1)
    grays = [ref] + [_gray(r, noise_seed=10 + i) for i, r in enumerate(rotations)]
    shifts = register_members(grays, 0)
    transforms = star_match_members(grays, 0)
    return (
        integrate_deep_image(grays, shifts, 0),
        integrate_deep_image(grays, shifts, 0, transforms=transforms),
        sum(1 for t in transforms if t is not None),
    )


def test_a_rotated_night_smears_the_deep_image_the_rescue_solves():
    """FAIL-BEFORE + AND-PASSES-AFTER, in one measurement, in numbers.

    The deep image exists for one reason: to clear a plate solver's detection
    floor on a field none of whose subs solved alone. Integer-shifting a member
    the night has turned lays its stars down as arcs across the reference's, so
    the image built to be *more* detectable is less so. Ground truth is the
    fixture's own catalogue; the still night is the control, so the assertion is
    a ratio rather than a bare number and does not move with the fixture's flux.
    """
    still_shift, still_warp, still_matched = _deep_pair([0.0] * 8)
    turn_shift, turn_warp, turn_matched = _deep_pair(ROTATIONS)
    assert still_matched == 8 and turn_matched == 8

    still = _deep_star_peak_snr(still_shift)
    # A still night is a rotation of zero: warping it changes nothing that matters.
    assert _deep_star_peak_snr(still_warp) > 0.7 * still

    # FAIL-BEFORE: shifted, a turning night loses most of its star peaks.
    assert _deep_star_peak_snr(turn_shift) < 0.3 * still, _deep_star_peak_snr(turn_shift)
    # AFTER: warped by the same matches that already place these subs, the deep
    # image of a turning night is as deep as a still one's.
    assert _deep_star_peak_snr(turn_warp) > 0.7 * still, _deep_star_peak_snr(turn_warp)


# --- the rotation the row is stamped with ----------------------------------

def test_a_star_matched_member_is_stamped_with_its_own_rotation(tmp_path):
    """FAIL-BEFORE: every rescued member used to inherit the reference's rotation.

    The member's *placement* has been right since star matching shipped — its
    ``wcs_json`` carries the composed, rotated CD — but the ``rotation_deg``
    column beside it still said the reference's number, which a member the night
    has turned knowably is not. Ground truth here is the fixture's own rotation
    ladder, not the matcher's opinion of itself: a member built at
    ``rotation_deg=r`` shows a sky turned by ``r`` against the reference, so its
    position angle must differ from the anchor's by exactly that, in that
    direction. Reverting the fix leaves every delta at 0.0 and every rung red.
    """
    proj, truth = _rotated_project(tmp_path, ROTATIONS)
    try:
        res = bootstrap_solve(proj, min_frames=4)
        assert res.engaged and res.anchored_on_solved_sub
        seen = 0
        for f in proj.iter_frames():
            if f.id not in truth or not f.wcs_json or f.rotation_deg is None:
                continue
            delta = f.rotation_deg - ANCHOR_ROTATION_DEG
            # The sign is pinned, not just the size: the pixel transform's own
            # ``rotation_deg`` runs the *other* way, so "ref ± θ" had a 50 %
            # chance of being worse than the approximation it replaced.
            assert delta == pytest.approx(truth[f.id], abs=0.25), (
                truth[f.id], f.rotation_deg)
            seen += 1
        assert seen >= 6
    finally:
        proj.close()


def test_a_shift_placed_member_keeps_the_references_rotation(tmp_path):
    """The other half: a member a translation placed shares the reference's CD.

    Nothing about that case may move — the rescue's ordinary, un-rotated burst is
    the one the owner's dithered nights actually take — so the stamped value is
    the anchor's own number exactly, not a re-derivation of it that lands a
    rounding away.
    """
    proj, truth = _rotated_project(tmp_path, [0.0] * 8)
    try:
        res = bootstrap_solve(proj, min_frames=4, star_match=False)
        assert res.engaged and res.n_star_matched == 0
        stamped = [f.rotation_deg for f in proj.iter_frames() if f.id in truth]
        assert stamped and all(v == ANCHOR_ROTATION_DEG for v in stamped), stamped
    finally:
        proj.close()


def test_member_rotation_deg_declines_rather_than_guessing():
    """No reference rotation, or a header it cannot read, is never invented."""
    from seestack.solve.bootstrap import member_rotation_deg

    ref = _ref_wcs_text()
    # Nothing to offset from — a solve that reported no rotation stays silent.
    assert member_rotation_deg(None, ref, ref) is None
    # An unreadable member header falls back to the honest approximation.
    assert member_rotation_deg(12.5, ref, "not a header") == 12.5
    assert member_rotation_deg(12.5, "not a header", ref) == 12.5
    # The reference against itself is a rotation of zero, exactly.
    assert member_rotation_deg(12.5, ref, ref) == pytest.approx(12.5, abs=1e-9)


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
