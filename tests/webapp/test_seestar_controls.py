"""⭐ Seestar-page upgrade, slice 4 — only the controls Seestar Studio verified
on the owner's S30 (firmware 9.75): stop and resume stacking, park with the
scope's current ``equ_mode``, focus, plate solve.

The fake scope answers in the shapes of Studio's ``seestar_sim.py`` (which in
turn follows what the real scope sent), including the one that matters most:
``scope_park {equ_mode}`` SETS the mount mode it is given.
"""

from __future__ import annotations

import json
import socket
import threading

import pytest

from webapp.seestar.client import FOCUSER_RANGE, SeestarClient, SeestarError
from webapp.seestar.manager import SeestarManager


class _SimScope:
    """A stateful JSON-RPC scope on 127.0.0.1, after Studio's simulator."""

    def __init__(self, *, equ_mode: bool | None = True, focus: int | None = 1560,
                 focus_as_dict: bool = False):
        self.equ_mode = equ_mode          # None: firmware without a mount block
        self.focus = focus                # None: no focuser position on offer
        self.focus_as_dict = focus_as_dict
        self.received: list[dict] = []
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def methods(self) -> list[str]:
        return [m["method"] for m in self.received]

    def sent(self, method: str) -> list[dict]:
        return [m for m in self.received if m["method"] == method]

    def _answer(self, m: str, p):  # noqa: ANN001 — (code, result) like the sim
        if m == "get_device_state":
            full = {"device": {"name": "Seestar-sim"}}
            if self.equ_mode is not None:
                full["mount"] = {"equ_mode": self.equ_mode, "close": False,
                                 "tracking": True, "move_type": "none"}
            keys = (p or {}).get("keys") if isinstance(p, dict) else None
            return 0, ({k: full[k] for k in keys if k in full} if keys else full)
        if m == "get_focuser_position":
            if self.focus is None:
                return 0, None
            return 0, ({"step": self.focus} if self.focus_as_dict else self.focus)
        if m == "move_focuser":
            pos = int(p["step"])
            if not 1200 <= pos <= 2600:
                return 109, "step out of range"
            self.focus = pos
            return 0, {"step": pos}
        if m == "scope_park":
            self.equ_mode = bool((p or {}).get("equ_mode", False))
            return 0, 0
        if m == "iscope_start_stack":
            return 0, 0
        if m in ("iscope_stop_view", "start_auto_focuse", "start_solve"):
            return 0, 0
        return 103, "method not found"

    def _serve(self) -> None:
        try:
            conn, _ = self._srv.accept()
        except OSError:
            return
        buf = b""
        with conn:
            while True:
                try:
                    data = conn.recv(4096)
                except OSError:
                    return
                if not data:
                    return
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    self.received.append(msg)
                    code, result = self._answer(msg["method"], msg.get("params"))
                    reply = {"id": msg["id"], "code": code}
                    if code:
                        reply["error"] = result
                    else:
                        reply["result"] = result
                    conn.sendall((json.dumps(reply) + "\r\n").encode())

    def close(self) -> None:
        self._srv.close()


@pytest.fixture
def scope():
    made: list[tuple[_SimScope, SeestarClient]] = []

    def make(**kw):
        sim = _SimScope(**kw)
        client = SeestarClient("127.0.0.1", sim.port)
        client.connect()
        made.append((sim, client))
        mgr = SeestarManager(get_settings=lambda: None)
        mgr._clients["127.0.0.1"] = client
        return sim, mgr

    yield make
    for sim, client in made:
        client.disconnect()
        sim.close()


# ---------------------------------------------------------------------------
# park — always with the mode the scope is in now
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [True, False])
def test_park_keeps_the_mount_mode_the_scope_is_in(scope, mode):
    sim, mgr = scope(equ_mode=mode)
    mgr.control("127.0.0.1", "park")
    (park,) = sim.sent("scope_park")
    assert park["params"] == {"equ_mode": mode}
    assert sim.equ_mode is mode             # the scope did not change mode
    # The mode was read fresh, from the mount block only, right before parking.
    ask = sim.received[sim.received.index(park) - 1]
    assert ask["method"] == "get_device_state" and ask["params"] == {"keys": ["mount"]}


def test_park_on_a_firmware_without_a_mount_block_sends_the_bare_call(scope):
    sim, mgr = scope(equ_mode=None)
    mgr.control("127.0.0.1", "park")
    (park,) = sim.sent("scope_park")
    assert "params" not in park   # the call this app always sent — no guessed mode


def test_park_refuses_when_the_mode_cannot_be_read():
    """A scope that will not say its mode is not parked with a guessed one."""
    class _Silent:
        is_connected = True

        def get_mount(self, timeout):  # noqa: ANN001, ARG002
            raise SeestarError("timed out")

        def park(self, equ_mode=None):  # noqa: ANN001
            raise AssertionError("parked without knowing the mount mode")

    mgr = SeestarManager(get_settings=lambda: None)
    mgr._clients["127.0.0.1"] = _Silent()
    mgr._auth["127.0.0.1"] = (mgr._clients["127.0.0.1"], "verified", None, 0.0)
    with pytest.raises(SeestarError):
        mgr.control("127.0.0.1", "park")


