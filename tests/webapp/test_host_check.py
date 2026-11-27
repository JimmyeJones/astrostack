"""The API answers home-network names only (DNS-rebinding guard, audit 2026-11-26)."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("host", [
    "192.168.1.20:8000", "truenas-scale:8000", "truenas-scale", "localhost:8000",
    "nas.local", "nas.lan:8000", "nas.home.arpa", "box.tailnet-123.ts.net", "testserver",
    "[::1]:8000", "10.0.0.5",
])
def test_home_network_hosts_are_answered(client, host):
    r = client.get("/api/settings", headers={"Host": host})
    assert r.status_code == 200, (host, r.text)


@pytest.mark.parametrize("host", ["evil.example.com", "attacker.net:8000",
                                  "rebind.12-34-56-78.nip.io"])
def test_public_names_are_refused(client, host):
    r = client.get("/api/settings", headers={"Host": host})
    assert r.status_code == 421
    assert "ASTROSTACK_ALLOWED_HOSTS" in r.json()["detail"]
    r = client.put("/api/settings", json={"auto_stack": True}, headers={"Host": host})
    assert r.status_code == 421


def test_the_owners_own_domain_can_be_allowed(client, monkeypatch):
    monkeypatch.setenv("ASTROSTACK_ALLOWED_HOSTS", "astro.example.com, *.mydomain.org")
    for host in ("astro.example.com", "nas.mydomain.org", "mydomain.org"):
        assert client.get("/api/settings", headers={"Host": host}).status_code == 200
    assert client.get("/api/settings", headers={"Host": "other.example.com"}).status_code == 421


def test_health_stays_open_for_the_docker_probe(client):
    assert client.get("/api/health", headers={"Host": "evil.example.com"}).status_code == 200


def test_the_page_itself_still_loads_under_any_name(client):
    r = client.get("/", headers={"Host": "evil.example.com"})
    assert r.status_code != 421
