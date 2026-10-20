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


def test_an_editor_export_after_the_failure_does_not_retire_it(client, solved_library):
    """An export (or a channel combine) re-renders light a stack already
    combined — it is a ``stack_runs`` row with a fresh stamp, but it is not a
    stack that *succeeded*. Exporting the old picture the morning after a refusal
    used to make "this target stopped producing pictures" vanish while the target
    still could not stack."""
    import json
    from pathlib import Path

    from PIL import Image

    from seestack.io.library import Library
    from seestack.io.project import StackRunRow

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _persist(client, _job("stack", state="error", target=safe, error=MEMORY_MSG,
                          when="2026-08-20T00:00:00Z"))

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            preview = Path(lib.target_dir(lib.find_target(safe))) / "master_preview.png"
            Image.new("RGB", (32, 32)).save(preview)

            def add(stamp: str, options: dict) -> int:
                return proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc=stamp,
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=str(preview), n_frames_used=3,
                    canvas_h=32, canvas_w=32, coverage_min=1, coverage_max=3,
                    options_json=json.dumps(options),
                ))

            # The genuine stack is from *before* the failure …
            stack_id = add("2026-08-19T22:15:03.412+00:00", {})
            # … and the export and the combine land after it.
            add("2026-08-21T09:00:00+00:00",
                {"editor_recipe": {"ops": []}, "derived_from": stack_id,
                 "display_space": True})
            add("2026-08-21T10:00:00+00:00", {"channel_combine": [], "weights": {}})
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get("/api/stack-failures").json()
    assert [f["safe"] for f in body["failures"]] == [safe]


# ------------------------------------------------- the Reprocess-all batch ---

def _failed_row(safe: str, error: str = f"MemoryError: {MEMORY_MSG}", *,
                error_kind: str = "memory_budget", failed_utc: str | None = None) -> dict:
    row = {"target": safe, "name": safe.replace("_", " "), "error": error,
           "error_kind": error_kind}
    if failed_utc is not None:
        row["failed_utc"] = failed_utc
    return row


def test_a_refusal_inside_a_DONE_reprocess_all_batch_is_reported():
    """The third recording site: the batch isolates each target into
    ``result["failed"]`` and finishes ``done`` — the walk that runs for days,
    unattended, used to be the one path whose refusal no screen mentioned."""
    found = latest_stack_failures([
        _job("reprocess_all", state="done", when="2026-08-29T05:00:00Z", result={
            "total": 3, "stacked": 1,
            "failed": [_failed_row("M_31"),
                       _failed_row("NGC_7000", "ValueError: no accepted, plate-solved "
                                   "frames to stack", error_kind="")],
        }),
    ])
    assert set(found) == {"M_31", "NGC_7000"}
    assert found["M_31"].kind == "memory_budget"
    assert found["M_31"].unattended is True
    assert "9.4 GB" in found["M_31"].message
    # An empty stamped kind (older rows, unclassified types) falls back to the
    # message classifier rather than reporting "".
    assert found["NGC_7000"].kind == classify_error_message("no accepted, plate-solved "
                                                            "frames to stack")
    # A row an older build wrote has no stamp of its own: the job's finish.
    assert found["M_31"].when_utc == "2026-08-29T05:00:00Z"


def test_a_row_carried_into_a_later_slice_keeps_its_own_failure_time():
    """A yielded slice re-reports the earlier slices' rows. Stamped with the
    later slice's finish, a stack that succeeded *between* the slices would look
    older than the failure and the note would come back for a fixed target."""
    first = _job("reprocess_all", when="2026-08-29T02:10:00Z", result={
        "failed": [_failed_row("M_31", failed_utc="2026-08-29T02:05:00Z")],
        "yielded": True})
    second = _job("reprocess_all", when="2026-08-29T09:00:00Z", result={
        "failed": [_failed_row("M_31", failed_utc="2026-08-29T02:05:00Z"),
                   _failed_row("M_42", failed_utc="2026-08-29T08:55:00Z")],
        "yielded": False})
    found = latest_stack_failures([second, first])
    assert set(found) == {"M_31", "M_42"}
    assert found["M_31"].when_utc == "2026-08-29T02:05:00Z"
    # His manual stack of M 31 between the slices retires it; M 42 stays.
    assert superseded_by_success(found["M_31"], "2026-08-29T04:00:00Z")
    assert not superseded_by_success(found["M_42"], "2026-08-29T04:00:00Z")


def test_a_malformed_reprocess_result_never_raises():
    assert latest_stack_failures([
        _job("reprocess_all", result=None),
        _job("reprocess_all", result={"failed": "oops"}),
        _job("reprocess_all", result={"failed": [None, 3, {}, {"target": "M_31"},
                                                 {"error": "no target"}]}),
        _job("reprocess_all", state="error", error="whole batch died"),
    ]) == {}


def test_endpoint_surfaces_a_reprocess_all_refusal_end_to_end(
        client, solved_library, monkeypatch):
    """The Scout's repro, through the real client: a batch whose every target
    hits the memory refusal finishes ``done`` with two ``failed`` rows — and
    ``/api/stack-failures`` used to answer ``[]``."""
    import time

    def refuse(proj, opts, **_kw):  # noqa: ANN001, ARG001
        raise MemoryError(MEMORY_MSG)
    monkeypatch.setattr("seestack.stack.stacker.run_stack", refuse)

    r = client.post("/api/reprocess-all")
    assert r.status_code == 200
    deadline = time.monotonic() + 90
    while True:
        body = client.get(f"/api/jobs/{r.json()['job_id']}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            break
        assert time.monotonic() < deadline, "reprocess-all did not finish"
        time.sleep(0.2)
    assert body["state"] == "done"
    assert len(body["result"]["failed"]) == 2
    # Each row carries its own failure time, so a later slice can carry it on.
    assert all(row.get("failed_utc") for row in body["result"]["failed"])

    targets = {t["safe_name"] for t in client.get("/api/targets").json()}
    failures = client.get("/api/stack-failures").json()["failures"]
    assert {f["safe"] for f in failures} == targets
    for f in failures:
        assert f["kind"] == "memory_budget"
        assert f["unattended"] is True
        assert "9.4 GB" in f["message"]
        assert f["when_utc"]
