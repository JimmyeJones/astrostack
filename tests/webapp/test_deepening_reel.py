"""The per-target "night after night" deepening reel endpoints."""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_stack(root, safe: str, name: str, *, subs: int, when: str,
               noise: float, seed: int) -> int:
    """Write a synthetic linear stack FITS and register a run for it."""
    lib = Library.open_or_create(root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        h = w = 48
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:h, 0:w]
        glow = 0.15 * np.exp(-(((xx - 24) ** 2 + (yy - 24) ** 2) / 200.0))
        chan = (0.1 + glow + noise * rng.standard_normal((h, w))).astype(np.float32)
        chan[22:26, 22:26] = 0.9
        cube = np.stack([chan, chan * 0.7, chan * 0.5]).astype(np.float32)
        fp = tdir / f"{name}.fits"
        fits.PrimaryHDU(data=cube).writeto(fp, overwrite=True)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=when, output_basename=name,
                fits_path=str(fp), tiff_path=None, preview_path=None,
                n_frames_used=subs, canvas_h=h, canvas_w=w,
                coverage_min=1, coverage_max=3, options_json="{}",
            ))
        finally:
            proj.close()
        return run_id
    finally:
        lib.close()


def test_deepening_info_self_hides_with_one_stack(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "master", subs=120, when="2026-05-01T00:00:00Z",
               noise=0.04, seed=1)
    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is False
    assert body["n_stacks"] == 1
    # And the animation itself 404s (nothing to show yet).
    assert client.get(f"/api/targets/{safe}/deepening-reel").status_code == 404


def test_deepening_info_reports_the_series(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # Register out of chronological order to prove the endpoint sorts by time.
    _add_stack(solved_library, safe, "s2", subs=505, when="2026-05-20T00:00:00Z",
               noise=0.008, seed=3)
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-12T00:00:00Z",
               noise=0.04, seed=2)
    _add_stack(solved_library, safe, "s3", subs=1240, when="2026-05-28T00:00:00Z",
               noise=0.004, seed=4)

    body = client.get(f"/api/targets/{safe}/deepening-reel/info").json()
    assert body["available"] is True
    assert body["n_stacks"] == 3
    assert body["first_subs"] == 120       # oldest
    assert body["last_subs"] == 1240       # newest (deepest)
    assert body["first_utc"] == "2026-05-12T00:00:00Z"
    assert body["last_utc"] == "2026-05-28T00:00:00Z"
    assert body["format"] in ("webp", "png")


def test_deepening_reel_serves_a_multiframe_animation(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-12T00:00:00Z",
               noise=0.04, seed=5)
    _add_stack(solved_library, safe, "s2", subs=505, when="2026-05-20T00:00:00Z",
               noise=0.01, seed=6)

    r = client.get(f"/api/targets/{safe}/deepening-reel")
    assert r.status_code == 200
    assert r.headers["content-type"] in ("image/webp", "image/png")

    from io import BytesIO

    from PIL import Image
    with Image.open(BytesIO(r.content)) as im:
        assert getattr(im, "n_frames", 1) == 2

    # A second request is served from the signature-keyed cache (still 200).
    assert client.get(f"/api/targets/{safe}/deepening-reel").status_code == 200


def test_deepening_reel_rebuilds_when_a_stack_is_added(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack(solved_library, safe, "s1", subs=120, when="2026-05-12T00:00:00Z",
               noise=0.04, seed=7)
    _add_stack(solved_library, safe, "s2", subs=505, when="2026-05-20T00:00:00Z",
               noise=0.01, seed=8)

    from io import BytesIO

    from PIL import Image
    with Image.open(BytesIO(client.get(f"/api/targets/{safe}/deepening-reel").content)) as im:
        assert getattr(im, "n_frames", 1) == 2

    # A third night lands → the cached reel's signature is stale → rebuilt to 3.
    _add_stack(solved_library, safe, "s3", subs=1240, when="2026-05-28T00:00:00Z",
               noise=0.004, seed=9)
    with Image.open(BytesIO(client.get(f"/api/targets/{safe}/deepening-reel").content)) as im:
        assert getattr(im, "n_frames", 1) == 3


def test_deepening_info_unknown_target_404(client, solved_library):
    assert client.get("/api/targets/does_not_exist/deepening-reel/info").status_code == 404
