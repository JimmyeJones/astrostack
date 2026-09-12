"""The "Moon for scale" disc on the shared picture.

The scale bar already tells a beginner "the whole frame is about 2.5 full Moons
wide". This is the same fact drawn instead of written — a faint circle at the
Moon's true angular size — and the thing worth pinning is that it is measured
off the *same* bar, self-hides on a field it would swamp, and is off unless
asked for.

**The fixture is the point here.** The 64 px synthetic in
``test_stack_render.py`` has a 3.6″/px WCS, so the full Moon is ~8× its frame
width and the disc would self-hide on every one of these tests — a green suite
that never once drew the thing it claims to test (AGENTS.md §8: a regression
test whose fixture cannot show the behaviour is green for the wrong reason). So
this file builds its own run at the owner's scale: a field about four Moons
across, where the disc lands at a quarter of the picture, as it does on an S30.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from seestack.scalebar import MOON_DIAMETER_ARCSEC

#: Wide enough that the disc is a comfortable quarter of the picture, the way it
#: is on the owner's S30 (150 mm, 2.1° field).
_MOONS_ACROSS = 4.0
_SIZE = 256


def _make_run(data_root, safe: str, *, moons_across: float = _MOONS_ACROSS,
              size: int = _SIZE) -> str:
    """A run whose master FITS carries a celestial WCS spanning ``moons_across``
    full Moons, so the Moon disc is a real, drawable fraction of the picture."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        yy, xx = np.mgrid[0:size, 0:size]
        c = size / 2
        blob = np.exp(-(((xx - c) ** 2 + (yy - c) ** 2) / (size * 2.0)))
        sky = 0.02 + 0.005 * np.random.default_rng(0).standard_normal((size, size))
        cube = np.stack([sky + blob, sky + 0.6 * blob,
                         sky + 0.3 * blob]).astype(np.float32)
        fits_path = tdir / "master.fits"
        hdu = fits.PrimaryHDU(data=cube)
        cdelt = (moons_across * MOON_DIAMETER_ARCSEC / size) / 3600.0
        hdu.header["CTYPE1"] = "RA---TAN"
        hdu.header["CTYPE2"] = "DEC--TAN"
        hdu.header["CRPIX1"] = size / 2 + 0.5
        hdu.header["CRPIX2"] = size / 2 + 0.5
        hdu.header["CRVAL1"] = 10.0
        hdu.header["CRVAL2"] = 20.0
        hdu.header["CD1_1"] = -cdelt
        hdu.header["CD1_2"] = 0.0
        hdu.header["CD2_1"] = 0.0
        hdu.header["CD2_2"] = cdelt
        hdu.writeto(fits_path, overwrite=True)
        preview_path = tdir / "master_preview.png"
        preview_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # overwritten by the save below

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=size, canvas_w=size, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return str(run_id)
    finally:
        lib.close()


def _run(client, solved_library, **kw) -> tuple[str, str]:
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _make_run(solved_library, safe, **kw)
    assert client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                       json={"stretch": 0.5, "black": 0.35}).status_code == 200
    return safe, run_id


def test_the_fixture_really_can_show_a_disc(client, solved_library):
    """Guard the guard: if this run's scale ever stopped putting the Moon inside
    the drawable range, every test below would pass by drawing nothing."""
    safe, run_id = _run(client, solved_library)
    ann = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    bar = ann["scale_bar"]
    assert bar is not None, "the fixture lost its WCS"
    moon_fraction = bar["fraction"] * MOON_DIAMETER_ARCSEC / bar["arcsec"]
    assert abs(moon_fraction - 1.0 / _MOONS_ACROSS) < 1e-6
    # Comfortably inside the "still a mark" ceiling the drawing applies.
    from seestack.skymarks import MOON_DISC_MAX_SHORT_FRACTION
    assert moon_fraction < MOON_DISC_MAX_SHORT_FRACTION


def test_moon_adds_the_disc_to_the_marked_picture(client, solved_library):
    safe, run_id = _run(client, solved_library)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/jpeg"
    marked = client.get(f"{url}?scale=true")
    with_moon = client.get(f"{url}?scale=true&moon=true")
    assert marked.status_code == with_moon.status_code == 200
    assert with_moon.headers["content-type"] == "image/jpeg"
    assert with_moon.content != marked.content
    # Marks go *on* the picture, never around it — the canvas is untouched.
    with Image.open(BytesIO(marked.content)) as a, \
            Image.open(BytesIO(with_moon.content)) as b:
        assert a.size == b.size
    # Its own filename, so saving both can't have one overwrite the other.
    assert "_scale_moon.jpg" in with_moon.headers["content-disposition"]
    assert "_scale.jpg" in marked.headers["content-disposition"]


