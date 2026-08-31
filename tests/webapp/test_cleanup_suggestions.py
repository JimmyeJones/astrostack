"""The read-only ``/api/targets/cleanup-suggestions`` endpoint that powers the
Library "these look like Seestar outputs/videos, not raw subs — remove?" nudge.

The pre-v0.184.9 scanner ingested a Seestar's own on-device stacked *output*
folders (and ``_video`` folders) as if they were raw sub-frames, leaving junk
targets in a library. This endpoint flags them (never deletes) so the owner can
clean up in one confirmation."""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow, StackRunRow


def _add_target(lib: Library, name: str, source_paths: list[Path]) -> str:
    entry, proj = lib.open_or_create_target(name)
    try:
        for sp in source_paths:
            proj.add_frame(FrameRow(source_path=str(sp)))
    finally:
        proj.close()
    lib.refresh_target_stats(entry.safe_name)
    return entry.safe_name


def test_flags_output_and_video_junk_but_not_real_targets(client, data_root: Path):
    incoming = data_root / "dump"
    # A real, deep target (its raw subs live in a plainly-named folder).
    real = incoming / "M 42"
    real.mkdir(parents=True)
    real_frames = [real / f"Light_{i:03d}.fit" for i in range(20)]

    # The Seestar's own on-device output, beside its raw-subs sibling → junk.
    (incoming / "M 31_sub").mkdir(parents=True)
    output = incoming / "M 31"
    output.mkdir()
    output_frame = output / "Stacked.fit"

    # A video capture → junk (by target name).
    vid = incoming / "Lunar_video"
    vid.mkdir()
    vid_frame = vid / "clip_000.fit"

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 42", real_frames)
        _add_target(lib, "M 31", [output_frame])
        _add_target(lib, "Lunar_video", [vid_frame])
    finally:
        lib.close()

    r = client.get("/api/targets/cleanup-suggestions")
    assert r.status_code == 200
    body = r.json()
    by_safe = {s["safe"]: s for s in body}
    # Exactly the two junk targets are flagged; the real M 42 is left alone.
    assert set(by_safe) == {"M_31", "Lunar_video"}
    assert by_safe["M_31"]["reason"] == "on_device_output"
    assert by_safe["Lunar_video"]["reason"] == "video"
    assert by_safe["M_31"]["detail"] and by_safe["Lunar_video"]["detail"]


def test_flags_a_photo_capture_target_at_any_frame_count(client, data_root: Path):
    """A ``*_photo`` target — the single stills the Seestar takes in
    scenery/planetary photo mode — is junk exactly like a ``*_video`` one, and
    like videos it is decided by *name* at any frame count (the frame-count gate
    would otherwise never even look at a folder of 40 snapshots)."""
    incoming = data_root / "dump"
    photos = incoming / "Scenery_photo"
    photos.mkdir(parents=True)
    photo_frames = [photos / f"IMG_{i:03d}.fit" for i in range(40)]
    real = incoming / "M 42"
    real.mkdir()

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "Scenery_photo", photo_frames)
        _add_target(lib, "M 42", [real / f"Light_{i:03d}.fit" for i in range(20)])
    finally:
        lib.close()

    body = client.get("/api/targets/cleanup-suggestions").json()
    by_safe = {s["safe"]: s for s in body}
    assert set(by_safe) == {"Scenery_photo"}
    assert by_safe["Scenery_photo"]["reason"] == "photo"
    assert "photo" in by_safe["Scenery_photo"]["detail"]


