"""The dogfood pass's sensor-defect line must read the keys the endpoint sends.

`scripts/agent-dogfood.sh --calibration` exists because no pass had ever held a
master dark, so every calibration surface had only ever been photographed in its
empty state. Its one line about broken photosites read `offer_repair` and
`summary` off `/api/calibration/defects` — **neither of which that endpoint has
ever returned.** It answers ``{"masters": [...], "repair": offer|None}``. So on
the first pass that actually built a master and *was* being offered the repair,
the probe printed ``offer=None`` and then dumped the raw dict: the line meant to
say whether the offer fires said the opposite of the truth, and buried the truth
in the fallback.

That is the failure mode this repo keeps writing guards against — a check that
silently answers ``None`` when it cannot find its subject enforces nothing, and a
pass that reads it comes back "clean" about a surface it never saw. The tooling
is not in the suite, so this is the seam worth pinning: the names the script
reads, against the names the endpoint sends, from both sides.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOGFOOD_SH = Path(__file__).resolve().parents[2] / "scripts" / "agent-dogfood.sh"

#: The keys the probe reads off the response's top level.
_PROBE_KEYS = ("masters", "repair")
#: What it used to read, kept by name so a copy-paste can't bring them back.
_KEYS_THE_ENDPOINT_NEVER_HAD = ("offer_repair", "summary")


@pytest.fixture(scope="module")
def defects_probe() -> str:
    """The inline Python the `--calibration` pass runs on the defects response."""
    src = DOGFOOD_SH.read_text(encoding="utf-8")
    m = re.search(
        r'curl -sf "\$BASE/api/calibration/defects" \| python -c \'\n(.*?)\n\'',
        src, re.S)
    assert m is not None, (
        f"could not find the defects probe in {DOGFOOD_SH.name}. If it moved or "
        "was rewritten, move this guard with it — the point is that the script "
        "and the endpoint agree about the key names, and a guard that cannot "
        "find its subject is the very thing this file is about."
    )
    return m.group(1)


def test_the_probe_reads_the_keys_the_endpoint_actually_sends(client,
                                                              defects_probe):
    """Both directions at once: the endpoint's real payload on a real library,
    and the names the script takes off it."""
    body = client.get("/api/calibration/defects").json()
    assert set(_PROBE_KEYS) <= set(body), (
        f"/api/calibration/defects no longer sends {_PROBE_KEYS} — the dogfood "
        "pass's one line about broken photosites reads those names"
    )
    for key in _PROBE_KEYS:
        assert f'"{key}"' in defects_probe, (
            f"the dogfood defects probe stopped reading {key!r}, which is what "
            "the endpoint sends"
        )


def test_the_probe_does_not_read_a_key_that_never_existed(defects_probe):
    """The actual bug, pinned: those two names are not in the response and never
    were, so reading them can only ever answer ``None``."""
    for key in _KEYS_THE_ENDPOINT_NEVER_HAD:
        assert key not in defects_probe, (
            f"the dogfood defects probe reads {key!r}, which "
            "/api/calibration/defects does not send — it will print None on an "
            "install that IS offering the repair"
        )


def test_the_endpoint_never_grew_those_names_instead(client):
    """The other way the guard above could be satisfied wrongly: if the endpoint
    had quietly started sending them, the probe would not have been wrong and
    this whole file would be about nothing."""
    body = client.get("/api/calibration/defects").json()
    assert not set(_KEYS_THE_ENDPOINT_NEVER_HAD) & set(body)
