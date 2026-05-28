"""
Drive the QC pipeline across all frames in a project.

Reads frame paths from the project DB, fans them out to a JobRunner, writes
results back to the DB and the model as they arrive. The actual QC function
``compute_for_db_row`` is module-level and pickleable so it can run in a child
process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from seestack.qc.metrics import FrameMetrics, compute_frame_metrics

log = logging.getLogger(__name__)


@dataclass
class QCResult:
    """What a worker returns. Keep simple types — must pickle."""

    frame_id: int
    metrics: FrameMetrics | None
    error: str | None


def compute_for_db_row(
    frame_id: int,
    fits_path: str,
    bayer_pattern: str | None,
    detect_streaks: bool = True,
) -> QCResult:
    """Module-level entry point used by JobRunner. Pickleable."""
    try:
        m = compute_frame_metrics(
            fits_path,
            bayer_pattern=bayer_pattern,
            detect_streaks=detect_streaks,
        )
        return QCResult(frame_id=frame_id, metrics=m, error=None)
    except Exception as exc:  # noqa: BLE001
        return QCResult(frame_id=frame_id, metrics=None, error=f"{type(exc).__name__}: {exc}")


def build_qc_arglist(project) -> list[tuple[int, str, str | None, bool]]:
    """Build ``[(frame_id, path, bayer, detect_streaks), ...]`` from a project."""
    out: list[tuple[int, str, str | None, bool]] = []
    for f in project.iter_frames():
        if f.id is None:
            continue
        path = f.cached_path or f.source_path
        if not path or not Path(path).exists():
            continue
        out.append((f.id, str(path), f.bayer_pattern, True))
    return out


def apply_qc_result_to_db(project, result: QCResult, *, auto_reject: bool = True) -> None:
    """
    Write one QC result into the project DB. If ``auto_reject`` is True, frames
    with detected streaks are auto-rejected (unless the user has overridden).
    """
    if result.metrics is None:
        project.update_frame(result.frame_id, reject_reason=f"qc_error:{result.error or 'unknown'}")
        return
    m = result.metrics
    fields: dict = {
        "fwhm_px": m.fwhm_px,
        "star_count": m.star_count,
        "sky_adu_median": m.sky_adu_median,
        "eccentricity_median": m.eccentricity_median,
        "streak_detected": m.streak_detected,
        "streak_count": m.streak_count,
    }
    if auto_reject and m.streak_detected:
        # Don't overwrite a user-driven decision.
        existing = project.get_frame(result.frame_id)
        if existing is not None and not existing.user_override:
            fields["accept"] = False
            fields["reject_reason"] = "auto:streak"
    project.update_frame(result.frame_id, **fields)
