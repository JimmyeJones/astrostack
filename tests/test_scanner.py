"""
Folder scanner: organise a tree of Seestar sub-folders into library targets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.ingest import find_fits_files
from seestack.io.library import Library
from seestack.io.project import REJECT_REASON_SEESTAR_OUTPUT, FrameRow, Project
from seestack.io.scanner import (
    _apply_seestar_convention,
    _ingest_into_target,
    _seestar_output_bases,
    classify_seestar_junk_target,
    container_target_children,
    duplicate_sub_base_name_from_name,
    duplicate_sub_target_base_name,
    is_capture_mode_target_name,
    is_mosaic_target_name,
    is_temp_folder_target_name,
    junk_output_frame_cap,
    mosaic_target_name,
    run_qc_and_solve,
    scan_and_organize,
)
from tests.synth import write_seestar_fits


def _seestar_tree(root: Path) -> Path:
    """
    Build a fake Seestar dump:

      root/
        M 42/Light_001.fit, Light_002.fit
        Andromeda/sub/Light_001.fit         (nested — mosaic-style)
        Empty/                              (no FITS — ignored)
        loose_a.fit, loose_b.fit            (loose in root → Unsorted)
    """
    root.mkdir(parents=True, exist_ok=True)
    m42 = root / "M 42"
    m42.mkdir()
    write_seestar_fits(m42 / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(m42 / "Light_002.fit", n_stars=5, seed=2)

    andromeda_sub = root / "Andromeda" / "sub"
    andromeda_sub.mkdir(parents=True)
    write_seestar_fits(andromeda_sub / "Light_001.fit", n_stars=5, seed=3)

    (root / "Empty").mkdir()

    write_seestar_fits(root / "loose_a.fit", n_stars=5, seed=4)
    write_seestar_fits(root / "loose_b.fit", n_stars=5, seed=5)
    return root


def test_scan_organizes_folders_into_targets(tmp_path):
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        names = {t.safe_name for t in result.targets}
        # One target per sub-folder with FITS, plus Unsorted for loose files.
        # The empty folder produces no target.
        assert names == {"M_42", "Andromeda", "Unsorted"}

        by_name = {t.safe_name: t for t in result.targets}
        assert by_name["M_42"].n_frames_added == 2
        # Nested files inside a sub-folder still belong to that one target.
        assert by_name["Andromeda"].n_frames_added == 1
        assert by_name["Unsorted"].n_frames_added == 2
        assert result.total_added == 5

        # Registry reflects it.
        assert {t.safe_name for t in lib.list_targets()} == {
            "M_42", "Andromeda", "Unsorted",
        }
        m42 = lib.find_target("M_42")
        assert m42 is not None and m42.n_frames == 2
    finally:
        lib.close()


def _fake(*names: str) -> list:
    """Build ``[(name, [Path]), ...]`` units for the pure-classifier test."""
    return [(n, [Path(f"{n}/x.fit")]) for n in names]


def test_apply_seestar_convention_maps_sub_and_skips_output_and_video():
    """The pure folder-classifier: raw '_sub' folders become targets, the
    Seestar's own output sibling and any '*_video' folder are skipped, and a
    mosaic gets its own '(mosaic)' target distinct from the single field."""
    units = _apply_seestar_convention(_fake(
        "M 31_sub", "M 31",                 # raw subs + on-device output
        "M 3_mosaic_sub", "M 3_mosaic",     # mosaic raw subs + mosaic output
        "M 3",                              # single-field output, but no _sub
        "Lunar_video", "Solar_video",       # videos
    ))
    names = [n for n, _ in units]
    # "M 31_sub" -> "M 31"; its bare "M 31" output is skipped.
    # "M 3_mosaic_sub" -> "M 3 (mosaic)"; its "M 3_mosaic" output is skipped.
    # bare "M 3" (no "M 3_sub" sibling) still ingests. Videos are gone.
    assert names == ["M 31", "M 3 (mosaic)", "M 3"]


def test_apply_seestar_convention_bare_folder_without_sub_sibling_kept():
    """A plainly-named folder with no '_sub' sibling is a non-Seestar layout
    and must still ingest exactly as before (no regression)."""
    units = _apply_seestar_convention(_fake("Andromeda", "M 42"))
    assert [n for n, _ in units] == ["Andromeda", "M 42"]


def test_apply_seestar_convention_is_case_insensitive():
    """Folder casing varies across firmware; suffix tests ignore case but the
    target name keeps the folder's original casing."""
    units = _apply_seestar_convention(_fake("Ngc 7000_SUB", "Ngc 7000", "Clip_VIDEO"))
    assert [n for n, _ in units] == ["Ngc 7000"]


def test_apply_seestar_convention_sibling_skip_is_parent_scoped():
    """The bare-``<T>``-is-output skip must fire only when the ``<T>_sub`` sibling
    shares the *same parent*. A ``<T>_sub`` under an unrelated parent (e.g. a
    container-expanded drop) must NOT cause a root-level bare ``<T>`` of real subs
    to be dropped — that silently loses a whole session's frames."""
    # M31 (root) is a real folder of subs; M31_sub lives under a *different*
    # parent (an expanded container). M31 must survive.
    units = _apply_seestar_convention(
        [("M31", ["/inc/M31/a.fit"]), ("M31_sub", ["/inc/MyWorks/M31_sub/b.fit"])],
        parents=["/inc", "/inc/MyWorks"],
    )
    names = [n for n, _ in units]
    assert "M31" in names  # root subs kept, not skipped as output
    # Both fold to the same target "M31", so both units are named "M31".
    assert names.count("M31") == 2


def test_apply_seestar_convention_sibling_skip_fires_for_true_sibling():
    """The same-parent output skip must still fire (no regression): a bare
    ``<T>`` beside its ``<T>_sub`` under the same parent is the on-device output
    and is skipped."""
    units = _apply_seestar_convention(
        [("M31_sub", ["/inc/M31_sub/a.fit"]), ("M31", ["/inc/M31/out.fit"])],
        parents=["/inc", "/inc"],
    )
    # M31_sub -> "M31"; the sibling bare "M31" output is skipped.
    assert [n for n, _ in units] == ["M31"]


def test_classify_junk_video_by_target_name():
    """A target named '<T>_video' is a Seestar video capture — flagged as junk
    regardless of what its frames' source folders look like (no disk needed)."""
    v = classify_seestar_junk_target("Lunar_video", [], n_frames=30)
    assert v is not None and v.reason == "video"
    # Case-insensitive on the suffix.
    assert classify_seestar_junk_target("Clip_VIDEO", [], 5) is not None


