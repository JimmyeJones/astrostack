"""``GET /api/targets/{safe}`` → ``auto_stack_hold`` — why a target's picture
has stopped updating, on the page the user actually looks at.

The walk-away path already refuses to publish a picture made thin by subs it
can't read, and already explains itself — but only in the scan job's summary on
the Jobs page, which is the one screen a beginner whose picture went stale has no
reason to visit. These pin the detail endpoint carrying the same numbers, the
silence on every healthy target, and the fail-soft parse (a note that can't be
trusted must never 500 the page, or appear at all).
"""

from __future__ import annotations

import json

from seestack.io.library import Library
from webapp.pipeline import AUTO_STACK_HOLD_META_KEY

_HOLD = {
    "target": "M_42", "offered": 787, "readable": 271, "unreadable": 516,
    "prior_best": 787, "reason": "that would be a thinner stack than this target already has",
}


def _set_hold(data_root, safe: str, blob) -> None:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_meta(AUTO_STACK_HOLD_META_KEY, blob)
        finally:
            proj.close()
    finally:
        lib.close()


def _first_safe(client) -> str:
    targets = client.get("/api/targets").json()
    assert targets
    return targets[0]["safe_name"]


def test_a_healthy_target_says_nothing(client, built_library):
    """No hold recorded — and therefore no note — is the overwhelmingly common
    case, and must stay a plain ``null``."""
    safe = _first_safe(client)
    body = client.get(f"/api/targets/{safe}").json()
    assert body["auto_stack_hold"] is None


def test_the_hold_is_carried_on_the_target_detail(client, built_library, data_root):
    """The numbers the Jobs page shows, on the Target page too — same fields, so
    the two screens can't drift into different stories."""
    safe = _first_safe(client)
    _set_hold(data_root, safe, json.dumps(_HOLD))
    hold = client.get(f"/api/targets/{safe}").json()["auto_stack_hold"]
    assert hold == {
        "offered": 787, "readable": 271, "unreadable": 516, "prior_best": 787,
        "reason": _HOLD["reason"],
    }


def test_the_list_endpoint_stays_cheap(client, built_library, data_root):
    """Populating this costs a project open per target, so the *list* response
    deliberately leaves it null even for a target that is held."""
    safe = _first_safe(client)
    _set_hold(data_root, safe, json.dumps(_HOLD))
    rows = client.get("/api/targets").json()
    assert all(r["auto_stack_hold"] is None for r in rows)


def test_a_garbled_hold_is_silently_ignored(client, built_library, data_root):
    """A blob written by a future version (or half-written) must read as
    "nothing to say", never as a 500 on the page that shows the picture."""
    safe = _first_safe(client)
    for blob in ("not json at all", "{}", json.dumps({"offered": "many"}), ""):
        _set_hold(data_root, safe, blob)
        r = client.get(f"/api/targets/{safe}")
        assert r.status_code == 200
        assert r.json()["auto_stack_hold"] is None
