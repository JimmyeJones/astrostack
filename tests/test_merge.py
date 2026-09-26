"""Multi-session project merge."""

from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.merge import carry_stack_runs, merge_projects
from seestack.io.project import FrameRow, Project, StackRunRow
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


def test_merge_dedupes_a_symlinked_respell_of_the_same_frame(tmp_path):
    # The same physical FITS reached via a different path spelling (a symlinked
    # NAS mount, a relative-vs-absolute scan root) must dedup on merge, exactly
    # as ingest does since v0.107.8 — otherwise the frame lands twice and is
    # double-weighted in the stack. Merge previously keyed on the raw string.
    raws = tmp_path / "raws"
    raws.mkdir()
    real = write_seestar_fits(raws / "frame_0.fit", seed=1, n_stars=10)

    # Destination already holds the frame under its real path.
    dst = Project.create(tmp_path / "dst", name="dst")
    dst.add_frame(FrameRow(
        source_path=str(real), cached_path=str(real),
        width_px=480, height_px=320, bayer_pattern="RGGB",
    ))

    # Source references the identical file through a symlinked directory, so the
    # raw string differs but os.path.realpath is the same.
    link_dir = tmp_path / "raws_link"
    link_dir.symlink_to(raws)
    respelled = link_dir / "frame_0.fit"
    assert str(respelled) != str(real)  # different spelling, same realpath
    src = Project.create(tmp_path / "src", name="src")
    src.add_frame(FrameRow(
        source_path=str(respelled), cached_path=str(respelled),
        width_px=480, height_px=320, bayer_pattern="RGGB",
    ))
    src.close()

    results = list(merge_projects(dst, [src.project_dir]))
    assert results[0].n_added == 0
    assert results[0].n_skipped_duplicate == 1
    assert dst.count() == 1  # not double-counted
    dst.close()


def test_merge_handles_non_project_dir(tmp_path):
    dst = _make_project(tmp_path, "dst", 0)
    bogus = tmp_path / "not_a_project"
    bogus.mkdir()
    results = list(merge_projects(dst, [bogus]))
    assert results[0].n_added == 0
    dst.close()


# --- the pictures travel too ------------------------------------------------
#
# `Library.merge_targets` deletes each source target's whole folder when it is
# done, so anything `merge_projects` leaves behind is destroyed — and until
# `carry_stack_runs` it left behind every stack the app had already made, under a
# Library nudge saying "keeps every sub — nothing is deleted".

def _write_run(proj, basename: str, *, note: str | None = None,
               n_frames: int = 7) -> int:
    """Record one stack run on ``proj`` with a real file set on disk."""
    out = proj.project_dir / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{basename}.fits").write_bytes(b"FITS-" + basename.encode())
    (out / f"{basename}.tif").write_bytes(b"TIFF-" + basename.encode())
    (out / f"{basename}_preview.png").write_bytes(b"PNG-" + basename.encode())
    (out / f"{basename}_coverage.fits").write_bytes(b"COV-" + basename.encode())
    return proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc="2026-09-01T22:00:00Z", output_basename=basename,
        fits_path=str(out / f"{basename}.fits"),
        tiff_path=str(out / f"{basename}.tif"),
        preview_path=str(out / f"{basename}_preview.png"),
        n_frames_used=n_frames, canvas_h=320, canvas_w=480,
        coverage_min=1, coverage_max=n_frames, options_json="{}", notes=note,
        total_exposure_s=70.0,
    ))


