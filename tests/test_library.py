"""
Library: shared registry across many target sub-projects.

These tests cover the things that would silently break a campaign:
  - creating / re-opening a library and finding the same targets.
  - cross-target queries (campaign totals) match the per-project truth.
  - RA/Dec lookup picks the closest registered target.
  - adopting an existing folder of projects into a fresh library.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seestack.io.library import Library, _angular_separation_deg, make_safe_name
from seestack.io.project import FrameRow, Project


_counter = [0]


def _add_frame(proj: Project, *, exposure_s: float, ra: float, dec: float,
               accept: bool = True) -> int:
    """Insert a fake frame with a guaranteed-unique source_path."""
    _counter[0] += 1
    return proj.add_frame(FrameRow(
        source_path=f"f_{_counter[0]}.fit",
        exposure_s=exposure_s,
        ra_center_deg=ra,
        dec_center_deg=dec,
        accept=accept,
    ))


def test_make_safe_name_handles_messy_input():
    assert make_safe_name("M 42") == "M_42"
    assert make_safe_name("NGC 7000 / North America") == "NGC_7000_North_America"
    # Leading/trailing punctuation stripped.
    assert make_safe_name("...M31...") == "M31"
    # Empty / non-alphanumeric input gets a fallback.
    assert make_safe_name("   ") == "target"
    # Truncated to a sensible length.
    long = make_safe_name("X" * 200)
    assert len(long) <= 64
    # Case is preserved (so "m31" and "M31" don't collide).
    assert make_safe_name("M31") != make_safe_name("m31").lower()


def test_create_open_and_list_targets(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.create_target("M 42", ra_deg=83.82, dec_deg=-5.39)
        p1.close()
        e2, p2 = lib.create_target("NGC 7000", ra_deg=314.75, dec_deg=44.32)
        p2.close()
        names = sorted(t.safe_name for t in lib.list_targets())
        assert names == ["M_42", "NGC_7000"]
        # Stored coords preserved.
        m42 = lib.find_target("M_42")
        assert m42 and abs(float(m42.ra_deg) - 83.82) < 1e-6
    finally:
        lib.close()

    # Re-opening the same library should see both targets.
    lib2 = Library.open(tmp_path / "lib")
    try:
        assert {t.safe_name for t in lib2.list_targets()} == {"M_42", "NGC_7000"}
    finally:
        lib2.close()


def test_open_or_create_is_idempotent(tmp_path):
    a = Library.open_or_create(tmp_path / "lib")
    a.close()
    b = Library.open_or_create(tmp_path / "lib")
    b.close()
    # No exception, no duplicate registry rows.


def test_refresh_target_stats_pulls_from_per_project_db(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        entry, proj = lib.create_target("M 42")
        try:
            _add_frame(proj, exposure_s=10.0, ra=83.5, dec=-5.5)
            _add_frame(proj, exposure_s=10.0, ra=83.6, dec=-5.4)
            _add_frame(proj, exposure_s=10.0, ra=83.7, dec=-5.3, accept=False)
        finally:
            proj.close()

        refreshed = lib.refresh_target_stats("M_42")
        assert refreshed is not None
        assert refreshed.n_frames == 3
        assert refreshed.n_frames_accepted == 2
        # Total exposure should sum only ACCEPTED frames.
        assert refreshed.total_exposure_s == pytest.approx(20.0, abs=0.01)
        # Median RA/Dec from accepted frames is filled in for the registry.
        assert abs(float(refreshed.ra_deg) - 83.55) < 0.01
        assert abs(float(refreshed.dec_deg) - (-5.45)) < 0.01
    finally:
        lib.close()


def test_target_ra_is_wrap_safe_across_ra_zero(tmp_path):
    """A target imaged near RA=0h has frames straddling the 0°/360° boundary.
    The registry RA must stay near 0°, not flip ~180° to the opposite side of the
    sky (which would break the sky-map plot and find_target_within matching)."""
    lib = Library.create(tmp_path / "lib")
    try:
        entry, proj = lib.create_target("RA-zero target")
        try:
            # 50/50 split across the wrap — a plain median lands at 180.0°.
            _add_frame(proj, exposure_s=10.0, ra=359.9, dec=20.0)
            _add_frame(proj, exposure_s=10.0, ra=0.1, dec=20.0)
        finally:
            proj.close()

        refreshed = lib.refresh_target_stats(entry.safe_name)
        assert refreshed is not None
        ra = float(refreshed.ra_deg)
        # Wrap-safe: within a hair of 0°/360°, on the correct side of the sky —
        # not the buggy 180.0°.
        assert min(ra, 360.0 - ra) < 0.5
        assert abs(float(refreshed.dec_deg) - 20.0) < 1e-6
    finally:
        lib.close()


def test_campaign_stats_sums_across_targets(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.create_target("M 42")
        try:
            _add_frame(p1, exposure_s=30.0, ra=83.6, dec=-5.4)
            _add_frame(p1, exposure_s=30.0, ra=83.6, dec=-5.4)
        finally:
            p1.close()
        e2, p2 = lib.create_target("M 31")
        try:
            _add_frame(p2, exposure_s=20.0, ra=10.7, dec=41.27)
        finally:
            p2.close()
        lib.refresh_target_stats("M_42")
        lib.refresh_target_stats("M_31")

        stats = lib.campaign_stats()
        assert stats["n_targets"] == 2
        assert stats["n_frames_accepted"] == 3
        assert stats["total_exposure_s"] == pytest.approx(80.0, abs=0.01)
    finally:
        lib.close()


def test_find_target_within_radius_finds_closest(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.create_target("A", ra_deg=10.0, dec_deg=0.0)
        p1.close()
        e2, p2 = lib.create_target("B", ra_deg=12.0, dec_deg=0.0)
        p2.close()
        # Point at (11.5, 0) — well within 5° of both, closer to B.
        hit = lib.find_target_within(11.5, 0.0, radius_deg=5.0)
        assert hit is not None and hit.safe_name == "B"

        # Point that's outside the radius of either.
        miss = lib.find_target_within(80.0, 80.0, radius_deg=2.0)
        assert miss is None
    finally:
        lib.close()


def test_adopt_existing_projects(tmp_path):
    """A library should be able to open a folder that already contains
    bare project sub-folders and register them."""
    root = tmp_path / "lib"
    targets_dir = root / "targets"
    targets_dir.mkdir(parents=True)
    # Pre-create two projects directly under targets/ — no library yet.
    p1 = Project.create(targets_dir / "M_42", name="M 42")
    _add_frame(p1, exposure_s=15.0, ra=83.6, dec=-5.4)
    p1.close()
    p2 = Project.create(targets_dir / "M_31", name="M 31")
    _add_frame(p2, exposure_s=15.0, ra=10.7, dec=41.27)
    p2.close()

    lib = Library.open(root)  # registry created from scratch, adopting both.
    try:
        names = sorted(t.safe_name for t in lib.list_targets())
        assert names == ["M_31", "M_42"]
        m42 = lib.find_target("M_42")
        # Coordinates inferred from accepted-frame medians.
        assert m42 is not None and m42.ra_deg is not None
    finally:
        lib.close()


def test_all_unicode_names_get_distinct_targets(tmp_path):
    """Two all-unicode names both clean to the ``"target"`` fallback in
    make_safe_name; the Library must still place them in *separate* projects
    (regression for the non-Latin-name collapse bug)."""
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.open_or_create_target("仙女座")          # Andromeda
        p1.close()
        e2, p2 = lib.open_or_create_target("猎户座大星云")     # Orion Nebula
        p2.close()
        # Distinct folders, both non-empty, one keeps the readable fallback.
        assert e1.safe_name != e2.safe_name
        assert e1.safe_name and e2.safe_name
        assert len(lib.list_targets()) == 2
        # Re-scanning either name is idempotent — no third target, stable folder.
        e1b, p1b = lib.open_or_create_target("仙女座")
        p1b.close()
        e2b, p2b = lib.open_or_create_target("猎户座大星云")
        p2b.close()
        assert e1b.safe_name == e1.safe_name
        assert e2b.safe_name == e2.safe_name
        assert len(lib.list_targets()) == 2
    finally:
        lib.close()


def test_names_differing_only_in_punctuation_do_not_merge(tmp_path):
    """``M 31`` and ``M_31`` both clean to ``M_31`` — they must not silently
    fold into one project."""
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.open_or_create_target("M 31")
        p1.close()
        e2, p2 = lib.open_or_create_target("M_31")
        p2.close()
        assert e1.safe_name != e2.safe_name
        assert len(lib.list_targets()) == 2
        # And each stays idempotent on re-open.
        e2b, p2b = lib.open_or_create_target("M_31")
        p2b.close()
        assert e2b.safe_name == e2.safe_name
        assert len(lib.list_targets()) == 2
    finally:
        lib.close()


def test_open_or_create_target_is_idempotent(tmp_path):
    """The scanner relies on open_or_create_target: first call creates,
    later calls re-open the same project without raising."""
    lib = Library.create(tmp_path / "lib")
    try:
        e1, p1 = lib.create_target("M 42")
        p1.close()
        # Second open_or_create on the same name must re-open, not raise.
        e2, p2 = lib.open_or_create_target("M 42")
        p2.close()
        assert e1.safe_name == e2.safe_name
        assert len(lib.list_targets()) == 1
        # A genuinely new name creates a new target.
        e3, p3 = lib.open_or_create_target("M 31")
        p3.close()
        assert len(lib.list_targets()) == 2
    finally:
        lib.close()


def test_merge_targets_moves_frames_and_removes_source(tmp_path):
    """Merging target B into A copies B's frames into A and deletes B."""
    lib = Library.create(tmp_path / "lib")
    try:
        ea, pa = lib.create_target("M 31 night 1")
        try:
            _add_frame(pa, exposure_s=10.0, ra=10.7, dec=41.27)
            _add_frame(pa, exposure_s=10.0, ra=10.7, dec=41.27)
        finally:
            pa.close()
        eb, pb = lib.create_target("M 31 night 2")
        try:
            _add_frame(pb, exposure_s=10.0, ra=10.8, dec=41.30)
            _add_frame(pb, exposure_s=10.0, ra=10.8, dec=41.30)
            _add_frame(pb, exposure_s=10.0, ra=10.8, dec=41.30)
        finally:
            pb.close()

        added = lib.merge_targets("M_31_night_1", ["M_31_night_2"])
        assert added == 3

        # Source target is gone from the registry and disk.
        assert lib.find_target("M_31_night_2") is None
        assert not (lib.targets_dir / "M_31_night_2").exists()

        # Destination now has all 5 frames.
        dest = lib.find_target("M_31_night_1")
        assert dest is not None and dest.n_frames == 5

        dproj = lib.open_target("M_31_night_1")
        try:
            assert dproj.count() == 5
        finally:
            dproj.close()
    finally:
        lib.close()


