"""The read-only ``/api/targets/cleanup-suggestions`` endpoint that powers the
Library "these look like Seestar outputs/videos, not raw subs — remove?" nudge.

The pre-v0.184.9 scanner ingested a Seestar's own on-device stacked *output*
folders (and ``_video`` folders) as if they were raw sub-frames, leaving junk
targets in a library. This endpoint flags them (never deletes) so the owner can
clean up in one confirmation."""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow


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
