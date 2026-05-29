"""Fixtures for the webapp tests.

We build a real on-disk dataset (incoming + library) with synthetic Seestar
FITS so the API runs against genuine Library/Project SQLite — no mocking of the
engine. ASTAP is never required: solve just marks frames unsolved and the
pipeline tolerates it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for synth
from synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

# Dimensions match make_synth_wcs_text() defaults so the injected WCS lines up.
FRAME_W, FRAME_H = 480, 320


def _make_incoming(incoming: Path) -> None:
    """Two Seestar-style target sub-folders, each with a few WCS'd frames."""
    incoming.mkdir(parents=True, exist_ok=True)
    for target, ra in (("M_42", 83.6), ("NGC_7000", 314.0)):
        d = incoming / target
        d.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            write_seestar_fits(
                d / f"frame_{i:03d}.fit",
                width=FRAME_W, height=FRAME_H, n_stars=30, seed=100 + i,
                add_wcs=True, ra_center_deg=ra, dec_center_deg=-5.0,
            )


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    _make_incoming(root / "incoming")
    return root


@pytest.fixture
def built_library(data_root: Path):
    """Run the scanner so the library has two targets with ingested frames."""
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    lib = Library.open_or_create(data_root / "library")
    try:
        scan_and_organize(lib, data_root / "incoming", copy_to_cache=False)
    finally:
        lib.close()
    return data_root


@pytest.fixture
def solved_library(built_library):
    """Inject a synthetic WCS into every frame so stacking can run without ASTAP."""
    from seestack.io.library import Library

    data_root = built_library
    wcs_text = make_synth_wcs_text(width=FRAME_W, height=FRAME_H)
    lib = Library.open_or_create(data_root / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                for f in proj.iter_frames():
                    proj.update_frame(
                        f.id, wcs_json=wcs_text,
                        ra_center_deg=83.6, dec_center_deg=-5.4,
                        width_px=FRAME_W, height_px=FRAME_H,
                        bayer_pattern="RGGB",
                    )
            finally:
                proj.close()
            lib.refresh_target_stats(entry.safe_name)
    finally:
        lib.close()
    return data_root


@pytest.fixture
def client(data_root: Path, monkeypatch):
    """A TestClient with lifespan run (worker + watcher started)."""
    monkeypatch.setenv("ASTROSTACK_DATA", str(data_root))
    # Disable the watcher loop side-effects during API tests.
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    from fastapi.testclient import TestClient

    from webapp.main import create_app

    app = create_app()
    with TestClient(app) as c:
        # Turn the watcher off so it doesn't enqueue jobs underneath the tests.
        c.put("/api/settings", json={"watcher_enabled": False})
        yield c