def test_merge_targets_keeps_the_sources_finished_pictures(tmp_path):
    """The Library nudge that fires this promises "nothing is deleted".

    Merging ends in ``delete_target(..., remove_files=True)`` — an ``rmtree`` of
    the source target's whole folder — so any stack the app had already made of
    that object went with it. With ``auto_stack`` on by default (v0.391.0) and a
    camera that writes one folder per night, those folders normally *do* hold a
    picture.
    """
    from seestack.io.project import StackRunRow

    lib = Library.create(tmp_path / "lib")
    try:
        ea, pa = lib.create_target("M 31 night 1")
        try:
            _add_frame(pa, exposure_s=10.0, ra=10.7, dec=41.27)
        finally:
            pa.close()
        eb, pb = lib.create_target("M 31 night 2")
        try:
            _add_frame(pb, exposure_s=10.0, ra=10.8, dec=41.30)
            out = pb.project_dir / "output"
            out.mkdir(parents=True, exist_ok=True)
            (out / "master.fits").write_bytes(b"night-two-master")
            (out / "master_preview.png").write_bytes(b"night-two-preview")
            run_id = pb.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-09-02T03:00:00Z",
                output_basename="master",
                fits_path=str(out / "master.fits"), tiff_path=None,
                preview_path=str(out / "master_preview.png"),
                n_frames_used=42, canvas_h=320, canvas_w=480,
                coverage_min=1, coverage_max=42, options_json="{}",
                notes="the picture of night two",
            ))
            pb.set_meta(f"editor_recipe:{run_id}", '{"ops": []}')
        finally:
            pb.close()

        result = lib.merge_targets_result("M_31_night_1", ["M_31_night_2"])
        assert result.frames_added == 1
        assert result.pictures_kept == 1

        # The source folder really is gone — this is not a "we stopped deleting"
        # fix, it is the picture moving out first.
        assert not (lib.targets_dir / "M_31_night_2").exists()

        dproj = lib.open_target("M_31_night_1")
        try:
            runs = list(dproj.iter_stack_runs())
            assert [r.notes for r in runs] == ["the picture of night two"]
            assert runs[0].n_frames_used == 42
            assert Path(runs[0].fits_path).read_bytes() == b"night-two-master"
            assert Path(runs[0].preview_path).read_bytes() == b"night-two-preview"
            assert dproj.get_meta(f"editor_recipe:{runs[0].id}") == '{"ops": []}'
        finally:
            dproj.close()
    finally:
        lib.close()


