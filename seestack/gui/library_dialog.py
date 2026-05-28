"""
Library Manager dialog.

One window for working with a *library* — a folder of many target projects:

  * **Scan a folder** of Seestar sub-folders. Each sub-folder becomes a
    target; loose files go to "Unsorted". Every frame is QC'd and
    plate-solved. Stacking is left to you, per target.
  * See every target at a glance (frames, exposure, last activity).
  * Open a target's project in the main window for stacking.
  * Merge two or more targets into one (for the "same object, two folders"
    case the one-folder-per-target scan can't know about).
  * Render the all-sky Aitoff map of the whole campaign.

The single-project workflow is untouched — ``File → Open project`` still
works for one-off targets outside any library.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seestack.io.library import Library
from seestack.io.project import Project
from seestack.solve.astap import find_astap

log = logging.getLogger(__name__)


# ---- scan worker thread --------------------------------------------------

class _ScanWorker(QThread):
    """
    Runs a full scan on a worker thread: organise a folder into targets,
    then QC + plate-solve every target. Heavy work (numeric QC, ASTAP
    subprocesses) is fanned out to a process pool inside the scanner.

    Signals
    -------
    progress(phase, done, total) : fine-grained progress within a phase.
    log_line(str)                : human-readable running commentary.
    finished_ok(dict)            : scan completed (summary dict).
    error(str)                   : scan aborted with an error.
    """

    progress = Signal(str, int, int)
    log_line = Signal(str)
    finished_ok = Signal(dict)
    error = Signal(str)

    def __init__(self, library_root: Path, scan_root: Path, *,
                 astap_path: str | None, copy_to_cache: bool,
                 run_solve: bool, parent=None) -> None:
        super().__init__(parent)
        self._library_root = library_root
        self._scan_root = scan_root
        self._astap_path = astap_path
        self._copy_to_cache = copy_to_cache
        self._run_solve = run_solve
        # Set by stop(); checked between targets and inside run_qc_and_solve
        # so a cancel takes effect promptly without corrupting the DB.
        self._should_stop = False

    def stop(self) -> None:
        self._should_stop = True

    def run(self) -> None:
        # Open the Library on *this* thread — SQLite connections can't be
        # shared across threads.
        from seestack.io.scanner import run_qc_and_solve, scan_and_organize

        try:
            lib = Library.open(self._library_root)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"could not open library: {exc}")
            return

        try:
            # --- Phase 1: organise folders into targets -----------------
            self.log_line.emit(f"Scanning {self._scan_root} …")
            scan_result = scan_and_organize(
                lib, self._scan_root,
                copy_to_cache=self._copy_to_cache,
                progress=lambda ph, d, t: self.progress.emit(ph, d, t),
            )
            self.log_line.emit(
                f"Organised {scan_result.n_targets} target(s); "
                f"{scan_result.total_added} new frame(s) ingested."
            )
            for tsr in scan_result.targets:
                self.log_line.emit(
                    f"  • {tsr.target_name}: +{tsr.n_frames_added} new"
                    + (f", {tsr.n_skipped_existing} already present"
                       if tsr.n_skipped_existing else "")
                    + (f", {tsr.n_errors} unreadable" if tsr.n_errors else "")
                )

            # --- Phase 2: QC + solve, target by target ------------------
            targets = lib.list_targets()
            for entry in targets:
                if self._should_stop:
                    self.log_line.emit("Stopped before finishing.")
                    break
                proj_dir = lib.target_dir(entry)
                if not (proj_dir / "project.sqlite").exists():
                    continue
                proj = Project.open(proj_dir)
                try:
                    summary = run_qc_and_solve(
                        proj,
                        astap_path=self._astap_path,
                        run_qc=True,
                        run_solve=self._run_solve,
                        progress=lambda ph, d, t, n=entry.name:
                            self.progress.emit(f"{ph} — {n}", d, t),
                        should_stop=lambda: self._should_stop,
                    )
                finally:
                    proj.close()
                lib.refresh_target_stats(entry.safe_name)
                msg = f"  ✓ {entry.name}: QC {summary['qc_done']}/{summary['qc_total']}"
                if self._run_solve:
                    msg += f", solved {summary['solve_done']}/{summary['solve_total']}"
                self.log_line.emit(msg)

            self.finished_ok.emit({
                "n_targets": scan_result.n_targets,
                "total_added": scan_result.total_added,
                "stopped": self._should_stop,
            })
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            lib.close()


# ---- main dialog ---------------------------------------------------------

class LibraryDialog(QDialog):
    """Modal dialog for managing a Library."""

    # Emitted with a project_dir Path when the user wants to open a target
    # in the main window.
    open_target_requested = Signal(object)

    def __init__(self, library: Library, parent=None) -> None:
        super().__init__(parent)
        self._library = library
        self._scan_worker: _ScanWorker | None = None
        self.setWindowTitle(f"Library — {library.root.name}")
        self.resize(940, 620)
        self._build_ui()
        self._reload(refresh_stats=True)
        # While a scan is running, repaint the table every couple of seconds
        # so frame counts update live. Pure read — see _reload's docstring.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self._reload)

    # ---- UI ------------------------------------------------------------

    def _build_ui(self) -> None:
        from seestack.gui.theme import ACCENT, FG_SECONDARY, BG_PANEL, BG_DIVIDER

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # --- header summary --------------------------------------------
        header_box = QWidget(self)
        header_box.setObjectName("libHeaderBox")
        header_box.setStyleSheet(
            f"QWidget#libHeaderBox {{"
            f"  background-color: {BG_PANEL};"
            f"  border: 1px solid {BG_DIVIDER};"
            f"  border-radius: 7px;"
            f"}}"
        )
        hb = QVBoxLayout(header_box)
        hb.setContentsMargins(14, 10, 14, 10)
        hb.setSpacing(2)
        self._summary_title = QLabel(
            f"<span style='color:{ACCENT}'>★</span> {self._library.root.name}"
        )
        self._summary_title.setStyleSheet(
            "font-size: 17px; font-weight: 600; background: transparent;"
        )
        hb.addWidget(self._summary_title)
        self._summary_label = QLabel("Loading…")
        self._summary_label.setStyleSheet(
            f"color: {FG_SECONDARY}; background: transparent;"
        )
        hb.addWidget(self._summary_label)
        root.addWidget(header_box)

        splitter = QSplitter(Qt.Horizontal, self)

        # --- left: target table ----------------------------------------
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 6, self)
        self._table.setHorizontalHeaderLabels(
            ["Target", "RA", "Dec", "Frames", "Exposure", "Last activity"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Extended selection so several targets can be picked for a merge.
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.doubleClicked.connect(self._on_open_target)
        self._table.itemSelectionChanged.connect(self._update_button_states)
        left_layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._btn_open = QPushButton("  ▸  Open target")
        self._btn_open.setProperty("primary", True)
        self._btn_open.setToolTip(
            "Open the selected target in the main window for stacking. "
            "Double-clicking a row does the same thing."
        )
        self._btn_open.clicked.connect(self._on_open_target)
        btn_row.addWidget(self._btn_open)

        self._btn_new = QPushButton("  ＋  New target…")
        self._btn_new.setToolTip(
            "Create a new, empty target inside this library."
        )
        self._btn_new.clicked.connect(self._on_new_target)
        btn_row.addWidget(self._btn_new)

        self._btn_merge = QPushButton("  ⤳  Merge…")
        self._btn_merge.setToolTip(
            "Merge two or more selected targets into one. Use this when the "
            "same object ended up in separate folders (e.g. two nights). "
            "Select the targets first (Ctrl/Shift-click), then click Merge."
        )
        self._btn_merge.clicked.connect(self._on_merge_targets)
        btn_row.addWidget(self._btn_merge)

        self._btn_delete = QPushButton("  ✕  Remove…")
        self._btn_delete.setProperty("danger", True)
        self._btn_delete.setToolTip(
            "Remove the selected target from the library. On-disk files are "
            "kept unless you tick the box that appears."
        )
        self._btn_delete.clicked.connect(self._on_delete_target)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # --- right: scan panel + log -----------------------------------
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(8)

        scan_box = QGroupBox("Scan a folder", self)
        sbl = QVBoxLayout(scan_box)

        blurb = QLabel(
            "Point Seestack at the folder your Seestar saves into. Each "
            "sub-folder becomes a target (a mosaic stays as one target); "
            "loose files go to “Unsorted”. Every frame is QC'd and "
            "plate-solved — you stack each target yourself afterwards."
        )
        blurb.setWordWrap(True)
        blurb.setProperty("role", "caption")
        sbl.addWidget(blurb)

        self._solve_check = QCheckBox("Plate-solve frames")
        self._solve_check.setChecked(True)
        astap = find_astap()
        if astap is None:
            self._solve_check.setChecked(False)
            self._solve_check.setEnabled(False)
            self._solve_check.setText("Plate-solve frames  (ASTAP not found)")
            self._solve_check.setToolTip(
                "ASTAP wasn't found on this machine. Install it and set its "
                "path under Settings → Set ASTAP path… to enable plate-solving."
            )
        else:
            self._solve_check.setToolTip(
                f"Run ASTAP ({astap.name}) on every frame to determine its "
                "sky coordinates. Needed before stacking. Slower than QC."
            )
        sbl.addWidget(self._solve_check)

        self._copy_check = QCheckBox("Copy frames into the library")
        self._copy_check.setChecked(False)
        self._copy_check.setToolTip(
            "Off (default): the library references your original files where "
            "they are — fast, no extra disk use.\n"
            "On: every frame is copied into the library's cache. Use this "
            "only if the scanned folder lives on a NAS / removable drive."
        )
        sbl.addWidget(self._copy_check)

        self._btn_scan = QPushButton("  🔭  Scan a folder…")
        self._btn_scan.setProperty("primary", True)
        self._btn_scan.clicked.connect(self._on_scan_clicked)
        sbl.addWidget(self._btn_scan)

        self._scan_progress = QProgressBar()
        self._scan_progress.setVisible(False)
        sbl.addWidget(self._scan_progress)

        self._scan_status = QLabel("Idle")
        self._scan_status.setProperty("role", "muted")
        sbl.addWidget(self._scan_status)

        right_layout.addWidget(scan_box)

        # Scan log.
        log_box = QGroupBox("Scan log", self)
        lbl = QVBoxLayout(log_box)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QTextEdit.NoWrap)
        self._log.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        lbl.addWidget(self._log)
        right_layout.addWidget(log_box, 1)

        # All-sky map + report.
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)
        self._btn_skymap = QPushButton("  🌌  All-sky map…")
        self._btn_skymap.setToolTip(
            "Render every target's position on an Aitoff projection of the "
            "whole sky, with bright stars and the Milky Way for reference."
        )
        self._btn_skymap.clicked.connect(self._on_render_skymap)
        bottom_row.addWidget(self._btn_skymap)
        self._btn_report = QPushButton("  ⓘ  Campaign report…")
        self._btn_report.setToolTip(
            "A summary of total integration time, frame counts, and "
            "per-target stats."
        )
        self._btn_report.clicked.connect(self._on_campaign_report)
        bottom_row.addWidget(self._btn_report)
        bottom_row.addStretch()
        right_layout.addLayout(bottom_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._update_button_states()

    # ---- table / reload ------------------------------------------------

    def _reload(self, *, refresh_stats: bool = False) -> None:
        """
        Repaint the target table + summary from the registry.

        ``refresh_stats`` re-reads every target's per-project DB first. It is
        skipped on the periodic timer tick: while a scan is running the scan
        worker already keeps those numbers fresh, and having the GUI thread
        *also* write the registry would cause SQLite write contention. The
        timer therefore does a pure read-and-repaint.
        """
        from seestack.gui.theme import ACCENT, SUCCESS, WARNING, DANGER

        if refresh_stats:
            for entry in self._library.list_targets():
                self._library.refresh_target_stats(entry.safe_name)

        prev_selected = set(self._selected_safe_names())

        targets = self._library.list_targets()
        stats = self._library.campaign_stats()
        self._summary_label.setText(
            f"<span style='color:{ACCENT}'><b>{stats['n_targets']}</b></span> "
            f"targets  ·  <b>{stats['n_frames_accepted']}</b> accepted frames "
            f" ·  total exposure <b>{_format_duration(stats['total_exposure_s'])}</b>"
        )

        self._table.setRowCount(len(targets))
        bold = QFont()
        bold.setBold(True)
        for r, t in enumerate(targets):
            name_item = _item(t.name)
            name_item.setFont(bold)
            name_item.setData(Qt.UserRole, t.safe_name)
            self._table.setItem(r, 0, name_item)
            self._table.setItem(r, 1, _item(
                _ra_str(t.ra_deg) if t.ra_deg is not None else "—",
                muted=t.ra_deg is None))
            self._table.setItem(r, 2, _item(
                _dec_str(t.dec_deg) if t.dec_deg is not None else "—",
                muted=t.dec_deg is None))
            frames_item = _item(
                f"{t.n_frames_accepted}/{t.n_frames}", align_right=True)
            if t.n_frames > 0:
                ratio = t.n_frames_accepted / t.n_frames
                frames_item.setForeground(QColor(
                    SUCCESS if ratio >= 0.9 else WARNING if ratio >= 0.7 else DANGER
                ))
            self._table.setItem(r, 3, frames_item)
            exp_item = _item(_format_duration(t.total_exposure_s), align_right=True)
            if t.total_exposure_s > 0:
                exp_item.setForeground(QColor(ACCENT))
            self._table.setItem(r, 4, exp_item)
            self._table.setItem(r, 5, _item(
                (t.last_activity_utc or "—").replace("T", " ").replace("Z", ""),
                muted=t.last_activity_utc is None))

        # Restore selection by safe_name (row indices may have shifted).
        if prev_selected:
            for r in range(self._table.rowCount()):
                it = self._table.item(r, 0)
                if it is not None and it.data(Qt.UserRole) in prev_selected:
                    self._table.selectRow(r)
        self._update_button_states()

    def _selected_safe_names(self) -> list[str]:
        """safe_names of every selected row (row 0 carries the safe_name)."""
        names: list[str] = []
        for idx in self._table.selectionModel().selectedRows():
            it = self._table.item(idx.row(), 0)
            if it is not None:
                sn = it.data(Qt.UserRole)
                if sn:
                    names.append(sn)
        return names

    def _update_button_states(self) -> None:
        """Enable/disable buttons based on selection and scan state."""
        scanning = self._scan_worker is not None and self._scan_worker.isRunning()
        sel = self._selected_safe_names()
        self._btn_open.setEnabled(len(sel) >= 1 and not scanning)
        self._btn_delete.setEnabled(len(sel) >= 1 and not scanning)
        self._btn_merge.setEnabled(len(sel) >= 2 and not scanning)
        self._btn_new.setEnabled(not scanning)
        # The scan button doubles as a Cancel button while a scan runs.
        self._btn_scan.setEnabled(True)

    # ---- target actions -----------------------------------------------

    def _on_open_target(self, *_) -> None:
        sel = self._selected_safe_names()
        if not sel:
            return
        entry = self._library.find_target(sel[0])
        if entry is None:
            return
        self.open_target_requested.emit(self._library.target_dir(entry))
        self.accept()

    def _on_new_target(self) -> None:
        name, ok = QInputDialog.getText(self, "New target", "Target name:")
        if not ok or not name.strip():
            return
        try:
            entry, proj = self._library.create_target(name.strip())
            proj.close()
        except FileExistsError as exc:
            QMessageBox.warning(self, "Already exists", str(exc))
            return
        self._reload(refresh_stats=True)

    def _on_merge_targets(self) -> None:
        sel = self._selected_safe_names()
        if len(sel) < 2:
            QMessageBox.information(
                self, "Select targets to merge",
                "Select two or more targets first (Ctrl-click or Shift-click "
                "rows), then click Merge.",
            )
            return
        entries = [self._library.find_target(s) for s in sel]
        entries = [e for e in entries if e is not None]
        names = [e.name for e in entries]
        primary, ok = QInputDialog.getItem(
            self, "Merge targets",
            "Keep which target?  All the others will be merged into it "
            "and then removed:",
            names, 0, editable=False,
        )
        if not ok:
            return
        primary_entry = entries[names.index(primary)]
        sources = [e.safe_name for e in entries if e.id != primary_entry.id]
        try:
            added = self._library.merge_targets(primary_entry.safe_name, sources)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Merge failed", str(exc))
            return
        QMessageBox.information(
            self, "Merge complete",
            f"Merged {len(sources)} target(s) into “{primary_entry.name}”.\n"
            f"{added} frame(s) moved.",
        )
        self._reload(refresh_stats=True)

    def _on_delete_target(self) -> None:
        sel = self._selected_safe_names()
        if not sel:
            return
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Remove target(s)?")
        msg.setText(
            f"Remove {len(sel)} target(s) from the library?\n\n"
            "On-disk files are kept unless you tick the box below."
        )
        delete_check = QCheckBox("Also delete the target folders from disk")
        msg.setCheckBox(delete_check)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        if msg.exec() != QMessageBox.Yes:
            return
        for sn in sel:
            self._library.delete_target(sn, remove_files=delete_check.isChecked())
        self._reload(refresh_stats=True)

    # ---- scanning ------------------------------------------------------

    def _on_scan_clicked(self) -> None:
        # While a scan runs, the button is a Cancel button.
        if self._scan_worker is not None and self._scan_worker.isRunning():
            self._scan_status.setText("Stopping…")
            self._scan_worker.stop()
            return

        folder = QFileDialog.getExistingDirectory(
            self, "Choose the folder to scan (your Seestar save folder)",
        )
        if not folder:
            return

        astap = find_astap()
        run_solve = self._solve_check.isChecked()
        self._library.set_meta("last_scan_root", folder)

        self._log.clear()
        self._scan_progress.setVisible(True)
        self._scan_progress.setRange(0, 0)  # indeterminate until first progress
        self._scan_worker = _ScanWorker(
            library_root=self._library.root,
            scan_root=Path(folder),
            astap_path=str(astap) if astap else None,
            copy_to_cache=self._copy_check.isChecked(),
            run_solve=run_solve,
            parent=self,
        )
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.log_line.connect(self._append_log)
        self._scan_worker.finished_ok.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

        from seestack.gui.theme import INFO
        self._btn_scan.setText("  ◼  Stop scan")
        self._btn_scan.setProperty("primary", False)
        self._btn_scan.setProperty("danger", True)
        self._btn_scan.style().unpolish(self._btn_scan)
        self._btn_scan.style().polish(self._btn_scan)
        self._scan_status.setText("Scanning…")
        self._scan_status.setStyleSheet(f"color: {INFO}; font-weight: 600;")
        self._refresh_timer.start()
        self._update_button_states()

    def _on_scan_progress(self, phase: str, done: int, total: int) -> None:
        if total > 0:
            self._scan_progress.setRange(0, total)
            self._scan_progress.setValue(done)
        else:
            self._scan_progress.setRange(0, 0)
        self._scan_status.setText(f"{phase}  ({done}/{total})" if total
                                  else phase)

    def _append_log(self, line: str) -> None:
        self._log.append(line)

    def _on_scan_finished(self, summary: dict) -> None:
        self._refresh_timer.stop()
        stopped = summary.get("stopped", False)
        self._append_log(
            "Scan cancelled." if stopped
            else f"Scan complete — {summary.get('n_targets', 0)} target(s)."
        )
        self._reset_scan_ui()
        self._reload(refresh_stats=True)

    def _on_scan_error(self, msg: str) -> None:
        self._refresh_timer.stop()
        self._append_log(f"ERROR: {msg}")
        self._reset_scan_ui()
        QMessageBox.warning(self, "Scan error", msg)
        self._reload(refresh_stats=True)

    def _reset_scan_ui(self) -> None:
        from seestack.gui.theme import FG_SECONDARY
        self._scan_worker = None
        self._scan_progress.setVisible(False)
        self._btn_scan.setText("  🔭  Scan a folder…")
        self._btn_scan.setProperty("primary", True)
        self._btn_scan.setProperty("danger", False)
        self._btn_scan.style().unpolish(self._btn_scan)
        self._btn_scan.style().polish(self._btn_scan)
        self._scan_status.setText("Idle")
        self._scan_status.setStyleSheet(f"color: {FG_SECONDARY};")
        self._update_button_states()

    def _stop_scan(self) -> None:
        """Stop a running scan worker. Safe to call when none is running."""
        w = self._scan_worker
        if w is None:
            return
        w.stop()
        if not w.wait(8000):
            # Still busy (e.g. an ASTAP solve mid-flight). Detach it from
            # this dialog so it isn't destroyed under Qt's feet, and let it
            # clean itself up when it finally returns.
            log.warning("scan worker didn't stop in time; detaching it")
            w.setParent(None)
            w.finished.connect(w.deleteLater)
        self._scan_worker = None
        self._refresh_timer.stop()

    # ---- skymap / report ----------------------------------------------

    def _on_render_skymap(self) -> None:
        try:
            from seestack.post.skymap import SkyMapOptions, render_to_png
        except ImportError as exc:
            QMessageBox.warning(self, "Missing dependency",
                                f"Matplotlib not available: {exc}")
            return
        out = self._library.root / "skymap.png"
        try:
            render_to_png(self._library, out,
                          SkyMapOptions(title=f"Campaign — {self._library.root.name}"))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Render failed", str(exc))
            return
        SkymapPreview(out, parent=self).exec()

    def _on_campaign_report(self) -> None:
        stats = self._library.campaign_stats()
        targets = self._library.list_targets()
        lines = [
            f"<b>Library:</b> {self._library.root}",
            f"<b>Targets:</b> {stats['n_targets']}",
            f"<b>Accepted frames:</b> {stats['n_frames_accepted']} / "
            f"{stats['n_frames']}",
            f"<b>Total integration:</b> "
            f"{_format_duration(stats['total_exposure_s'])}",
            "",
            "<b>Per-target breakdown</b>",
        ]
        for t in targets:
            lines.append(
                f"&nbsp;&nbsp;{t.name}: {t.n_frames_accepted}/{t.n_frames} "
                f"frames · {_format_duration(t.total_exposure_s)} · "
                f"last {(t.last_activity_utc or '—')}"
            )
        QMessageBox.information(self, "Campaign report", "<br>".join(lines))

    # ---- shutdown ------------------------------------------------------

    def reject(self) -> None:  # type: ignore[override]
        # The scan worker is parented to this dialog — it must be stopped (or
        # detached) before the dialog is destroyed, or Qt aborts with
        # "QThread: Destroyed while thread is still running".
        self._stop_scan()
        super().reject()

    def accept(self) -> None:  # type: ignore[override]
        self._stop_scan()
        super().accept()


# ---- skymap preview ------------------------------------------------------

class SkymapPreview(QDialog):
    """Shows a saved all-sky PNG."""

    def __init__(self, image_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("All-sky map")
        self.resize(900, 520)
        layout = QVBoxLayout(self)
        label = QLabel()
        pix = QPixmap(str(image_path))
        if pix.isNull():
            label.setText(f"could not load image at {image_path}")
        else:
            label.setPixmap(pix.scaledToWidth(880, Qt.SmoothTransformation))
        layout.addWidget(label)
        path_lbl = QLabel(f"Saved to {image_path}")
        path_lbl.setProperty("role", "caption")
        layout.addWidget(path_lbl)


# ---- helpers -------------------------------------------------------------

def _item(text: str, *, align_right: bool = False,
          muted: bool = False) -> QTableWidgetItem:
    """QTableWidget cell. ``muted`` greys placeholder/missing values."""
    from seestack.gui.theme import FG_DISABLED
    item = QTableWidgetItem(text)
    if align_right:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if muted:
        item.setForeground(QColor(FG_DISABLED))
    return item


def _ra_str(ra_deg: float) -> str:
    """RA in hours:minutes."""
    h = ra_deg / 15.0
    hh = int(h)
    mm = (h - hh) * 60.0
    return f"{hh:02d}h {mm:04.1f}m"


def _dec_str(dec_deg: float) -> str:
    sign = "+" if dec_deg >= 0 else "-"
    a = abs(dec_deg)
    dd = int(a)
    mm = (a - dd) * 60.0
    return f"{sign}{dd:02d}° {mm:04.1f}'"


def _format_duration(seconds: float) -> str:
    """Friendly duration. 3725 → '1h 2m 5s'."""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"
