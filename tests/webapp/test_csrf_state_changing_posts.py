"""Regression tests: state-changing endpoints must not be triggerable by a
cross-site request on the passwordless LAN app (audit 2026-09-30, section C-F2).

The app has no password by default (AGENTS.md §1). A page on any other site the
owner visits can auto-submit a ``<form>`` at it — a bodiless or form-encoded POST
that needs no CORS preflight — and the browser will attach any cached Basic-auth
credentials, so a password does not help. Endpoints that take a JSON body are
safe on their own (a browser will not send ``application/json`` cross-site
without a preflight this app never grants), but ``/api/reprocess-all``,
``/api/scan``, ``/api/jobs/clear`` and their kind accept an empty body, and each
returned 200 to such a request on main @ 024babd.

The fix is one check in the auth gate (``webapp/main.py``): for every
state-changing method, a request whose ``Sec-Fetch-Site`` says ``cross-site``,
or whose ``Origin`` (else ``Referer``) names a different host than the request's
``Host``, is refused with 403. A browser always sends at least one of those on a
cross-site POST and cannot forge them from a page. A request carrying none of
them (curl, the observer's scripts, this test client by default) is allowed —
that is the standard trade, and it keeps the owner's own tools working.

The audit's own version of this test sent *no* headers at all and expected a
refusal; that would have refused every script the owner runs, so the cross-site
cases here carry exactly what a browser sends from another site, and the
no-header case is pinned as *allowed*.
"""
from __future__ import annotations

import pytest

# Endpoints that perform or queue real work / mutate state and accept a
# body-less or form request. Kept to a few high-impact ones so the intent is clear.
CSRF_SENSITIVE = [
    "/api/reprocess-all",   # restacks the ENTIRE library — hours/days of CPU
    "/api/scan",            # full rescan of incoming/
    "/api/jobs/clear",      # clears the job history
]

FORM = {"Content-Type": "application/x-www-form-urlencoded"}
# What a browser sends when a page on another site submits a form at the app.
EVIL_ORIGIN = {"Origin": "http://evil.example"}


@pytest.mark.parametrize("path", CSRF_SENSITIVE)
def test_bodiless_cross_site_post_is_refused(client, path: str) -> None:
    r = client.post(path, headers=EVIL_ORIGIN)
    assert r.status_code == 403, (
        f"{path} accepted a bodiless cross-site POST: {r.status_code}")
    assert "another site" in r.json()["detail"]


@pytest.mark.parametrize("path", CSRF_SENSITIVE)
def test_form_encoded_cross_site_post_is_refused(client, path: str) -> None:
    # Exactly what an auto-submitting cross-site <form> sends: no preflight.
    r = client.post(path, data={}, headers={**FORM, **EVIL_ORIGIN})
    assert r.status_code == 403, (
        f"{path} accepted a form-encoded cross-site POST: {r.status_code}")


@pytest.mark.parametrize("path", CSRF_SENSITIVE)
def test_sec_fetch_site_cross_site_is_refused_even_with_a_matching_origin(
        client, path: str) -> None:
    # The fetch-metadata header is set by the browser and cannot be forged by a
    # page; it is checked first and on its own.
    r = client.post(path, headers={"Sec-Fetch-Site": "cross-site",
                                   "Origin": "http://testserver"})
    assert r.status_code == 403


def test_a_referer_from_another_site_is_refused_when_there_is_no_origin(client) -> None:
    r = client.post("/api/jobs/clear", headers={"Referer": "http://evil.example/page"})
    assert r.status_code == 403


def test_an_origin_of_null_is_refused(client) -> None:
    # A sandboxed iframe or a page on a data: URL sends ``Origin: null``; the
    # app's own pages never do.
    r = client.post("/api/jobs/clear", headers={"Origin": "null"})
    assert r.status_code == 403


def test_a_matching_host_on_another_port_is_refused(client) -> None:
    # The port is part of the origin: a page served by some other service on the
    # same NAS is a different site.
    r = client.post("/api/jobs/clear", headers={"Origin": "http://testserver:9000"})
    assert r.status_code == 403


def test_a_password_does_not_help_a_cross_site_request(client) -> None:
    """The browser resends cached Basic credentials, so the credential is the
    victim's; the request is still refused, and before any password check."""
    client.post("/api/auth/password", json={"password": "secret1"})
    try:
        r = client.post("/api/jobs/clear", headers=EVIL_ORIGIN, auth=("admin", "secret1"))
        assert r.status_code == 403
        assert "another site" in r.json()["detail"]
    finally:
        client.post("/api/auth/password", json={"password": ""}, auth=("admin", "secret1"))


# --- what must keep working ------------------------------------------------------

@pytest.mark.parametrize("path", CSRF_SENSITIVE)
def test_the_apps_own_frontend_is_allowed(client, path: str) -> None:
    # A same-origin fetch sends both of these; ``testserver`` is this client's host.
    r = client.post(path, headers={"Origin": "http://testserver",
                                   "Sec-Fetch-Site": "same-origin"})
    assert r.status_code != 403, (path, r.status_code, r.text)


def test_a_matching_origin_alone_is_allowed(client) -> None:
    r = client.post("/api/jobs/clear", headers={"Origin": "http://testserver"})
    assert r.status_code == 200


def test_a_matching_referer_alone_is_allowed(client) -> None:
    r = client.post("/api/jobs/clear", headers={"Referer": "http://testserver/jobs"})
    assert r.status_code == 200


def test_default_ports_are_understood(client) -> None:
    # ``Origin: http://host`` and ``Host: host:80`` name one origin.
    r = client.post("/api/jobs/clear", headers={"Origin": "http://testserver:80"})
    assert r.status_code == 200


def test_the_vite_dev_proxy_shape_is_allowed(client) -> None:
    # `npm run dev` proxies /api to the backend without rewriting Host
    # (frontend/vite.config.ts sets no changeOrigin), so the backend sees the
    # dev server's own host in both headers.
    r = client.post("/api/jobs/clear", headers={"Host": "localhost:5173",
                                                "Origin": "http://localhost:5173"})
    assert r.status_code == 200


def test_a_proxied_install_is_allowed_by_the_forwarded_host(client) -> None:
    # A reverse proxy that rewrites Host still forwards the browser's host; a
    # page cannot set X-Forwarded-Host without a preflight, so it is safe to
    # accept as a second name for "this site".
    r = client.post("/api/jobs/clear", headers={"Origin": "http://astro.lan",
                                                "X-Forwarded-Host": "astro.lan"})
    assert r.status_code == 200


@pytest.mark.parametrize("path", CSRF_SENSITIVE)
def test_a_request_with_no_browser_headers_is_allowed(client, path: str) -> None:
    # curl, the observer's scripts, the owner's own tooling: no Origin, no
    # Referer, no Sec-Fetch-Site. Refusing these would break every script.
    r = client.post(path)
    assert r.status_code != 403, (path, r.status_code, r.text)


def test_reads_are_never_refused(client) -> None:
    # Only state-changing methods are gated: a cross-site GET can be embedded
    # in an <img> and refusing it would gain nothing.
    r = client.get("/api/jobs", headers={**EVIL_ORIGIN, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200


def test_health_stays_open(client) -> None:
    assert client.get("/api/health", headers=EVIL_ORIGIN).status_code == 200
