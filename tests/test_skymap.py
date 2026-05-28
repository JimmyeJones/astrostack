"""
All-sky map renderer: smoke tests.

The actual visual quality is a matter of eyeballing — we just check that
the Aitoff figure builds without raising on an empty library and on a
library with several targets, and that the saved PNG is non-trivial.
"""

from __future__ import annotations

from pathlib import Path

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg", force=True)

from seestack.io.library import Library
from seestack.post.skymap import (
    SkyMapOptions,
    _format_duration,
    _ra_to_aitoff_rad,
    render_skymap,
    render_to_png,
)


def test_ra_to_aitoff_wraps():
    # RA 0 maps to screen-x 0.
    assert abs(_ra_to_aitoff_rad(0.0)) < 1e-9
    # The coordinate is negated (RA increases leftward), so RA 180 → -pi.
    assert _ra_to_aitoff_rad(180.0) == pytest.approx(-3.141592653, abs=1e-6)
    # 360 wraps back to 0.
    assert _ra_to_aitoff_rad(360.0) == pytest.approx(0.0, abs=1e-6)
    # Wrap from 270 should give the same as -90.
    assert _ra_to_aitoff_rad(270.0) == pytest.approx(_ra_to_aitoff_rad(-90.0))
    # RA increasing should move the point left (more negative x).
    assert _ra_to_aitoff_rad(90.0) < _ra_to_aitoff_rad(30.0)


def test_format_duration_friendly():
    assert _format_duration(0) == "0s"
    assert _format_duration(45) == "45s"
    assert _format_duration(120) == "2m 0s"
    assert _format_duration(3725) == "1h 2m 5s"


def test_render_empty_library_does_not_raise(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        fig = render_skymap(lib, SkyMapOptions(title="empty"))
        assert fig is not None
    finally:
        lib.close()


def test_render_to_png_writes_a_real_file(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        e, p = lib.create_target("M 42", ra_deg=83.6, dec_deg=-5.4)
        p.close()
        e2, p2 = lib.create_target("M 31", ra_deg=10.7, dec_deg=41.27)
        p2.close()
        out = render_to_png(lib, tmp_path / "skymap.png",
                            SkyMapOptions(thumbnail_size_deg=0))
        assert out.exists()
        # Non-trivial PNG (>10 KB rules out an empty axes).
        assert out.stat().st_size > 10_000
    finally:
        lib.close()


def test_render_handles_targets_without_coords(tmp_path):
    """Targets with NULL ra/dec must be silently skipped from the map but
    not crash the render."""
    lib = Library.create(tmp_path / "lib")
    try:
        e, p = lib.create_target("Unknown")  # no coords given
        p.close()
        e2, p2 = lib.create_target("M 42", ra_deg=83.6, dec_deg=-5.4)
        p2.close()
        fig = render_skymap(lib, SkyMapOptions(thumbnail_size_deg=0))
        assert fig is not None
    finally:
        lib.close()
