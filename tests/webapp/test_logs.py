"""In-app log buffer endpoint."""

from __future__ import annotations

import logging


def test_logs_endpoint_captures_recent_messages(client):
    logging.getLogger("seestack.stack.test").warning(
        "Output canvas: 11194x14127 union of 2773 footprints",
    )
    r = client.get("/api/logs", params={"level": "WARNING"})
    assert r.status_code == 200
    body = r.json()
    msgs = [e["message"] for e in body["logs"]]
    assert any("11194x14127" in m for m in msgs)
    assert body["last_seq"] >= 1


def test_logs_level_filter_excludes_info(client):
    logging.getLogger("seestack.test").info("an info line that should be filtered out")
    logging.getLogger("seestack.test").error("a distinctive error line xyzzy")
    r = client.get("/api/logs", params={"level": "ERROR"})
    msgs = [e["message"] for e in r.json()["logs"]]
    assert any("xyzzy" in m for m in msgs)
    assert all("should be filtered out" not in m for m in msgs)
