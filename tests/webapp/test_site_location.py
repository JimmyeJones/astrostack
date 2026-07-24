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

from webapp.site_location import detect_site_from_library  # noqa: E402


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