def test_merge_keeps_the_source_folder_when_its_picture_cannot_be_carried(
        tmp_path, monkeypatch):
    """Deleting the folder is what makes the loss permanent — so if the pictures
    did not make it across, the folder stays. Two library entries and nothing
    lost beats a tidy library and a missing picture."""
    import seestack.io.merge as merge_mod
    from seestack.io.project import StackRunRow

    lib = Library.create(tmp_path / "lib")
    try:
        _, pa = lib.create_target("M 31 night 1")
        try:
            _add_frame(pa, exposure_s=10.0, ra=10.7, dec=41.27)
        finally:
            pa.close()
        _, pb = lib.create_target("M 31 night 2")
        try:
            _add_frame(pb, exposure_s=10.0, ra=10.8, dec=41.30)
            out = pb.project_dir / "output"
            out.mkdir(parents=True, exist_ok=True)
            (out / "master.fits").write_bytes(b"irreplaceable")
            (out / "master_preview.png").write_bytes(b"irreplaceable-preview")
            pb.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-09-02T03:00:00Z",
                output_basename="master", fits_path=str(out / "master.fits"),
                tiff_path=None, preview_path=str(out / "master_preview.png"),
                n_frames_used=5, canvas_h=10, canvas_w=10,
                coverage_min=1, coverage_max=5, options_json="{}",
            ))
        finally:
            pb.close()

        real_copy = merge_mod.shutil.copy2

        def fail_on_the_preview(source, dest, *a, **kw):
            if str(source).endswith("_preview.png"):
                raise OSError(28, "No space left on device")
            return real_copy(source, dest, *a, **kw)

        monkeypatch.setattr(merge_mod.shutil, "copy2", fail_on_the_preview)
        result = lib.merge_targets_result("M_31_night_1", ["M_31_night_2"])

        assert result.pictures_kept == 0
        # The frames still merged — that half succeeded and is not undone.
        assert result.frames_added == 1
        # …and the picture is still exactly where it was.
        assert lib.find_target("M_31_night_2") is not None
        kept = tmp_path / "lib" / "targets" / "M_31_night_2" / "output"
        assert (kept / "master.fits").read_bytes() == b"irreplaceable"
    finally:
        lib.close()


