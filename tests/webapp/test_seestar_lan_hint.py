"""Seestar discovery from inside a bridged Docker container, and ``{ip}`` validation.

Audit 2026-11-26: with no subnet set, discovery broadcast on the container's own
(bridge) network, so it could never find the owner's scope; and the ``{ip}``
path parameter accepted any host string.
"""
from __future__ import annotations

import ipaddress

import pytest

from webapp.seestar import discovery


@pytest.mark.parametrize("host, net", [
    ("192.168.1.20:8000", "192.168.1.0/24"),
    ("10.0.0.5", "10.0.0.0/24"),
    ("127.0.0.1:8000", None),
    ("8.8.8.8", None),
    ("[fe80::1]:8000", None),
    (None, None),
    ("", None),
])
def test_lan_hint_is_the_private_network_the_browser_used(host, net):
    got = discovery.lan_hint_network(host)
    assert (str(got) if got else None) == net


def test_an_unknown_name_gives_no_hint():
    assert discovery.lan_hint_network("no-such-host.invalid:8000") is None


def test_scan_sweeps_the_hinted_lan_only_when_nothing_else_answers(monkeypatch):
    probed: list[str] = []
    monkeypatch.setattr(discovery, "discover_udp", lambda subnet, timeout: {})
    monkeypatch.setattr(discovery, "_probe",
                        lambda host, port=4700: probed.append(host) or host == "192.168.7.42")
    hint = ipaddress.ip_network("192.168.7.0/24")
    assert discovery.scan("", lan_hint=hint) == ["192.168.7.42"]
    assert len(probed) == 254
    probed.clear()
    # A pinned scope or an explicit subnet means the owner told us where to look.
    discovery.scan("", extra_ips=["192.168.7.9"], lan_hint=hint)
    assert probed == ["192.168.7.9"]
    probed.clear()
    discovery.scan("", lan_hint=None)
    assert probed == []


@pytest.mark.parametrize("ip, ok", [
    ("192.168.1.50", True), ("10.1.2.3", True),
    ("127.0.0.1", True), ("8.8.8.8", False), ("example.com", False),
    ("192.168.1.50:80", False),
])
def test_scope_addresses_must_be_on_the_home_network(client, ip, ok):
    r = client.get(f"/api/seestar/{ip}/state")
    if ok:
        assert r.status_code != 422
    else:
        assert r.status_code == 422, r.text
