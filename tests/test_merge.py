"""Multi-session project merge."""

import pytest

pytest.importorskip("astropy")

from seestack.io.merge import merge_projects
from seestack.io.project import FrameRow, Project
from tests.synth import make_synth_wcs_text, write_seestar_fits


def _make_project(tmp_path, name: str, n: int, *, base_seed: int = 0):
    proj = Project.create(tmp_path / name, name=name)
    raws = tmp_path / f"{name}_raws"
    raws.mkdir()
    wcs_text = make_synth_wcs_text()
    for i in range(n):
        path = write_seestar_fits(raws / f"{name}_{i}.fit", seed=base_seed + i, n_stars=10)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            fwhm_px=3.0,
        ))
    return proj


def test_merge_pulls_frames_into_destination(tmp_path):
    src = _make_project(tmp_path, "session_a", 5, base_seed=10)
    dst = _make_project(tmp_path, "destination", 3, base_seed=20)
    src.close()

    results = list(merge_projects(dst, [src.project_dir]))
    assert len(results) == 1
    assert results[0].n_added == 5
    assert results[0].n_skipped_duplicate == 0
    assert dst.count() == 3 + 5
    dst.close()


def test_merge_skips_duplicates_by_source_path(tmp_path):
    src = _make_project(tmp_path, "session_b", 4, base_seed=30)
    dst = _make_project(tmp_path, "destination_b", 0)
    src.close()
    # First merge: all 4 added.
    list(merge_projects(dst, [src.project_dir]))
    # Second merge: 0 added (all are duplicates by source_path).
    results = list(merge_projects(dst, [src.project_dir]))
    assert results[0].n_added == 0
    assert results[0].n_skipped_duplicate == 4
    dst.close()


def test_merge_preserves_target_pointing_hints(tmp_path):
    # A frame merged *before* it is plate-solved carries only its header-derived
    # target-pointing hints (ra_hint_deg/dec_hint_deg, no wcs_json). Those must
    # survive the merge, or the later solve falls back to a slow blind all-sky
    # search instead of a localized one around the mount's pointing.
    src = Project.create(tmp_path / "hint_src", name="hint_src")
    raws = tmp_path / "hint_raws"
    raws.mkdir()
    path = write_seestar_fits(raws / "unsolved_0.fit", seed=1, n_stars=10)
    src.add_frame(FrameRow(
        source_path=str(path), cached_path=str(path),
        width_px=480, height_px=320, bayer_pattern="RGGB",
        ra_hint_deg=202.5, dec_hint_deg=47.2,  # unsolved: hints only, no WCS
    ))
    src.close()

    dst = _make_project(tmp_path, "hint_dst", 0)
    results = list(merge_projects(dst, [src.project_dir]))
    assert results[0].n_added == 1
    merged = list(dst.iter_frames())
    assert len(merged) == 1
    assert merged[0].ra_hint_deg == pytest.approx(202.5)
    assert merged[0].dec_hint_deg == pytest.approx(47.2)
    dst.close()


def test_merge_handles_non_project_dir(tmp_path):
    dst = _make_project(tmp_path, "dst", 0)
    bogus = tmp_path / "not_a_project"
    bogus.mkdir()
    results = list(merge_projects(dst, [bogus]))
    assert results[0].n_added == 0
    dst.close()
