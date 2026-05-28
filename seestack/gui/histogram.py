"""
Lightweight histogram widget.

Pure-Qt, zero extra dependencies. Used to visualise the distribution of a metric
(FWHM, star count, sky ADU, etc.) across the project. Hover over a bar to see
the bin range and count. Double-click a bar to filter the table to that range
(future M5 feature; the widget exposes a signal for it now).

Why not QtCharts or matplotlib? QtCharts adds a separate Qt module dependency
and matplotlib is heavy to import. A 200-line custom widget is faster, lighter,
and gives us exactly the look we want.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class HistogramWidget(QWidget):
    """
    Bar histogram for a single metric.

    Signals
    -------
    rangeSelected(float lo, float hi) : double-click on a bar emits its range.
    """

    rangeSelected = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: np.ndarray = np.array([])
        self._title: str = ""
        self._unit: str = ""
        self._n_bins: int = 30
        self._bin_edges: np.ndarray = np.array([])
        self._bin_counts: np.ndarray = np.array([])
        self._highlight_range: tuple[float, float] | None = None
        self.setMouseTracking(True)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_data(self, values: Sequence[float], title: str = "", unit: str = "") -> None:
        arr = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
        self._values = arr
        self._title = title
        self._unit = unit
        if arr.size == 0:
            self._bin_edges = np.array([])
            self._bin_counts = np.array([])
        else:
            lo, hi = float(arr.min()), float(arr.max())
            if hi <= lo:
                hi = lo + 1.0
            self._bin_counts, self._bin_edges = np.histogram(arr, bins=self._n_bins, range=(lo, hi))
        self.update()

    def set_highlight_range(self, lo: float | None, hi: float | None) -> None:
        if lo is None or hi is None:
            self._highlight_range = None
        else:
            self._highlight_range = (lo, hi)
        self.update()

    # ---- painting -----------------------------------------------------

    def paintEvent(self, event):  # noqa: N802 — Qt API
        from seestack.gui.theme import (
            BG_SUNKEN, BG_DIVIDER, FG_PRIMARY, FG_SECONDARY, ACCENT, LINK,
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        # Subtle panel background so the bars have something to read against.
        painter.fillRect(rect, QColor(BG_SUNKEN))

        # Title
        if self._title:
            painter.setPen(QColor(FG_PRIMARY))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(8, 14, f"{self._title}")
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(FG_SECONDARY))
            painter.drawText(
                8 + painter.fontMetrics().horizontalAdvance(self._title) + 8,
                14, f"n={self._values.size}",
            )

        if self._bin_counts.size == 0:
            painter.setPen(QColor(FG_SECONDARY))
            painter.drawText(
                rect.x() + max(0, rect.width() // 2 - 30),
                rect.y() + max(20, rect.height() // 2),
                "no data",
            )
            painter.end()
            return

        plot_top = 22
        plot_bottom = rect.height() - 18
        plot_left = 8
        plot_right = rect.width() - 8
        plot_h = max(1, plot_bottom - plot_top)
        plot_w = max(1, plot_right - plot_left)

        max_count = max(int(self._bin_counts.max()), 1)
        n = len(self._bin_counts)
        bar_w = plot_w / n
        edges = self._bin_edges
        hi_lo, hi_hi = (self._highlight_range or (None, None))

        bar_color = QColor(LINK)
        highlight_color = QColor(ACCENT)
        for i, c in enumerate(self._bin_counts):
            x = plot_left + i * bar_w
            h = plot_h * (c / max_count)
            bar_rect = QRectF(x, plot_bottom - h, bar_w - 1, h)
            in_highlight = (
                hi_lo is not None
                and hi_hi is not None
                and edges[i] >= hi_lo
                and edges[i + 1] <= hi_hi
            )
            painter.fillRect(bar_rect, highlight_color if in_highlight else bar_color)

        # Axis line
        painter.setPen(QPen(QColor(BG_DIVIDER), 1))
        painter.drawLine(plot_left, plot_bottom, plot_right, plot_bottom)

        # Min/max labels
        painter.setPen(QColor(FG_SECONDARY))
        unit = (" " + self._unit) if self._unit else ""
        painter.drawText(plot_left, rect.height() - 4, f"{edges[0]:.2f}{unit}")
        text = f"{edges[-1]:.2f}{unit}"
        fm = painter.fontMetrics()
        painter.drawText(plot_right - fm.horizontalAdvance(text), rect.height() - 4, text)
        painter.end()

    # ---- mouse --------------------------------------------------------

    def mouseDoubleClickEvent(self, event):  # noqa: N802 — Qt API
        if self._bin_edges.size == 0:
            return
        plot_left = 8
        plot_right = self.width() - 8
        if event.position().x() < plot_left or event.position().x() > plot_right:
            return
        rel = (event.position().x() - plot_left) / max(1, plot_right - plot_left)
        n = len(self._bin_counts)
        i = int(np.clip(rel * n, 0, n - 1))
        lo = float(self._bin_edges[i])
        hi = float(self._bin_edges[i + 1])
        self.rangeSelected.emit(lo, hi)

    def mouseMoveEvent(self, event):  # noqa: N802 — Qt API
        if self._bin_edges.size == 0:
            self.setToolTip("")
            return
        plot_left = 8
        plot_right = self.width() - 8
        if event.position().x() < plot_left or event.position().x() > plot_right:
            self.setToolTip("")
            return
        rel = (event.position().x() - plot_left) / max(1, plot_right - plot_left)
        n = len(self._bin_counts)
        i = int(np.clip(rel * n, 0, n - 1))
        lo = float(self._bin_edges[i])
        hi = float(self._bin_edges[i + 1])
        c = int(self._bin_counts[i])
        self.setToolTip(f"{self._title}: {lo:.2f}–{hi:.2f}{(' ' + self._unit) if self._unit else ''}  ({c} frames)")
        super().mouseMoveEvent(event)
