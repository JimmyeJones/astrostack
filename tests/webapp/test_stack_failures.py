""""Why did this target stop producing pictures?" — the last failed stack.

The unattended half is the point: a walk-away stack that refuses is caught *per
target* inside the scan job (so one target can't sink the batch), which leaves
the scan job ``done`` and the refusal filed in its result where nobody looks.
"""

from __future__ import annotations

from webapp.jobs import Job, classify_error_message, classify_job_error
from webapp.stackfailure import latest_stack_failures, superseded_by_success

MEMORY_MSG = (
    "stack output canvas 8000x6000 ×1.5 drizzle needs ~9.4 GB of working memory, "
    "over the ~6.0 GB budget. To fit, switch Canvas mode to 'reference' (~5.1 GB), "
    "or raise ASTROSTACK_MAX_STACK_GB to override."
)


def _job(kind: str, *, state="done", target=None, error=None, error_kind=None,
         result=None, when="2026-08-29T02:00:00Z") -> Job:
    j = Job(kind=kind, target=target, state=state)
    j.error, j.error_kind, j.result = error, error_kind, result
    j.created_utc = j.finished_utc = when
    return j


# ------------------------------------------------------- reading the history --

def test_a_failed_manual_stack_is_reported():
    found = latest_stack_failures([
        _job("stack", state="error", target="M_31", error=MEMORY_MSG,
             error_kind="memory_budget"),
    ])
    assert set(found) == {"M_31"}
    f = found["M_31"]
    assert f.kind == "memory_budget"
    assert f.message == MEMORY_MSG
    assert f.unattended is False


def test_an_unattended_refusal_inside_a_DONE_scan_job_is_reported():
    """The case this exists for — and the one a "failed jobs" query misses.

    The scan job itself succeeded; only one target's auto-stack blew up, and the
    message lives in the scan's own result.
    """
    found = latest_stack_failures([
        _job("pipeline", state="done", result={
            "auto_stacked": ["NGC_7000"],
            "stack_errors": {"M_31": MEMORY_MSG},
        }),
    ])
    assert set(found) == {"M_31"}
    f = found["M_31"]
    assert f.unattended is True
    assert f.message == MEMORY_MSG
    # Classified from the message alone, since the unattended path keeps no
    # exception — so the UI gets the same plain-language translation.
    assert f.kind == "memory_budget"


def test_a_successful_scan_with_no_stack_errors_reports_nothing():
    assert latest_stack_failures([
        _job("pipeline", state="done", result={"auto_stacked": ["M_31"]}),
        _job("stack", state="done", target="M_31"),
        _job("qc_solve", state="error", target="M_31", error="solver exploded"),
    ]) == {}


def test_the_newest_failure_wins_whatever_order_the_jobs_arrive_in():
    old = _job("stack", state="error", target="M_31", error="old problem",
               when="2026-08-01T00:00:00Z")
    new = _job("pipeline", state="done", when="2026-08-20T00:00:00Z",
               result={"stack_errors": {"M_31": "new problem"}})
    assert latest_stack_failures([old, new])["M_31"].message == "new problem"
    assert latest_stack_failures([new, old])["M_31"].message == "new problem"


def test_several_targets_in_one_scan_are_each_reported():
    found = latest_stack_failures([
        _job("pipeline", state="done",
             result={"stack_errors": {"M_31": "a", "NGC_7000": "b"}}),
    ])
    assert {k: v.message for k, v in found.items()} == {"M_31": "a", "NGC_7000": "b"}


def test_a_malformed_result_never_raises():
    for result in (None, [], {"stack_errors": "boom"}, {"stack_errors": {"": "x"}},
                   {"stack_errors": {"M_31": ""}}):
        assert latest_stack_failures([_job("pipeline", result=result)]) == {}


# ------------------------------------------------- retiring a fixed failure ---

def test_a_stack_that_succeeded_afterwards_retires_the_failure():
    f = latest_stack_failures([
        _job("stack", state="error", target="M_31", error=MEMORY_MSG,
             when="2026-08-20T00:00:00Z"),
    ])["M_31"]
    # The stack run stamp is a full isoformat offset, the job stamp ends in "Z" —
    # different shapes, so this can only work parsed, never string-compared.
    assert superseded_by_success(f, "2026-08-21T22:15:03.412+00:00") is True
    assert superseded_by_success(f, "2026-08-19T22:15:03.412+00:00") is False


def test_a_target_that_has_never_stacked_keeps_its_failure():
    f = latest_stack_failures([
        _job("stack", state="error", target="M_31", error=MEMORY_MSG),
    ])["M_31"]
    assert superseded_by_success(f, None) is False
    # An unparseable stamp is treated as "not superseded": saying so once too
    # often beats going quiet about a target that is genuinely stuck.
    assert superseded_by_success(f, "not a date") is False


# --------------------------------------------------------- the classifier -----

def test_the_message_classifier_matches_the_exception_one():
    for msg, kind in (
        (MEMORY_MSG, "memory_budget"),
        ("no accepted, plate-solved frames to stack", "no_solved_frames"),
        ("no frames could be aligned into the canvas", "no_alignment"),
        ("reference wcs could not be parsed", "no_reference_wcs"),
        ("no FITS files found in that folder", "no_fits_in_folder"),
        ("something nobody has seen before", None),
    ):
        assert classify_error_message(msg) == kind
        assert classify_job_error(ValueError(msg)) == kind
    # The exception path still adds what only the *type* can say.
    assert classify_job_error(MemoryError("out of room")) == "memory_budget"
    assert classify_error_message("out of room") is None


# ------------------------------------------------------------- the endpoint ---

def _persist(client, job: Job) -> None:
    client.app.state.job_manager._persist(job)


def test_endpoint_surfaces_an_unattended_refusal(client, built_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _persist(client, _job("pipeline", state="done",
                          result={"stack_errors": {safe: MEMORY_MSG}}))

    body = client.get("/api/stack-failures").json()
    assert [f["safe"] for f in body["failures"]] == [safe]
    f = body["failures"][0]
    assert f["kind"] == "memory_budget"
    assert f["unattended"] is True
    assert "9.4 GB" in f["message"]        # the engine's own actionable sentence
    assert f["name"]                        # the display name, for the UI


def test_endpoint_is_empty_on_a_healthy_install(client, built_library):
    assert client.get("/api/stack-failures").json() == {"failures": []}


def test_endpoint_drops_a_failure_for_a_target_that_no_longer_exists(
    client, built_library,
):
    _persist(client, _job("stack", state="error", target="Deleted_target",
                          error=MEMORY_MSG))
    assert client.get("/api/stack-failures").json()["failures"] == []


def test_endpoint_retires_the_failure_once_a_stack_succeeds(client, solved_library):
    """The self-hiding half: a long-fixed failure must never nag."""
    from pathlib import Path

    from PIL import Image

    from seestack.io.library import Library
    from seestack.io.project import StackRunRow

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _persist(client, _job("stack", state="error", target=safe, error=MEMORY_MSG,
                          when="2026-08-20T00:00:00Z"))
    assert len(client.get("/api/stack-failures").json()["failures"]) == 1

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            preview = Path(lib.target_dir(lib.find_target(safe))) / "master_preview.png"
            Image.new("RGB", (32, 32)).save(preview)
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-08-21T22:15:03.412+00:00",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=str(preview), n_frames_used=3,
                canvas_h=32, canvas_w=32, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()

    assert client.get("/api/stack-failures").json()["failures"] == []
