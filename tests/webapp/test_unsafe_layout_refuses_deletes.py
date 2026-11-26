"""An install already in the unsafe nested layout must not delete (AGENTS.md §10).

``nested_incoming_conflict`` refuses a settings save that *enters* the layout,
but an install that reached it earlier still boots (§9) — and until this fix
every destructive endpoint went ahead. The full audit (2026-11-26, backend.md
finding 9, exp3) put ``incoming/`` inside ``library/targets``: the scan adopts
each raw folder as a target's own project folder, and "Delete target, remove
files" then ``rmtree``d 3 of 6 raw subs. The raws have no backup.

These tests build exactly that shape and drive the real endpoints.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for synth
from synth import write_seestar_fits  # noqa: E402


def _raws(incoming: Path) -> list[Path]:
    return sorted(p for p in incoming.rglob("*.fit"))


@pytest.fixture
def nested_root(tmp_path: Path) -> Path:
    """``incoming/`` = ``library/targets`` — the audit's exp3 layout."""
    root = tmp_path / "data"
    library = root / "library"
    incoming = library / "targets"
    for target, ra in (("M_42", 83.6), ("NGC_7000", 314.0)):
        d = incoming / target
        d.mkdir(parents=True)
        for i in range(3):
            write_seestar_fits(
                d / f"frame_{i:03d}.fit", width=96, height=64, n_stars=10,
                seed=200 + i, add_wcs=True, ra_center_deg=ra,
                dec_center_deg=-5.0,
            )
    (root / "state").mkdir(parents=True)
    (root / "state" / "config.json").write_text(json.dumps({
        "watcher_enabled": False,
        "incoming_dir": str(incoming),
        "library_root": str(library),
    }))
    # Adopt the raw folders as targets, the way the app's scan does on a box
    # that is already in this layout.
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    lib = Library.open_or_create(library)
    try:
        scan_and_organize(lib, incoming, copy_to_cache=False)
        assert {t.safe_name for t in lib.list_targets()} >= {"M_42", "NGC_7000"}
    finally:
        lib.close()
    return root


@pytest.fixture
def nested_client(nested_root: Path, monkeypatch):
    monkeypatch.setenv("ASTROSTACK_DATA", str(nested_root))
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    from fastapi.testclient import TestClient

    from webapp.main import create_app

    with TestClient(create_app()) as c:
        yield c


def _incoming(root: Path) -> Path:
    return root / "library" / "targets"


def test_delete_target_with_files_is_refused_and_the_raws_survive(nested_root, nested_client):
    before = _raws(_incoming(nested_root))
    assert len(before) == 6
    r = nested_client.delete("/api/targets/M_42", params={"remove_files": "true"})
    assert r.status_code == 409, r.text
    assert "incoming" in r.json()["detail"]
    assert _raws(_incoming(nested_root)) == before
    # Refused, not half-done: the target is still registered.
    assert nested_client.get("/api/targets/M_42").status_code == 200


def test_delete_target_without_files_still_works(nested_root, nested_client):
    """Forgetting a target touches no file — no reason to refuse it."""
    before = _raws(_incoming(nested_root))
    r = nested_client.delete("/api/targets/M_42")
    assert r.status_code == 200, r.text
    assert _raws(_incoming(nested_root)) == before


def test_merge_is_refused(nested_root, nested_client):
    before = _raws(_incoming(nested_root))
    r = nested_client.post("/api/targets/merge",
                           json={"into": "M_42", "sources": ["NGC_7000"]})
    assert r.status_code == 409, r.text
    assert _raws(_incoming(nested_root)) == before


@pytest.mark.parametrize("call", [
    ("post", "/api/targets/M_42/cache/clear", None),
    ("post", "/api/targets/M_42/stack-runs/prune", {"keep": 0}),
    ("delete", "/api/targets/M_42/stack-runs/1", None),
    ("post", "/api/scan", None),
    ("post", "/api/reprocess-all", None),
])
def test_other_destructive_endpoints_are_refused(nested_root, nested_client, call):
    method, url, body = call
    before = _raws(_incoming(nested_root))
    r = nested_client.request(method.upper(), url, json=body)
    assert r.status_code == 409, (url, r.status_code, r.text)
    assert "incoming" in r.json()["detail"]
    assert _raws(_incoming(nested_root)) == before


def test_system_reports_the_conflict_for_the_dashboard(nested_client):
    folders = nested_client.get("/api/system").json()["folders"]
    assert folders["layout_conflict"]
    assert "incoming" in folders["layout_conflict"]


def test_a_queued_pipeline_refuses_to_scan(nested_root):
    """The watcher queues the pipeline without going through the endpoint."""
    from webapp import pipeline
    from webapp.config import SettingsStore

    settings = SettingsStore(str(nested_root)).get()

    class _Job:
        id = "j"

        def set_progress(self, *a, **k):  # pragma: no cover - must not be reached
            raise AssertionError("the scan started")

    with pytest.raises(RuntimeError, match="incoming"):
        pipeline._pipeline_body(settings, None, _Job(), root=None)


def test_a_safe_layout_reports_no_conflict(client):
    folders = client.get("/api/system").json()["folders"]
    assert folders.get("layout_conflict") is None