def test_merge_carries_the_sources_finished_pictures(tmp_path):
    src = _make_project(tmp_path, "night_two", 3, base_seed=10)
    run_id = _write_run(src, "master", note="night two")
    src.set_meta(f"editor_recipe:{run_id}", '{"ops": [{"id": "tone.stretch"}]}')
    src.set_meta("astap_path", "/usr/bin/astap")          # not per-run
    src.close()
    src_again = Project.open(tmp_path / "night_two")

    dst = _make_project(tmp_path, "night_one", 2, base_seed=20)
    results = list(merge_projects(dst, [src_again.project_dir],
                                  copy_stack_runs=True))
    src_again.close()

    assert results[0].n_runs_copied == 1
    carried = list(dst.iter_stack_runs())
    assert len(carried) == 1
    assert carried[0].notes == "night two"
    assert carried[0].n_frames_used == 7
    # The files are the destination's own now — readable after the source folder
    # is deleted, which is what merge_targets does next.
    for path in (carried[0].fits_path, carried[0].tiff_path, carried[0].preview_path):
        assert path is not None
        assert Path(path).is_file()
        assert Path(path).parent == dst.project_dir / "output"
    # …including the siblings that resolve off the basename, not off a column.
    stem = Path(carried[0].fits_path).stem
    assert (dst.project_dir / "output" / f"{stem}_coverage.fits").is_file()
    # The saved edit recipe follows its picture, re-keyed to the new run id.
    assert dst.get_meta(f"editor_recipe:{carried[0].id}") == (
        '{"ops": [{"id": "tone.stretch"}]}')
    # A project-meta key that is not per-run is left alone.
    assert dst.get_meta("astap_path") is None
    dst.close()


def test_merge_does_not_carry_stack_runs_unless_asked(tmp_path):
    """The default is unchanged: this module's original job is frame rows."""
    src = _make_project(tmp_path, "src_runs", 2, base_seed=10)
    _write_run(src, "master")
    src.close()
    src_again = Project.open(tmp_path / "src_runs")
    dst = _make_project(tmp_path, "dst_runs", 1, base_seed=20)
    results = list(merge_projects(dst, [src_again.project_dir]))
    src_again.close()
    assert results[0].n_runs_copied == 0
    assert list(dst.iter_stack_runs()) == []
    dst.close()


def test_a_carried_picture_never_overwrites_the_destinations_own(tmp_path):
    """Both nights' stacks are called ``master`` — the Seestar names every folder
    the same way, so a straight copy would replace the destination's picture with
    the source's and the merge would *lose* one while claiming to keep both."""
    dst = _make_project(tmp_path, "keeper", 2, base_seed=20)
    _write_run(dst, "master", note="mine", n_frames=99)
    src = _make_project(tmp_path, "other_night", 2, base_seed=10)
    _write_run(src, "master", note="theirs", n_frames=7)
    src.close()
    src_again = Project.open(tmp_path / "other_night")

    assert carry_stack_runs(dst, src_again).copied == 1
    src_again.close()

    runs = {r.notes: r for r in dst.iter_stack_runs()}
    assert set(runs) == {"mine", "theirs"}
    assert runs["mine"].n_frames_used == 99
    assert runs["theirs"].n_frames_used == 7
    mine = Path(runs["mine"].fits_path)
    theirs = Path(runs["theirs"].fits_path)
    assert mine != theirs
    assert mine.read_bytes() == b"FITS-master"       # untouched
    assert theirs.read_bytes() == b"FITS-master"     # its own copy, own name
    assert runs["theirs"].output_basename != runs["mine"].output_basename
    dst.close()


def test_a_run_whose_files_are_gone_is_not_carried_as_an_empty_row(tmp_path):
    src = _make_project(tmp_path, "gone", 1, base_seed=10)
    _write_run(src, "master")
    for leftover in (src.project_dir / "output").iterdir():
        leftover.unlink()
    src.close()
    src_again = Project.open(tmp_path / "gone")
    dst = _make_project(tmp_path, "gone_dst", 1, base_seed=20)
    carried = carry_stack_runs(dst, src_again)
    assert (carried.copied, carried.lost) == (0, 0)   # nothing left to lose
    assert list(dst.iter_stack_runs()) == []
    src_again.close()
    dst.close()


