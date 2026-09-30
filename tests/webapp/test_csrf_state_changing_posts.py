"""Regression test: state-changing endpoints must not be triggerable by a
cross-site "simple request" on the passwordless LAN app (audit 2026-09-30, sec C).

The app has no password by default (AGENTS.md §1). A cross-site page can send a
form-encoded or bodiless POST with NO CORS preflight (an auto-submitting <form>),
and the browser will attach any cached Basic-auth credentials. Endpoints that take
a JSON/pydantic body are safe — a browser cannot send application/json cross-site
without a preflight this app never grants (see webapp/routers/updates.py). But an
endpoint that accepts an empty/optional/form body is CSRF-triggerable.

This test posts exactly what a cross-site form sends (empty body, and
application/x-www-form-urlencoded) at endpoints that queue whole-library work or
mutate state, and asserts they are refused. It FAILS on main @ 024babd, where each
returns 200/2xx (verified: /api/reprocess-all, /api/scan, /api/jobs/clear). The fix
is an Origin/Referer (or Sec-Fetch-Site) check on state-changing methods, or a
required body on each endpoint.
"""
from __future__ import annotations

import pytest

# Endpoints that perform or queue real work / mutate state and currently accept a
# body-less or form request. Kept to a few high-impact ones so the intent is clear.
CSRF_SENSITIVE = [
    "/api/reprocess-all",   # restacks the ENTIRE library — hours/days of CPU
    "/api/scan",            # full rescan of incoming/
    "/api/jobs/clear",      # clears the job history
]


@pytest.mark.parametrize("path", CSRF_SENSITIVE)
def test_bodiless_cross_site_post_is_refused(client, path: str) -> None:
    r = client.post(path)
    assert r.status_code in (403, 422), (
        f"{path} accepted a bodiless (CSRF-shaped) POST: {r.status_code}")


@pytest.mark.parametrize("path", CSRF_SENSITIVE)
def test_form_encoded_cross_site_post_is_refused(client, path: str) -> None:
    # Exactly what an auto-submitting cross-site <form> sends: no preflight.
    r = client.post(path, data={}, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code in (403, 422), (
        f"{path} accepted a form-encoded (CSRF-shaped) POST: {r.status_code}")
