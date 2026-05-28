"""Seestack GUI entry point — launches the main window."""

from __future__ import annotations

import logging
import sys


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Imported lazily so non-GUI uses (tests, scripts) don't pull Qt.
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from seestack.gui.main_window import MainWindow
    from seestack.gui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("Seestack")
    app.setApplicationDisplayName("Seestack")
    # A slightly larger base font reads better on the high-DPI displays
    # most users will have. Falls back to system default if the family
    # isn't available.
    app.setFont(QFont("Segoe UI", 10))
    apply_theme(app)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