def test_merge_targets_unknown_destination_raises(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        with pytest.raises(FileNotFoundError):
            lib.merge_targets("does_not_exist", ["also_missing"])
    finally:
        lib.close()


def test_angular_separation_haversine_is_symmetric():
    # Sanity: known small angle.
    d = _angular_separation_deg(0.0, 0.0, 0.0, 1.0)
    assert abs(d - 1.0) < 1e-6
    # Symmetric.
    a = _angular_separation_deg(45.0, 30.0, 100.0, -20.0)
    b = _angular_separation_deg(100.0, -20.0, 45.0, 30.0)
    assert abs(a - b) < 1e-9
    # Same point = 0.
    assert _angular_separation_deg(123.4, -5.6, 123.4, -5.6) == 0.0


def test_flag_legacy_mixed_drop_sets_and_persists_the_flag(tmp_path):
    """``flag_legacy_mixed_drop`` marks a target (idempotently) and the flag is
    readable via both ``find_target`` and ``list_targets`` — the signal
    cleanup-suggestions reads to surface a legacy whole-device drop for removal."""
    lib = Library.create(tmp_path / "lib")
    try:
        lib.create_target("MyWorks")
        lib.create_target("M 31")
        assert lib.find_target("MyWorks").legacy_mixed_drop is None

        out = lib.flag_legacy_mixed_drop("MyWorks")
        assert out is not None and out.legacy_mixed_drop == 1
        # Idempotent: flagging again stays 1.
        assert lib.flag_legacy_mixed_drop("MyWorks").legacy_mixed_drop == 1
        # Only the flagged target is affected.
        by_name = {t.name: t for t in lib.list_targets()}
        assert by_name["MyWorks"].legacy_mixed_drop == 1
        assert by_name["M 31"].legacy_mixed_drop is None
        # Unknown target → None, no error.
        assert lib.flag_legacy_mixed_drop("nope") is None
    finally:
        lib.close()


def test_old_library_without_legacy_mixed_drop_column_is_migrated(tmp_path):
    """A registry created before the ``legacy_mixed_drop`` column existed must
    gain it on open (additive migration; §9 live-in-place upgrade), defaulting to
    NULL, and stay fully usable."""
    import sqlite3

    root = tmp_path / "lib"
    root.mkdir()
    (root / "targets").mkdir()
    db = root / "library.sqlite"
    # A v4-style targets table (has cover_stack_run_id, lacks legacy_mixed_drop).
    con = sqlite3.connect(db)
    con.executescript(
        """
        PRAGMA user_version = 4;
        CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, safe_name TEXT NOT NULL UNIQUE,
            ra_deg REAL, dec_deg REAL, created_utc TEXT NOT NULL,
            last_activity_utc TEXT, n_frames INTEGER NOT NULL DEFAULT 0,
            n_frames_accepted INTEGER NOT NULL DEFAULT 0,
            total_exposure_s REAL NOT NULL DEFAULT 0,
            last_stack_preview TEXT, notes TEXT, tags TEXT, cover_stack_run_id INTEGER
        );
        INSERT INTO targets(name, safe_name, created_utc)
            VALUES('MyWorks','MyWorks','2026-01-01T00:00:00Z');
        """
    )
    con.commit()
    con.close()

    lib = Library.open(root)
    try:
        cols = {r["name"] for r in lib._conn.execute("PRAGMA table_info(targets)")}
        assert "legacy_mixed_drop" in cols
        entry = lib.find_target("MyWorks")
        assert entry is not None and entry.legacy_mixed_drop is None
        # And it's usable after migration.
        assert lib.flag_legacy_mixed_drop("MyWorks").legacy_mixed_drop == 1
    finally:
        lib.close()


# ---- registry centre of a mosaic ------------------------------------------
#
# A 2x2 Seestar S30 mosaic of M31 (1.20° x 2.13° panels, 15 % overlap). The
# per-axis median over the subs lands on a *panel* as soon as one panel holds one
# more sub than the others — 1.04° from the mosaic's middle, outside the life
# list's match radius — so the registry centre has to come from the panels.

_M31 = (10.6847, 41.2690)


def _add_mosaic(proj: Project, centre: tuple[float, float],
                counts: list[int], *, cols: int = 2) -> None:
    import math
    ra0, dec0 = centre
    step_dec = 2.13 * 0.85
    step_ra = 1.20 * 0.85 / math.cos(math.radians(dec0))
    rows = math.ceil(len(counts) / cols)
    for p, n in enumerate(counts):
        c, r = p % cols, p // cols
        ra = ra0 + (c - (cols - 1) / 2) * step_ra
        dec = dec0 + (r - (rows - 1) / 2) * step_dec
        for k in range(n):
            # A dither of a few arc-minutes around the panel's pointing.
            _add_frame(proj, exposure_s=10.0,
                       ra=(ra + 0.02 * ((k % 5) - 2)) % 360.0,
                       dec=dec + 0.02 * ((k % 3) - 1))


@pytest.mark.parametrize("counts", [[25, 25, 25, 26], [30, 28, 27, 25], [25, 25, 25, 25]])
def test_mosaic_registry_centre_is_the_panels_middle_not_one_panel(tmp_path, counts):
    from seestack.lifelist import catalog_capture_status
    from seestack.nightplan import CatalogObject

    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("M 31")
        try:
            _add_mosaic(proj, _M31, counts)
        finally:
            proj.close()
        refreshed = lib.refresh_target_stats("M_31")
        assert refreshed is not None
        off = _angular_separation_deg(float(refreshed.ra_deg), float(refreshed.dec_deg), *_M31)
        assert off < 0.1, f"registry centre {off:.2f}° from the mosaic's middle"
        m31 = CatalogObject(id="M31", name="Andromeda Galaxy", ra_deg=_M31[0],
                            dec_deg=_M31[1], type="Galaxy", con="And")
        [status] = catalog_capture_status([m31], lib.list_targets())
        assert status.captured
    finally:
        lib.close()


def test_single_field_registry_centre_is_unchanged_median(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("M 42")
        try:
            for k in range(40):
                _add_frame(proj, exposure_s=10.0, ra=83.82 + 0.013 * (k % 7),
                           dec=-5.39 + 0.011 * (k % 4))
        finally:
            proj.close()
        refreshed = lib.refresh_target_stats("M_42")
        import numpy as np
        ras = [83.82 + 0.013 * (k % 7) for k in range(40)]
        decs = [-5.39 + 0.011 * (k % 4) for k in range(40)]
        assert float(refreshed.ra_deg) == pytest.approx(float(np.median(ras)), abs=1e-9)
        assert float(refreshed.dec_deg) == pytest.approx(float(np.median(decs)), abs=1e-9)
    finally:
        lib.close()


def test_mixed_objects_keep_the_centre_on_the_majority_object(tmp_path):
    """Two different objects ~10° apart in one target: the centre stays on the
    bigger one, not in the empty sky between them."""
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("M 31")
        try:
            _add_mosaic(proj, _M31, [25, 25, 25, 26])
            _add_mosaic(proj, (23.46, 30.66), [40], cols=1)  # M33
        finally:
            proj.close()
        refreshed = lib.refresh_target_stats("M_31")
        off = _angular_separation_deg(float(refreshed.ra_deg), float(refreshed.dec_deg), *_M31)
        assert off < 0.1
    finally:
        lib.close()


def test_mosaic_centre_across_ra_zero(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("Seam")
        try:
            _add_mosaic(proj, (0.2, 20.0), [26, 25, 25, 25])
        finally:
            proj.close()
        refreshed = lib.refresh_target_stats("Seam")
        assert 0.0 <= float(refreshed.ra_deg) < 360.0
        off = _angular_separation_deg(float(refreshed.ra_deg), float(refreshed.dec_deg), 0.2, 20.0)
        assert off < 0.1
    finally:
        lib.close()


# ---- the target's own field on the registry (life list match radius) -------
#
# The life list's 0.35° match radius was sized for an S50 frame; the owner shoots
# an S30, whose ~2.1° x 1.2° field holds M32 (0.40° from M31) in every M31 frame.
# The registry now carries the short side of the field the target's own solved
# subs measured, and the life list matches inside it.


def _add_solved_field(proj: Project, centre: tuple[float, float], *, n: int,
                      pixscale: float, width: int, height: int) -> None:
    for k in range(n):
        _counter[0] += 1
        proj.add_frame(FrameRow(
            source_path=f"f_{_counter[0]}.fit", exposure_s=10.0,
            ra_center_deg=centre[0] + 0.01 * ((k % 5) - 2),
            dec_center_deg=centre[1] + 0.01 * ((k % 3) - 1),
            pixscale_arcsec=pixscale, width_px=width, height_px=height,
            accept=True,
        ))


@pytest.mark.parametrize(
    "scope, pixscale, width, height, short_deg, m32_captured",
    [
        # Seestar S30: 150 mm, 2.9 µm, 1920 x 1080 — the owner's scope.
        ("S30", 3.99, 1920, 1080, 1.197, True),
        # Seestar S50: 250 mm, 2.9 µm, 1080 x 1920 portrait — unchanged behaviour.
        ("S50", 2.39, 1080, 1920, 0.717, False),
    ],
)
def test_life_list_matches_inside_the_targets_own_field(
        tmp_path, scope, pixscale, width, height, short_deg, m32_captured):
    from seestack.lifelist import catalog_capture_status
    from seestack.nightplan import load_catalog

    cat = [o for o in load_catalog() if o.id in ("M31", "M32", "M110")]
    m31 = next(o for o in cat if o.id == "M31")
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("M 31")
        try:
            _add_solved_field(proj, (m31.ra_deg, m31.dec_deg), n=30,
                              pixscale=pixscale, width=width, height=height)
        finally:
            proj.close()
        refreshed = lib.refresh_target_stats("M_31")
        assert refreshed.frame_short_deg == pytest.approx(short_deg, abs=0.005)
        assert lib.find_target("M_31").frame_short_deg == refreshed.frame_short_deg
        status = {e.catalog_id: e for e in catalog_capture_status(cat, lib.list_targets())}
        assert status["M31"].captured
        assert status["M32"].captured is m32_captured, scope
        # M110 sits 0.61° off — past even the S30's inscribed margin, so a
        # neighbour that may be outside a rotated frame is still never claimed.
        assert not status["M110"].captured
    finally:
        lib.close()


def test_unsolved_target_has_no_field_and_a_refresh_keeps_a_known_one(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("M 31")
        try:
            _add_frame(proj, exposure_s=10.0, ra=_M31[0], dec=_M31[1])
        finally:
            proj.close()
        assert lib.refresh_target_stats("M_31").frame_short_deg is None
        proj = lib.open_target("M_31")
        try:
            _add_solved_field(proj, _M31, n=3, pixscale=3.99, width=1920, height=1080)
        finally:
            proj.close()
        assert lib.refresh_target_stats("M_31").frame_short_deg == pytest.approx(1.197, abs=0.005)
    finally:
        lib.close()


def test_v5_registry_without_frame_short_deg_upgrades_in_place(tmp_path):
    """A registry written before the column existed opens, gains it as NULL and
    keeps every row — the life list then falls back to the old floor."""
    import sqlite3

    root = tmp_path / "lib"
    root.mkdir()
    con = sqlite3.connect(root / "library.sqlite")
    con.executescript(
        """
        PRAGMA user_version = 5;
        CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, safe_name TEXT NOT NULL UNIQUE,
            ra_deg REAL, dec_deg REAL, created_utc TEXT NOT NULL,
            last_activity_utc TEXT, n_frames INTEGER NOT NULL DEFAULT 0,
            n_frames_accepted INTEGER NOT NULL DEFAULT 0,
            total_exposure_s REAL NOT NULL DEFAULT 0,
            last_stack_preview TEXT, notes TEXT, tags TEXT, cover_stack_run_id INTEGER,
            legacy_mixed_drop INTEGER, folder_name TEXT
        );
        INSERT INTO targets(name, safe_name, ra_deg, dec_deg, created_utc, n_frames)
            VALUES('M 31','M_31',10.685,41.269,'2026-01-01T00:00:00Z',5);
        """
    )
    con.commit()
    con.close()

    lib = Library.open(root)
    try:
        cols = {r["name"] for r in lib._conn.execute("PRAGMA table_info(targets)")}
        assert "frame_short_deg" in cols
        assert "panel_footprint" in cols
        entry = lib.find_target("M_31")
        assert entry is not None and entry.frame_short_deg is None
        assert entry.panel_footprint is None
        assert entry.n_frames == 5 and entry.ra_deg == pytest.approx(10.685)
    finally:
        lib.close()


# ---- a mosaic is judged against its own panels (life list) -----------------
#
# One frame's circle around a mosaic's middle answers a whole-target question
# with a per-panel number: the Lagoon + Trifid 2x2 left M20 grey, and a 2x2 with
# one panel never shot claimed sky in that missing quadrant. The registry now
# stamps the panels themselves and the life list asks "is it inside a panel?".


def _add_s30_mosaic(proj: Project, centre: tuple[float, float], cols: int, rows: int,
                    *, overlap: float = 0.15, n: int = 40, skip: tuple = (),
                    rotation: float | None = 0.0,
                    repoint: dict | None = None) -> None:
    """S30 portrait subs (3.99″/px, 1080 x 1920 — 1.197° E-W x 2.128° N-S at
    rotation 0) on a ``cols`` x ``rows`` grid, with a small dither and a ±1°
    spread of solved rotation; ``skip`` lists ``(col, row)`` panels never shot
    (col grows east, row north); ``repoint`` maps a ``(col, row)`` panel to a
    northward shift (degrees) its second half of subs took — a second night."""
    import math
    ra0, dec0 = centre
    step_ra = 1.197 * (1 - overlap) / math.cos(math.radians(dec0))
    step_dec = 2.128 * (1 - overlap)
    for r in range(rows):
        for c in range(cols):
            if (c, r) in skip:
                continue
            ra = ra0 + (c - (cols - 1) / 2) * step_ra
            dec = dec0 + (r - (rows - 1) / 2) * step_dec
            for k in range(n):
                _counter[0] += 1
                proj.add_frame(FrameRow(
                    source_path=f"f_{_counter[0]}.fit", exposure_s=10.0,
                    ra_center_deg=(ra + 0.02 * ((k % 5) - 2)) % 360.0,
                    dec_center_deg=(dec + 0.02 * ((k % 3) - 1)
                                    + ((repoint or {}).get((c, r), 0.0)
                                       if k >= n // 2 else 0.0)),
                    pixscale_arcsec=3.99, width_px=1080, height_px=1920,
                    rotation_deg=(None if rotation is None
                                  else rotation + ((k % 7) - 3) / 3.0),
                    accept=True,
                ))


def _life_list_for(tmp_path, centre, cols, rows, ids, **kw):
    from seestack.lifelist import catalog_capture_status
    from seestack.nightplan import load_catalog

    by_id = {o.id: o for o in load_catalog()}
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("Mosaic")
        try:
            _add_s30_mosaic(proj, centre, cols, rows, **kw)
        finally:
            proj.close()
        entry = lib.refresh_target_stats("Mosaic")
        status = catalog_capture_status([by_id[i] for i in ids], lib.list_targets())
        return entry, {e.catalog_id: e.captured for e in status}
    finally:
        lib.close()


def _catalog_centre(cid: str) -> tuple[float, float]:
    from seestack.nightplan import load_catalog
    obj = next(o for o in load_catalog() if o.id == cid)
    return obj.ra_deg, obj.dec_deg


@pytest.mark.parametrize("centre_id, cols, rows, lit, grey", [
    # The classic Lagoon + Trifid 2x2: M20 is 1.38° off the middle, in a panel.
    ("M8", 2, 2, ["M8", "M20"], ["M28"]),
    # Markarian's Chain 3x3: M87 (1.49°) and M99 (2.15°) are in its outer panels.
    ("M84", 3, 3, ["M84", "M86", "M87", "M99"], ["M88", "M100"]),
    # M31 2x2: M110 (0.61°) is in a panel; M33 is 15° away.
    ("M31", 2, 2, ["M31", "M32", "M110"], ["M33"]),
])
def test_life_list_lights_what_any_mosaic_panel_holds(tmp_path, centre_id, cols, rows,
                                                       lit, grey):
    entry, captured = _life_list_for(tmp_path, _catalog_centre(centre_id), cols, rows,
                                     lit + grey)
    assert entry.panel_footprint is not None
    assert [i for i in lit if not captured[i]] == []
    assert [i for i in grey if captured[i]] == []


@pytest.mark.parametrize("repoint", [None, {(1, 1): 0.15}, {(1, 1): 0.25}],
                         ids=["all-tight", "ne-repointed", "ne-capped"])
def test_one_wobbly_panel_does_not_grey_what_a_tight_panel_holds(tmp_path, repoint):
    """Each panel is kept clear of the edges by its *own* subs' spread. A single
    mosaic-wide margin — the worst panel's — greyed an object 0.07° inside the
    south-west panel's west edge as soon as the north-east panel took a second
    night 0.15° off, though the south-west panel's subs never moved and the
    object is in every one of them. The re-pointed panel still asks its own,
    wider margin: an object as close to *its* east edge stays grey."""
    import math

    from seestack.lifelist import catalog_capture_status
    from seestack.nightplan import CatalogObject

    ra0, dec0 = 150.0, 30.0
    step_ra = 1.197 * 0.85 / math.cos(math.radians(dec0))
    step_dec = 2.128 * 0.85
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("W")
        try:
            _add_s30_mosaic(proj, (ra0, dec0), 2, 2, repoint=repoint)
        finally:
            proj.close()
        entry = lib.refresh_target_stats("W")

        def near_edge(cid: str, col: int, row: int, east: bool) -> CatalogObject:
            dec = dec0 + (row - 0.5) * step_dec
            ra = (ra0 + (col - 0.5) * step_ra
                  + (1 if east else -1) * (1.197 / 2 - 0.07) / math.cos(math.radians(dec)))
            return CatalogObject(id=cid, name="", type="Gx", con="", ra_deg=ra,
                                 dec_deg=dec, size_arcmin=1.0,
                                 blurb="")

        sw = near_edge("SW", 0, 0, east=False)
        ne = near_edge("NE", 1, 1, east=True)
        status = {e.catalog_id: e.captured
                  for e in catalog_capture_status([sw, ne], lib.list_targets())}
        assert entry.panel_footprint is not None
        assert status["SW"] is True
        assert status["NE"] is (repoint is None)
    finally:
        lib.close()


def test_life_list_never_claims_the_quadrant_an_l_shaped_mosaic_never_shot(tmp_path):
    """A 2x2 at 10 % overlap with its north-east panel absent keeps its centre at
    the 2x2 middle; one frame's circle there reached 0.40° into the missing
    quadrant and called an object there captured."""
    import math

    from seestack.lifelist import catalog_capture_status
    from seestack.nightplan import CatalogObject

    centre = (150.0, 30.0)
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("L")
        try:
            _add_s30_mosaic(proj, centre, 2, 2, overlap=0.10, skip=((1, 1),))
        finally:
            proj.close()
        entry = lib.refresh_target_stats("L")
        assert _angular_separation_deg(float(entry.ra_deg), float(entry.dec_deg),
                                       *centre) < 0.05
        d = 0.40 / math.sqrt(2)
        cos_dec = math.cos(math.radians(centre[1]))
        objs = [
            # 0.40° into the never-shot north-east quadrant.
            CatalogObject(id="NE", name="", ra_deg=centre[0] + d / cos_dec,
                          dec_deg=centre[1] + d, type="Galaxy", con="Leo"),
            # The same distance into the shot south-west one.
            CatalogObject(id="SW", name="", ra_deg=centre[0] - d / cos_dec,
                          dec_deg=centre[1] - d, type="Galaxy", con="Leo"),
            # Just past the west edge of the western panels.
            CatalogObject(id="W", name="", type="Galaxy", con="Leo",
                          ra_deg=centre[0] - (1.197 * 0.9 / 2 + 1.197 / 2 + 0.05) / cos_dec,
                          dec_deg=centre[1] - 0.5),
        ]
        captured = {e.catalog_id: e.captured
                    for e in catalog_capture_status(objs, lib.list_targets())}
        assert captured == {"NE": False, "SW": True, "W": False}
    finally:
        lib.close()


def test_a_single_field_and_an_unknown_rotation_keep_the_one_circle(tmp_path):
    """No panel split, or panels whose rotation was never solved: no footprint,
    so the life list matches exactly as v0.502.2 did — M110 stays grey beside a
    single S30 M31 field."""
    entry, captured = _life_list_for(tmp_path / "a", _M31, 1, 1, ["M31", "M32", "M110"])
    assert entry.panel_footprint is None
    assert captured == {"M31": True, "M32": True, "M110": False}

    entry, captured = _life_list_for(tmp_path / "b", _M31, 2, 2, ["M31", "M110"],
                                     rotation=None)
    assert entry.panel_footprint is None
    assert captured == {"M31": True, "M110": False}


def test_panel_footprint_is_restamped_on_every_refresh(tmp_path):
    """Unlike the field size it is not COALESCEd: frames dropped down to one
    panel must not leave the old mosaic's footprint claiming its sky."""
    lib = Library.create(tmp_path / "lib")
    try:
        _entry, proj = lib.create_target("M 31")
        try:
            _add_s30_mosaic(proj, _M31, 2, 1)
        finally:
            proj.close()
        assert lib.refresh_target_stats("M_31").panel_footprint is not None
        proj = lib.open_target("M_31")
        try:
            for f in list(proj.iter_frames()):
                if f.ra_center_deg > _M31[0]:
                    proj.update_frame(f.id, accept=False)
        finally:
            proj.close()
        assert lib.refresh_target_stats("M_31").panel_footprint is None
    finally:
        lib.close()
