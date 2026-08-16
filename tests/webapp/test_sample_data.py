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
