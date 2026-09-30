"""Settings → App updates: the endpoints that ask the NAS helper to update.

The page half only reads ``state/updater/status.json`` and writes
``state/updater/request.json``; ``scripts/update_agent.py`` does the work. The
last test here is the contract between the two: every request this router
writes is one the helper's validator accepts, and it never carries a ref.
"""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import pytest

import webapp
from webapp.routers.updates import HELPER_STALE_S, update_status

ROOT = Path(__file__).resolve().parents[2]


def _queue(data_root: Path) -> Path:
    q = data_root / "state" / "updater"
    q.mkdir(parents=True, exist_ok=True)
    return q


def _helper(data_root: Path, **fields) -> Path:
    """Write the status file the NAS helper would write."""
    q = _queue(data_root)
    status = {"schema": 1, "agent_version": 1, "agent_seen_at": time.time(),
              "state": "idle", "job": None, "available": None, "rollback": None,
              "last_result": None, **fields}
    (q / "status.json").write_text(json.dumps(status))
    return q


def _newer() -> str:
    parts = [int(p) for p in webapp.__version__.split(".")]
    parts[-1] += 1
    return ".".join(map(str, parts))


def test_no_helper_reads_as_missing_and_refuses_every_action(client, data_root) -> None:
    st = client.get("/api/updates").json()
    assert st["helper"] == "missing" and st["running_version"] == webapp.__version__
    for path, body in (("/api/updates/check", {}), ("/api/updates/apply", {"version": _newer()}),
                       ("/api/updates/rollback", {})):
        r = client.post(path, json=body)
        assert r.status_code == 409 and "helper" in r.json()["detail"]
    assert not (data_root / "state" / "updater" / "request.json").exists()


def test_a_stale_heartbeat_reads_as_stale(data_root) -> None:
    q = _helper(data_root, agent_seen_at=time.time() - HELPER_STALE_S - 5, state="updating")
    st = update_status(q)
    assert st["helper"] == "stale" and st["state"] == "idle"


def test_check_writes_one_request_and_then_reads_as_pending(client, data_root) -> None:
    q = _helper(data_root)
    r = client.post("/api/updates/check", json={})
    assert r.status_code == 200 and r.json()["action"] == "check"
    req = json.loads((q / "request.json").read_text())
    assert req["action"] == "check" and isinstance(req["requested_at"], float)
    st = client.get("/api/updates").json()
    assert st["pending"] == {"id": req["id"], "action": "check"}
    assert client.post("/api/updates/check", json={}).status_code == 409     # one at a time


def test_an_hour_old_request_no_longer_counts_as_pending(data_root) -> None:
    q = _helper(data_root)
    (q / "request.json").write_text(json.dumps({"id": "x", "action": "check",
                                                "requested_at": time.time() - 3700}))
    assert update_status(q)["pending"] is None


def test_busy_helper_refuses_a_second_action(client, data_root) -> None:
    _helper(data_root, state="updating", job={"id": "a", "action": "update"})
    assert client.post("/api/updates/check", json={}).status_code == 409


def test_update_needs_a_newer_checked_version(client, data_root) -> None:
    _helper(data_root, available={"version": webapp.__version__, "commit": "abc"})
    st = client.get("/api/updates").json()
    assert st["update_available"] is False
    assert client.post("/api/updates/apply", json={"version": webapp.__version__}).status_code == 409

    q = _helper(data_root, available={"version": _newer(), "commit": "abc"})
    assert client.get("/api/updates").json()["update_available"] is True
    r = client.post("/api/updates/apply", json={"version": "9.9.9"})       # not what was offered
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    assert not (q / "request.json").exists()
    r = client.post("/api/updates/apply", json={"version": _newer()})
    assert r.status_code == 200
    assert json.loads((q / "request.json").read_text())["action"] == "update"


def test_version_comparison_is_numeric_not_text(data_root) -> None:
    parts = webapp.__version__.split(".")
    ten_more = ".".join(parts[:-1] + [str(int(parts[-1]) + 10)])
    q = _helper(data_root, available={"version": ten_more})
    assert update_status(q)["update_available"] is True


def test_rollback_rules(client, data_root) -> None:
    _helper(data_root)
    assert client.post("/api/updates/rollback", json={}).status_code == 409   # nothing recorded

    q = _helper(data_root, rollback={"to_version": "0.455.7", "needs_restore_data": True,
                                     "backup": "snapshot"})
    r = client.post("/api/updates/rollback", json={})
    assert r.status_code == 409 and "database format" in r.json()["detail"]
    r = client.post("/api/updates/rollback", json={"restore_data": True, "confirm": "restore"})
    assert r.status_code == 400
    assert not (q / "request.json").exists()
    r = client.post("/api/updates/rollback", json={"restore_data": True, "confirm": "RESTORE"})
    assert r.status_code == 200
    req = json.loads((q / "request.json").read_text())
    assert req["restore_data"] is True and req["confirm"] == "RESTORE"


def test_code_only_rollback_when_the_old_version_can_read_the_data(client, data_root) -> None:
    q = _helper(data_root, rollback={"to_version": "0.480.0", "needs_restore_data": False})
    assert client.post("/api/updates/rollback", json={}).status_code == 200
    req = json.loads((q / "request.json").read_text())
    assert req["restore_data"] is False and "confirm" not in req


def test_every_request_the_page_writes_is_one_the_helper_accepts(client, data_root) -> None:
    spec = importlib.util.spec_from_file_location("update_agent", ROOT / "scripts" / "update_agent.py")
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    cases = [
        ("/api/updates/check", {}, {"available": None}),
        ("/api/updates/apply", {"version": _newer()}, {"available": {"version": _newer()}}),
        ("/api/updates/rollback", {"restore_data": True, "confirm": "RESTORE"},
         {"rollback": {"to_version": "0.1.0", "needs_restore_data": True}}),
        ("/api/updates/rollback", {}, {"rollback": {"to_version": "0.1.0", "needs_restore_data": False}}),
    ]
    for path, body, fields in cases:
        q = _helper(data_root, **fields)
        (q / "request.json").unlink(missing_ok=True)
        assert client.post(path, json=body).status_code == 200, path
        raw = (q / "request.json").read_bytes()
        parsed = agent.validate_request(raw, now=time.time())
        assert parsed["action"] == path.rsplit("/", 1)[1].replace("apply", "update")
        assert "ref" not in json.loads(raw)


@pytest.mark.parametrize("path", ["/api/updates", "/api/updates/check"])
def test_the_observer_token_cannot_reach_updates(path) -> None:
    from webapp.main import _READONLY_GET_PATHS

    assert path not in _READONLY_GET_PATHS


@pytest.mark.parametrize("path", ["/api/updates/check", "/api/updates/apply", "/api/updates/rollback"])
def test_a_bodiless_or_form_post_cannot_start_anything(client, data_root, path) -> None:
    """What a cross-site page can send without a CORS preflight: no body, or a
    form / text body. None of it may queue a request."""
    q = _helper(data_root, available={"version": _newer()},
                rollback={"to_version": "0.1.0", "needs_restore_data": False})
    assert client.post(path).status_code == 422
    r = client.post(path, content=f'{{"version": "{_newer()}"}}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 422
    r = client.post(path, data={"version": _newer()})
    assert r.status_code == 422
    assert not (q / "request.json").exists()