def test_an_archived_runs_files_are_found_by_its_path_not_its_basename(tmp_path):
    """A re-stack archives the previous set to ``{base}_{stamp}.*`` and repoints
    the row's three path columns while leaving ``output_basename`` alone — so a
    carry that trusted ``output_basename`` would copy the *newer* run's pixels
    over the older run's history row, twice."""
    src = _make_project(tmp_path, "restacked", 1, base_seed=10)
    out = src.project_dir / "output"
    old_id = _write_run(src, "master", note="first")
    archived = {}
    for suffix in (".fits", ".tif", "_preview.png", "_coverage.fits"):
        old = out / f"master{suffix}"
        new = out / f"master_20260901_220000{suffix}"
        old.rename(new)
        archived[str(old)] = str(new)
    src.repoint_stack_runs(archived)
    # Distinct pixels, so "which file did the row end up pointing at?" is
    # answerable by content rather than by name (a rename copies neither).
    (out / "master_20260901_220000.fits").write_bytes(b"FITS-the-older-picture")
    _write_run(src, "master", note="second")          # the new canonical set
    src.close()
    src_again = Project.open(tmp_path / "restacked")

    dst = _make_project(tmp_path, "restacked_dst", 1, base_seed=20)
    assert carry_stack_runs(dst, src_again).copied == 2
    src_again.close()
    runs = {r.notes: r for r in dst.iter_stack_runs()}
    assert set(runs) == {"first", "second"}
    assert Path(runs["first"].fits_path).read_bytes() == b"FITS-the-older-picture"
    assert Path(runs["second"].fits_path).read_bytes() == b"FITS-master"
    assert old_id is not None
    dst.close()


def test_a_picture_that_cannot_be_copied_is_reported_lost_not_half_carried(
        tmp_path, monkeypatch):
    """The caller deletes the source folder next, so "we got most of it" is the
    one answer this must never give."""
    import seestack.io.merge as merge_mod

    src = _make_project(tmp_path, "unlucky", 1, base_seed=10)
    _write_run(src, "master", note="at risk")
    src.close()
    src_again = Project.open(tmp_path / "unlucky")
    dst = _make_project(tmp_path, "unlucky_dst", 1, base_seed=20)

    real_copy = merge_mod.shutil.copy2

    def fail_on_the_preview(source, dest, *a, **kw):
        if str(source).endswith("_preview.png"):
            raise OSError(28, "No space left on device")
        return real_copy(source, dest, *a, **kw)

    monkeypatch.setattr(merge_mod.shutil, "copy2", fail_on_the_preview)
    carried = carry_stack_runs(dst, src_again)
    src_again.close()

    assert (carried.copied, carried.lost) == (0, 1)
    assert list(dst.iter_stack_runs()) == []
    # …and no orphan files left behind in the destination either.
    out = dst.project_dir / "output"
    assert not out.exists() or list(out.iterdir()) == []
    dst.close()


def test_merge_does_not_carry_the_sources_whole_series_reel(tmp_path):
    """The deepening reel is a cache of the *source* target's whole history of
    stacks, not of the run it happens to sit beside — so carrying it would land a
    picture of the wrong history in the destination's output folder, under a
    basename whose own reel is built from the merged series on the next request.

    It is in ``RUN_ARTEFACT_SUFFIXES`` so that deleting a run reclaims it; this
    pins the other half of that registration.
    """
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES, SERIES_ARTEFACTS

    src = _make_project(tmp_path, "night_two", 3, base_seed=10)
    _write_run(src, "master", note="night two")
    out = src.project_dir / "output"
    for kind in SERIES_ARTEFACTS:
        (out / f"master{RUN_ARTEFACT_SUFFIXES[kind]}").write_bytes(b"REEL")
    src.close()
    src_again = Project.open(tmp_path / "night_two")

    dst = _make_project(tmp_path, "night_one", 2, base_seed=20)
    results = list(merge_projects(dst, [src_again.project_dir],
                                  copy_stack_runs=True))
    src_again.close()

    # The picture itself still came across — this must not have become "carry
    # nothing".
    assert results[0].n_runs_copied == 1
    landed = sorted(p.name for p in (dst.project_dir / "output").iterdir())
    assert any(n.endswith(".fits") for n in landed), landed
    for kind in sorted(SERIES_ARTEFACTS):
        suffix = RUN_ARTEFACT_SUFFIXES[kind]
        assert not any(n.endswith(suffix) for n in landed), (
            f"{suffix} should not have been carried: {landed}")
    dst.close()
