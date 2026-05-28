"""
Frame table — the central view of a project.

Shows one row per frame with metadata + computed metrics. Designed for 10k+
rows: backed by a Qt model that lazy-fetches from the project DB instead of
loading everything into memory.

Columns
-------
✓ (accept)  | id | name | timestamp | exp | gain | FWHM | stars |
sky ADU | ecc | streaks | reject reason

Click the ✓ column to toggle accept/reject manually (sets ``user_override``).
Click any header to sort. Right-click a row for actions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import QHeaderView, QMenu, QTableView

from seestack.io.project import FrameRow, Project

log = logging.getLogger(__name__)


@dataclass
class Column:
    key: str           # FrameRow attribute name
    label: str
    width: int = 80
    fmt: str = ""      # python format spec, e.g. ".2f"
    numeric: bool = False


COLUMNS: list[Column] = [
    Column("accept", "✓", 28),
    Column("id", "ID", 56, numeric=True),
    Column("source_path", "Name", 240),
    Column("timestamp_utc", "Timestamp (UTC)", 160),
    Column("exposure_s", "Exp (s)", 60, fmt=".1f", numeric=True),
    Column("gain", "Gain", 50, fmt=".0f", numeric=True),
    Column("fwhm_px", "FWHM", 64, fmt=".2f", numeric=True),
    Column("star_count", "Stars", 56, numeric=True),
    Column("sky_adu_median", "Sky ADU", 76, fmt=".0f", numeric=True),
    Column("eccentricity_median", "Ecc.", 60, fmt=".2f", numeric=True),
    Column("streak_count", "Streaks", 60, numeric=True),
    Column("reject_reason", "Reason", 120),
]

# Custom sort role — proxy uses this so numeric columns sort by value, not by
# their formatted string. Avoids the "10 sorts before 9" trap.
SORT_ROLE = Qt.ItemDataRole.UserRole + 1


class FrameTableModel(QAbstractTableModel):
    """
    Project-backed table model.

    Holds a list of FrameRow snapshots in memory. For 10k frames this is fine
    — each row is small (~300 bytes), so the whole table fits in a few MB.
    Updates from the QC pipeline come through ``update_frame``, which patches
    the in-memory row and emits ``dataChanged``.
    """

    def __init__(self, project: Project | None = None, parent: Any = None) -> None:
        super().__init__(parent)
        self._project: Project | None = None
        self._rows: list[FrameRow] = []
        self._row_index: dict[int, int] = {}  # frame_id -> row index
        if project is not None:
            self.set_project(project)

    # ---- bound to a project --------------------------------------------

    def set_project(self, project: Project | None) -> None:
        self.beginResetModel()
        self._project = project
        self._rows = list(project.iter_frames()) if project else []
        self._rebuild_index()
        self.endResetModel()

    def reload(self) -> None:
        if self._project is None:
            return
        self.beginResetModel()
        self._rows = list(self._project.iter_frames())
        self._rebuild_index()
        self.endResetModel()

    def _rebuild_index(self) -> None:
        self._row_index = {f.id: i for i, f in enumerate(self._rows) if f.id is not None}

    def add_frame(self, frame: FrameRow) -> None:
        if frame.id is None:
            return
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append(frame)
        self._row_index[frame.id] = row
        self.endInsertRows()

    def update_frame(self, frame_id: int, **fields: Any) -> None:
        """Patch one row in-place. Called when QC results stream in."""
        idx = self._row_index.get(frame_id)
        if idx is None:
            return
        row = self._rows[idx]
        for k, v in fields.items():
            if hasattr(row, k):
                setattr(row, k, v)
        top = self.index(idx, 0)
        bottom = self.index(idx, len(COLUMNS) - 1)
        self.dataChanged.emit(top, bottom)

    # ---- Qt model API --------------------------------------------------

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: D401
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section].label
        if role == Qt.ItemDataRole.ToolTipRole and orientation == Qt.Orientation.Horizontal:
            return _column_tooltip(COLUMNS[section].key)
        return None

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = COLUMNS[index.column()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._format_cell(row, col)
        if role == SORT_ROLE:
            # Raw value for sorting. Numeric columns sort numerically; missing
            # values sort to the end regardless of direction.
            return self._sort_key(row, col)
        if role == Qt.ItemDataRole.CheckStateRole and col.key == "accept":
            return Qt.CheckState.Checked if row.accept else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.TextAlignmentRole and col.numeric:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole and not row.accept:
            # Faded red wash so the row is obviously rejected without being
            # so loud that the rest of the data becomes unreadable.
            return QBrush(QColor(56, 24, 30))
        if role == Qt.ItemDataRole.ForegroundRole:
            # Subtle row-level coloring: rejected rows go warm-grey, the
            # accept-checkbox column gets the green / red status colour.
            if not row.accept:
                return QBrush(QColor("#a08585"))
            if col.key == "accept":
                return QBrush(QColor("#5dd39e"))  # SUCCESS
        if role == Qt.ItemDataRole.ToolTipRole:
            if col.key == "source_path":
                return row.source_path
        return None

    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid():
            return False
        col = COLUMNS[index.column()]
        if col.key == "accept" and role == Qt.ItemDataRole.CheckStateRole:
            row = self._rows[index.row()]
            new_accept = value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked
            row.accept = bool(new_accept)
            row.user_override = True
            row.reject_reason = None if row.accept else "user"
            if self._project is not None and row.id is not None:
                self._project.update_frame(
                    row.id,
                    accept=row.accept,
                    user_override=True,
                    reject_reason=row.reject_reason,
                )
            top = self.index(index.row(), 0)
            bottom = self.index(index.row(), len(COLUMNS) - 1)
            self.dataChanged.emit(top, bottom)
            return True
        return False

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        f = super().flags(index)
        if not index.isValid():
            return f
        if COLUMNS[index.column()].key == "accept":
            return f | Qt.ItemFlag.ItemIsUserCheckable
        return f

    # ---- formatting ----------------------------------------------------

    @staticmethod
    def _format_cell(row: FrameRow, col: Column) -> str:
        if col.key == "accept":
            return ""  # checkbox, no text
        v = getattr(row, col.key, None)
        if v is None:
            return ""
        if col.key == "source_path":
            return Path(v).name
        if col.fmt and isinstance(v, (int, float)):
            try:
                return format(v, col.fmt)
            except (TypeError, ValueError):
                return str(v)
        return str(v)

    @staticmethod
    def _sort_key(row: FrameRow, col: Column) -> Any:
        """Raw value used for sorting. None always sorts last."""
        if col.key == "accept":
            return 1 if row.accept else 0
        v = getattr(row, col.key, None)
        if v is None:
            # Push missing values to the bottom regardless of sort direction.
            # QSortFilterProxyModel compares None as smallest, so we substitute
            # +inf for ascending sorts; the proxy reverses naturally for desc.
            return float("inf") if col.numeric else "￿"
        if col.key == "source_path":
            return Path(v).name.lower()
        return v


def _column_tooltip(key: str) -> str:
    """Hover tips for column headers — links into the glossary mentally."""
    tips = {
        "fwhm_px":
            "Full-width half-max in pixels — how sharp stars are. Lower is better. "
            "See the glossary for what's typical for the Seestar.",
        "star_count":
            "Number of stars detected. A sudden drop in this is a strong cloud signal.",
        "sky_adu_median":
            "Median sky background brightness. Higher = light pollution, moonlight, "
            "or thin clouds.",
        "eccentricity_median":
            "How elongated stars look. 0=round, 1=streaked. "
            "High eccentricity means tracking errors or wind.",
        "streak_count":
            "Detected streaks (satellites, planes, meteors). 0 is what you want.",
        "reject_reason":
            "Why a frame is rejected. 'user' = you toggled it manually.",
    }
    return tips.get(key, "")


class _RejectedFilterProxy(QSortFilterProxyModel):
    """
    Sort proxy that can additionally hide rejected frames.

    The user toggles this via the "Show rejected" checkbox in the action bar.
    Default is to show everything (so the rejected greyed-out rows are still
    visible — the toggle is for when the list is too noisy to use otherwise).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._show_rejected = True

    def set_show_rejected(self, show: bool) -> None:
        self._show_rejected = show
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:  # noqa: N802
        if self._show_rejected:
            return True
        src_model = self.sourceModel()
        if not isinstance(src_model, FrameTableModel):
            return True
        if 0 <= source_row < len(src_model._rows):
            return src_model._rows[source_row].accept
        return True