def test_flags_another_programs_temp_folder_at_any_frame_count(client, data_root: Path):
    """``batch_stack_tmp`` — some other stacking program's scratch folder in the
    owner's real ``\\\\TRUENAS\\astro`` share — has no ``_sub`` sibling, so it
    ingests as an ordinary target and sits in the library forever. Like a capture
    folder it is decided by *name* at any frame count: a temp folder can hold any
    number of files, so the on-device-output size gate would never look at it.

    A real target that merely *sounds* temporary is untouched — the list is exact
    names, never a ``*_tmp`` pattern."""
    incoming = data_root / "dump"
    scratch = incoming / "batch_stack_tmp"
    scratch.mkdir(parents=True)
    scratch_frames = [scratch / f"w_{i:03d}.fit" for i in range(30)]
    # A real target whose folder name merely looks temporary.
    lookalike = incoming / "NGC 7000_tmp"
    lookalike.mkdir()

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "batch_stack_tmp", scratch_frames)
        _add_target(
            lib, "NGC 7000_tmp",
            [lookalike / f"Light_{i:03d}.fit" for i in range(30)],
        )
    finally:
        lib.close()

    body = client.get("/api/targets/cleanup-suggestions").json()
    by_safe = {s["safe"]: s for s in body}
    assert set(by_safe) == {"batch_stack_tmp"}
    assert by_safe["batch_stack_tmp"]["reason"] == "temp_folder"
    assert "batch_stack_tmp" in by_safe["batch_stack_tmp"]["detail"]


def test_flags_a_legacy_mixed_drop_target_regardless_of_size(client, data_root: Path):
    """A target flagged at scan time as a legacy whole-device / mixed-folder drop
    must be surfaced for one-click cleanup even though it is *large* — the cheap
    frame-count-gated junk detectors skip big targets, so the registry flag is the
    only thing that reaches it. An unflagged large target is never surfaced."""
    incoming = data_root / "dump"
    giant = incoming / "MyWorks"
    giant.mkdir(parents=True)
    # A big jumble of frames (well above the frame-count cleanup gate).
    giant_frames = [giant / f"Light_{i:03d}.fit" for i in range(30)]
    real = incoming / "M 42"
    real.mkdir()
    real_frames = [real / f"Light_{i:03d}.fit" for i in range(30)]

    lib = Library.open_or_create(data_root / "library")
    try:
        giant_safe = _add_target(lib, "MyWorks", giant_frames)
        _add_target(lib, "M 42", real_frames)
        # Simulate the scan-time heal flagging the giant leftover.
        lib.flag_legacy_mixed_drop(giant_safe)
    finally:
        lib.close()

    r = client.get("/api/targets/cleanup-suggestions")
    assert r.status_code == 200
    body = r.json()
    by_safe = {s["safe"]: s for s in body}
    # Only the flagged giant target is surfaced; the real large M 42 is untouched.
    assert set(by_safe) == {giant_safe}
    assert by_safe[giant_safe]["reason"] == "legacy_mixed_drop"
    assert by_safe[giant_safe]["n_frames"] == 30
    assert by_safe[giant_safe]["detail"]


def test_clean_library_gives_empty_list(client, data_root: Path):
    incoming = data_root / "dump"
    real = incoming / "Andromeda"
    real.mkdir(parents=True)
    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "Andromeda", [real / "Light_001.fit"])
    finally:
        lib.close()

    r = client.get("/api/targets/cleanup-suggestions")
    assert r.status_code == 200
    assert r.json() == []


def test_flags_a_sub_named_duplicate_the_base_target_now_owns(client, data_root: Path):
    """The upgrade-path leftover: a pre-v0.184.9 scan built a ``M 31_sub`` target;
    a later scan folded the same subs into ``M 31``. The ``_sub`` duplicate is
    flagged (reason ``duplicate_sub``) because the base already owns every frame —
    while the real ``M 31`` target and an unrelated target are left alone."""
    incoming = data_root / "dump"
    (incoming / "M 31_sub").mkdir(parents=True)
    subs = [incoming / "M 31_sub" / f"Light_{i:03d}.fit" for i in range(6)]

    lib = Library.open_or_create(data_root / "library")
    try:
        # Both targets registered against the SAME raw subs (the duplicate state).
        _add_target(lib, "M 31", subs)        # base — the convention's target
        _add_target(lib, "M 31_sub", subs)    # leftover duplicate
        _add_target(lib, "Orion", [incoming / "Orion" / "Light_001.fit"])
    finally:
        lib.close()

    body = client.get("/api/targets/cleanup-suggestions").json()
    by_safe = {s["safe"]: s for s in body}
    assert set(by_safe) == {"M_31_sub"}
    assert by_safe["M_31_sub"]["reason"] == "duplicate_sub"
    assert "M 31" in by_safe["M_31_sub"]["detail"]

    # Actionable: removing it leaves the base target intact and clears the nudge.
    assert client.delete("/api/targets/M_31_sub").status_code == 200
    assert client.get("/api/targets/cleanup-suggestions").json() == []
    assert client.get("/api/targets/M_31").status_code == 200


