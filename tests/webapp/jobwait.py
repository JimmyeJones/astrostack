"""How long a webapp test waits on a background job — said once.

This is the harness's **patience**, not an assertion about the app. Every check
in the files that use it is about what the job *did*; the deadline only decides
how long to keep asking before calling it stuck, and a job that genuinely never
finishes still fails the test, three minutes later instead of one.

**Why it is a shared number.** The scan-job waits in ``tests/webapp`` were
hand-rolled per file, and the short ones flake in exactly the conditions
AGENTS.md §7 prescribes for a run: under ``-n 4`` on a 4-core box, a scan
sharing the machine with three numpy-heavy stacking workers takes longer than a
minute. ``test_skipped_folders.py`` hit that in 2026-09-17 and raised *its* copy
to 180 s; ``test_scoped_scan.py`` — the same shape, the same 60 s budget, in the
file right beside it — then failed the identical way on unmodified
``origin/main`` on 2026-09-29 (``job … did not finish in 60s``, the captured log
showing the scan had run), and passed alone in 28 s. Fixing one copy of a number
and leaving its twins is how that comes back, so the number and the loop now
live here and the scan suites import them.

Deliberately **not** a sweep of every ``_wait_job`` in ``tests/webapp``: the
suites that wait on a stack, an export or an archive already pass 120–180 s of
their own, and rewriting correct files buys nothing. This covers the scan-job
population the two measured failures came from.
"""

from __future__ import annotations

import time
from typing import Any

#: Seconds to let a background job finish before calling it stuck. Matches the
#: longest wait already in this directory (``test_incoming_readonly_guard.py``),
#: so the shared number is the repo's own convention rather than a new one.
JOB_TIMEOUT_S = 180


def wait_job(client, job_id: str, timeout: float = JOB_TIMEOUT_S) -> dict[str, Any]:
    """Poll ``/api/jobs/<id>`` until it reaches a terminal state, then return it.

    Raises ``AssertionError`` — never returns a half-finished body — so a job
    that hangs is a test failure that names itself rather than a confusing
    assertion further down.
    """
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")
