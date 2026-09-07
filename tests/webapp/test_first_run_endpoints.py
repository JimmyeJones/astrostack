"""Every read-only endpoint answers on a brand-new install, and on a target
that has been ingested but never stacked.

Those are the two states a beginner is actually in first, and they are the two
the rest of the suite tests least: nearly every webapp test builds a library,
solves it and stacks it before it asks a question, because that is what the
interesting assertions need. So an endpoint that divides by a zero frame count,
indexes ``[0]`` into an empty run list, or reads a preview file that does not
exist yet would be caught by nobody until it 500-ed on somebody's first
evening — the one session where a stack trace is least recoverable, because
there is nothing on screen to go back to.

The sweep is enumerated from the app's **own OpenAPI schema** rather than a
hand-written list, so an endpoint added next month is covered the day it is
added and nobody has to remember this file exists. It asserts only the weak
thing — *no 5xx* — deliberately: 404 ("no picture yet") and 422 ("that needs a
query parameter") are honest answers to these questions and each endpoint's own
tests pin what it should actually say. What this pins is that the answer is
never a crash.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _get_paths(client, *, templated: bool) -> list[str]:
    """Every ``/api`` GET path in the app's schema, with or without parameters.

    ``templated=False`` returns the parameterless ones; ``templated=True``
    returns the ones whose only parameter is ``{safe}`` (a target), which is the
    largest family and the one a never-stacked target exercises. Paths needing a
    run/frame/job id are left out — they have no answer before the first stack,
    and "404 for a run that does not exist" is a different question.
    """
    paths = []
    for path, ops in client.app.openapi()["paths"].items():
        if "get" not in ops or not path.startswith("/api"):
            continue
        has_param = "{" in path
        if templated:
            if "{safe}" not in path or path.replace("{safe}", "").count("{"):
                continue
        elif has_param:
            continue
        paths.append(path)
    return sorted(set(paths))


def _sweep(client, paths: list[str], *, safe: str | None = None) -> list[str]:
    """GET each path; return a readable line per 5xx (or raised) response."""
    failures = []
    for path in paths:
        url = path.replace("{safe}", safe) if safe else path
        try:
            resp = client.get(url)
        except Exception as exc:  # noqa: BLE001 — a raised handler is the bug
            failures.append(f"{url} raised {exc!r}")
            continue
        if resp.status_code >= 500:
            failures.append(f"{url} -> {resp.status_code} {resp.text[:200]}")
    return failures


@pytest.fixture
def fresh_client(tmp_path: Path, monkeypatch):
    """A client over a data root with **nothing** in it — not even ``incoming/``.

    Deliberately not the shared ``client`` fixture, whose ``data_root`` already
    writes two folders of synthetic subs: this is the state the app is in the
    first time it is opened, before the owner has pointed it at anything.
    """
    monkeypatch.setenv("ASTROSTACK_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    from fastapi.testclient import TestClient

    from webapp.main import create_app

    with TestClient(create_app()) as c:
        c.put("/api/settings", json={"watcher_enabled": False})
        yield c


def test_the_sweep_would_actually_report_a_crash():
    """The two sweeps below assert an *empty* list, so a helper that quietly
    reported nothing would pass for ever. Point it at a route that raises."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/api/boom")
    def boom() -> dict:
        raise RuntimeError("first-run crash")

    @app.get("/api/fine")
    def fine() -> dict:
        return {}

    with TestClient(app, raise_server_exceptions=False) as c:
        assert _get_paths(c, templated=False) == ["/api/boom", "/api/fine"]
        failures = _sweep(c, ["/api/boom", "/api/fine"])
    assert len(failures) == 1 and failures[0].startswith("/api/boom -> 500")


def test_every_parameterless_get_answers_on_a_brand_new_install(fresh_client):
    paths = _get_paths(fresh_client, templated=False)
    # A guard on the enumeration itself: if the schema walk ever silently stops
    # matching (a FastAPI upgrade, a router moved), an empty sweep would pass.
    assert len(paths) > 30, f"only found {len(paths)} parameterless GETs"
    assert fresh_client.get("/api/targets").json() == [], "fixture is not empty"
    assert _sweep(fresh_client, paths) == []


def test_every_target_get_answers_before_the_first_stack(client, built_library):
    targets = client.get("/api/targets").json()
    assert targets, "built_library should have produced targets"
    safe = targets[0]["safe_name"]
    assert client.get(f"/api/targets/{safe}/stack-runs").json() == [], \
        "this target must not have been stacked"
    paths = _get_paths(client, templated=True)
    assert len(paths) > 20, f"only found {len(paths)} per-target GETs"
    assert _sweep(client, paths, safe=safe) == []
