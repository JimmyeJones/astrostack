"""Footprint view — projection, hit-testing, painting smoke."""

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QPaintEvent, QPolygonF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from seestack.gui.footprint_view import Footprint, FootprintView  # noqa: E402

_app = QApplication.instance() or QApplication([])


def test_set_footprints_recomputes_center():
    view = FootprintView()
    fps = [
        Footprint(frame_id=1, corners_radec_deg=[
            (100.0, 20.0), (100.5, 20.0), (100.5, 19.5), (100.0, 19.5),
        ]),
        Footprint(frame_id=2, corners_radec_deg=[
            (100.2, 19.9), (100.7, 19.9), (100.7, 19.4), (100.2, 19.4),
        ]),
    ]
    view.set_footprints(fps)
    # Median of the corner RAs should be near 100.x.
    assert 99.5 < view._center_ra_deg < 101.0
    assert 19.0 < view._center_dec_deg < 20.5


def test_set_selected_does_not_crash():
    view = FootprintView()
    view.resize(400, 300)
    view.set_footprints([Footprint(frame_id=1, corners_radec_deg=[
        (10.0, 10.0), (10.1, 10.0), (10.1, 9.9), (10.0, 9.9),
    ])])
    view.set_selected(1)
    # Force a paint to populate the screen-poly cache.
    view.show()
    QApplication.processEvents()


def test_paint_with_no_data_is_safe():
    view = FootprintView()
    view.resize(200, 200)
    view.show()
    QApplication.processEvents()  # triggers paintEvent
    # No exception = success.
