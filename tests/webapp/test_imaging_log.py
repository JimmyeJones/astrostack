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
    engine_version: str | None = None, stack_fwhm_px: float | None = None,
    capture_start_utc: str | None = None, capture_end_utc: str | None = None,
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
                stack_fwhm_px=stack_fwhm_px,
                capture_start_utc=capture_start_utc,
                capture_end_utc=capture_end_utc,
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

    # Newest first: the 2026-07-20 run leads. Neither fixture recorded a capture
    # window, so "Shot" is honestly blank and "Stacked" (last) carries the stamp.
    newer, older = rows[1], rows[2]
    assert newer[0] == ""
    assert newer[-1] == "2026-07-20"
    assert newer[2] == "200"
    assert newer[3] == "1.4 h"
    assert newer[5] == "none"   # no calibration applied
    assert newer[6] == "yes"    # mosaic
    assert newer[8] == "0.192.0"

    assert older[0] == ""
    assert older[-1] == "2026-05-01"
    assert older[2] == "30"
    assert older[3] == "15 min"
    assert older[5] == "dark+flat"
    assert older[6] == "no"


def test_the_log_dates_a_run_by_the_nights_it_was_shot_not_the_day_it_was_stacked(
    client, solved_library,
):
    """The fixture is the point: the subs are from 2024 and the stack ran in
    2026 — a re-stack of a back catalogue, which is exactly what a Seestar owner
    arriving with thousands of subs does. A same-day fixture cannot show this
    bug, and the log's leading column used to carry the 2026 date."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, basename="restack", n_frames=505,
                  exposure_s=15150, timestamp="2026-07-20T11:00:00Z",
                  capture_start_utc="2024-11-15T22:10:00Z",
                  capture_end_utc="2024-11-18T03:40:00Z")

    rows = _parse(client.get("/api/imaging-log.csv").text)
    assert rows[0][0] == "Shot" and rows[0][-1] == "Stacked"
    row = rows[1]
    # 03:40 UTC on the 18th still belongs to the night of the 17th — the same
    # noon-to-noon bucket the Nights card uses, not a raw calendar date.
    assert row[0] == "2024-11-15 to 2024-11-17"
    assert row[-1] == "2026-07-20"


def test_a_single_night_run_reads_as_one_plain_date(client, solved_library):
    """One night is one ISO date — a spreadsheet can still parse the column."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, basename="onenight", n_frames=60,
                  exposure_s=1800, timestamp="2026-07-20T11:00:00Z",
                  capture_start_utc="2024-11-15T21:00:00Z",
                  capture_end_utc="2024-11-15T23:30:00Z")

    row = _parse(client.get("/api/imaging-log.csv").text)[1]
    assert row[0] == "2024-11-15"


def test_row_count_matches_runs_across_targets(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, basename="a", n_frames=10,
                  exposure_s=300, timestamp="2026-06-01T00:00:00Z")
    _register_run(solved_library, safe, basename="b", n_frames=20,
                  exposure_s=600, timestamp="2026-06-02T00:00:00Z")
    rows = _parse(client.get("/api/imaging-log.csv").text)
    assert len(rows) == 3  # header + the 2 runs on this target


def test_per_run_stack_fwhm_is_reported_over_the_target_median(client, solved_library):
    """When a run stored its own measured sharpness (schema ≥ 14), the log's
    "Typical star size" reflects *that stack*, not the static target-wide frame
    median — so two nights of one target can show different sharpness."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(solved_library, safe, basename="sharp", n_frames=40,
                  exposure_s=1200, timestamp="2026-06-10T00:00:00Z",
                  stack_fwhm_px=1.8)
    rows = _parse(client.get("/api/imaging-log.csv").text)
    star_size_col = IMAGING_LOG_COLUMNS.index("Typical star size (px)")
    run_row = next(r for r in rows[1:] if r[-1] == "2026-06-10")
    assert run_row[star_size_col] == "1.8"
