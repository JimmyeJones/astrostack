"""
Frame preview pane.

Shows the thumbnail of the currently selected frame, with key metrics
underneath. Includes a Bayer-pattern override combo for cases where the FITS
header pattern is wrong (some software writes BAYERPAT='RGGB' while actually
laying the data out differently — manually trying GBRG/BGGR/GRBG fixes that).

Thumbs are generated on demand in a worker thread so the GUI never blocks.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seestack.gui.thumbnail import generate_thumbnail, thumb_path_for

log = logging.getLogger(__name__)

BAYER_PATTERNS = ("RGGB", "BGGR", "GRBG", "GBRG")


class _ThumbWorker(QThread):
    """Generate one thumbnail on a worker thread (not a process — single op)."""

    done = Signal(int, str)  # frame_id, output_path

    def __init__(self, frame_id: int, fits_path: Path, out_path: Path,
                 bayer_pattern: str | None) -> None:
        super().__init__()
        self.frame_id = frame_id
        self.fits_path = fits_path
        self.out_path = out_path
        self.bayer_pattern = bayer_pattern

    def run(self) -> None:
        try:
            generate_thumbnail(
                self.fits_path,
                self.out_path,
                bayer_pattern=self.bayer_pattern,
            )
            self.done.emit(self.frame_id, str(self.out_path))
        except Exception as exc:  # noqa: BLE001
            log.warning("thumbnail failed for %s: %s", self.fits_path, exc)


class PreviewPane(QWidget):
    """Right-hand-side preview of the currently selected frame."""

    def __init__(self, project_dir: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = Path(project_dir) if project_dir else None
        self._current_id: int | None = None
        self._current_frame = None
        # In-flight thumbnail workers. ``_ThumbWorker`` has no event loop, so
        # ``quit()`` can't interrupt it — instead we keep every worker alive in
        # this list until it finishes naturally, then drop it. This is what
        # prevents the "QThread: Destroyed while thread is still running" crash
        # when the user clicks through frames faster than thumbnails render.
        # Stale results are simply ignored (see _on_thumb_ready).
        self._workers: list[_ThumbWorker] = []
        # User's Bayer override for the currently displayed frame; None = use header.
        self._bayer_override: str | None = None

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(4, 4, 4, 4)

        from seestack.gui.theme import BG_SUNKEN, FG_SECONDARY, BG_DIVIDER

        self._image = QLabel("☆\n\nSelect a frame to preview")
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumSize(280, 280)
        self._image.setStyleSheet(
            f"background:{BG_SUNKEN}; color:{FG_SECONDARY}; "
            f"border: 1px solid {BG_DIVIDER}; border-radius: 6px; "
            f"font-size: 16px;"
        )
        layout.addWidget(self._image)

        # Bayer-pattern controls.
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(QLabel("Bayer:"))
        self._bayer_combo = QComboBox()
        self._bayer_combo.addItem("(from header)", userData=None)
        for p in BAYER_PATTERNS:
            self._bayer_combo.addItem(p, userData=p)
        self._bayer_combo.setToolTip(
            "Override the Bayer mosaic pattern used for debayering this preview. "
            "Try other patterns if the colour looks wrong — some FITS files "
            "have an incorrect BAYERPAT header."
        )
        self._bayer_combo.currentIndexChanged.connect(self._on_bayer_changed)
        bar.addWidget(self._bayer_combo)

        self._refresh_btn = QPushButton("Regenerate")
        self._refresh_btn.setToolTip("Discard the cached thumbnail and re-render with the current Bayer pattern.")
        self._refresh_btn.clicked.connect(self._on_regenerate)
        bar.addWidget(self._refresh_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._caption = QLabel("")
        self._caption.setWordWrap(True)
        self._caption.setProperty("role", "caption")
        layout.addWidget(self._caption)

    def set_project_dir(self, project_dir: Path | None) -> None:
        self._project_dir = Path(project_dir) if project_dir else None
        self.clear()

    def clear(self) -> None:
        self._current_id = None
        self._current_frame = None
        self._image.setText("☆\n\nSelect a frame to preview")
        self._image.setPixmap(QPixmap())
        self._caption.setText("")

    def show_frame(self, frame) -> None:
        """``frame`` is a FrameRow."""
        if self._project_dir is None or frame.id is None:
            return
        self._current_id = frame.id
        self._current_frame = frame
        self._caption.setText(_caption_for(frame))
        self._render(use_cached=True)

    def _render(self, *, use_cached: bool) -> None:
        if self._current_frame is None or self._project_dir is None:
            return
        frame = self._current_frame
        path = thumb_path_for(self._project_dir, frame.id)
        if use_cached and path.exists():
            self._image.setPixmap(QPixmap(str(path)))
            return
        src = Path(frame.cached_path) if frame.cached_path else Path(frame.source_path)
        if not src.exists():
            self._image.setText("source file unavailable")
            return
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
        self._image.setText("generating preview…")
        bayer = self._bayer_override or frame.bayer_pattern
        worker = _ThumbWorker(frame.id, src, path, bayer)
        worker.done.connect(self._on_thumb_ready)
        # finished() fires after run() returns — use it to reap the worker.
        worker.finished.connect(lambda w=worker: self._reap_worker(w))
        self._workers.append(worker)
        worker.start()

    def _reap_worker(self, worker: "_ThumbWorker") -> None:
        """Drop a finished worker once Qt is done with its thread."""
        try:
            self._workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def _on_thumb_ready(self, frame_id: int, out_path: str) -> None:
        # Ignore results for frames the user already navigated away from.
        if frame_id != self._current_id:
            return
        self._image.setPixmap(QPixmap(out_path))

    def shutdown(self) -> None:
        """Block until all in-flight thumbnail workers finish. Call from closeEvent."""
        for worker in list(self._workers):
            worker.wait(3000)
        self._workers.clear()

    def _on_bayer_changed(self, _idx: int) -> None:
        """User picked a different Bayer pattern — regenerate with it."""
        self._bayer_override = self._bayer_combo.currentData()
        self._render(use_cached=False)

    def _on_regenerate(self) -> None:
        self._render(use_cached=False)


def _caption_for(frame) -> str:
    parts = [Path(frame.source_path).name]
    if frame.timestamp_utc:
        parts.append(frame.timestamp_utc)
    if frame.exposure_s is not None:
        parts.append(f"{frame.exposure_s:.1f}s")
    metrics = []
    if frame.fwhm_px is not None:
        metrics.append(f"FWHM {frame.fwhm_px:.2f}")
    if frame.star_count is not None:
        metrics.append(f"{frame.star_count} stars")
    if frame.streak_count:
        metrics.append(f"{frame.streak_count} streaks")
    line2 = "  ·  ".join(metrics)
    return "<br/>".join(["  ·  ".join(parts), line2]) if line2 else "  ·  ".join(parts)
