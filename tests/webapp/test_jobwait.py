"""The shared job-wait helper does what the scan suites rely on.

:mod:`tests.webapp.jobwait` is harness code, so it gets the same treatment as
any other shared helper: its contract is pinned here rather than being whatever
three call sites happen to tolerate. The thing that matters is that it keeps
polling until the job is *terminal* and then hands back that body — a helper
that returned a still-running body would turn a slow job into a confusing
assertion further down instead of a named timeout.
"""

from __future__ import annotations

import pytest

from tests.webapp.jobwait import JOB_TIMEOUT_S, wait_job


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _FakeClient:
    """Answers ``/api/jobs/<id>`` with a scripted sequence of states."""

    def __init__(self, states):
        self._states = list(states)
        self.calls = 0

    def get(self, _url):
        self.calls += 1
        state = self._states.pop(0) if len(self._states) > 1 else self._states[0]
        return _FakeResponse({"state": state, "result": {"seen": self.calls}})


def test_it_keeps_asking_until_the_job_is_terminal():
    client = _FakeClient(["running", "running", "done"])
    body = wait_job(client, "abc")
    assert body["state"] == "done"
    assert client.calls == 3


@pytest.mark.parametrize("state", ["done", "error", "cancelled", "interrupted"])
def test_every_terminal_state_ends_the_wait(state):
    """``error`` and ``interrupted`` are results a caller asserts *about* — the
    helper must not sit on them until the deadline."""
    client = _FakeClient([state])
    assert wait_job(client, "abc")["state"] == state
    assert client.calls == 1


def test_a_job_that_never_finishes_fails_by_name():
    client = _FakeClient(["running"])
    with pytest.raises(AssertionError, match="did not finish"):
        wait_job(client, "abc", timeout=0.3)


def test_the_shared_deadline_is_the_generous_one():
    """The whole point of sharing it: the scan suites stop carrying a 60 s
    budget that flakes under ``-n 4`` on a 4-core box (see the module
    docstring). A number below the longest wait already in this directory would
    put the flake straight back."""
    assert JOB_TIMEOUT_S >= 180
