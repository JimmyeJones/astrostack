"""
System-tray notifications.

A tiny shim around ``QSystemTrayIcon.showMessage``. We keep a process-wide
tray-icon instance so notifications survive past the call (Qt requires the
icon object to outlive the notification). On systems where the tray isn't
available the call becomes a no-op so it's safe to fire from anywhere.

Specifically useful for the overnight-batch workflow: pop a Windows toast
when the plan / stack finishes so the user notices even if they alt-tabbed.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

log = logging.getLogger(__name__)

_tray: QSystemTrayIcon | None = None


def _get_tray() -> QSystemTrayIcon | None:
    global _tray
    if _tray is not None:
        return _tray
    if QApplication.instance() is None or not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    # Use the app's window icon if available; otherwise an empty icon.
    icon = QIcon()
    app = QApplication.instance()
    if isinstance(app, QApplication):
        icon = app.windowIcon() or icon
    _tray = QSystemTrayIcon(icon)
    _tray.setToolTip("Seestack")
    _tray.show()
    return _tray


def notify_user(
    title: str,
    body: str,
    *,
    timeout_ms: int = 8000,
    success: bool = True,
) -> None:
    """
    Pop a system tray notification.

    No-op when there's no QApplication or the tray isn't available. Tries
    ``QSystemTrayIcon.showMessage`` first; logs the message regardless so
    a headless run still records it.
    """
    log.info("[notify] %s — %s", title, body)
    tray = _get_tray()
    if tray is None:
        return
    icon = (
        QSystemTrayIcon.MessageIcon.Information
        if success
        else QSystemTrayIcon.MessageIcon.Warning
    )
    try:
        tray.showMessage(title, body, icon, timeout_ms)
    except Exception as exc:  # noqa: BLE001 — never let a notification crash the app
        log.debug("tray showMessage failed: %s", exc)
