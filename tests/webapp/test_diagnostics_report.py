"""``POST/GET /api/diagnostics/report`` — "Create a report for Claude" (1.0 roadmap M1)."""
from __future__ import annotations

import json


def test_report_endpoints(client):
    r = client.post("/api/diagnostics/report")
    assert r.status_code == 200 and r.json()["job_id"]
    again = client.post("/api/diagnostics/report")
    assert again.status_code == 200
    rep = client.get("/api/diagnostics/report")
    assert rep.status_code == 200
    assert "attachment" in rep.headers.get("content-disposition", "")
    body = rep.json()
    assert body["astrostack_report"] == 1
    assert {"diagnostics", "pending", "seestar", "jobs", "app_version"} <= set(body)
    assert "key" in body["seestar"]
    text = json.dumps(body)
    assert "/data" not in text and "incoming/" not in text
