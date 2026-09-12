"""Shared best-effort observer-site detection (:mod:`webapp.site_location`).

The angle parsing and header extraction are covered in ``test_plan.py``; here we
exercise the library-probing entry point both routers now share.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("astropy")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root (real webapp)
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))  # tests/ for synth
from synth import write_seestar_fits  # noqa: E402

from webapp.site_location import (  # noqa: E402
    detect_site_from_library,
    probe_site_from_library,
)


def _build_library(root: Path, *, site_lat=None, site_lon=None):
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    incoming = root / "incoming" / "M_42"
    incoming.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        write_seestar_fits(
            incoming / f"frame_{i:03d}.fit",
            width=64, height=64, n_stars=8, seed=10 + i,
            site_lat=site_lat, site_lon=site_lon,
        )
    lib = Library.open_or_create(root / "library")
    scan_and_organize(lib, root / "incoming", copy_to_cache=False)
    return lib


def test_detect_site_from_library_reads_sitelong(tmp_path):
    lib = _build_library(tmp_path, site_lat=51.5, site_lon=-0.13)
    try:
        site = detect_site_from_library(lib)
    finally:
        lib.close()
    assert site is not None
    lat, lon = site
    assert lat == pytest.approx(51.5)
    assert lon == pytest.approx(-0.13)


def test_detect_site_from_library_none_when_header_absent(tmp_path):
    # No SITELAT/SITELONG written → nothing to detect, and no crash.
    lib = _build_library(tmp_path)
    try:
        assert detect_site_from_library(lib) is None
    finally:
        lib.close()


def test_detect_site_from_library_respects_the_probe_cap(tmp_path):
    # With the cap at 0 the probe reads no headers and returns None even though a
    # site is present — the bound that keeps a locationless library cheap.
    lib = _build_library(tmp_path, site_lat=51.5, site_lon=-0.13)
    try:
        assert detect_site_from_library(lib, max_probes=0) is None
    finally:
        lib.close()


# --- why there is no site ---------------------------------------------------
#
# The three ways a probe comes back empty want three different sentences, and
# until the reason existed every surface said the same one: "it reads your
# location automatically from a plate-solved Seestar frame — so once you've
# solved some subs it'll just work." That is right for an empty library and
# false for a library whose subs carry no SITELAT, which is exactly what the
# bundled sample is. These pin that the two are distinguishable.


def test_a_library_whose_frames_carry_no_site_says_so_rather_than_no_frames(tmp_path):
    # The bug's own case: three perfectly good, scanned frames, no site header.
    # "Shoot more subs" is the wrong advice here and this is what lets the UI
    # know it.
    lib = _build_library(tmp_path)
    try:
        probe = probe_site_from_library(lib)
    finally:
        lib.close()
    assert probe.site is None
    assert probe.reason == "no-site-header"


def test_a_library_with_a_site_reports_found(tmp_path):
    lib = _build_library(tmp_path, site_lat=51.5, site_lon=-0.13)
    try:
        probe = probe_site_from_library(lib)
    finally:
        lib.close()
    assert probe.site == pytest.approx((51.5, -0.13))
    assert probe.reason == "found"


def test_an_empty_library_reports_no_frames(tmp_path):
    from seestack.io.library import Library

    lib = Library.open_or_create(tmp_path / "library")
    try:
        probe = probe_site_from_library(lib)
    finally:
        lib.close()
    assert probe == (None, "no-frames")


def test_frames_whose_files_have_gone_report_unreadable_not_missing_headers(tmp_path):
    # Storage offline / files moved: neither "shoot more subs" nor "fill in
    # Settings" is the honest next step, so this must not collapse into either.
    lib = _build_library(tmp_path, site_lat=51.5, site_lon=-0.13)
    try:
        for fits in (tmp_path / "incoming" / "M_42").glob("*.fit"):
            fits.unlink()
        probe = probe_site_from_library(lib)
    finally:
        lib.close()
    assert probe == (None, "unreadable")


def test_one_unreadable_frame_among_readable_ones_is_still_a_header_problem(tmp_path):
    # "unreadable" is claimed only when *every* probed path failed — a library
    # with one gap and no headers is a header problem, not a storage one.
    lib = _build_library(tmp_path)
    try:
        first = sorted((tmp_path / "incoming" / "M_42").glob("*.fit"))[0]
        first.unlink()
        probe = probe_site_from_library(lib)
    finally:
        lib.close()
    assert probe == (None, "no-site-header")


def test_detect_site_from_library_still_answers_exactly_the_site(tmp_path):
    # The thin wrapper every existing caller uses is the probe's `.site`, so the
    # two can never disagree about where the telescope is.
    lib = _build_library(tmp_path, site_lat=-33.86, site_lon=151.2)
    try:
        assert detect_site_from_library(lib) == probe_site_from_library(lib).site
    finally:
        lib.close()


def test_the_reason_rides_on_the_one_walk_every_caller_already_stands_in_front_of(
        monkeypatch):
    """`probe_site_from_library` must go *through* `detect_site_from_library`.

    Ten call sites across five test modules monkeypatch that name to stand in for
    the header probe, and one of them (`test_activity_calendar.py::
    test_configured_site_lon_wins_and_skips_header_probe`) raises from it to
    prove the probe does not run. When the walk was briefly moved out from under
    it, nine of those patches silently became no-ops that still passed — they
    were forcing the value the real probe happened to return anyway — and the
    "must not run" guard stopped guarding anything. Only the tenth, which forced
    a *different* value, went red. This pins the seam so the next refactor fails
    loudly instead of quietly.
    """
    import webapp.site_location as site_location

    calls: list[object] = []

    def _stand_in(lib, **kw):
        calls.append(lib)
        return (20.0, 150.0)

    monkeypatch.setattr(site_location, "detect_site_from_library", _stand_in)
    probe = site_location.probe_site_from_library(object())
    assert calls, "probe_site_from_library bypassed detect_site_from_library"
    assert probe == ((20.0, 150.0), "found")