def test_does_not_flag_a_sub_duplicate_the_base_does_not_fully_own(client, data_root: Path):
    """Safety: if the base target does NOT already own every one of the ``_sub``
    target's subs (e.g. a re-scan hasn't run since the upgrade), removing the
    duplicate could lose the only copy — so it is NOT offered for removal."""
    incoming = data_root / "dump"
    (incoming / "M 31_sub").mkdir(parents=True)
    subs = [incoming / "M 31_sub" / f"Light_{i:03d}.fit" for i in range(6)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 31", subs[:3])    # base owns only half the subs
        _add_target(lib, "M 31_sub", subs)
    finally:
        lib.close()

    assert client.get("/api/targets/cleanup-suggestions").json() == []


def test_does_not_flag_a_standalone_sub_named_target(client, data_root: Path):
    """A ``_sub``-named target with no matching base target is left alone — it is
    the only copy of those subs, not a duplicate."""
    incoming = data_root / "dump"
    (incoming / "Nebula_sub").mkdir(parents=True)
    subs = [incoming / "Nebula_sub" / f"Light_{i:03d}.fit" for i in range(6)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "Nebula_sub", subs)
    finally:
        lib.close()

    assert client.get("/api/targets/cleanup-suggestions").json() == []


def test_does_not_flag_a_sub_duplicate_that_carries_stack_run_history(
    client, data_root: Path
):
    """Data-safety: a ``_sub`` duplicate whose base owns every sub is normally
    offered for removal — but NOT when the duplicate carries the user's own
    stack-run history. One-click cleanup deletes the registry target (keeping
    files on disk), which would silently drop that history from the UI, so the
    target with real user data is left alone."""
    incoming = data_root / "dump"
    (incoming / "M 31_sub").mkdir(parents=True)
    subs = [incoming / "M 31_sub" / f"Light_{i:03d}.fit" for i in range(6)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 31", subs)        # base — owns all the subs
        dup_safe = _add_target(lib, "M 31_sub", subs)  # leftover duplicate
        # The duplicate carries a real stack-run the user produced from it.
        _, proj = lib.open_or_create_target("M 31_sub")
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-07-01T00:00:00Z",
                output_basename="m31_stack", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=6, canvas_h=480, canvas_w=320,
                coverage_min=6, coverage_max=6, options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()

    # Without the guard this would be flagged ``duplicate_sub`` and deleting it
    # would lose the run history; with it, the target is not offered at all.
    assert client.get("/api/targets/cleanup-suggestions").json() == []
    assert dup_safe == "M_31_sub"


def test_does_not_flag_a_sub_duplicate_that_carries_user_notes(
    client, data_root: Path
):
    """Data-safety (notes variant): a ``_sub`` duplicate the base fully owns is
    still NOT offered for removal when the user has written free-text notes on
    it — those notes live only on this target and would vanish from the UI."""
    incoming = data_root / "dump"
    (incoming / "M 31_sub").mkdir(parents=True)
    subs = [incoming / "M 31_sub" / f"Light_{i:03d}.fit" for i in range(6)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 31", subs)
        _add_target(lib, "M 31_sub", subs)
        lib.update_target("M_31_sub", notes="Best session so far — keep!")
    finally:
        lib.close()

    assert client.get("/api/targets/cleanup-suggestions").json() == []


def test_flagged_target_can_then_be_deleted(client, data_root: Path):
    """The suggestion is actionable: the flagged safe_name deletes cleanly via the
    existing endpoint (the one-click "remove these" the Library wires up)."""
    incoming = data_root / "dump"
    (incoming / "Comet_sub").mkdir(parents=True)
    output = incoming / "Comet"
    output.mkdir()
    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "Comet", [output / "Stacked.fit"])
    finally:
        lib.close()

    body = client.get("/api/targets/cleanup-suggestions").json()
    assert [s["safe"] for s in body] == ["Comet"]

    assert client.delete("/api/targets/Comet").status_code == 200
    # Gone from the library, and no longer suggested.
    assert client.get("/api/targets/cleanup-suggestions").json() == []


# --- mosaics: the two places cleanup could not reach the owner's library -----
# From the owner's real S30 share (2026-08-31). Both were verified against live
# data: three "<T>_MOSAIC_SUB" duplicates with no cleanup path at all, and
# "<T>_MOSAIC" on-device outputs (11 and 7 frames) that sailed past a cap
# written for a single field's ONE stacked image.


def test_flags_a_mosaic_sub_duplicate_the_mosaic_target_now_owns(
    client, data_root: Path,
):
    """``M 44_mosaic_sub`` duplicates the ``M 44 (mosaic)`` target the convention
    builds from that folder — not the single-field ``M 44``, whose footprint is
    different. The detector used to bail on ``_mosaic_sub`` entirely, so these
    three targets in the owner's library had no cleanup path at all."""
    incoming = data_root / "dump"
    (incoming / "M 44_mosaic_sub").mkdir(parents=True)
    subs = [incoming / "M 44_mosaic_sub" / f"Light_{i:03d}.fit" for i in range(6)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 44 (mosaic)", subs)     # the convention's target
        _add_target(lib, "M 44_mosaic_sub", subs)   # leftover duplicate
        # The single-field target of the same object is a DIFFERENT footprint and
        # must never be treated as the mosaic duplicate's base.
        _add_target(lib, "M 44", [incoming / "M 44_sub" / "Light_001.fit"])
    finally:
        lib.close()

    body = client.get("/api/targets/cleanup-suggestions").json()
    by_safe = {s["safe"]: s for s in body}
    assert set(by_safe) == {"M_44_mosaic_sub"}
    assert by_safe["M_44_mosaic_sub"]["reason"] == "duplicate_sub"
    assert "M 44 (mosaic)" in by_safe["M_44_mosaic_sub"]["detail"]


def test_flags_a_multi_panel_mosaic_on_device_output(client, data_root: Path):
    """A mosaic's on-device output holds one stacked image per panel, so the
    owner's 11-frame ``M 44_MOSAIC`` and 7-frame ``NGC 6960_MOSAIC`` never even
    reached the classifier behind the ≤2-frame gate. A real mosaic target of
    hundreds of subs is still left alone."""
    incoming = data_root / "dump"
    (incoming / "M 44_mosaic_sub").mkdir(parents=True)
    output = incoming / "M 44_mosaic"
    output.mkdir()
    real = incoming / "NGC 7000_mosaic_sub"

    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 44_mosaic",
                    [output / f"Stacked_{i:02d}.fit" for i in range(11)])
        _add_target(lib, "NGC 7000 (mosaic)",
                    [real / f"Light_{i:04d}.fit" for i in range(300)])
    finally:
        lib.close()

    body = client.get("/api/targets/cleanup-suggestions").json()
    by_safe = {s["safe"]: s for s in body}
    assert set(by_safe) == {"M_44_mosaic"}
    assert by_safe["M_44_mosaic"]["reason"] == "on_device_output"
