"""Bulk FITS upload endpoint + its pure sanitisation helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root ahead of tests/ so ``import webapp`` finds the real package, not the
# ``tests/webapp`` test package (conftest puts tests/ on the path for ``synth``).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from synth import write_seestar_fits  # noqa: E402

from webapp.routers.upload import (  # noqa: E402
    is_fits_name,
    safe_component,
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


def test_upload_strips_a_traversal_filename_to_a_basename(client, data_root, tmp_path) -> None:
    body = _fits_bytes(tmp_path)
    r = client.post(
        "/api/upload",
        files=[("files", ("../../../../evil.fit", body, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    assert [f["name"] for f in r.json()["saved"]] == ["evil.fit"]
    # Written strictly inside incoming/, never at a traversed path.
    assert (data_root / "incoming" / "evil.fit").exists()
    assert not (tmp_path.parent / "evil.fit").exists()


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