def test_classify_junk_video_by_source_folder(tmp_path):
    """Even without a '_video' target name, frames sourced entirely from a
    '*_video' folder are a video capture."""
    vid = tmp_path / "Solar_video"
    vid.mkdir()
    paths = [str(vid / "f001.fit"), str(vid / "f002.fit")]
    v = classify_seestar_junk_target("Solar", paths, n_frames=2)
    assert v is not None and v.reason == "video"


def test_apply_seestar_convention_skips_photo_folders():
    """The Seestar writes single-shot stills into '*_photo/' folders
    ('Planetary_photo/', 'Scenery_photo/') beside the '*_video/' ones. They hold
    no stackable deep-sky subs, so they must be skipped exactly like videos —
    before this they fell through every rule and ingested as junk targets."""
    units = _apply_seestar_convention(_fake(
        "M 31_sub", "M 31",                          # real target + its output
        "Planetary_photo", "Scenery_photo",          # single-shot stills
        "Planetary_video", "Scenery_video",          # video captures
    ))
    assert [n for n, _ in units] == ["M 31"]
    # Case-insensitive, like every other suffix test.
    assert _apply_seestar_convention(_fake("Scenery_PHOTO")) == []


def test_classify_junk_photo_by_target_name():
    """A library that already ingested a '*_photo' folder (any older build, or
    an older scan) gets a cleanup nudge, with wording that names stills rather
    than claiming it is a video."""
    v = classify_seestar_junk_target("Scenery_photo", [], n_frames=40)
    assert v is not None and v.reason == "photo"
    assert "photo" in v.detail and "video" not in v.detail
    assert classify_seestar_junk_target("Planetary_PHOTO", [], 5) is not None


def test_classify_junk_photo_by_source_folder(tmp_path):
    """Even under a different target name, frames sourced entirely from a
    '*_photo' folder are single stills, not subs."""
    photos = tmp_path / "Planetary_photo"
    photos.mkdir()
    paths = [str(photos / "IMG_001.fit"), str(photos / "IMG_002.fit")]
    v = classify_seestar_junk_target("Jupiter", paths, n_frames=2)
    assert v is not None and v.reason == "photo"


def test_is_capture_mode_target_name_covers_both_and_nothing_else():
    """The shared name test the cleanup endpoint uses to decide by name alone,
    before paying to open a target's project."""
    assert is_capture_mode_target_name("Lunar_video")
    assert is_capture_mode_target_name("  Scenery_PHOTO  ")
    assert not is_capture_mode_target_name("M 31")
    assert not is_capture_mode_target_name("M 31_sub")


def test_classify_junk_on_device_output_when_sub_sibling_present(tmp_path):
    """A 1-frame target whose sole frame sits in a bare '<T>/' folder that has a
    raw-subs '<T>_sub/' sibling on disk is the Seestar's own stacked output."""
    (tmp_path / "M 31_sub").mkdir()          # the raw-subs sibling
    output = tmp_path / "M 31"               # the on-device output folder
    output.mkdir()
    v = classify_seestar_junk_target(
        "M 31", [str(output / "Stacked.fit")], n_frames=1)
    assert v is not None and v.reason == "on_device_output"
    assert "M 31_sub" in v.detail


def test_classify_junk_mosaic_output_when_mosaic_sub_sibling_present(tmp_path):
    """The '<name>_sub' sibling test also covers a mosaic output '<T>_mosaic/'
    beside its '<T>_mosaic_sub/' raw subs."""
    (tmp_path / "M 3_mosaic_sub").mkdir()
    output = tmp_path / "M 3_mosaic"
    output.mkdir()
    v = classify_seestar_junk_target(
        "M 3_mosaic", [str(output / "Stacked.fit")], n_frames=1)
    assert v is not None and v.reason == "on_device_output"


def test_classify_junk_multi_panel_mosaic_output(tmp_path):
    """A mosaic's on-device output is one stacked image **per panel**, not one
    image, so the single-field ≤2-frame cap never even looked at it. The owner's
    real library proves it: ``M 44_MOSAIC`` holds 11 frames and
    ``NGC 6960_MOSAIC`` 7, and both lingered as junk targets forever."""
    (tmp_path / "M 44_mosaic_sub").mkdir()          # the raw-subs sibling
    output = tmp_path / "M 44_mosaic"
    output.mkdir()
    panels = [str(output / f"Stacked_{i:02d}.fit") for i in range(11)]
    v = classify_seestar_junk_target("M 44_mosaic", panels, n_frames=11)
    assert v is not None and v.reason == "on_device_output"
    # The wording must not claim it is one image when there are eleven.
    assert "panel" in v.detail and "single stacked image" not in v.detail


def test_classify_not_junk_for_a_real_mosaic_stack(tmp_path):
    """The looser mosaic cap must stay far below any real target: a mosaic's raw
    subs number in the hundreds/thousands, so a big one is never flagged."""
    (tmp_path / "M 44_mosaic_sub").mkdir()
    output = tmp_path / "M 44_mosaic"
    output.mkdir()
    paths = [str(output / f"Light_{i:04d}.fit") for i in range(400)]
    assert classify_seestar_junk_target("M 44_mosaic", paths, n_frames=400) is None


def test_classify_junk_temp_folder_by_target_name():
    """``batch_stack_tmp`` in the owner's real share is some other program's
    scratch folder living in ``\\\\TRUENAS\\astro``; it has no ``_sub`` sibling, so
    it ingests as an ordinary target and lingers as a junk tile. Decided by name
    at any frame count — a temp folder holds whatever that run was mid-way
    through, so its size says nothing."""
    v = classify_seestar_junk_target("batch_stack_tmp", [], n_frames=137)
    assert v is not None and v.reason == "temp_folder"
    assert "batch_stack_tmp" in v.detail
    # Case-insensitive and whitespace-tolerant, like every other name test.
    assert classify_seestar_junk_target("  Batch_Stack_TMP ", [], 1) is not None


def test_classify_junk_temp_folder_by_source_folder(tmp_path):
    """Even under a different target name, frames sourced entirely from a
    scratch folder are that program's leftovers."""
    scratch = tmp_path / "batch_stack_tmp"
    scratch.mkdir()
    paths = [str(scratch / f"f{i:03d}.fit") for i in range(9)]
    v = classify_seestar_junk_target("Some Target", paths, n_frames=9)
    assert v is not None and v.reason == "temp_folder"


