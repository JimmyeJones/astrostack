"""API responses are gzip-compressed for browsers that accept it (audit 2026-11-26:
the deepest target's page downloaded 20.6 MB of frame JSON uncompressed)."""
from __future__ import annotations


def test_a_large_json_response_is_compressed(client):
    r = client.get("/api/glossary", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_no_compression_without_asking(client):
    r = client.get("/api/glossary", headers={"Accept-Encoding": "identity"})
    assert r.headers.get("content-encoding") is None


def test_the_docker_health_probe_gets_plain_json(client):
    # The compose healthcheck uses urllib, which asks for no encoding.
    r = client.get("/api/health", headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") is None
