"""Find Seestar scopes on the LAN.

The reliable way is the scope's own protocol: broadcast a ``scan_iscope`` UDP
datagram on port 4720 and treat anything that answers as a genuine Seestar
(other devices that merely happen to have TCP 4700 open won't reply). We keep an
optional TCP-4700 sweep as a fallback, but only when the user explicitly sets a
subnet — auto-sweeping the whole /24 tends to surface unrelated boxes that
accept the socket and then sit silent, which is just noise.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from webapp.seestar.client import DEFAULT_PORT

log = logging.getLogger(__name__)

_PROBE_TIMEOUT = 0.4
_MAX_WORKERS = 64
# Don't try to sweep anything bigger than a /23 — a /16 would be 65k probes.
_MAX_HOSTS = 1024

_UDP_PORT = 4720
_UDP_MSG = json.dumps({"id": 1, "method": "scan_iscope", "params": ""}).encode("utf-8")


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


def _broadcast_addrs(subnet: str) -> list[str]:
    """Broadcast targets for UDP discovery: the subnet-directed broadcast (most
    reliable) plus the global broadcast as a fallback."""
    addrs = ["255.255.255.255"]
    net = _candidate_network(subnet)
    if net is not None:
        addrs.insert(0, str(net.broadcast_address))
    return list(dict.fromkeys(addrs))  # dedupe, keep order


def discover_udp(subnet: str = "", *, timeout: float = 1.5) -> dict[str, dict]:
    """Broadcast ``scan_iscope`` and collect responders. Returns a map of
    ``ip -> parsed reply`` (reply may be empty if it didn't parse — the address
    alone confirms a Seestar). Never raises."""
    found: dict[str, dict] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.4)
        for addr in _broadcast_addrs(subnet):
            try:
                sock.sendto(_UDP_MSG, (addr, _UDP_PORT))
            except OSError as exc:
                log.debug("seestar: udp broadcast to %s failed: %s", addr, exc)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, peer = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            ip = peer[0]
            reply: dict = {}
            try:
                parsed = json.loads(data.decode("utf-8", "replace"))
                if isinstance(parsed, dict):
                    reply = parsed
            except ValueError:
                pass
            found[ip] = reply
    finally:
        sock.close()
    if found:
        log.info("seestar: UDP discovery found %s", ", ".join(sorted(found)))
    return found


def _probe(host: str, port: int = DEFAULT_PORT) -> bool:
    try:
        with socket.create_connection((host, port), _PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def scan(subnet: str = "", *, extra_ips: list[str] | None = None,
         udp_timeout: float = 1.5) -> list[str]:
    """Discover Seestars. Combines native UDP discovery (trustworthy), any
    ``extra_ips`` the user pinned, and — only when ``subnet`` is explicitly
    set — a TCP-4700 sweep of that subnet. Returns sorted, de-duplicated IPs."""
    found: set[str] = set(discover_udp(subnet, timeout=udp_timeout))

    # User-pinned IPs: confirm with a quick TCP probe so dead entries drop off.
    tcp_targets = list(extra_ips or [])
    # Only sweep a subnet when the user opted in by configuring one explicitly.
    if subnet.strip():
        net = _candidate_network(subnet)
        if net is not None:
            hosts = list(net.hosts())
            if len(hosts) > _MAX_HOSTS:
                log.warning("seestar: subnet %s too large (%d hosts); skipping sweep",
                            net, len(hosts))
            else:
                tcp_targets.extend(str(h) for h in hosts)

    if tcp_targets:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            for host, ok in zip(tcp_targets, pool.map(_probe, tcp_targets)):
                if ok:
                    found.add(host)

    return sorted(found, key=lambda ip: tuple(int(p) for p in ip.split(".")))