def test_classify_not_junk_for_a_real_target_that_merely_sounds_temporary():
    """The list is EXACT names, not a ``*_tmp`` pattern — a real folder someone
    named badly must never be condemned by shape alone (AGENTS.md §1: no blind
    guessing on the on-by-default ingest path)."""
    assert not is_temp_folder_target_name("M 31_tmp")
    assert not is_temp_folder_target_name("tmp")
    assert not is_temp_folder_target_name("batch_stack_tmp_sub")
    assert classify_seestar_junk_target("NGC 7000_tmp", [], n_frames=500) is None


def test_is_temp_folder_target_name_matches_only_the_listed_names():
    """The shared name test the cleanup endpoint uses to decide by name alone,
    before paying to open a target's project."""
    assert is_temp_folder_target_name("batch_stack_tmp")
    assert is_temp_folder_target_name("  BATCH_STACK_TMP  ")
    assert not is_temp_folder_target_name("M 31")
    assert not is_temp_folder_target_name("M 31_sub")


def test_junk_output_frame_cap_is_looser_only_for_a_mosaic():
    """The shared cap the cleanup endpoint prefilters on, so it can skip opening
    a big target's project without keeping its own copy of the limit."""
    assert junk_output_frame_cap("M 31") == 2
    assert junk_output_frame_cap("M 44_mosaic") > 2
    # A mosaic's *raw subs* folder is not an output folder — no loosening there.
    assert junk_output_frame_cap("M 44_mosaic_sub") == 2


def test_classify_not_junk_without_a_sub_sibling(tmp_path):
    """A bare output folder with NO '_sub' sibling is a non-Seestar layout the
    scanner keeps — it must not be flagged (no false positive)."""
    output = tmp_path / "Andromeda"
    output.mkdir()
    v = classify_seestar_junk_target(
        "Andromeda", [str(output / "img.fit")], n_frames=1)
    assert v is None


def test_classify_not_junk_when_the_target_is_the_raw_subs(tmp_path):
    """The raw-subs folder itself ('<T>_sub/') is the real data — never junk,
    even though its own name would form a spurious '<T>_sub_sub' sibling."""
    subs = tmp_path / "M 31_sub"
    subs.mkdir()
    v = classify_seestar_junk_target(
        "M 31", [str(subs / "Light_001.fit")], n_frames=1)
    assert v is None


def test_classify_not_junk_for_a_real_stack_with_many_frames(tmp_path):
    """A genuine light-frame stack has many subs; even sitting beside a '_sub'
    sibling it is above the 1-frame-output threshold and never flagged."""
    (tmp_path / "M 31_sub").mkdir()
    output = tmp_path / "M 31"
    output.mkdir()
    paths = [str(output / f"Light_{i:03d}.fit") for i in range(50)]
    v = classify_seestar_junk_target("M 31", paths, n_frames=50)
    assert v is None


def test_classify_not_junk_for_an_empty_frameless_target():
    """No source paths and a non-video name → nothing to judge → None."""
    assert classify_seestar_junk_target("M 42", [], n_frames=0) is None


def test_duplicate_sub_base_name_recognises_a_sub_named_duplicate():
    """A ``<T>_sub``-named target whose frames all sit under a ``*_sub/`` folder →
    the base name ``<T>`` (the target the convention now folds those subs into)."""
    subs = [Path(f"/dump/M 31_sub/Light_{i:03d}.fit") for i in range(6)]
    assert duplicate_sub_target_base_name("M 31_sub", subs) == "M 31"


def test_duplicate_sub_base_name_is_none_without_a_sub_name():
    """A plainly-named target is never a ``_sub`` duplicate."""
    subs = [Path(f"/dump/M 31_sub/Light_{i:03d}.fit") for i in range(6)]
    assert duplicate_sub_target_base_name("M 31", subs) is None


def test_duplicate_sub_base_name_is_none_when_frames_not_under_a_sub_folder():
    """The name ends ``_sub`` but the frames live in a plainly-named folder — not
    the Seestar raw-subs shape, so don't call it a duplicate."""
    subs = [Path(f"/dump/Weird/Light_{i:03d}.fit") for i in range(6)]
    assert duplicate_sub_target_base_name("Weird_sub", subs) is None


def test_duplicate_sub_base_name_is_none_for_mixed_source_folders():
    """Frames spread across more than one folder don't fit the single-folder
    ``<T>_sub/`` shape."""
    subs = [Path("/dump/M 31_sub/a.fit"), Path("/dump/other_sub/b.fit")]
    assert duplicate_sub_target_base_name("M 31_sub", subs) is None


def test_duplicate_sub_base_name_maps_mosaic_sub_to_the_mosaic_target():
    """A ``<T>_mosaic_sub``-named leftover duplicates the ``<T> (mosaic)`` target
    the convention builds from that folder — NOT the single-field ``<T>``, whose
    footprint is different. (This used to return ``None``: the mosaic case was
    deferred as "device-specific", and the owner's library has three of them —
    ``M 3_MOSAIC_SUB``, ``M 44_MOSAIC_SUB``, ``NGC 6960_MOSAIC_SUB`` — with no
    cleanup path at all.)"""
    subs = [Path("/dump/M 3_mosaic_sub/a.fit"), Path("/dump/M 3_mosaic_sub/b.fit")]
    assert duplicate_sub_target_base_name("M 3_mosaic_sub", subs) == "M 3 (mosaic)"


def test_duplicate_sub_base_name_from_name_matches_the_convention():
    """The pure name-shape half, and the property that matters: the base it names
    is exactly the target ``_apply_seestar_convention`` builds from that folder,
    so the duplicate detector and the scanner can never disagree."""
    assert duplicate_sub_base_name_from_name("M 31_sub") == "M 31"
    assert duplicate_sub_base_name_from_name("M 3_mosaic_sub") == "M 3 (mosaic)"
    assert duplicate_sub_base_name_from_name("M 31") is None
    assert duplicate_sub_base_name_from_name("_sub") is None
    for folder in ("M 31_sub", "M 3_mosaic_sub"):
        [(built, _)] = _apply_seestar_convention(_fake(folder))
        assert duplicate_sub_base_name_from_name(folder) == built


