"""The "try it with a sample image" onboarding demo target.

Proves the generated sample is a *real, stackable* target (so a newcomer walks
the genuine journey on it), that loading is idempotent, and that removing it
sweeps up its files and touches nothing else.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from seestack.io.library import Library
from seestack.stack.stacker import StackOptions, run_stack
from webapp import sample_data


@pytest.fixture
def lib(tmp_path: Path):
    library = Library.open_or_create(tmp_path / "library")
    try:
        yield library
    finally:
        library.close()


def test_status_is_not_loaded_on_a_fresh_library(lib):
    status = sample_data.get_sample_status(lib)
    assert status.loaded is False
    assert status.safe is None
    assert status.n_frames == 0


def test_load_builds_a_valid_solved_target(lib):
    status = sample_data.load_sample(lib)
    assert status.loaded is True
    assert status.safe is not None
    assert status.n_frames == sample_data._N_SUBS

    # It shows up as an ordinary target and every frame is accepted + solved,
    # so QC/stack/edit run on it unmodified.
    entry = lib.find_target(sample_data.SAMPLE_TARGET_NAME)
    assert entry is not None
    proj = lib.open_target(entry.safe_name)
    try:
        frames = list(proj.iter_frames())
        assert len(frames) == sample_data._N_SUBS
        assert all(f.accept for f in frames)
        assert all(f.wcs_json for f in frames)
    finally:
        proj.close()


def test_load_publishes_the_sample_frames_to_the_library_row(lib):
    """The demo's subs must be visible to every *library-level* surface, not only
    inside its own project DB.

    ``load_sample`` ingested and QC'd six frames but never refreshed the library
    entry, so the Library card read "0/0 frames" with no integration, the
    Dashboard's Frames/Integration tiles stayed at zero, and the Tonight planner
    ranked the demo as "you haven't captured any of it yet" — on the very screen
    a newcomer sees right after asking for a sample."""
    status = sample_data.load_sample(lib)
    entry = lib.find_target(status.safe)
    assert entry.n_frames == sample_data._N_SUBS
    assert entry.n_frames_accepted == sample_data._N_SUBS
    assert entry.total_exposure_s > 0.0
    # The same row the Library list renders from, not just a direct lookup.
    listed = next(e for e in lib.list_targets() if e.safe_name == status.safe)
    assert listed.n_frames == sample_data._N_SUBS


def test_sample_actually_stacks_and_reduces_noise(lib):
    """The demo is only worth offering if it stacks cleanly — combining the
    dithered subs must average the sky noise down (~√N), the whole point of
    stacking a beginner sees on their own data."""
    sample_data.load_sample(lib)
    entry = lib.find_target(sample_data.SAMPLE_TARGET_NAME)
    proj = lib.open_target(entry.safe_name)
    try:
        result = run_stack(
            proj, StackOptions(sigma_clip=False, max_workers=1, output_name="sample")
        )
        assert result.n_frames_used == sample_data._N_SUBS
        assert result.n_align_failed == 0

        from astropy.io import fits

        stacked = fits.getdata(result.fits_path).astype(np.float32)
        # Background-noise standard deviation on the stacked image should sit well
        # below a single sub's (~50 ADU sky sigma in the raw mosaic). We don't need
        # a tight √N figure — just clear evidence the stack combined real frames.
        finite = stacked[np.isfinite(stacked)]
        # A robust spread (MAD-based sigma) over the darker half (sky, not stars).
        median = float(np.median(finite))
        sky = finite[finite <= median]
        sky_sigma = 1.4826 * float(np.median(np.abs(sky - np.median(sky))))
        assert sky_sigma < 40.0
    finally:
        proj.close()


def test_load_is_idempotent(lib):
    first = sample_data.load_sample(lib)
    second = sample_data.load_sample(lib)
    assert second.loaded is True
    assert second.safe == first.safe
    # No duplicate target and no duplicated frames.
    assert sum(1 for e in lib.list_targets()
               if e.name == sample_data.SAMPLE_TARGET_NAME) == 1
    assert second.n_frames == first.n_frames


def test_remove_deletes_only_the_sample_and_its_files(lib, tmp_path):
    # A real (non-sample) target alongside the sample.
    real_entry, real_proj = lib.create_target("My Real Target")
    real_proj.close()

    status = sample_data.load_sample(lib)
    sample_dir = lib.targets_dir / status.safe
    assert sample_dir.exists()

    removed = sample_data.remove_sample(lib)
    assert removed is True

    # Sample gone, its on-disk folder swept up, real target untouched.
    assert sample_data.get_sample_status(lib).loaded is False
    assert not sample_dir.exists()
    assert lib.find_target(real_entry.safe_name) is not None


def test_remove_on_a_fresh_library_is_a_no_op(lib):
    assert sample_data.remove_sample(lib) is False


def test_api_status_load_remove(client):
    # Fresh: not loaded.
    r = client.get("/api/sample")
    assert r.status_code == 200
    assert r.json()["loaded"] is False

    # Load: creates it.
    r = client.post("/api/sample")
    assert r.status_code == 201
    body = r.json()
    assert body["loaded"] is True
    assert body["n_frames"] == sample_data._N_SUBS
    safe = body["safe"]

    # It's a normal target now.
    assert client.get(f"/api/targets/{safe}").status_code == 200

    # Status reflects it.
    assert client.get("/api/sample").json()["loaded"] is True

    # Remove: gone.
    r = client.delete("/api/sample")
    assert r.status_code == 200
    assert r.json()["loaded"] is False
    assert client.get(f"/api/targets/{safe}").status_code == 404


# --- the 2×2 mosaic sample --------------------------------------------------
#
# The single-field sample above has no uncovered pixel and one coverage plateau,
# so every surface gated on NaN "no coverage" — the union canvas, coverage
# levelling, per-panel photometry, the uncovered-fraction note, the depth map,
# Auto's border trim — is structurally invisible on it. That is how D1 (Auto
# cropping a mosaic to its overlap band) survived twenty clean sweeps: every
# sweep ran this sample. These pin the second, opt-in demo that can show it.


def test_mosaic_sample_is_a_real_four_panel_mosaic(lib):
    status = sample_data.load_sample(lib, shape="mosaic")
    assert status.loaded is True
    assert status.n_frames == sum(sample_data._MOSAIC_PANEL_SUBS)

    entry = lib.find_target(sample_data.SAMPLE_MOSAIC_TARGET_NAME)
    assert entry is not None
    proj = lib.open_target(entry.safe_name)
    try:
        frames = sorted(proj.iter_frames(), key=lambda f: f.source_path)
        assert all(f.accept for f in frames)
        assert all(f.wcs_json for f in frames)

        # Each sub records *its own panel's* centre, not the mosaic's — every
        # per-panel decision in the engine (QC grading, photometric
        # normalisation, quality weighting) clusters on exactly this pair, so a
        # sample whose subs all shared one centre would exercise none of it.
        from seestack.stack.pointings import pointing_groups

        labels = pointing_groups(
            [(f.ra_center_deg, f.dec_center_deg) for f in frames], min_members=3)
        assert labels is not None
        assert len(set(labels)) == len(sample_data._MOSAIC_PANEL_SUBS)
        # …and the panels are deliberately uneven: one was clouded out early.
        sizes = sorted(labels.count(lab) for lab in set(labels))
        assert sizes == sorted(sample_data._MOSAIC_PANEL_SUBS)
    finally:
        proj.close()


def test_mosaic_sample_stacks_onto_a_ragged_multi_level_canvas(lib):
    """The property the whole sample exists for: a canvas with **uncovered**
    pixels and more than one coverage plateau.

    Fails on the single-field sample by construction — its canvas is one fully
    covered plateau, which is why a mosaic bug can hide from every pass over it.
    """
    from seestack.edit.coverage_trim import coverage_is_mosaic

    sample_data.load_sample(lib, shape="mosaic")
    entry = lib.find_target(sample_data.SAMPLE_MOSAIC_TARGET_NAME)
    proj = lib.open_target(entry.safe_name)
    try:
        result = run_stack(
            proj, StackOptions(sigma_clip=False, max_workers=1, output_name="mosaic")
        )
        assert result.n_frames_used == sum(sample_data._MOSAIC_PANEL_SUBS)
        assert result.n_align_failed == 0

        from astropy.io import fits

        stacked = fits.getdata(result.fits_path).astype(np.float32)
        # The union canvas is bigger than one frame in both axes…
        assert stacked.shape[-1] > sample_data._WIDTH
        assert stacked.shape[-2] > sample_data._HEIGHT
        # …and its ragged corners really are NaN, not zeros.
        uncovered = float(np.mean(~np.isfinite(stacked)))
        assert 0.005 < uncovered < 0.25

        cov = fits.getdata(
            Path(result.fits_path).parent / f"{Path(result.fits_path).stem}_framecov.fits"
        ).astype(np.float32)
        assert coverage_is_mosaic(cov) is True
    finally:
        proj.close()


def test_mosaic_panels_look_at_one_shared_sky_in_their_overlaps(lib):
    """Neighbouring panels must hold the *same stars* where they overlap.

    Without this the overlap is two unrelated star fields, and nothing that
    measures a mosaic's seams — the union canvas, per-panel photometry, or the
    open "match each panel's gain from the overlaps" item — is being exercised
    at all. Rendered directly (no stack) so the check is about the sample.
    """
    panels, window = sample_data._mosaic_layout()
    stars = sample_data._star_catalog(
        seed=42, width=window[0], height=window[1],
        n_stars=sample_data._MOSAIC_N_STARS,
    )
    left, right = panels[0], panels[1]
    a = sample_data._render_star_field(
        stars, noise_seed=1, star_shift=(0.0, 0.0), origin=left.origin)
    b = sample_data._render_star_field(
        stars, noise_seed=2, star_shift=(0.0, 0.0), origin=right.origin)

    # The sky rectangle both panels see, expressed in each one's own pixels.
    x0 = max(left.origin[0], right.origin[0])
    x1 = min(left.origin[0] + sample_data._WIDTH, right.origin[0] + sample_data._WIDTH)
    y0 = max(left.origin[1], right.origin[1])
    y1 = min(left.origin[1] + sample_data._HEIGHT, right.origin[1] + sample_data._HEIGHT)
    assert x1 - x0 > 30 and y1 - y0 > 30, "the panels must actually overlap"

    pa = a[y0 - left.origin[1]: y1 - left.origin[1],
           x0 - left.origin[0]: x1 - left.origin[0]].astype(np.float64)
    pb = b[y0 - right.origin[1]: y1 - right.origin[1],
           x0 - right.origin[0]: x1 - right.origin[0]].astype(np.float64)
    assert pa.shape == pb.shape
    # The right panel is the hazy one (dimmer stars, brighter sky), so compare
    # the *pattern*: a correlation this high can only come from the same stars.
    corr = float(np.corrcoef(pa.ravel() - pa.mean(), pb.ravel() - pb.mean())[0, 1])
    assert corr > 0.9


def test_the_mosaic_has_a_wholly_hazy_panel_to_level(lib):
    """One panel was shot through haze — dimmer signal on a brighter sky.

    A mosaic whose panels are all equally deep and equally clear reads as
    "nothing to level", and every per-panel surface stays quiet on it.
    """
    panels, window = sample_data._mosaic_layout()
    stars = sample_data._star_catalog(
        seed=42, width=window[0], height=window[1],
        n_stars=sample_data._MOSAIC_N_STARS,
    )
    hazy = panels[sample_data._MOSAIC_HAZY_PANEL]
    clear = panels[0]
    assert hazy.signal_scale < 1.0 and hazy.sky_scale > 1.0

    a = sample_data._render_star_field(
        stars, noise_seed=1, star_shift=(0.0, 0.0), origin=clear.origin)
    b = sample_data._render_star_field(
        stars, noise_seed=1, star_shift=(0.0, 0.0), origin=hazy.origin,
        signal_scale=hazy.signal_scale, sky_scale=hazy.sky_scale)
    assert float(np.median(b)) > float(np.median(a))


def test_the_two_samples_are_separate_targets_and_both_are_removed(lib):
    field = sample_data.load_sample(lib)
    mosaic = sample_data.load_sample(lib, shape="mosaic")
    assert field.safe != mosaic.safe
    # Loading the mosaic leaves the single field exactly as it was — every page
    # height and editor baseline ever measured was measured on that one.
    assert sample_data.get_sample_status(lib).n_frames == sample_data._N_SUBS
    assert sample_data.load_sample(lib, shape="mosaic").safe == mosaic.safe

    field_dir = lib.targets_dir / field.safe
    mosaic_dir = lib.targets_dir / mosaic.safe
    assert field_dir.exists() and mosaic_dir.exists()

    assert sample_data.remove_sample(lib) is True
    assert sample_data.get_sample_status(lib).loaded is False
    assert sample_data.get_sample_status(lib, shape="mosaic").loaded is False
    assert not field_dir.exists()
    assert not mosaic_dir.exists()


def test_api_loads_the_field_sample_by_default_and_the_mosaic_on_request(client):
    # No body → the single field, byte-for-byte what the Dashboard button does.
    body = client.post("/api/sample").json()
    assert body["loaded"] is True
    assert body["n_frames"] == sample_data._N_SUBS
    assert body["mosaic_loaded"] is False

    body = client.post("/api/sample", json={"shape": "mosaic"}).json()
    assert body["loaded"] is True, "the field sample is untouched"
    assert body["mosaic_loaded"] is True
    assert body["mosaic_n_frames"] == sum(sample_data._MOSAIC_PANEL_SUBS)
    mosaic_safe = body["mosaic_safe"]
    assert client.get(f"/api/targets/{mosaic_safe}").status_code == 200

    # Status reports both; one DELETE removes both.
    status = client.get("/api/sample").json()
    assert status["loaded"] is True and status["mosaic_loaded"] is True
    gone = client.delete("/api/sample").json()
    assert gone["loaded"] is False and gone["mosaic_loaded"] is False
    assert client.get(f"/api/targets/{mosaic_safe}").status_code == 404


# --- the full-size mosaic sample -------------------------------------------
#
# Both samples above fit *inside* the editor's preview proxy: `edit/proxy.py`
# strides only above `PROXY_MAX_PX` (1500), the field sample is 480 px wide and
# the mosaic's union canvas ~907 px, so `get_proxy` hands each back at
# `proxy_scale == 1.0`. Everything the editor gates on a decimated proxy is
# therefore unreachable on them — the five preview↔export advisories, the
# preview-scale caption, and the whole of "Check it at full size" (its button,
# modal, navigator, `X-Loupe-Window` marker and split comparison). The owner's
# own mosaics are ~3494×2470, i.e. that is his ordinary state. These pin the
# third demo, which is the same 2×2 mosaic shot at full-size panels.


def test_the_big_sample_is_the_only_one_the_editor_proxy_decimates(lib):
    """The property the full-size demo exists for: `proxy_scale > 1`.

    Fails on both other samples by construction — their canvases are under the
    1500 px cap — which is why the editor's whole decimated-proxy surface could
    never be reached by a pass over them.
    """
    from seestack.edit.coverage_trim import coverage_is_mosaic
    from seestack.edit.proxy import PROXY_MAX_PX, build_proxy

    # The two existing samples' canvases are below the cap, said in the same
    # currency the proxy uses, so this test states *why* a third one was needed
    # rather than only asserting the third one's own number.
    for cfg in (sample_data._MOSAIC_SMALL,):
        _panels, window = sample_data._mosaic_layout(cfg)
        assert max(window) <= PROXY_MAX_PX
    assert max(sample_data._WIDTH, sample_data._HEIGHT) <= PROXY_MAX_PX

    status = sample_data.load_sample(lib, shape="big")
    assert status.loaded is True
    assert status.n_frames == sum(sample_data._MOSAIC_PANEL_SUBS)

    entry = lib.find_target(sample_data.SAMPLE_BIG_TARGET_NAME)
    assert entry is not None
    proj = lib.open_target(entry.safe_name)
    try:
        result = run_stack(
            proj, StackOptions(sigma_clip=False, max_workers=1, output_name="big")
        )
        assert result.n_frames_used == sum(sample_data._MOSAIC_PANEL_SUBS)
        assert result.n_align_failed == 0

        from astropy.io import fits

        stacked = fits.getdata(result.fits_path).astype(np.float32)
        # Past the cap on its long side — the one thing the other two are not.
        assert stacked.shape[-1] > PROXY_MAX_PX

        _proxy, scale = build_proxy(result.fits_path)
        # Exactly 2: the gentlest decimation there is, chosen deliberately so
        # the sample is the *smallest* canvas that reaches this surface at all.
        assert scale == 2.0

        # …and it is still the same ragged, multi-level mosaic — a bigger
        # picture of the same thing, not a tidier one. Uncovered corners are
        # NaN (not zeros), so the coverage-gated surfaces still speak too.
        uncovered = float(np.mean(~np.isfinite(stacked)))
        assert 0.005 < uncovered < 0.25

        cov = fits.getdata(
            Path(result.fits_path).parent / f"{Path(result.fits_path).stem}_framecov.fits"
        ).astype(np.float32)
        assert coverage_is_mosaic(cov) is True
    finally:
        proj.close()


def test_the_big_sample_points_its_panels_the_way_the_small_one_does(lib):
    """Four panels, uneven depth — the scale is the only thing that differs."""
    from seestack.stack.pointings import pointing_groups

    sample_data.load_sample(lib, shape="big")
    entry = lib.find_target(sample_data.SAMPLE_BIG_TARGET_NAME)
    proj = lib.open_target(entry.safe_name)
    try:
        frames = sorted(proj.iter_frames(), key=lambda f: f.source_path)
        assert all(f.accept for f in frames)
        assert all(f.wcs_json for f in frames)
        # The frames record the full-size sensor, not the small one's.
        assert {(f.width_px, f.height_px) for f in frames} == {
            (sample_data._BIG_FRAME_W, sample_data._BIG_FRAME_H)
        }

        labels = pointing_groups(
            [(f.ra_center_deg, f.dec_center_deg) for f in frames], min_members=3)
        assert labels is not None
        assert len(set(labels)) == len(sample_data._MOSAIC_PANEL_SUBS)
        sizes = sorted(labels.count(lab) for lab in set(labels))
        assert sizes == sorted(sample_data._MOSAIC_PANEL_SUBS)
    finally:
        proj.close()


def test_the_three_samples_are_separate_targets_and_all_are_removed(lib):
    field = sample_data.load_sample(lib)
    mosaic = sample_data.load_sample(lib, shape="mosaic")
    big = sample_data.load_sample(lib, shape="big")
    assert len({field.safe, mosaic.safe, big.safe}) == 3

    dirs = [lib.targets_dir / s.safe for s in (field, mosaic, big)]
    assert all(d.exists() for d in dirs)

    assert sample_data.remove_sample(lib) is True
    for shape in ("field", "mosaic", "big"):
        assert sample_data.get_sample_status(lib, shape=shape).loaded is False
    assert not any(d.exists() for d in dirs)


def test_the_existing_two_samples_generate_byte_identical_pixels():
    """A pin, not a check: the field sample's page-height baselines and the
    mosaic's trim/coverage numbers were all measured on these exact pixels.

    The frame size became a parameter when the full-size demo was added, so
    anything that reaches for it by accident — a default changed, a constant
    threaded one call too far — moves data every recorded measurement rests on.
    A digest is the cheapest thing that notices.
    """
    import hashlib

    h = hashlib.sha256()
    for i, shift in enumerate(sample_data._dither_offsets(sample_data._N_SUBS)):
        h.update(sample_data._make_star_field(
            seed=42, noise_seed=100 + i, star_shift=shift).tobytes())
    assert h.hexdigest() == (
        "9542995fa105c120d7ebb23fbc772d77d62ff72d84ac3d55f2806eeba9263ccf"
    ), "the single-field sample's generated subs moved"

    cfg = sample_data._MOSAIC_SMALL
    panels, window = sample_data._mosaic_layout(cfg)
    assert window == (900, 610)
    stars = sample_data._star_catalog(
        seed=42, width=window[0], height=window[1], n_stars=cfg.n_stars)
    h = hashlib.sha256()
    for panel in panels:
        for sub, shift in enumerate(sample_data._dither_offsets(panel.n_subs)):
            h.update(sample_data._render_star_field(
                stars, noise_seed=cfg.noise_base + panel.index * 20 + sub,
                star_shift=shift, origin=panel.origin,
                signal_scale=panel.signal_scale, sky_scale=panel.sky_scale,
                frame=cfg.frame).tobytes())
    assert h.hexdigest() == (
        "00f0faae83d03fe5ee8b2f33e07937e1f55a6bddf36b981c7f5a76a64a38b24f"
    ), "the 2×2 mosaic sample's generated subs moved"


def test_api_loads_the_big_sample_on_request(client):
    body = client.post("/api/sample", json={"shape": "big"}).json()
    # The other two are untouched — this is a third target, not a replacement.
    assert body["loaded"] is False
    assert body["mosaic_loaded"] is False
    assert body["big_loaded"] is True
    assert body["big_n_frames"] == sum(sample_data._MOSAIC_PANEL_SUBS)
    big_safe = body["big_safe"]
    assert client.get(f"/api/targets/{big_safe}").status_code == 200

    status = client.get("/api/sample").json()
    assert status["big_loaded"] is True and status["big_safe"] == big_safe
    gone = client.delete("/api/sample").json()
    assert gone["big_loaded"] is False and gone["big_safe"] is None
    assert client.get(f"/api/targets/{big_safe}").status_code == 404


# ---- generated calibration frames (dogfood tooling) ------------------------
#
# Nothing in the running app calls these; `scripts/agent-dogfood.sh
# --calibration` does, to put a scratch install into the one state no pass had
# ever been in. What the flag is worth depends entirely on the master being a
# *matching* one, so that is what is pinned here rather than the pixels.


def test_the_generated_darks_match_the_sample_lights_acquisition(
    tmp_path: Path,
) -> None:
    """A master whose exposure/gain/temperature/sensor differ from the lights is
    refused by the registry, which would leave the pass in the very empty state
    it is trying to escape — silently, and looking exactly like a clean run."""
    from astropy.io import fits

    from webapp.sample_data import _write_sample_fits

    sample_data.write_sample_calibration_frames(tmp_path / "darks", "dark")
    _write_sample_fits(tmp_path / "light.fit", index=0, star_shift=(0.0, 0.0))

    light = fits.getheader(tmp_path / "light.fit")
    dark = fits.getheader(tmp_path / "darks" / "dark_000.fit")
    for key in ("EXPTIME", "GAIN", "CCD-TEMP", "BAYERPAT"):
        assert dark[key] == light[key], key
    assert (dark["NAXIS1"], dark["NAXIS2"]) == (light["NAXIS1"], light["NAXIS2"])


def test_every_generated_frame_declares_its_kind(tmp_path: Path) -> None:
    """``discover`` classifies from ``IMAGETYP`` and from nothing else, so a
    writer that forgot the card would produce folders the app cannot see."""
    from seestack.calibrate import discover

    for kind in ("dark", "flat", "bias"):
        n = sample_data.write_sample_calibration_frames(tmp_path / kind, kind)
        assert n == 6
        found = discover.classify_folder(tmp_path / kind)
        assert found is not None, kind
        assert found[0] == kind


def test_the_darks_hot_pixels_are_a_fixed_pattern(tmp_path: Path) -> None:
    """Hot pixels that moved between frames would be erased by the median
    combine, and the defect census — the surface they exist to reach — would
    find a perfectly clean camera."""
    import numpy as np
    from astropy.io import fits

    sample_data.write_sample_calibration_frames(tmp_path / "darks", "dark")
    a = fits.getdata(tmp_path / "darks" / "dark_000.fit").astype(float)
    b = fits.getdata(tmp_path / "darks" / "dark_005.fit").astype(float)

    hot_a = set(map(tuple, np.argwhere(a > 5000)))
    hot_b = set(map(tuple, np.argwhere(b > 5000)))
    assert hot_a and hot_a == hot_b
    # …and they are a handful of pixels, not a corrupted frame.
    assert len(hot_a) < a.size // 100


def test_an_unknown_kind_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dark/flat/bias"):
        sample_data.write_sample_calibration_frames(tmp_path / "x", "light")
