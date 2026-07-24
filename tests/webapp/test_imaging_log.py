"""`GET /api/imaging-log.csv`: the downloadable *Your imaging log* record —
cross-target aggregation, newest-first ordering, and the empty-library case."""

from __future__ import annotations

import csv
import io
import json

from seestack.imaging_log import IMAGING_LOG_COLUMNS
from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(
    data_root, safe: str, *, basename: str, n_frames: int,
    exposure_s: float | None, timestamp: str,
    calstat: str | None = None, is_mosaic: bool | None = None,
    engine_version: str | None = None,
) -> None:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=timestamp,
                output_basename=basename, fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=n_frames,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=n_frames,
                options_json=json.dumps({"sigma_clip": True}),
                total_exposure_s=exposure_s, calstat=calstat,
                is_mosaic=is_mosaic, engine_version=engine_version,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def _parse(csv_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


def test_empty_library_yields_header_only_csv(client, solved_library):
    r = client.get("/api/imaging-log.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "imaging-log.csv" in r.headers["content-disposition"]
    rows = _parse(r.text)
    assert rows == [IMAGING_LOG_COLUMNS]


def test_one_row_per_run_newest_first(client, solved_library):
    targets = client.get("/api/targets").json()
    assert len(targets) >= 2
    first = targets[0]["safe_name"]
    second = targets[1]["safe_name"]
    # Older run on the first target, newer run on the second.
    _register_run(solved_library, first, basename="older",
                  n_frames=30, exposure_s=900, timestamp="2026-05-01T00:00:00Z",
                  calstat="dark+flat", is_mosaic=False, engine_version="0.190.0")
    _register_run(solved_library, second, basename="newer",
                  n_frames=200, exposure_s=3600 + 24 * 60,
                  timestamp="2026-07-20T00:00:00Z",
                  calstat=None, is_mosaic=True, engine_version="0.192.0")

    r = client.get("/api/imaging-log.csv")
    assert r.status_code == 200
    rows = _parse(r.text)
    assert rows[0] == IMAGING_LOG_COLUMNS
    assert len(rows) == 3  # header + 2 runs

    # Newest first: the 2026-07-20 run leads.
    newer, older = rows[1], rows[2]
    assert newer[0] == "2026-07-20"
    assert newer[2] == "200"
    assert newer[3] == "1h 24m"
    assert newer[5] == "none"   # no calibration applied
    assert newer[6] == "yes"    # mosaic
    assert newer[8] == "0.192.0"

    assert older[0] == "2026-05-01"
    assert older[2] == "30"
    assert older[3] == "15m"
    assert older[5] == "dark+flat"
    assert older[6] == "no"


def test_row_count_matches_runs_across_targets(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, basename="a", n_frames=10,
                  exposure_s=300, timestamp="2026-06-01T00:00:00Z")
    _register_run(solved_library, safe, basename="b", n_frames=20,
                  exposure_s=600, timestamp="2026-06-02T00:00:00Z")
    rows = _parse(client.get("/api/imaging-log.csv").text)
    assert len(rows) == 3  # header + the 2 runs on this target
