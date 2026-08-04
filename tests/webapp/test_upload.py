"""Bulk FITS upload endpoint + its pure sanitisation helpers."""

from __future__ import annotations

import io
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

# Repo root ahead of tests/ so ``import webapp`` finds the real package, not the
# ``tests/webapp`` test package (conftest puts tests/ on the path for ``synth``).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from synth import write_seestar_fits  # noqa: E402

from webapp.routers import upload as upload_mod  # noqa: E402
from webapp.routers.upload import (  # noqa: E402
    confined_dest,
    is_fits_name,
    safe_component,
    safe_relname,
    safe_relpath,
    safe_target_dir,
)


def _fits_bytes(tmp_path: Path, name: str = "u.fit") -> bytes:
    p = tmp_path / name
    write_seestar_fits(p, width=64, height=64, n_stars=5, seed=1)
    return p.read_bytes()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Light_001.fit", "Light_001.fit"),
    ("M31/Light_001.fit", "Light_001.fit"),          # webkitdirectory relative path
    ("C:\\subs\\Light_001.fit", "Light_001.fit"),    # Windows path
    ("  spaced.fit  ", "spaced.fit"),
    ("../../../etc/passwd", "passwd"),               # traversal → basename only
    ("..", None),
    (".", None),
    ("...", None),
    ("", None),
    ("only/dir/", None),
    ("a\0b.fit", None),                              # embedded NUL
])
def test_safe_component(raw: str, expected: str | None) -> None:
    assert safe_component(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Light_001.fit", "Light_001.fit"),                     # plain basename, unchanged
    ("night1/Light_001.fit", "night1__Light_001.fit"),      # webkitdirectory relative path preserved
    ("M31/night2/Light_001.fit", "M31__night2__Light_001.fit"),
    ("C:\\subs\\Light_001.fit", "C:__subs__Light_001.fit"),  # Windows separators
    ("./a/b.fit", "a__b.fit"),                              # current-dir segment dropped
    ("  a/ b .fit ", "a__b .fit"),                          # segments stripped
    ("../evil.fit", None),                                  # a ``..`` segment rejects the whole name
    ("a/../b.fit", None),                                   # traversal anywhere in the path
    ("..", None), (".", None), ("...", None), ("", None),
    ("only/dir/", "only__dir"),                             # flattened; rejected later as non-FITS
    ("a\0b.fit", None),                                     # embedded NUL
])
def test_safe_relname(raw: str, expected: str | None) -> None:
    assert safe_relname(raw) == expected


@pytest.mark.parametrize("name,ok", [
    ("x.fit", True), ("x.FITS", True), ("x.fts", True),
    ("x.png", False), ("x.fit.gz", False), ("x", False), ("x.txt", False),
])
def test_is_fits_name(name: str, ok: bool) -> None:
    assert is_fits_name(name) is ok


def test_safe_target_dir_blank_is_incoming(tmp_path: Path) -> None:
    inc = tmp_path / "incoming"
    assert safe_target_dir(inc, "") == inc
    assert safe_target_dir(inc, "   ") == inc