# ---------------------------------------------------------------------------
# stop / resume stacking, autofocus, plate solve — Studio's shapes verbatim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action,method,params", [
    ("stop_stack", "iscope_stop_view", {"stage": "Stack"}),
    ("resume", "iscope_start_stack", {"restart": False}),
    ("autofocus", "start_auto_focuse", None),
    ("solve", "start_solve", None),
])
def test_each_verified_control_sends_studios_shape(scope, action, method, params):
    sim, mgr = scope()
    mgr.control("127.0.0.1", action)
    (sent,) = sim.sent(method)
    assert sent.get("params") == params


def test_resume_never_restarts_the_stack_count(scope):
    sim, mgr = scope()
    mgr.control("127.0.0.1", "resume")
    assert sim.sent("iscope_start_stack")[0]["params"]["restart"] is False


def test_stop_stack_is_not_stop_everything(scope):
    """Pausing the stack keeps the view (and its frames); the old Stop still
    ends the whole view."""
    sim, mgr = scope()
    mgr.control("127.0.0.1", "stop_stack")
    mgr.control("127.0.0.1", "stop")
    stage, everything = sim.sent("iscope_stop_view")
    assert stage["params"] == {"stage": "Stack"}
    assert "params" not in everything


# ---------------------------------------------------------------------------
# focus — the firmware takes an absolute position; we nudge from a fresh read
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("as_dict", [False, True])
def test_focus_nudge_moves_from_the_current_position(scope, as_dict):
    sim, mgr = scope(focus=1560, focus_as_dict=as_dict)
    assert mgr.control("127.0.0.1", "focus", {"steps": -10}) == {"from": 1560, "to": 1550}
    assert sim.sent("move_focuser")[0]["params"] == {"step": 1550, "ret_step": True}
    assert mgr.control("127.0.0.1", "focus", {"steps": 50}) == {"from": 1550, "to": 1600}
    assert sim.focus == 1600


@pytest.mark.parametrize("start,steps", [(FOCUSER_RANGE[1] - 5, 10), (FOCUSER_RANGE[0] + 5, -10)])
def test_focus_nudge_past_the_end_is_refused_before_anything_moves(scope, start, steps):
    sim, mgr = scope(focus=start)
    with pytest.raises(SeestarError, match="range"):
        mgr.control("127.0.0.1", "focus", {"steps": steps})
    assert sim.sent("move_focuser") == []


def test_focus_nudge_with_no_known_position_refuses(scope):
    sim, mgr = scope(focus=None)
    with pytest.raises(SeestarError, match="focuser"):
        mgr.control("127.0.0.1", "focus", {"steps": 10})
    assert sim.sent("move_focuser") == []


def test_client_move_focuser_refuses_an_out_of_range_position(scope):
    sim, mgr = scope()
    with pytest.raises(SeestarError):
        mgr._clients["127.0.0.1"].move_focuser(FOCUSER_RANGE[1] + 1)
    assert sim.sent("move_focuser") == []


def test_a_firmware_error_reaches_the_caller(scope):
    sim, mgr = scope()
    with pytest.raises(SeestarError, match="error"):
        mgr._clients["127.0.0.1"]._rpc("move_focuser", {"step": 9999, "ret_step": True})


def test_focus_without_steps_is_a_bad_parameter(scope):
    _, mgr = scope()
    with pytest.raises(SeestarError, match="bad parameters"):
        mgr.control("127.0.0.1", "focus", {})


# ---------------------------------------------------------------------------
# the endpoints — control-gated and validated like goto
# ---------------------------------------------------------------------------

_NEW = [("stop-stack", None), ("resume", None), ("autofocus", None),
        ("focus", {"steps": 10}), ("solve", None)]


@pytest.mark.parametrize("path,body", _NEW)
def test_new_controls_are_blocked_when_disabled(client, path, body):
    assert client.post(f"/api/seestar/1.2.3.4/{path}", json=body).status_code == 409


@pytest.mark.parametrize("path,body", _NEW)
def test_new_controls_stay_gated_while_only_monitoring(client, path, body):
    client.put("/api/settings", json={
        "seestar_enabled": True, "seestar_scan_subnet": "203.0.113.0/31"})
    try:
        r = client.post(f"/api/seestar/1.2.3.4/{path}", json=body)
        assert r.status_code == 409
        assert "control is disabled" in r.json()["detail"].lower()
    finally:
        client.put("/api/settings", json={"seestar_enabled": False})


@pytest.mark.parametrize("body", [{"steps": 201}, {"steps": -201}, {"steps": "x"}, {}])
def test_focus_rejects_an_oversized_or_missing_nudge(client, body):
    assert client.post("/api/seestar/1.2.3.4/focus", json=body).status_code == 422


def test_focus_rejects_a_zero_nudge(client):
    client.put("/api/settings", json={
        "seestar_enabled": True, "seestar_control_enabled": True,
        "seestar_scan_subnet": "203.0.113.0/31"})
    try:
        assert client.post("/api/seestar/1.2.3.4/focus", json={"steps": 0}).status_code == 422
    finally:
        client.put("/api/settings", json={
            "seestar_enabled": False, "seestar_control_enabled": False})