def test_is_mosaic_target_name_recognises_what_the_convention_builds():
    """Anything that groups targets by *where they point* needs this: a mosaic
    and the single field of the same object share a centre but not a canvas, and
    the convention keeps them apart on purpose. Asserted against the name the
    convention actually builds, so the spelling has one definition."""
    [(built, _)] = _apply_seestar_convention(_fake("M 44_mosaic_sub"))
    assert is_mosaic_target_name(built)
    assert is_mosaic_target_name("M 44 night 2 (MOSAIC)")
    assert not is_mosaic_target_name("M 44")
    # The device's own output folder is not the mosaic *target* — different name,
    # and it is junk rather than a target to keep clustered with the mosaic.
    assert not is_mosaic_target_name("M 44_mosaic")


def test_duplicate_sub_base_name_is_none_with_no_frames():
    """No source paths → no single ``*_sub/`` folder to key on → None."""
    assert duplicate_sub_target_base_name("M 31_sub", []) is None


def test_scan_is_seestar_aware_end_to_end(tmp_path):
    """A realistic Seestar dump produces exactly the two real targets — one
    single-field, one mosaic — with the raw subs, and NO junk target from the
    on-device output or video folders."""
    scan_root = tmp_path / "incoming"
    (scan_root / "M 3_sub").mkdir(parents=True)
    write_seestar_fits(scan_root / "M 3_sub" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(scan_root / "M 3_sub" / "Light_002.fit", n_stars=5, seed=2)
    write_seestar_fits(scan_root / "M 3_sub" / "Light_003.fit", n_stars=5, seed=3)
    # The Seestar's own single stacked output for M 3 (must be ignored).
    (scan_root / "M 3").mkdir()
    write_seestar_fits(scan_root / "M 3" / "Stacked.fit", n_stars=5, seed=10)
    # A mosaic of the same object — its raw subs + its own output.
    (scan_root / "M 3_mosaic_sub").mkdir()
    write_seestar_fits(scan_root / "M 3_mosaic_sub" / "Light_001.fit", n_stars=5, seed=4)
    write_seestar_fits(scan_root / "M 3_mosaic_sub" / "Light_002.fit", n_stars=5, seed=5)
    (scan_root / "M 3_mosaic").mkdir()
    write_seestar_fits(scan_root / "M 3_mosaic" / "Stacked.fit", n_stars=5, seed=11)
    # A video capture (must be ignored).
    (scan_root / "Lunar_video").mkdir()
    write_seestar_fits(scan_root / "Lunar_video" / "clip_001.fit", n_stars=5, seed=6)

    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        by_name = {t.target_name: t for t in result.targets}
        # Exactly two real targets, kept distinct (mosaic never merged in).
        assert set(by_name) == {"M 3", "M 3 (mosaic)"}
        assert by_name["M 3"].n_frames_added == 3           # the raw subs, not the 1 output
        assert by_name["M 3 (mosaic)"].n_frames_added == 2
        # No bogus output/video targets in the registry.
        assert {t.name for t in lib.list_targets()} == {"M 3", "M 3 (mosaic)"}
    finally:
        lib.close()


def test_seestar_output_bases_maps_single_field_sub_only():
    """``_sub`` single-field folders yield a bare-output base to reject; mosaic
    ``_mosaic_sub`` and plain non-Seestar folders yield nothing."""
    bases = _seestar_output_bases(_fake("M 31_sub", "M 31", "M 3_mosaic_sub", "Andromeda"))
    assert bases == {"M 31": "M 31"}


def test_seestar_output_bases_leaves_a_bare_folder_it_is_ingesting_alone():
    """The output-reject must not turn round and reject the very frames the
    convention just ingested.

    A bare ``M 31/`` with no same-parent ``M 31_sub`` is *real subs* — v0.277.4
    made the convention ingest it — so registering ``M 31`` as an output base
    would mark those frames as on-device output. The base still registers when
    the bare folder is genuinely skipped as output (same parent), and when it
    isn't in the drop at all (an already-migrated library still heals)."""
    # Unrelated container child: the bare root folder is ingested → no base.
    assert _seestar_output_bases(
        _fake("M 31", "M 31_sub"), parents=["/inc", "/inc/MyWorks"]) == {}
    # A true same-parent output folder → the base still registers.
    assert _seestar_output_bases(
        _fake("M 31", "M 31_sub"), parents=["/inc", "/inc"]) == {"M 31": "M 31"}
    # No bare folder in the drop at all → the upgrade-path healing is untouched.
    assert _seestar_output_bases(
        _fake("M 31_sub"), parents=["/inc/MyWorks"]) == {"M 31": "M 31"}


def test_scan_keeps_a_tiny_root_session_when_a_container_shares_its_name(tmp_path):
    """Regression (the residual of the v0.277.4 fix): a root-level bare ``M 31/``
    holding only a sub or two must stay *accepted*, not just ingested.

    v0.277.4 parent-scoped the convention's skip, so the folder is ingested — but
    ``_seestar_output_bases`` still built its reject map from a global basename
    set, so the unrelated container's ``M 31_sub`` registered ``M 31`` as an
    on-device-output base and the size guard (≤2 frames, an output folder holds
    one image) then rejected exactly those root subs. A 3-sub session was safe;
    a 2-sub one silently left the stack."""
    scan_root = tmp_path / "incoming"
    (scan_root / "M 31").mkdir(parents=True)
    for i in range(2):                       # small enough to trip the size guard
        write_seestar_fits(scan_root / "M 31" / f"Light_{i:03d}.fit", n_stars=5, seed=i)
    works = scan_root / "MyWorks"
    (works / "M 31_sub").mkdir(parents=True)
    for i in range(2):
        write_seestar_fits(works / "M 31_sub" / f"Light_{i:03d}.fit", n_stars=5, seed=50 + i)

    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        entry = lib.find_target("M 31")
        assert entry is not None
        proj = lib.open_target(entry.safe_name)
        try:
            frames = list(proj.iter_frames())
        finally:
            proj.close()
        root_subs = [f for f in frames if "MyWorks" not in f.source_path]
        assert len(root_subs) == 2, [f.source_path for f in frames]
        assert all(f.accept for f in root_subs)
        assert all(f.reject_reason is None for f in root_subs)
        assert all(f.accept for f in frames)
    finally:
        lib.close()


def test_scan_still_rejects_a_real_on_device_output_beside_its_subs(tmp_path):
    """The no-regression half: a genuine same-parent ``M 31/`` output folder
    beside ``M 31_sub/`` is still recognised and its frame still rejected."""
    scan_root = tmp_path / "incoming"
    (scan_root / "M 31").mkdir(parents=True)
    write_seestar_fits(scan_root / "M 31" / "Stacked_60s.fit", n_stars=5, seed=9)
    (scan_root / "M 31_sub").mkdir(parents=True)
    for i in range(3):
        write_seestar_fits(scan_root / "M 31_sub" / f"Light_{i:03d}.fit", n_stars=5, seed=i)

    lib = Library.create(tmp_path / "lib")
    try:
        # First scan under the convention: the bare folder is skipped outright,
        # so nothing from it is ingested at all.
        scan_and_organize(lib, scan_root)
        entry = lib.find_target("M 31")
        proj = lib.open_target(entry.safe_name)
        try:
            assert all("M 31_sub" in f.source_path for f in proj.iter_frames())
            # Now simulate the pre-v0.184.9 library this heals: the output frame
            # already registered inside the same target.
            proj.add_frame(FrameRow(
                source_path=str(scan_root / "M 31" / "Stacked_60s.fit")))
        finally:
            proj.close()
        scan_and_organize(lib, scan_root)
        proj = lib.open_target(entry.safe_name)
        try:
            out = [f for f in proj.iter_frames() if f.source_path.endswith("Stacked_60s.fit")]
            assert len(out) == 1
            assert out[0].accept is False
            assert out[0].reject_reason == REJECT_REASON_SEESTAR_OUTPUT
        finally:
            proj.close()
    finally:
        lib.close()


def test_reject_seestar_output_frames_rejects_output_and_video_not_subs(tmp_path):
    """The Project helper additively rejects frames whose source lives in the
    bare ``<T>/`` output folder or any ``*_video`` folder, leaves the raw ``_sub``
    frames accepted, and never touches a user-overridden accept."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        root = tmp_path / "incoming"
        sub_a = proj.add_frame(FrameRow(source_path=str(root / "M 31_sub" / "Light_001.fit")))
        sub_b = proj.add_frame(FrameRow(source_path=str(root / "M 31_sub" / "Light_002.fit")))
        out = proj.add_frame(FrameRow(source_path=str(root / "M 31" / "Stacked_60s.fit")))
        vid = proj.add_frame(FrameRow(source_path=str(root / "M 31_video" / "clip.fit")))
        # A frame the user manually accepted must survive even if it looks like output.
        kept = proj.add_frame(FrameRow(
            source_path=str(root / "M 31" / "Stacked_keep.fit"), user_override=True))

        rejected = proj.reject_seestar_output_frames("M 31")
        assert set(rejected) == {out, vid}
        assert proj.get_frame(out).accept is False
        assert proj.get_frame(out).reject_reason == REJECT_REASON_SEESTAR_OUTPUT
        assert proj.get_frame(vid).accept is False
        assert proj.get_frame(sub_a).accept is True and proj.get_frame(sub_b).accept is True
        assert proj.get_frame(kept).accept is True  # user override preserved

        # Idempotent: a second call rejects nothing more.
        assert proj.reject_seestar_output_frames("M 31") == []
    finally:
        proj.close()


def test_reject_seestar_output_frames_keeps_a_real_subs_folder_sharing_the_base_name(tmp_path):
    """Mixed-source guard (regression): a genuine ``<T>/`` folder of many raw subs
    — a user's own non-Seestar capture — that merely shares the base name of a
    Seestar ``<T>_sub/`` seen in the same scan must NOT be mass-rejected as
    on-device output. The Seestar's output is a *single* image, so only a folder
    with ``<= _MAX_SEESTAR_OUTPUT_FRAMES`` frames is treated as output. Fails
    before the frame-count guard (all 8 subs were rejected by basename alone)."""
    proj = Project.create(tmp_path / "proj", name="Andromeda")
    try:
        root = tmp_path / "incoming"
        # 8 real subs the user dropped into a plain folder literally named "Andromeda".
        real_ids = [
            proj.add_frame(FrameRow(source_path=str(root / "Andromeda" / f"Light_{i:03d}.fit")))
            for i in range(8)
        ]
        # 3 Seestar subs merged in from the sibling "Andromeda_sub/".
        sub_ids = [
            proj.add_frame(FrameRow(source_path=str(root / "Andromeda_sub" / f"Light_{i:03d}.fit")))
            for i in range(3)
        ]
        rejected = proj.reject_seestar_output_frames("Andromeda")
        assert rejected == []  # folder too big to be the on-device output — nothing rejected
        for fid in real_ids + sub_ids:
            assert proj.get_frame(fid).accept is True
    finally:
        proj.close()


def test_reject_seestar_output_frames_rejects_a_multi_frame_video_folder(tmp_path):
    """A ``*_video`` capture legitimately holds many frames and they are all junk
    (not stackable deep-sky subs), so the single-image size guard applies only to
    the bare ``<T>/`` output folder and must NOT spare a multi-frame video folder."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        root = tmp_path / "incoming"
        vids = [
            proj.add_frame(FrameRow(source_path=str(root / "M 31_video" / f"frame_{i:03d}.fit")))
            for i in range(6)
        ]
        rejected = proj.reject_seestar_output_frames("M 31")
        assert set(rejected) == set(vids)
    finally:
        proj.close()


def test_reject_seestar_output_frames_rejects_a_multi_frame_photo_folder(tmp_path):
    """Same family as the ``*_video`` case above, and the half the scan-time
    ``_photo`` skip does not reach: a ``*_photo`` stills folder an old whole-card
    drop already merged into a real target holds many finished snapshots, all junk
    in a deep-sky stack. The single-image size guard must not spare them either —
    otherwise that target keeps averaging finished pictures into its own."""
    proj = Project.create(tmp_path / "proj", name="M 31")
    try:
        root = tmp_path / "incoming"
        photos = [
            proj.add_frame(FrameRow(
                source_path=str(root / "Scenery_photo" / f"IMG_{i:03d}.fit")))
            for i in range(6)
        ]
        keep = proj.add_frame(FrameRow(
            source_path=str(root / "M 31_sub" / "Light_001.fit")))
        rejected = proj.reject_seestar_output_frames("M 31")
        assert set(rejected) == set(photos)      # every snapshot, none spared
        assert keep not in rejected              # the real subs are untouched
    finally:
        proj.close()


def test_rescan_rejects_pre_v0_184_9_output_pollution_end_to_end(tmp_path):
    """Upgrade path: a library first scanned before the Seestar convention
    shipped merged the on-device output into the ``<T>`` target. Re-scanning with
    the fixed scanner ingests the raw ``<T>_sub`` subs and additively rejects that
    output frame so it leaves the stack/reference pool (regression for the ⭐⭐
    upgrade-path pollution bug)."""
    scan_root = tmp_path / "incoming"
    (scan_root / "M 31_sub").mkdir(parents=True)
    write_seestar_fits(scan_root / "M 31_sub" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(scan_root / "M 31_sub" / "Light_002.fit", n_stars=5, seed=2)
    write_seestar_fits(scan_root / "M 31_sub" / "Light_003.fit", n_stars=5, seed=3)
    # The Seestar's own on-device output, sitting in the bare "M 31/" folder.
    (scan_root / "M 31").mkdir()
    output_file = write_seestar_fits(scan_root / "M 31" / "Stacked_60s.fit", n_stars=5, seed=10)

    lib = Library.create(tmp_path / "lib")
    try:
        # Seed the pre-fix polluted state: the OLD scanner made "M 31" a target
        # and ingested the on-device output frame into it as if it were a sub.
        entry, proj = lib.open_or_create_target("M 31")
        try:
            proj.add_frame(FrameRow(source_path=str(output_file)))
        finally:
            proj.close()

        result = scan_and_organize(lib, scan_root)
        m31 = next(t for t in result.targets if t.safe_name == "M_31")
        assert m31.n_frames_added == 3               # the three raw subs
        assert m31.n_output_frames_rejected == 1     # the on-device output

        proj = lib.open_target("M_31")
        try:
            frames = list(proj.iter_frames())
            assert len(frames) == 4                  # 3 subs + 1 seeded output
            accepted = [f for f in proj.iter_frames(accepted_only=True)]
            assert len(accepted) == 3                # output no longer in the pool
            out = next(f for f in frames if f.source_path == str(output_file))
            assert out.accept is False
            assert out.reject_reason == REJECT_REASON_SEESTAR_OUTPUT
        finally:
            proj.close()
    finally:
        lib.close()


def test_scan_expands_a_whole_device_container_drop(tmp_path):
    """A whole Seestar share/card copied in with its container level intact
    (incoming/MyWorks/{...}) must expand into the real per-target folders, not
    lump every object + output + video into one giant 'MyWorks' target
    (regression for the whole-device-drop bug)."""
    scan_root = tmp_path / "incoming"
    works = scan_root / "MyWorks"
    (works / "M 31_sub").mkdir(parents=True)
    write_seestar_fits(works / "M 31_sub" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(works / "M 31_sub" / "Light_002.fit", n_stars=5, seed=2)
    (works / "M 31").mkdir()  # on-device output for M 31 — must be skipped
    write_seestar_fits(works / "M 31" / "Stacked.fit", n_stars=5, seed=10)
    (works / "NGC 7000_mosaic_sub").mkdir()
    write_seestar_fits(works / "NGC 7000_mosaic_sub" / "Light_001.fit", n_stars=5, seed=3)
    write_seestar_fits(works / "NGC 7000_mosaic_sub" / "Light_002.fit", n_stars=5, seed=4)
    (works / "Lunar_video").mkdir()  # video — must be skipped
    write_seestar_fits(works / "Lunar_video" / "clip.fit", n_stars=5, seed=6)

    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        by_name = {t.target_name: t for t in result.targets}
        assert set(by_name) == {"M 31", "NGC 7000 (mosaic)"}   # no "MyWorks"
        assert by_name["M 31"].n_frames_added == 2             # subs, not the output
        assert by_name["NGC 7000 (mosaic)"].n_frames_added == 2
        assert {t.name for t in lib.list_targets()} == {"M 31", "NGC 7000 (mosaic)"}
    finally:
        lib.close()


def test_scan_keeps_root_subs_when_container_has_same_named_sub(tmp_path):
    """Regression: a root-level bare 'M 31/' folder of REAL subs must not be
    dropped just because an unrelated whole-device container elsewhere in the
    same drop contains an 'M 31_sub/' child. Before the sibling test was
    parent-scoped, the container's 'M 31_sub' put 'm 31_sub' into one global name
    set, so the root 'M 31/' was skipped as if it were on-device output and its
    whole session vanished."""
    scan_root = tmp_path / "incoming"
    # Root-level real subs of M 31 (>2 frames, so not mistaken for a 1-image
    # on-device output), with NO 'M 31_sub' sibling of their own at root.
    (scan_root / "M 31").mkdir(parents=True)
    for i in range(3):
        write_seestar_fits(scan_root / "M 31" / f"Light_{i:03d}.fit", n_stars=5, seed=i)
    # A separate whole-device container with an unrelated same-named M 31_sub.
    works = scan_root / "MyWorks"
    (works / "M 31_sub").mkdir(parents=True)
    write_seestar_fits(works / "M 31_sub" / "Light_001.fit", n_stars=5, seed=50)
    write_seestar_fits(works / "M 31_sub" / "Light_002.fit", n_stars=5, seed=51)

    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        entry = lib.find_target("M 31")
        assert entry is not None
        proj = lib.open_target(entry.safe_name)
        try:
            srcs = [f.source_path for f in proj.iter_frames()]
            accepted = [f for f in proj.iter_frames() if f.accept]
        finally:
            proj.close()
        # Both the 3 root subs and the 2 container subs land in the one M 31
        # target, and the root subs are accepted (the output-reject size guard
        # leaves a >2-frame folder alone).
        root_subs = [s for s in srcs if "MyWorks" not in s]
        assert len(root_subs) == 3, srcs
        assert len(srcs) == 5, srcs
        assert len(accepted) == 5
    finally:
        lib.close()


def test_container_target_children_spans_multiple_folders():
    """The pure classifier returns the set of immediate container children the
    given frame paths live under — the mixed-drop signature is ≥2."""
    works = Path("/incoming/MyWorks")
    sources = [
        "/incoming/MyWorks/M 31_sub/Light_001.fit",
        "/incoming/MyWorks/M 31_sub/Light_002.fit",
        "/incoming/MyWorks/M 31/Stacked.fit",
        "/incoming/MyWorks/Lunar_video/clip.fit",
    ]
    assert container_target_children(works, sources) == {"M 31_sub", "M 31", "Lunar_video"}


def test_container_target_children_single_folder_is_not_mixed():
    """A real single-field target — every frame in one child folder — spans just
    one folder, so it is never mistaken for a mixed drop."""
    works = Path("/incoming/M 31_sub")
    sources = [
        "/incoming/M 31_sub/Light_001.fit",
        "/incoming/M 31_sub/Light_002.fit",
    ]
    # relative to the folder itself the files have <1 sub-part, so no children;
    # relative to a container that IS the folder, span is 0 (< 2) → not mixed.
    assert container_target_children(Path("/incoming"), sources) == {"M 31_sub"}
    assert container_target_children(works, sources) == set()


def test_container_target_children_returns_none_for_outside_path():
    """Any path not under the container means the frames are not a clean
    whole-container drop → None (never flagged)."""
    works = Path("/incoming/MyWorks")
    sources = [
        "/incoming/MyWorks/M 31_sub/Light_001.fit",
        "/elsewhere/Random/Light_002.fit",
    ]
    assert container_target_children(works, sources) is None


def test_rescan_flags_a_legacy_whole_device_drop_target(tmp_path):
    """The upgrade heal: a library an OLD scan built by lumping a whole container
    (incoming/MyWorks/{several objects + output + video}) into ONE giant target
    must, on a re-scan with the container-expanding scanner, (a) grow the correct
    per-target versions and (b) flag the leftover giant target for one-click
    cleanup — without deleting anything. Fail-before: the giant target is never
    flagged, so it keeps auto-stacking mixed-pointing gibberish forever."""
    scan_root = tmp_path / "incoming"
    works = scan_root / "MyWorks"
    (works / "M 31_sub").mkdir(parents=True)
    write_seestar_fits(works / "M 31_sub" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(works / "M 31_sub" / "Light_002.fit", n_stars=5, seed=2)
    (works / "M 31").mkdir()  # the Seestar's on-device output for M 31
    write_seestar_fits(works / "M 31" / "Stacked.fit", n_stars=5, seed=10)
    (works / "NGC 7000_mosaic_sub").mkdir()
    write_seestar_fits(works / "NGC 7000_mosaic_sub" / "Light_001.fit", n_stars=5, seed=3)
    (works / "Lunar_video").mkdir()  # a video capture
    write_seestar_fits(works / "Lunar_video" / "clip.fit", n_stars=5, seed=6)

    lib = Library.create(tmp_path / "lib")
    try:
        # Seed the pre-fix state exactly like the old (pre-container-expansion)
        # scanner did: the whole "MyWorks" container becomes ONE target holding
        # every FITS found recursively beneath it.
        all_files = find_fits_files(works, recursive=True)
        _ingest_into_target(lib, "MyWorks", all_files, copy_to_cache=False)
        giant = lib.find_target("MyWorks")
        assert giant is not None and giant.n_frames == 5
        assert giant.legacy_mixed_drop is None  # not yet flagged

        # Re-scan with the current scanner: it expands the container into the real
        # per-target folders AND heals the leftover giant target.
        result = scan_and_organize(lib, scan_root)
        by_name = {t.target_name: t for t in result.targets}
        assert set(by_name) == {"M 31", "NGC 7000 (mosaic)"}  # correct targets exist

        giant = lib.find_target("MyWorks")
        assert giant is not None, "the giant target must NOT be deleted (reversible)"
        assert giant.legacy_mixed_drop == 1  # flagged for one-click cleanup
        assert giant.n_frames == 5           # frames untouched — nothing removed
    finally:
        lib.close()


def test_rescan_does_not_flag_a_real_single_field_target(tmp_path):
    """A normal library with no mixed-drop container must never gain the flag —
    the heal only fires inside the container-expansion branch, and only for a
    pre-existing giant target whose frames span ≥2 of the container's folders."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        for entry in lib.list_targets():
            assert entry.legacy_mixed_drop is None, entry.name
    finally:
        lib.close()


def test_scan_keeps_a_plain_nested_non_seestar_folder_as_one_target(tmp_path):
    """A plainly-nested non-Seestar folder (children share no '_sub' convention
    name) must still ingest as ONE target — the container expansion must not
    fire for it (no regression for the Andromeda/sub layout)."""
    scan_root = tmp_path / "incoming"
    proj = scan_root / "MyProject"
    (proj / "night1").mkdir(parents=True)
    (proj / "night2").mkdir()
    write_seestar_fits(proj / "night1" / "Light_001.fit", n_stars=5, seed=1)
    write_seestar_fits(proj / "night2" / "Light_002.fit", n_stars=5, seed=2)

    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        by_name = {t.target_name: t for t in result.targets}
        assert set(by_name) == {"MyProject"}       # one target, both nights folded in
        assert by_name["MyProject"].n_frames_added == 2
    finally:
        lib.close()


def test_scan_is_idempotent(tmp_path):
    """Re-scanning the same tree adds nothing the second time."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        first = scan_and_organize(lib, scan_root)
        assert first.total_added == 5

        second = scan_and_organize(lib, scan_root)
        assert second.total_added == 0
        # Everything is now "skipped existing".
        assert sum(t.n_skipped_existing for t in second.targets) == 5
        # Still exactly three targets — no duplicates created.
        assert len(lib.list_targets()) == 3
    finally:
        lib.close()


def test_scan_picks_up_new_frames_on_rescan(tmp_path):
    """Adding a night to an existing folder and re-scanning ingests just
    the new frames into the existing target."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        # New frame dropped into the existing M 42 folder.
        write_seestar_fits(scan_root / "M 42" / "Light_003.fit", n_stars=5, seed=9)
        result = scan_and_organize(lib, scan_root)
        m42 = next(t for t in result.targets if t.safe_name == "M_42")
        assert m42.n_frames_added == 1
        assert lib.find_target("M_42").n_frames == 3
    finally:
        lib.close()


def test_scan_counts_a_cache_refresh_as_refreshed_not_added(tmp_path):
    """A mid-copy-truncated sub whose source later completes is refreshed (not
    re-added) on re-scan, so the scanner reports it under n_frames_refreshed —
    which the pipeline uses to re-QC the target even with no new frames."""
    scan_root = tmp_path / "seestar"
    (scan_root / "M 42").mkdir(parents=True)
    full = write_seestar_fits(scan_root / "M 42" / "Light_001.fit", n_stars=5, seed=1)
    full_bytes = full.read_bytes()
    full.write_bytes(full_bytes[: len(full_bytes) // 2])  # simulate still-copying

    lib = Library.create(tmp_path / "lib")
    try:
        # copy_to_cache=True so the truncated bytes land in the Stage-1 cache.
        first = scan_and_organize(lib, scan_root, copy_to_cache=True)
        m42_first = next(t for t in first.targets if t.safe_name == "M_42")
        assert m42_first.n_frames_added == 1 and m42_first.n_frames_refreshed == 0

        full.write_bytes(full_bytes)  # the copy finishes
        second = scan_and_organize(lib, scan_root, copy_to_cache=True)
        m42 = next(t for t in second.targets if t.safe_name == "M_42")
        assert m42.n_frames_added == 0        # nothing new
        assert m42.n_frames_refreshed == 1    # but the cache was refreshed
        # The refreshed frame's id is surfaced so the pipeline can drop its
        # now-stale cached previews (which key on id alone).
        assert len(m42.refreshed_frame_ids) == 1
        proj = lib.open_target("M_42")
        try:
            assert m42.refreshed_frame_ids[0] == next(iter(proj.iter_frames())).id
        finally:
            proj.close()
    finally:
        lib.close()


def test_scan_counts_a_still_copying_empty_sub_as_skip_not_error(tmp_path):
    """A 0-byte (still-copying / stalled-transfer) sub is a benign skip that will
    be retried once it has bytes — not a failure. It must land in the scan's
    n_skipped tally, never inflate the scary n_errors count a beginner sees."""
    scan_root = tmp_path / "seestar"
    (scan_root / "M 42").mkdir(parents=True)
    write_seestar_fits(scan_root / "M 42" / "Light_001.fit", n_stars=5, seed=1)
    (scan_root / "M 42" / "Light_002.fit").write_bytes(b"")  # still copying

    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, scan_root)
        m42 = next(t for t in result.targets if t.safe_name == "M_42")
        assert m42.n_frames_added == 1          # the complete sub ingested
        assert m42.n_errors == 0                # the empty one is NOT an error...
        assert m42.n_skipped_existing == 1      # ...it is a skip (retried next scan)
    finally:
        lib.close()


def test_scan_empty_root_produces_no_targets(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    lib = Library.create(tmp_path / "lib")
    try:
        result = scan_and_organize(lib, empty)
        assert result.n_targets == 0
        assert lib.list_targets() == []
    finally:
        lib.close()


def test_scan_missing_root_raises(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        with pytest.raises(NotADirectoryError):
            scan_and_organize(lib, tmp_path / "does_not_exist")
    finally:
        lib.close()


def test_scan_progress_callback_fires(tmp_path):
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    calls: list[tuple[str, int, int]] = []
    try:
        scan_and_organize(lib, scan_root, progress=lambda *a: calls.append(a))
        assert calls, "progress callback never fired"
        assert all(phase == "Organizing" for phase, _d, _t in calls)
        # Final call reports done == total.
        assert calls[-1][1] == calls[-1][2]
    finally:
        lib.close()


def test_run_qc_serial_populates_metrics(tmp_path):
    """run_qc_and_solve(serial=True, run_solve=False) fills QC metrics for
    every frame without needing ASTAP."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        proj = lib.open_target("M_42")
        try:
            calls: list[tuple] = []
            summary = run_qc_and_solve(
                proj, run_qc=True, run_solve=False, serial=True,
                progress=lambda *a: calls.append(a),
            )
            assert summary["qc_total"] == 2
            assert summary["qc_done"] == 2
            # Every frame now has a star_count metric written.
            for f in proj.iter_frames():
                assert f.star_count is not None
            # Progress reported under the "QC" phase.
            assert calls and all(c[0] == "QC" for c in calls)
        finally:
            proj.close()
    finally:
        lib.close()


def test_run_qc_and_solve_honours_should_stop(tmp_path):
    """A should_stop that returns True immediately means no QC work runs."""
    scan_root = _seestar_tree(tmp_path / "seestar")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        proj = lib.open_target("M_42")
        try:
            summary = run_qc_and_solve(
                proj, run_qc=True, run_solve=False, serial=True,
                should_stop=lambda: True,
            )
            assert summary["qc_done"] == 0
        finally:
            proj.close()
    finally:
        lib.close()
def test_no_output_base_is_registered_against_a_mosaic_target():
    """The *frame-level* on-device-output reject is never armed for a mosaic.

    `Project.reject_seestar_output_frames` carries a ≤2-frame guard, and a
    mosaic's on-device output is one image *per panel* (11 in the owner's real
    `M 44_mosaic/`) — so if that reject ever ran over a mosaic target it would
    spare exactly the frames it exists to catch. It never runs over one:
    `_seestar_output_bases` skips `*_mosaic_sub` outright, and the key it would
    otherwise have produced (`M 44_mosaic`) is not the name the convention gives
    the target anyway (`M 44 (mosaic)`), so the lookup in `scan_and_organize`
    could not match even if the skip were removed. Both halves are pinned here.
    """
    bases = _seestar_output_bases(_fake("M 44_mosaic_sub", "M 44_mosaic"))
    assert bases.get(mosaic_target_name("M 44")) is None
    assert bases.get("M 44_mosaic") is None
    # …while the single-field case it *is* for still registers, so this test
    # can't pass by the helper having stopped working altogether.
    single = _seestar_output_bases(_fake("M 31_sub"))
    assert single.get("M 31") == "M 31"


def test_a_mosaics_on_device_output_never_reaches_the_mosaic_target(tmp_path):
    """…and the same invariant end-to-end, which is the one that matters: the
    11 panel images in a bare `<T>_mosaic/` folder are not in the mosaic's
    stack pool, because they are not ingested into any target at all."""
    scan_root = tmp_path / "incoming"
    (scan_root / "M 44_mosaic").mkdir(parents=True)
    for i in range(11):
        write_seestar_fits(scan_root / "M 44_mosaic" / f"Stacked_{i:02d}.fit",
                           n_stars=5, seed=100 + i)
    (scan_root / "M 44_mosaic_sub").mkdir(parents=True)
    for i in range(4):
        write_seestar_fits(scan_root / "M 44_mosaic_sub" / f"Light_{i:03d}.fit",
                           n_stars=5, seed=i)

    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, scan_root)
        entry = lib.find_target(mosaic_target_name("M 44"))
        assert entry is not None, [t.name for t in lib.list_targets()]
        proj = lib.open_target(entry.safe_name)
        try:
            sources = proj.source_paths()
        finally:
            proj.close()
        assert sources and all("M 44_mosaic_sub" in s for s in sources)
        # Not merely absent from the mosaic target — absent from the library.
        for t in lib.list_targets():
            other = lib.open_target(t.safe_name)
            try:
                assert not any(Path(s).parent.name == "M 44_mosaic"
                               for s in other.source_paths()), t.name
            finally:
                other.close()
    finally:
        lib.close()