def test_safe_target_dir_named_stays_under_incoming(tmp_path: Path) -> None:
    inc = tmp_path / "incoming"
    assert safe_target_dir(inc, "M31") == (inc / "M31").resolve()
    # Traversal in the target name is stripped to a basename, never escapes.
    assert safe_target_dir(inc, "../evil") == (inc / "evil").resolve()
    assert safe_target_dir(inc, "..") is None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def test_upload_saves_fits_to_incoming_and_kicks_a_scan(client, data_root, tmp_path) -> None:
    body = _fits_bytes(tmp_path)
    r = client.post(
        "/api/upload",
        data={"target": "M_99"},
        files=[("files", ("Light_001.fit", body, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["target"] == "M_99"
    assert [f["name"] for f in payload["saved"]] == ["Light_001.fit"]
    assert payload["rejected"] == []
    assert payload["job_id"]  # a scan was enqueued to ingest it
    landed = data_root / "incoming" / "M_99" / "Light_001.fit"
    assert landed.exists()
    assert landed.read_bytes() == body
    # No orphan .part sidecar left behind (the temp name is now unique, so glob).
    assert list((data_root / "incoming" / "M_99").glob("*.part")) == []


def test_upload_rejects_non_fits_but_keeps_the_good_ones(client, data_root, tmp_path) -> None:
    good = _fits_bytes(tmp_path)
    r = client.post(
        "/api/upload",
        files=[
            ("files", ("keep.fit", good, "application/octet-stream")),
            ("files", ("notes.txt", b"hello", "text/plain")),
        ],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert [f["name"] for f in payload["saved"]] == ["keep.fit"]
    assert len(payload["rejected"]) == 1
    assert payload["rejected"][0]["name"] == "notes.txt"
    assert "FITS" in payload["rejected"][0]["reason"]
    # Blank target → loose in incoming/ (the scanner's Unsorted catch-all).
    assert payload["target"] == ""
    assert (data_root / "incoming" / "keep.fit").exists()
    assert not (data_root / "incoming" / "notes.txt").exists()


def test_upload_rejects_a_traversal_filename(client, data_root, tmp_path) -> None:
    # A ``..`` segment in the (subpath-preserving) name is rejected outright rather
    # than silently rewritten — a legitimate folder upload never contains one, and
    # nothing is written outside incoming/.
    body = _fits_bytes(tmp_path)
    r = client.post(
        "/api/upload",
        files=[("files", ("../../../../evil.fit", body, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["saved"] == []
    assert [f["name"] for f in payload["rejected"]] == ["../../../../evil.fit"]
    assert not (tmp_path.parent / "evil.fit").exists()
    assert not (data_root / "incoming" / "evil.fit").exists()


def test_upload_keeps_two_same_named_subs_from_different_folders(
    client, data_root, tmp_path
) -> None:
    """Regression: a folder upload where two *different* subs share a basename
    across session subfolders (Seestar restarts frame numbering each session) must
    keep both — before the fix the second was silently dropped as "already present"
    (basename collision), losing real data."""
    write_seestar_fits(tmp_path / "a.fit", width=64, height=64, n_stars=5, seed=1)
    write_seestar_fits(tmp_path / "b.fit", width=64, height=64, n_stars=8, seed=2)
    a = (tmp_path / "a.fit").read_bytes()
    b = (tmp_path / "b.fit").read_bytes()
    assert a != b  # genuinely different subs
    r = client.post(
        "/api/upload",
        data={"target": "M_31"},
        files=[
            ("files", ("night1/Light_0001.fit", a, "application/octet-stream")),
            ("files", ("night2/Light_0001.fit", b, "application/octet-stream")),
        ],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    # Both saved, under distinct (subpath-preserving) names — nothing skipped.
    assert payload["skipped"] == []
    saved = {f["name"] for f in payload["saved"]}
    assert saved == {"night1__Light_0001.fit", "night2__Light_0001.fit"}
    d = data_root / "incoming" / "M_31"
    assert (d / "night1__Light_0001.fit").read_bytes() == a
    assert (d / "night2__Light_0001.fit").read_bytes() == b


def test_upload_skips_a_file_already_present(client, data_root, tmp_path) -> None:
    body = _fits_bytes(tmp_path)
    files = [("files", ("dup.fit", body, "application/octet-stream"))]
    first = client.post("/api/upload", data={"target": "M_dup"}, files=files)
    assert first.status_code == 200
    assert len(first.json()["saved"]) == 1
    second = client.post("/api/upload", data={"target": "M_dup"}, files=files)
    assert second.status_code == 200
    payload = second.json()
    assert payload["saved"] == []
    assert [f["name"] for f in payload["skipped"]] == ["dup.fit"]
    # Nothing new saved → no scan enqueued.
    assert payload["job_id"] is None


def test_upload_rejects_an_invalid_target_folder_name(client, tmp_path) -> None:
    body = _fits_bytes(tmp_path)
    r = client.post(
        "/api/upload",
        data={"target": ".."},
        files=[("files", ("x.fit", body, "application/octet-stream"))],
    )
    assert r.status_code == 400
    assert "target" in r.json()["detail"].lower()


class _FakeUpload:
    """Minimal UploadFile stand-in that yields its body chunk-by-chunk, awaiting
    between chunks so two concurrent streams genuinely interleave."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self._i = 0

    async def read(self, _n: int) -> bytes:
        import asyncio
        await asyncio.sleep(0)  # yield control → force interleaving
        if self._i >= len(self._chunks):
            return b""
        c = self._chunks[self._i]
        self._i += 1
        return c

    async def close(self) -> None:
        pass


def test_stream_to_disk_concurrent_same_name_never_corrupts(tmp_path) -> None:
    """Regression: two concurrent POSTs of the *same* filename used to stream into
    one shared ``<name>.part`` at once, interleaving into a corrupt file both then
    renamed into place. With a unique per-request temp file, the winner is a
    *complete* copy of exactly one upload — never a scrambled mix."""
    import asyncio

    from webapp.routers.upload import _stream_to_disk

    dest = tmp_path / "Light_001.fit"
    body_a = b"AAAAAAAA" * 2048   # 16 KiB, distinct byte from B
    body_b = b"BBBBBBBB" * 2048

    def _chunks(b: bytes, n: int = 1024) -> list[bytes]:
        return [b[i:i + n] for i in range(0, len(b), n)]

    async def _run() -> list[int]:
        return await asyncio.gather(
            _stream_to_disk(_FakeUpload(_chunks(body_a)), dest),
            _stream_to_disk(_FakeUpload(_chunks(body_b)), dest),
        )

    written = asyncio.run(_run())

    final = dest.read_bytes()
    # The landed file is a whole, uncorrupted copy of one upload (last rename
    # wins) — not an interleave of the two (which would fail both checks).
    assert final in (body_a, body_b)
    assert len(final) == len(body_a)
    assert sorted(written) == [len(body_a), len(body_b)]
    # Both unique sidecars were renamed/cleaned up — no orphan left behind.
    assert list(tmp_path.glob("*.part")) == []


def test_stream_to_disk_cleans_up_the_temp_when_the_rename_fails(tmp_path, monkeypatch) -> None:
    """Regression: an ``os.replace`` that fails *after* the temp is fully written
    (a cross-device dest, a permission / NAS blip) must not orphan the ``.part``
    sidecar — the failure now cleans up its own complete temp."""
    import asyncio

    from webapp.routers import upload as upload_mod

    dest = tmp_path / "Light_001.fit"

    def _boom(_src, _dst) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr(upload_mod.os, "replace", _boom)

    with pytest.raises(OSError):
        asyncio.run(upload_mod._stream_to_disk(_FakeUpload([b"AAAA" * 256]), dest))

    # The rename failed, so nothing landed — and the fully-written temp was
    # removed rather than left as an orphaned .part (fails-before: it stayed).
    assert not dest.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_stream_to_disk_cleans_up_the_temp_when_the_final_flush_fails(tmp_path, monkeypatch) -> None:
    """Regression: a buffered-write ENOSPC that surfaces at the *final* ``close()``
    flush (not mid-stream) must not orphan the ``.part`` sidecar. The close used to
    sit outside the unlink guard, so this last-flush failure leaked the temp."""
    import asyncio

    from webapp.routers import upload as upload_mod

    dest = tmp_path / "Light_001.fit"
    real_fdopen = upload_mod.os.fdopen

    class _CloseBoomFH:
        """Wraps the real file handle but raises ENOSPC on close (as a buffered
        flush would), after really closing the fd so nothing is leaked."""

        def __init__(self, fd: int) -> None:
            self._real = real_fdopen(fd, "wb")

        def write(self, b: bytes) -> int:
            return self._real.write(b)

        def close(self) -> None:
            self._real.close()
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(upload_mod.os, "fdopen", lambda fd, _mode: _CloseBoomFH(fd))

    with pytest.raises(OSError):
        asyncio.run(upload_mod._stream_to_disk(_FakeUpload([b"AAAA" * 256]), dest))

    # The flush failed, so nothing landed — and the partial temp was removed
    # rather than left as an orphaned .part (fails-before: it stayed).
    assert not dest.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_upload_closes_every_part_on_all_paths(client, data_root, tmp_path, monkeypatch) -> None:
    """Regression: each uploaded part is closed on *every* branch — saved, skipped,
    and rejected — not only the streamed-to-disk one. Starlette closes form uploads
    only on a parse error, so a rejected part previously leaked open until GC."""
    from starlette.datastructures import UploadFile

    closed: list[str] = []
    orig_close = UploadFile.close

    async def _tracking_close(self) -> None:
        closed.append(self.filename or "")
        await orig_close(self)

    monkeypatch.setattr(UploadFile, "close", _tracking_close)

    good = _fits_bytes(tmp_path, "good.fit")
    dup = _fits_bytes(tmp_path, "dup.fit")
    # Pre-place the dup so it takes the "already present" skip branch.
    (data_root / "incoming" / "M_close").mkdir(parents=True, exist_ok=True)
    (data_root / "incoming" / "M_close" / "dup.fit").write_bytes(dup)

    r = client.post(
        "/api/upload",
        data={"target": "M_close"},
        files=[
            ("files", ("good.fit", good, "application/octet-stream")),  # saved
            ("files", ("dup.fit", dup, "application/octet-stream")),    # skipped
            ("files", ("notes.txt", b"x", "text/plain")),               # rejected
        ],
    )
    assert r.status_code == 200, r.text
    # The framework also closes each part at request teardown, so counting is
    # relative: now that the endpoint closes on *every* path, all three parts get
    # the same number of closes. Before the fix the saved part was closed once
    # more than the skipped/rejected ones (endpoint + framework vs framework
    # only), so the counts were unequal (fails-before).
    counts = {n: closed.count(n) for n in ("good.fit", "dup.fit", "notes.txt")}
    assert all(c >= 1 for c in counts.values())
    assert len(set(counts.values())) == 1, counts


# ---------------------------------------------------------------------------
# Folder-preserving upload (``preserve_folders``)
#
# A dragged Seestar folder must land like a NAS drop — real directories under
# ``incoming/`` — so the scanner's folder convention (``<T>_sub`` → target
# ``<T>``, ``*_video`` skipped, a whole-device container expanded) actually
# fires. Flattening every path into one filename tipped every object's subs into
# a single ``Unsorted`` pile.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Light_001.fit", "Light_001.fit"),
    ("M 31_sub/Light_001.fit", "M 31_sub/Light_001.fit"),
    ("MyWorks/M 31_sub/Light_001.fit", "MyWorks/M 31_sub/Light_001.fit"),
    ("C:\\subs\\M31_sub\\Light_001.fit", "C:/subs/M31_sub/Light_001.fit"),
    ("/M 31_sub/Light_001.fit", "M 31_sub/Light_001.fit"),   # leading separator
    ("a//b/./c.fit", "a/b/c.fit"),                            # empty/dot segments
    ("  M31_sub  /  Light_001.fit  ", "M31_sub/Light_001.fit"),
    ("../../../etc/passwd", None),                            # traversal → rejected
    ("a/../b.fit", None),
    ("", None),
    # A trailing separator just means the last segment is the "filename"; it's
    # kept as a path and the FITS-suffix check downstream rejects it, so nothing
    # is ever written for it.
    ("only/dir/", "only/dir"),
    ("a\0b.fit", None),
])
def test_safe_relpath(raw: str, expected: str | None) -> None:
    assert safe_relpath(raw) == expected


def test_safe_relpath_caps_the_depth_keeping_the_tail() -> None:
    """An absurdly deep drop can't grow an unbounded tree under incoming/; the
    *tail* is kept because the target folder sits right above the file."""
    deep = "/".join(f"d{i}" for i in range(12)) + "/Light_001.fit"
    out = safe_relpath(deep)
    assert out is not None
    parts = out.split("/")
    assert len(parts) == 6
    assert parts[-1] == "Light_001.fit"
    assert parts[0] == "d7"


def test_confined_dest_rejects_an_escape(tmp_path: Path) -> None:
    root = tmp_path / "incoming"
    root.mkdir()
    assert confined_dest(root, "M31_sub/a.fit") == (root / "M31_sub" / "a.fit").resolve()
    # A symlinked subfolder pointing outside must not become a write target.
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    assert confined_dest(root, "link/a.fit") is None


def test_upload_preserves_the_dropped_folder_structure(client, data_root, tmp_path) -> None:
    """The headline: dragging a Seestar folder in creates the real folders under
    ``incoming/`` rather than one flat pile, so the Seestar-aware scanner sees
    ``M 31_sub`` / ``M 13_sub`` and makes two targets. Fails before the fix (both
    files landed flat as ``M 31_sub__Light_0001.fit`` in ``incoming/``)."""
    write_seestar_fits(tmp_path / "a.fit", width=64, height=64, n_stars=5, seed=1)
    write_seestar_fits(tmp_path / "b.fit", width=64, height=64, n_stars=8, seed=2)
    a = (tmp_path / "a.fit").read_bytes()
    b = (tmp_path / "b.fit").read_bytes()
    r = client.post(
        "/api/upload",
        data={"preserve_folders": "true"},
        files=[
            ("files", ("M 31_sub/Light_0001.fit", a, "application/octet-stream")),
            ("files", ("M 13_sub/Light_0001.fit", b, "application/octet-stream")),
        ],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert {f["name"] for f in payload["saved"]} == {
        "M 31_sub/Light_0001.fit", "M 13_sub/Light_0001.fit"}
    assert sorted(payload["folders"]) == ["M 13_sub", "M 31_sub"]
    inc = data_root / "incoming"
    assert (inc / "M 31_sub" / "Light_0001.fit").read_bytes() == a
    assert (inc / "M 13_sub" / "Light_0001.fit").read_bytes() == b
    # Nothing flattened into the root.
    assert not list(inc.glob("*.fit"))
    assert list(inc.glob("**/*.part")) == []


def test_upload_preserved_folders_nest_under_a_named_target(
    client, data_root, tmp_path
) -> None:
    body = _fits_bytes(tmp_path)
    r = client.post(
        "/api/upload",
        data={"target": "MyWorks", "preserve_folders": "true"},
        files=[("files", ("M 31_sub/Light_0001.fit", body, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    assert r.json()["folders"] == ["M 31_sub"]
    assert (data_root / "incoming" / "MyWorks" / "M 31_sub" / "Light_0001.fit").exists()


def test_upload_without_preserve_folders_is_unchanged(client, data_root, tmp_path) -> None:
    """Upgrade safety: the flag is opt-in, so an older frontend (which sends no
    ``preserve_folders``) still gets the flattened single-folder behaviour and an
    empty, ignorable ``folders`` list."""
    body = _fits_bytes(tmp_path)
    r = client.post(
        "/api/upload",
        files=[("files", ("M 31_sub/Light_0001.fit", body, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert [f["name"] for f in payload["saved"]] == ["M 31_sub__Light_0001.fit"]
    assert payload["folders"] == []
    assert (data_root / "incoming" / "M 31_sub__Light_0001.fit").exists()
    assert not (data_root / "incoming" / "M 31_sub").exists()


def test_upload_preserve_folders_still_rejects_traversal(client, data_root, tmp_path) -> None:
    body = _fits_bytes(tmp_path)
    r = client.post(
        "/api/upload",
        data={"preserve_folders": "true"},
        files=[("files", ("../../evil.fit", body, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["saved"] == []
    assert [f["name"] for f in payload["rejected"]] == ["../../evil.fit"]
    assert not (data_root / "evil.fit").exists()
    assert not (data_root / "incoming" / "evil.fit").exists()


def test_upload_preserve_folders_skips_an_already_present_file(
    client, data_root, tmp_path
) -> None:
    body = _fits_bytes(tmp_path)
    files = [("files", ("M 31_sub/Light_0001.fit", body, "application/octet-stream"))]
    first = client.post("/api/upload", data={"preserve_folders": "true"}, files=files)
    assert first.status_code == 200, first.text
    assert len(first.json()["saved"]) == 1
    second = client.post("/api/upload", data={"preserve_folders": "true"}, files=files)
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["saved"] == []
    assert [f["name"] for f in payload["skipped"]] == ["M 31_sub/Light_0001.fit"]
    assert payload["job_id"] is None  # nothing new → no scan enqueued


def test_uploaded_seestar_folders_become_the_right_targets(
    client, data_root, tmp_path
) -> None:
    """End-to-end proof of *why* this matters: run the real scanner over what the
    upload landed and confirm the Seestar convention produced the true targets
    (``M 31_sub`` → "M 31", ``*_video`` ignored) instead of one Unsorted pile."""
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    write_seestar_fits(tmp_path / "a.fit", width=64, height=64, n_stars=5, seed=1)
    write_seestar_fits(tmp_path / "b.fit", width=64, height=64, n_stars=8, seed=2)
    a = (tmp_path / "a.fit").read_bytes()
    b = (tmp_path / "b.fit").read_bytes()
    r = client.post(
        "/api/upload",
        data={"preserve_folders": "true"},
        files=[
            ("files", ("M 31_sub/Light_0001.fit", a, "application/octet-stream")),
            ("files", ("M 13_sub/Light_0001.fit", b, "application/octet-stream")),
        ],
    )
    assert r.status_code == 200, r.text

    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, data_root / "incoming")
        names = {t.name for t in lib.list_targets()}
    finally:
        lib.close()
    # The two uploaded folders became their own real targets (rather than every
    # sub landing in one "Unsorted" pile). Other fixture targets may also be
    # present in incoming/, so assert on ours specifically.
    assert {"M 31", "M 13"} <= names
    assert "Unsorted" not in names


# ---------------------------------------------------------------------------
# .zip uploads — one request instead of thousands of multipart parts
# ---------------------------------------------------------------------------

def _zip_bytes(members: dict[str, bytes]) -> bytes:
    """Build an in-memory ``.zip`` from ``{arcname: content}``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in members.items():
            zf.writestr(arcname, content)
    return buf.getvalue()


def test_upload_unpacks_a_zip_of_a_seestar_folder(client, data_root, tmp_path) -> None:
    """The headline case: a beginner right-click-compresses their Seestar folder
    and drops the single ``.zip`` in. Its FITS land keeping the archive's own
    directories — so the scanner's ``M 31_sub`` → *M 31* convention still fires —
    and the archive itself is not left on the NAS."""
    write_seestar_fits(tmp_path / "a.fit", width=64, height=64, n_stars=5, seed=1)
    write_seestar_fits(tmp_path / "b.fit", width=64, height=64, n_stars=8, seed=2)
    a = (tmp_path / "a.fit").read_bytes()
    b = (tmp_path / "b.fit").read_bytes()
    blob = _zip_bytes({
        "M 31_sub/": b"",                 # a directory entry — ignored, not a file
        "M 31_sub/Light_0001.fit": a,
        "M 31_sub/Light_0002.fit": b,
    })
    r = client.post(
        "/api/upload",
        files=[("files", ("seestar.zip", blob, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert {f["name"] for f in payload["saved"]} == {
        "M 31_sub/Light_0001.fit", "M 31_sub/Light_0002.fit"}
    assert payload["rejected"] == []
    assert payload["folders"] == ["M 31_sub"]
    assert payload["job_id"]  # a scan was enqueued to ingest the unpacked subs
    assert payload["bytes_written"] == len(a) + len(b)

    inc = data_root / "incoming"
    assert (inc / "M 31_sub" / "Light_0001.fit").read_bytes() == a
    assert (inc / "M 31_sub" / "Light_0002.fit").read_bytes() == b
    # The archive itself never stays behind, and no .part sidecar is orphaned.
    assert list(inc.glob("**/*.zip")) == []
    assert list(inc.glob("**/*.part")) == []


def test_zip_lands_inside_a_named_target_folder(client, data_root, tmp_path) -> None:
    blob = _zip_bytes({"night1/Light_0001.fit": _fits_bytes(tmp_path)})
    r = client.post(
        "/api/upload",
        data={"target": "M_99"},
        files=[("files", ("subs.zip", blob, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    assert r.json()["target"] == "M_99"
    assert (data_root / "incoming" / "M_99" / "night1" / "Light_0001.fit").exists()


def test_zip_member_traversal_never_escapes_the_destination(
    client, data_root, tmp_path
) -> None:
    """A hostile archive's ``..``/absolute entries are refused — nothing is ever
    written outside ``incoming/`` (we never call ``extractall``), and an absolute
    member is dropped rather than quietly re-rooted into a real ``etc/`` folder."""
    good = _fits_bytes(tmp_path)
    blob = _zip_bytes({
        "../../../../evil.fit": good,
        "/etc/evil.fit": good,
        "M 31_sub/Light_0001.fit": good,
    })
    r = client.post(
        "/api/upload",
        files=[("files", ("hostile.zip", blob, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    # The one legitimate member still lands; both hostile entries are refused.
    assert [f["name"] for f in payload["saved"]] == ["M 31_sub/Light_0001.fit"]
    reasons = [f["reason"] for f in payload["rejected"]]
    assert any("2 entr" in reason and "unsafe name" in reason for reason in reasons), reasons
    assert not (data_root / "evil.fit").exists()
    assert not (data_root.parent / "evil.fit").exists()
    assert not Path("/etc/evil.fit").exists()
    assert not (data_root / "incoming" / "etc").exists()
    assert not (data_root / "incoming" / "evil.fit").exists()


def test_zip_non_fits_members_are_reported_as_one_line(client, data_root, tmp_path) -> None:
    """A zipped capture folder is full of thumbnails and logs — those are left out
    and summarised in a single plain-language line, not thousands of rows."""
    good = _fits_bytes(tmp_path)
    blob = _zip_bytes({
        "M 31_sub/Light_0001.fit": good,
        "M 31_sub/thumbnail.jpg": b"jpeg",
        "M 31_sub/log.txt": b"text",
    })
    r = client.post("/api/upload", files=[("files", ("mixed.zip", blob, "application/zip"))])
    assert r.status_code == 200, r.text
    payload = r.json()
    assert [f["name"] for f in payload["saved"]] == ["M 31_sub/Light_0001.fit"]
    assert len(payload["rejected"]) == 1
    assert payload["rejected"][0]["name"] == "mixed.zip"
    assert "2 other file(s)" in payload["rejected"][0]["reason"]
    assert not (data_root / "incoming" / "M 31_sub" / "thumbnail.jpg").exists()


def test_a_file_that_is_not_really_a_zip_is_reported_plainly(client, data_root) -> None:
    r = client.post(
        "/api/upload",
        files=[("files", ("broken.zip", b"not a zip at all", "application/zip"))],
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["saved"] == []
    assert payload["job_id"] is None  # nothing landed → no scan
    assert len(payload["rejected"]) == 1
    assert "not a readable .zip file" in payload["rejected"][0]["reason"]
    assert list((data_root / "incoming").glob("**/*.part")) == []


def test_zip_member_already_present_is_skipped(client, data_root, tmp_path) -> None:
    blob = _zip_bytes({"M 31_sub/Light_0001.fit": _fits_bytes(tmp_path)})
    files = [("files", ("subs.zip", blob, "application/zip"))]
    first = client.post("/api/upload", files=files)
    assert first.status_code == 200, first.text
    assert len(first.json()["saved"]) == 1
    second = client.post("/api/upload", files=files)
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["saved"] == []
    assert [f["name"] for f in payload["skipped"]] == ["M 31_sub/Light_0001.fit"]
    assert payload["job_id"] is None


def test_a_zip_bomb_is_refused_before_anything_is_written(
    client, data_root, tmp_path, monkeypatch
) -> None:
    """The uncompressed total is checked against the free space *before* the first
    member is written — otherwise a highly-compressible archive fills the NAS."""
    blob = _zip_bytes({"M 31_sub/Light_0001.fit": _fits_bytes(tmp_path)})

    real_disk_usage = shutil.disk_usage

    class _Tiny:
        # Enough room for the archive itself, nowhere near the reserve once the
        # members' uncompressed total is counted.
        total = free = used = upload_mod._DISK_RESERVE_BYTES + len(blob) + 16

    def fake_disk_usage(path):  # noqa: ANN001
        p = Path(path)
        inc = (data_root / "incoming").resolve()
        if p.resolve() == inc or inc in p.resolve().parents:
            return _Tiny
        return real_disk_usage(path)

    monkeypatch.setattr(upload_mod.shutil, "disk_usage", fake_disk_usage)
    r = client.post("/api/upload", files=[("files", ("bomb.zip", blob, "application/zip"))])
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["saved"] == []
    assert [f["reason"] for f in payload["rejected"]] == ["not enough disk space"]
    assert not (data_root / "incoming" / "M 31_sub").exists()
    assert list((data_root / "incoming").glob("**/*.part")) == []


def test_zip_member_cap_reports_what_it_left_out(
    client, data_root, tmp_path, monkeypatch
) -> None:
    good = _fits_bytes(tmp_path)
    blob = _zip_bytes({f"M 31_sub/Light_{i:04d}.fit": good for i in range(4)})
    monkeypatch.setattr(upload_mod, "_ZIP_MAX_MEMBERS", 2)
    r = client.post("/api/upload", files=[("files", ("big.zip", blob, "application/zip"))])
    assert r.status_code == 200, r.text
    payload = r.json()
    assert len(payload["saved"]) == 2
    assert len(payload["rejected"]) == 1
    assert "only the first 2 files" in payload["rejected"][0]["reason"]
    assert "2 more left out" in payload["rejected"][0]["reason"]


def test_extract_member_stops_at_the_size_the_archive_declares(tmp_path) -> None:
    """The free-space guard trusts the zip directory's ``file_size``; a member that
    streams *more* than it declared is aborted rather than allowed to overrun it
    (a lying central directory is the classic zip-bomb shape). Leaves no sidecar."""
    class _FakeZip:
        """Hands back more bytes than the ZipInfo declares."""

        def open(self, info):  # noqa: ANN001, ARG002
            return io.BytesIO(b"x" * 4096)

    info = zipfile.ZipInfo("Light_0001.fit")
    info.file_size = 8  # declared far smaller than what the stream yields
    dest = tmp_path / "Light_0001.fit"
    with pytest.raises(ValueError):
        upload_mod._extract_member(_FakeZip(), info, dest)
    assert not dest.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_extract_member_writes_a_well_formed_entry(tmp_path) -> None:
    """Companion to the cap test: a member whose stream matches its declared size
    lands complete and atomically (no leftover sidecar)."""
    payload = b"y" * 300

    class _FakeZip:
        def open(self, info):  # noqa: ANN001, ARG002
            return io.BytesIO(payload)

    info = zipfile.ZipInfo("Light_0001.fit")
    info.file_size = len(payload)
    dest = tmp_path / "Light_0001.fit"
    assert upload_mod._extract_member(_FakeZip(), info, dest) == len(payload)
    assert dest.read_bytes() == payload
    assert list(tmp_path.glob("*.part")) == []


@pytest.mark.parametrize("name,ok", [
    ("subs.zip", True), ("SUBS.ZIP", True),
    ("x.fit", False), ("x.zip.fit", False), ("x", False), ("archive.tar.gz", False),
])
def test_is_zip_name(name: str, ok: bool) -> None:
    assert upload_mod.is_zip_name(name) is ok


def test_uploaded_zip_becomes_the_right_targets(client, data_root, tmp_path) -> None:
    """End-to-end: run the real scanner over what a dropped ``.zip`` landed and
    confirm the Seestar folder convention produced the true targets."""
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    write_seestar_fits(tmp_path / "a.fit", width=64, height=64, n_stars=5, seed=1)
    write_seestar_fits(tmp_path / "b.fit", width=64, height=64, n_stars=8, seed=2)
    blob = _zip_bytes({
        "MyWorks/M 31_sub/Light_0001.fit": (tmp_path / "a.fit").read_bytes(),
        "MyWorks/M 13_sub/Light_0001.fit": (tmp_path / "b.fit").read_bytes(),
    })
    r = client.post("/api/upload", files=[("files", ("seestar.zip", blob, "application/zip"))])
    assert r.status_code == 200, r.text
    assert len(r.json()["saved"]) == 2

    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, data_root / "incoming")
        names = {t.name for t in lib.list_targets()}
    finally:
        lib.close()
    assert {"M 31", "M 13"} <= names
    assert "Unsorted" not in names
