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
    # No orphan .part sidecar left behind.
    assert not (data_root / "incoming" / "M_99" / "Light_001.fit.part").exists()


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
