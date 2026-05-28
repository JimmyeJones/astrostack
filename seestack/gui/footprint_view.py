"""
Sky footprint view.

Once frames are plate-solved, each one has a 4-corner RA/Dec footprint. Drawing
those overlapping polygons on a tangent-plane projection gives an immediate
sense of:

  - How well the session covered the target (one big stack? Mosaic panels?
    Drift between frames?).
  - Which frames are outliers in pointing (probably the start of a session
    when the mount was settling).
  - How much overlap there is in mosaic captures.

The widget is intentionally simple — no full sky catalogue overlay, no labels.
Just polygons. Selected frame's footprint is highlighted.

Coordinates: project to a local tangent plane centered on the median (RA, Dec)
of all footprints. For the small angular extents a Seestar covers (a few
degrees at most), that's accurate enough to look correct.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget


@dataclass
class Footprint:
    """One frame's sky footprint."""

    frame_id: int
    corners_radec_deg: list[tuple[float, float]]  # 4 corners, image order
    accepted: bool = True


class FootprintView(QWidget):
    """
    Plot a set of footprints. Click on one to emit ``frameClicked``.

    No interaction beyond click selection; pan/zoom can come later if useful.
    """

    frameClicked = Signal(int)  # frame_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._footprints: list[Footprint] = []
        self._selected_id: int | None = None
        self._center_ra_deg: float = 0.0
        self._center_dec_deg: float = 0.0
        self._scale: float = 1.0  # px per degree
        self._margin_px: int = 12
        # Last-painted screen polygons by frame id, used for hit testing.
        self._screen_polys: dict[int, QPolygonF] = {}
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(False)

    def set_footprints(self, footprints: Iterable[Footprint]) -> None:
        self._footprints = list(footprints)
        self._recompute_projection()
        self.update()

    def set_selected(self, frame_id: int | None) -> None:
        self._selected_id = frame_id
        self.update()

    # ---- projection --------------------------------------------------

    def _recompute_projection(self) -> None:
        if not self._footprints:
            self._center_ra_deg = 0.0
            self._center_dec_deg = 0.0
            self._scale = 1.0
            return
        all_ra = [c[0] for fp in self._footprints for c in fp.corners_radec_deg]
        all_dec = [c[1] for fp in self._footprints for c in fp.corners_radec_deg]
        # Median is robust to a few wildly off frames.
        all_ra.sort()
        all_dec.sort()
        self._center_ra_deg = all_ra[len(all_ra) // 2]
        self._center_dec_deg = all_dec[len(all_dec) // 2]
        # We compute scale lazily in paintEvent based on the widget size.

    def _project(self, ra_deg: float, dec_deg: float) -> tuple[float, float]:
        """Tangent-plane projection of (RA, Dec) → (x_deg, y_deg) on a flat plane."""
        cos_dec = math.cos(math.radians(self._center_dec_deg))
        x = (ra_deg - self._center_ra_deg) * cos_dec
        y = -(dec_deg - self._center_dec_deg)  # flip so north is up on screen
        return x, y

    # ---- painting ----------------------------------------------------

    def paintEvent(self, event):  # noqa: N802 — Qt API
        from seestack.gui.theme import BG_SUNKEN, FG_SECONDARY

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(BG_SUNKEN))
        self._screen_polys.clear()

        if not self._footprints:
            painter.setPen(QColor(FG_SECONDARY))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No solved frames yet. Run Plate Solve.")
            painter.end()
            return

        # Find the projected bounding box and pick a scale.
        xs: list[float] = []
        ys: list[float] = []
        for fp in self._footprints:
            for ra, dec in fp.corners_radec_deg:
                px, py = self._project(ra, dec)
                xs.append(px)
                ys.append(py)
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        span_x = max(x_max - x_min, 1e-3)
        span_y = max(y_max - y_min, 1e-3)
        plot_w = max(1, self.width() - 2 * self._margin_px)
        plot_h = max(1, self.height() - 2 * self._margin_px - 16)  # extra for label
        sx = plot_w / span_x
        sy = plot_h / span_y
        self._scale = min(sx, sy)

        offset_x = self._margin_px - x_min * self._scale + (plot_w - span_x * self._scale) * 0.5
        offset_y = self._margin_px - y_min * self._scale + (plot_h - span_y * self._scale) * 0.5

        # Draw rejected frames in faded grey first so accepted/selected appear on top.
        for fp in self._footprints:
            if fp.accepted or fp.frame_id == self._selected_id:
                continue
            self._draw_footprint(painter, fp, offset_x, offset_y, accepted=False, selected=False)
        for fp in self._footprints:
            if not fp.accepted:
                continue
            if fp.frame_id == self._selected_id:
                continue
            self._draw_footprint(painter, fp, offset_x, offset_y, accepted=True, selected=False)
        # Selected footprint last so it's drawn on top.
        for fp in self._footprints:
            if fp.frame_id == self._selected_id:
                self._draw_footprint(painter, fp, offset_x, offset_y, accepted=fp.accepted, selected=True)

        # Caption.
        from seestack.gui.theme import FG_SECONDARY
        painter.setPen(QColor(FG_SECONDARY))
        caption = (
            f"Center RA {self._center_ra_deg:.3f}°  Dec {self._center_dec_deg:.3f}°  "
            f"·  span {span_x:.2f}° × {span_y:.2f}°  ·  {len(self._footprints)} frames"
        )
        painter.drawText(self._margin_px, self.height() - 4, caption)
        painter.end()

    def _draw_footprint(self, painter: QPainter, fp: Footprint,
                        offset_x: float, offset_y: float,
                        *, accepted: bool, selected: bool) -> None:
        poly = QPolygonF()
        for ra, dec in fp.corners_radec_deg:
            x, y = self._project(ra, dec)
            poly.append(QPointF(x * self._scale + offset_x, y * self._scale + offset_y))
        # Cache screen-space polygon for hit testing in mousePressEvent. Store
        # *before* we close the polygon, so the cached version has 4 vertices.
        self._screen_polys[fp.frame_id] = QPolygonF(poly)
        if len(poly) > 0:
            poly.append(poly[0])
        # Theme-aware colors: amber for selected, cool blue for accepted,
        # muted red for rejected. Keeps visual consistency with the rest
        # of the GUI (accept = green-ish/blue cool, reject = warm red,
        # selected = warm amber accent).
        from seestack.gui.theme import ACCENT, LINK, DANGER
        if selected:
            acc = QColor(ACCENT)
            pen = QPen(acc, 2.2)
            fill = QColor(acc); fill.setAlpha(55)
        elif accepted:
            pen_color = QColor(LINK); pen_color.setAlpha(210)
            pen = QPen(pen_color, 1.1)
            fill = QColor(LINK); fill.setAlpha(28)
        else:
            pen_color = QColor(DANGER); pen_color.setAlpha(170)
            pen = QPen(pen_color, 1.0)
            fill = QColor(DANGER); fill.setAlpha(18)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawPolygon(poly)

    # ---- mouse -------------------------------------------------------

    def mousePressEvent(self, event):  # noqa: N802 — Qt API
        if event.button() != Qt.MouseButton.LeftButton or not self._screen_polys:
            return
        click = QPointF(event.position())
        # Walk all polygons; emit the smallest one containing the click. With
        # heavy overlap that's the most informative pick.
        best_id: int | None = None
        best_area = float("inf")
        for frame_id, poly in self._screen_polys.items():
            if not poly.containsPoint(click, Qt.FillRule.OddEvenFill):
                continue
            # Approximate area via bounding box — exact area is overkill for
            # picking the "innermost" hit.
            br = poly.boundingRect()
            area = br.width() * br.height()
            if area < best_area:
                best_area = area
                best_id = frame_id
        if best_id is not None:
            self.frameClicked.emit(best_id)