def test_the_disc_is_the_moons_true_size_on_the_shared_pixels(client, solved_library):
    """The one number that has to be right: the circle is as wide as the Moon
    would look in this field. Measured on the served picture, against the scale
    bar the same endpoint reports — so the file and the app's own claim about it
    are compared, not the code against itself."""
    safe, run_id = _run(client, solved_library)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/jpeg"
    marked = client.get(f"{url}?scale=true")
    with_moon = client.get(f"{url}?scale=true&moon=true")

    with Image.open(BytesIO(marked.content)) as a, \
            Image.open(BytesIO(with_moon.content)) as b:
        before = np.asarray(a.convert("RGB"), dtype=np.int16)
        after = np.asarray(b.convert("RGB"), dtype=np.int16)
        width = a.size[0]
    # The pixels the disc added, ignoring JPEG's own ringing around the marks
    # that were already there.
    changed = np.abs(after - before).sum(axis=2) > 40
    ys, xs = np.nonzero(changed)
    assert xs.size, "the disc drew nothing"

    ann = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    bar = ann["scale_bar"]
    expected = bar["fraction"] * MOON_DIAMETER_ARCSEC / bar["arcsec"] * width
    span = xs.max() - xs.min()
    assert abs(span - expected) <= 0.08 * expected, (
        f"the disc spans {span}px but the Moon is {expected:.0f}px in this field")


def test_a_field_too_tight_for_the_moon_draws_no_disc(client, solved_library):
    """A heavy crop or a tight single object can want a circle wider than the
    picture. The disc stands aside there rather than drawing something that
    would misstate the scale — the bar's own sentence already says the honest
    thing in words on a field that tight."""
    safe, run_id = _run(client, solved_library, moons_across=0.4)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/jpeg"
    assert (client.get(f"{url}?scale=true&moon=true").content
            == client.get(f"{url}?scale=true").content)


def test_moon_without_scale_is_a_no_op(client, solved_library):
    """The disc is an addition to the scale marks, measured off the same bar —
    never a second path that could disagree with them about pixel scale."""
    safe, run_id = _run(client, solved_library)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/jpeg"
    assert client.get(f"{url}?moon=true").content == client.get(url).content


def test_existing_downloads_are_byte_for_byte_unchanged(client, solved_library):
    """Upgrade safety (§9): the disc is opt-in, so every bookmarked URL and every
    surface that hasn't been taught about it gets exactly the bytes it got
    before this existed."""
    safe, run_id = _run(client, solved_library)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/jpeg"
    plain = client.get(url).content
    assert client.get(f"{url}?moon=false").content == plain
    marked = client.get(f"{url}?scale=true").content
    assert client.get(f"{url}?scale=true&moon=false").content == marked


def test_the_disc_composes_with_north_up_and_the_keepsake(client, solved_library):
    """It layers exactly like the bar and the rose: under both caption variants,
    and following the pixels through a North-up turn."""
    safe, run_id = _run(client, solved_library)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/jpeg"
    for extra in ("north_up=true", "keepsake=true"):
        without = client.get(f"{url}?{extra}&scale=true")
        with_moon = client.get(f"{url}?{extra}&scale=true&moon=true")
        assert without.status_code == with_moon.status_code == 200
        assert with_moon.content != without.content, f"no disc with {extra}"
        with Image.open(BytesIO(without.content)) as a, \
                Image.open(BytesIO(with_moon.content)) as b:
            assert a.size == b.size


def test_a_run_with_no_wcs_has_no_disc_to_draw(client, solved_library):
    """Same graceful no-op the bar and the rose already have: an older/edited run
    has no honest scale, so there is no honest Moon either."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = tdir / "nowcs.fits"
        cube = np.full((3, 64, 64), 0.2, dtype=np.float32)
        fits.PrimaryHDU(data=cube).writeto(fits_path, overwrite=True)
        preview_path = tdir / "nowcs_preview.png"
        preview_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="nowcs", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=64, canvas_w=64, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()
    assert client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                       json={"stretch": 0.5, "black": 0.35}).status_code == 200
    url = f"/api/targets/{safe}/stack-runs/{run_id}/jpeg"
    assert (client.get(f"{url}?scale=true&moon=true").content
            == client.get(url).content)
