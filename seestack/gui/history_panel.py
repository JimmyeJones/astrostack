"""
Stack-history panel.

Shows every stack run recorded for the current project. The user can pick a
past run to view its preview, restore its settings into the Stack dialog, or
open its output folder in Explorer.

The expensive thing (the FITS) is not loaded — we lean on the preview PNG
that was already saved as part of the run output.
"""

from __future__ import annotations

import json
import logging
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seestack.io.project import Project, StackRunRow
from seestack.stack.stacker import StackOptions

log = logging.getLogger(__name__)


class HistoryPanel(QWidget):
    """Right-pane history viewer with per-run preview + actions."""

    # Emitted when the user picks "Load these settings" — main window
    # populates a fresh Stack dialog with them.
    settingsRequested = Signal(object)  # StackOptions

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._project: Project | None = None
        self._runs: list[StackRunRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        title = QLabel("<b>Stack history</b>")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list, stretch=2)

        from seestack.gui.theme import BG_SUNKEN, FG_SECONDARY, BG_DIVIDER
        self._preview = QLabel("☆\n\nSelect a run to preview")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(240, 200)
        self._preview.setStyleSheet(
            f"background:{BG_SUNKEN}; color:{FG_SECONDARY}; "
            f"border: 1px solid {BG_DIVIDER}; border-radius: 6px;"
        )
        layout.addWidget(self._preview, stretch=2)

        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._detail.setOpenExternalLinks(True)
        layout.addWidget(self._detail)

        btn_row = QHBoxLayout()
        self._btn_load = QPushButton("Load these settings")
        self._btn_load.clicked.connect(self._on_load_settings)
        self._btn_open = QPushButton("Open output folder")
        self._btn_open.clicked.connect(self._on_open_folder)
        self._btn_export = QPushButton("Export workflow…")
        self._btn_export.setToolTip(
            "Generate a Siril script or PixInsight recipe to continue "
            "processing this stack in your tool of choice."
        )
        self._btn_export.clicked.connect(self._on_export_workflow)
        self._btn_delete = QPushButton("Delete entry")
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_load)
        btn_row.addWidget(self._btn_open)
        btn_row.addWidget(self._btn_export)
        btn_row.addWidget(self._btn_delete)
        layout.addLayout(btn_row)
        self._set_buttons_enabled(False)

    def set_project(self, project: Project | None) -> None:
        self._project = project
        self.reload()

    def reload(self) -> None:
        self._list.clear()
        self._runs = []
        self._preview.setPixmap(QPixmap())
        self._preview.setText("Select a run to preview")
        self._detail.setText("")
        if self._project is None:
            return
        for run in self._project.iter_stack_runs():
            self._runs.append(run)
            label = self._format_list_label(run)
            item = QListWidgetItem(label)
            self._list.addItem(item)

    # ---- UI handlers --------------------------------------------------

    def _on_row_changed(self, row: int) -> None:
        if not (0 <= row < len(self._runs)):
            self._set_buttons_enabled(False)
            return
        self._set_buttons_enabled(True)
        run = self._runs[row]
        # Preview from disk (cheap).
        if run.preview_path and Path(run.preview_path).exists():
            pix = QPixmap(run.preview_path)
            self._preview.setPixmap(pix.scaledToWidth(360, Qt.TransformationMode.SmoothTransformation))
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("(preview not available)")
        self._detail.setText(self._format_detail(run))

    def _on_load_settings(self) -> None:
        run = self._current_run()
        if run is None:
            return
        try:
            data = json.loads(run.options_json)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "Bad options", f"Could not parse stored options: {exc}")
            return
        keys = {f.name for f in fields(StackOptions)}
        filtered = {k: v for k, v in data.items() if k in keys}
        try:
            opts = StackOptions(**filtered)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Bad options", str(exc))
            return
        self.settingsRequested.emit(opts)

    def _on_open_folder(self) -> None:
        run = self._current_run()
        if run is None or not run.fits_path:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(run.fits_path).parent)))

    def _on_delete(self) -> None:
        run = self._current_run()
        if run is None or run.id is None or self._project is None:
            return
        if QMessageBox.question(
            self,
            "Delete history entry",
            f"Remove the {run.timestamp_utc} entry from the history?\n\n"
            "Output files on disk are not touched.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._project.delete_stack_run(run.id)
        self.reload()

    # ---- helpers ------------------------------------------------------

    def _current_run(self) -> StackRunRow | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._runs):
            return self._runs[row]
        return None

    def _set_buttons_enabled(self, on: bool) -> None:
        self._btn_load.setEnabled(on)
        self._btn_open.setEnabled(on)
        self._btn_export.setEnabled(on)
        self._btn_delete.setEnabled(on)

    def _on_export_workflow(self) -> None:
        run = self._current_run()
        if run is None:
            return
        from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
        from dataclasses import fields as _fields

        choices = ["Siril (.ssf)", "PixInsight (.js recipe)"]
        choice, ok = QInputDialog.getItem(
            self, "Export workflow",
            "Generate a script for:", choices, 0, False,
        )
        if not ok:
            return

        # Reconstruct StackOptions from the run's saved JSON.
        try:
            opts_data = json.loads(run.options_json)
        except json.JSONDecodeError:
            opts_data = {}
        keys = {f.name for f in _fields(StackOptions)}
        opts = StackOptions(**{k: v for k, v in opts_data.items() if k in keys})

        if choice.startswith("Siril"):
            default_name = f"{run.output_basename}_process.ssf"
            filt = "Siril script (*.ssf)"
        else:
            default_name = f"{run.output_basename}_pixinsight.js"
            filt = "PixInsight script (*.js)"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save workflow script", default_name, filt,
        )
        if not save_path:
            return
        from seestack.post.export_scripts import (
            write_pixinsight_recipe, write_siril_script,
        )
        try:
            if choice.startswith("Siril"):
                write_siril_script(run, opts, save_path)
            else:
                write_pixinsight_recipe(run, opts, save_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Workflow exported", f"Written to {save_path}.")

    @staticmethod
    def _format_list_label(run: StackRunRow) -> str:
        ts = run.timestamp_utc[:19].replace("T", " ")
        return f"{ts}  ·  {run.output_basename}  ({run.n_frames_used} frames)"

    @staticmethod
    def _format_detail(run: StackRunRow) -> str:
        parts = [
            f"<b>{run.output_basename}</b>",
            f"{run.timestamp_utc[:19].replace('T', ' ')} UTC",
            f"{run.canvas_w}×{run.canvas_h} canvas",
            f"{run.n_frames_used} frames, coverage {run.coverage_min}–{run.coverage_max}",
        ]
        if run.notes:
            parts.append(f"<i>{run.notes}</i>")
        return "<br>".join(parts)