class FrameTableView(QTableView):
    """Sortable, batch-friendly table view with sensible defaults applied."""

    restoreRequested = Signal(int)   # frame_id, emitted from context menu
    rejectRequested = Signal(int)    # frame_id, emitted from context menu

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(20)
        self.setShowGrid(False)
        self.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._proxy: _RejectedFilterProxy | None = None  # type: ignore[no-redef]

    def set_model(self, model: FrameTableModel) -> None:
        proxy = _RejectedFilterProxy(self)
        proxy.setSourceModel(model)
        proxy.setSortRole(SORT_ROLE)
        super().setModel(proxy)
        self._proxy = proxy
        h = self.horizontalHeader()
        for i, col in enumerate(COLUMNS):
            self.setColumnWidth(i, col.width)
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.sortByColumn(1, Qt.SortOrder.AscendingOrder)

    def set_show_rejected(self, show: bool) -> None:
        if self._proxy is not None:
            self._proxy.set_show_rejected(show)

    def _show_context_menu(self, pos) -> None:
        if self._proxy is None:
            return
        idx = self.indexAt(pos)
        if not idx.isValid():
            return
        src_idx = self._proxy.mapToSource(idx)
        src_model = self._proxy.sourceModel()
        if not isinstance(src_model, FrameTableModel):
            return
        row = src_idx.row()
        if not (0 <= row < len(src_model._rows)):
            return
        frame = src_model._rows[row]
        if frame.id is None:
            return
        menu = QMenu(self)
        if frame.accept:
            act = QAction("Reject this frame", self)
            act.triggered.connect(lambda: self.rejectRequested.emit(frame.id))
            menu.addAction(act)
        else:
            act = QAction(
                f"Restore (was rejected: {frame.reject_reason or 'unknown'})", self,
            )
            act.triggered.connect(lambda: self.restoreRequested.emit(frame.id))
            menu.addAction(act)
        menu.exec(self.viewport().mapToGlobal(pos))
