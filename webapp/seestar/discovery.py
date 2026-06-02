"""Find Seestar scopes on the LAN by probing TCP port 4700.

There's no official discovery protocol, so we sweep a subnet: either the CIDR
the user configured, or one auto-derived from the container's primary route.
Each host gets a short-timeout TCP connect to 4700; the ones that accept are
candidate Seestars. Probing is done with a bounded thread pool so a /24 sweep
finishes in a couple of seconds even though most hosts don't answer.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from concurrent.futures import ThreadPoolExecutor

from webapp.seestar.client import DEFAULT_PORT

log = logging.getLogger(__name__)

_PROBE_TIMEOUT = 0.4
_MAX_WORKERS = 64
# Don't try to sweep anything bigger than a /23 — a /16 would be 65k probes.
_MAX_HOSTS = 1024


def _primary_ipv4() -> str | None:
    """Best-effort local IPv4 address (the one used for off-box traffic)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packets sent for UDP connect
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _candidate_network(subnet: str) -> ipaddress.IPv4Network | None:
    if subnet.strip():
        try:
            return ipaddress.ip_network(subnet.strip(), strict=False)  # type: ignore[return-value]
        except ValueError:
            log.warning("seestar: invalid scan subnet %r; falling back to auto", subnet)
    ip = _primary_ipv4()
    if not ip:
        return None
    try:
        return ipaddress.ip_network(f"{ip}/24", strict=False)  # type: ignore[return-value]
    except ValueError:
        return None


def _probe(host: str, port: int = DEFAULT_PORT) -> bool:
    try:
        with socket.create_connection((host, port), _PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def scan(subnet: str = "", *, extra_ips: list[str] | None = None) -> list[str]:
    """Return reachable Seestar IPs (port 4700 open) on the subnet, plus any
    ``extra_ips`` that respond. Result is sorted and de-duplicated."""
    found: set[str] = set()
    targets: list[str] = list(extra_ips or [])

    net = _candidate_network(subnet)
    if net is not None:
        hosts = list(net.hosts())
        if len(hosts) > _MAX_HOSTS:
            log.warning("seestar: subnet %s too large (%d hosts); skipping sweep",
                        net, len(hosts))
        else:
            targets.extend(str(h) for h in hosts)

    if not targets:
        return []

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        for host, ok in zip(targets, pool.map(_probe, targets)):
            if ok:
                found.add(host)
    return sorted(found, key=lambda ip: tuple(int(p) for p in ip.split(".")))
