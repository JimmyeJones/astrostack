"""
Main application window.

Layout:

    +----------------------------------------------------+
    | menu / toolbar                                     |
    +-----------------------------+----------------------+
    | frame table (large)         | preview pane         |
    |                             |                      |
    |                             +----------------------+
    |                             | metric histograms    |
    +-----------------------------+----------------------+
    | status bar: device · project · progress            |
    +----------------------------------------------------+

The window is the only thing that talks to the project DB from the GUI side. It
owns the FrameTableModel and feeds updates into it; everything else (preview,
histograms) reads from the model.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seestack import __version__
from seestack.core.cache import CacheManager
from seestack.core.jobs import JobRunner, JobResult
from seestack.core.xp import device_summary
from seestack.gui.footprint_view import Footprint, FootprintView
from seestack.gui.frame_table import FrameTableModel, FrameTableView
from seestack.gui.glossary_viewer import GlossaryDialog
from seestack.gui.histogram import HistogramWidget
from seestack.gui.history_panel import HistoryPanel
from seestack.gui.notify import notify_user
from seestack.gui.plan_dialog import PlanEditor, PlanRunner
from seestack.gui.preview import PreviewPane
from seestack.gui.stack_dialog import StackOptionsDialog
from seestack.gui.thumbnail import ensure_thumb_cache_current
from seestack.io.ingest import find_fits_files, ingest_files
from seestack.io.project import Project
from seestack.io.wcs_io import footprint_radec_deg, wcs_from_text
from seestack.qc.runner import (
    QCResult,
    apply_qc_result_to_db,
    build_qc_arglist,
    compute_for_db_row,
)
from seestack.solve.runner import (
    SolveResult,
    apply_solve_result_to_db,
    build_solve_arglist,
    solve_one,
)
from seestack.solve.astap import find_astap
from seestack.stack.stacker import StackOptions, StackResult, run_stack

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Seestack {__version__}")
        self.resize(1400, 800)
        self.setAcceptDrops(True)  # see dragEnterEvent / dropEvent

        self._project: Project | None = None
        self._cache: CacheManager | None = None
        self._model = FrameTableModel()
        self._qc_runner: JobRunner | None = None
        self._solve_runner: JobRunner | None = None
        self._stack_thread: _StackThread | None = None
        # Currently-open library root, if any. We keep just the path here so
        # re-opening the library manager re-uses the same library.
        self._library_root: Path | None = None

        self._build_ui()
        self._build_menus()
        self._update_window_title()

    # ---- ui scaffolding -----------------------------------------------

    def _build_ui(self) -> None:
        # Left pane: frame table
        self._table = FrameTableView()
        self._table.set_model(self._model)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Right pane: tabbed — Preview | Footprints, with histograms below.
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self._right_tabs = QTabWidget()
        self._preview = PreviewPane()
        self._footprints = FootprintView()
        self._footprints.frameClicked.connect(self._on_footprint_clicked)
        self._history = HistoryPanel()
        self._history.settingsRequested.connect(self._on_load_history_settings)
        self._right_tabs.addTab(self._preview, "Preview")
        self._right_tabs.addTab(self._footprints, "Footprints")
        self._right_tabs.addTab(self._history, "History")
        right_layout.addWidget(self._right_tabs, stretch=2)

        # Histograms — one per key metric.
        self._hist_fwhm = HistogramWidget()
        self._hist_stars = HistogramWidget()
        self._hist_sky = HistogramWidget()
        self._hist_ecc = HistogramWidget()
        for h in (self._hist_fwhm, self._hist_stars, self._hist_sky, self._hist_ecc):
            right_layout.addWidget(h, stretch=1)

        # Action bar above the table. Each button gets a small unicode glyph
        # so the visual scan from left-to-right reads like a pipeline:
        # add → measure → solve → stack. The Stack button is styled as the
        # primary action (warm accent) so it visually pops once it's enabled.
        action_bar = QWidget()
        bar_layout = QHBoxLayout(action_bar)
        bar_layout.setContentsMargins(4, 4, 4, 4)
        bar_layout.setSpacing(6)
        self._btn_ingest = QPushButton("  ＋  Add frames…")
        self._btn_ingest.setToolTip(
            "Add Seestar .fit raws to this project. Files are copied into the local "
            "Stage 1 cache so the rest of the pipeline reads from local disk, not the NAS."
        )
        self._btn_ingest.clicked.connect(self._on_ingest)
        self._btn_ingest.setEnabled(False)

        self._btn_qc = QPushButton("  ✓  Run QC")
        self._btn_qc.setToolTip(
            "Compute per-frame quality metrics: FWHM, star count, sky background, "
            "eccentricity, and streak detection. Hover any column header for details."
        )
        self._btn_qc.clicked.connect(self._on_run_qc)
        self._btn_qc.setEnabled(False)

        self._btn_solve = QPushButton("  ⊕  Plate solve")
        self._btn_solve.setToolTip(
            "Run ASTAP on every unsolved frame to determine its WCS (the precise sky "
            "coordinates of every pixel). Required before alignment, mosaic stitching, "
            "and photometric color calibration. Already-solved frames are skipped."
        )
        self._btn_solve.clicked.connect(self._on_run_solve)
        self._btn_solve.setEnabled(False)

        self._btn_stack = QPushButton("  ★  Stack…")
        self._btn_stack.setToolTip(
            "Combine all accepted, plate-solved frames into a single output image. "
            "Picks a reference frame automatically, aligns every other frame to it, "
            "rejects outlier pixels (satellite trails, etc.), and writes the result "
            "as 32-bit FITS plus a stretched TIFF preview."
        )
        self._btn_stack.clicked.connect(self._on_run_stack)
        self._btn_stack.setEnabled(False)
        # Style as primary action — picks up the warm accent in theme.py.
        self._btn_stack.setProperty("primary", True)

        self._btn_cancel = QPushButton("  ✕  Cancel")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_cancel_job)
        self._btn_cancel.setProperty("danger", True)

        bar_layout.addWidget(self._btn_ingest)
        bar_layout.addWidget(self._btn_qc)
        bar_layout.addWidget(self._btn_solve)
        bar_layout.addWidget(self._btn_stack)
        bar_layout.addWidget(self._btn_cancel)
        bar_layout.addStretch(1)
        self._show_rejected = QCheckBox("Show rejected")
        self._show_rejected.setChecked(True)
        self._show_rejected.setToolTip(
            "When off, hides frames marked as rejected (greyed-out rows). "
            "Right-click any frame to manually accept / reject / restore."
        )
        self._show_rejected.toggled.connect(self._table.set_show_rejected)
        bar_layout.addWidget(self._show_rejected)

        # Restore / reject from context menu.
        self._table.restoreRequested.connect(self._on_restore_frame)
        self._table.rejectRequested.connect(self._on_reject_frame)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addWidget(action_bar)
        left_layout.addWidget(self._table)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Central widget is a stack: page 0 = welcome screen (shown when no
        # project is open), page 1 = the working splitter. We swap pages in
        # ``_set_project`` and the new/open-project handlers.
        self._central_stack = QStackedWidget()
        self._welcome = self._build_welcome_page()
        self._central_stack.addWidget(self._welcome)
        self._central_stack.addWidget(splitter)
        self._central_stack.setCurrentIndex(0)
        self.setCentralWidget(self._central_stack)

        # Status bar — each chip uses an icon-glyph so the eye can scan the
        # status of the three things you actually care about (compute, plate
        # solver, project) at a glance.
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)
        self._status_device = QLabel(f"⚙ {device_summary()}")
        self._status_device.setToolTip(
            "Compute backend used for the stack hot loops.\n"
            "GPU acceleration requires CuPy on an NVIDIA card.\n"
            "Install with: pip install cupy-cuda12x"
        )
        self._status_astap = QLabel(self._astap_status_text())
        self._status_project = QLabel("◌  no project")
        self._status_project.setProperty("role", "muted")
        self._status_progress = QProgressBar()
        self._status_progress.setMaximumWidth(220)
        self._status_progress.setVisible(False)
        sb.addPermanentWidget(self._status_device)
        sb.addPermanentWidget(QLabel(" · "))
        sb.addPermanentWidget(self._status_astap)
        sb.addPermanentWidget(QLabel(" · "))
        sb.addPermanentWidget(self._status_project)
        sb.addPermanentWidget(self._status_progress)

    def _build_menus(self) -> None:
        m = self.menuBar()
        file_menu = m.addMenu("&File")

        new_act = QAction("&New project…", self)
        new_act.triggered.connect(self._on_new_project)
        new_act.setShortcut("Ctrl+N")
        file_menu.addAction(new_act)

        open_act = QAction("&Open project…", self)
        open_act.triggered.connect(self._on_open_project)
        open_act.setShortcut("Ctrl+O")
        file_menu.addAction(open_act)

        file_menu.addSeparator()

        plan_act = QAction("&Plan && batch run…", self)
        plan_act.setShortcut("Ctrl+B")
        plan_act.setToolTip(
            "Set up an ingest → QC → solve → stack pipeline and run it as a "
            "single unattended job, or save the plan for later."
        )
        plan_act.triggered.connect(self._on_run_plan_dialog)
        file_menu.addAction(plan_act)

        load_plan_act = QAction("&Load and run plan…", self)
        load_plan_act.triggered.connect(self._on_load_run_plan)
        file_menu.addAction(load_plan_act)

        file_menu.addSeparator()

        quit_act = QAction("&Quit", self)
        quit_act.triggered.connect(self.close)
        quit_act.setShortcut("Ctrl+Q")
        file_menu.addAction(quit_act)

        # ---- Library menu --------------------------------------------
        # The library lets you scan a folder of Seestar sub-folders into many
        # target sub-projects, QC + solve them, and view all-sky campaign
        # stats. Single-project mode (File → Open) still works.
        library_menu = m.addMenu("&Library")

        new_lib_act = QAction("New library…", self)
        new_lib_act.setToolTip(
            "Create a new library folder. Each target you image becomes a "
            "sub-project inside it; the library tracks campaign-wide stats."
        )
        new_lib_act.triggered.connect(self._on_new_library)
        library_menu.addAction(new_lib_act)

        open_lib_act = QAction("Open library…", self)
        open_lib_act.setToolTip(
            "Open an existing Seestack library folder. Adopts any bare "
            "target projects already inside the folder automatically."
        )
        open_lib_act.triggered.connect(self._on_open_library)
        library_menu.addAction(open_lib_act)

        library_menu.addSeparator()

        manage_lib_act = QAction("Manage library…", self)
        manage_lib_act.setShortcut("Ctrl+L")
        manage_lib_act.setToolTip(
            "Open the library manager: scan a folder into targets, review the "
            "target list, merge targets, and view the all-sky campaign map. "
            "Requires an open library."
        )
        manage_lib_act.triggered.connect(self._on_manage_library)
        library_menu.addAction(manage_lib_act)

        tools_menu = m.addMenu("&Tools")
        merge_act = QAction("&Merge other project into this one…", self)
        merge_act.setToolTip(
            "Pull frames from another Seestack project (typically a different "
            "night of the same target) into the currently open project. "
            "Frames already present are skipped. Cached files are copied."
        )
        merge_act.triggered.connect(self._on_merge_project)
        tools_menu.addAction(merge_act)

        identify_act = QAction("&Identify target (SIMBAD)…", self)
        identify_act.setToolTip(
            "Look up the project's median sky position in the SIMBAD catalog "
            "and suggest stacking settings based on the object type."
        )
        identify_act.triggered.connect(self._on_identify_target)
        tools_menu.addAction(identify_act)

        compare_act = QAction("&Compare two stacks…", self)
        compare_act.setToolTip(
            "Side-by-side viewer for two stack outputs (FITS or TIFF), at "
            "matched autostretch. Useful for validating settings changes."
        )
        compare_act.triggered.connect(self._on_compare_stacks)
        tools_menu.addAction(compare_act)

        settings_menu = m.addMenu("&Settings")
        astap_act = QAction("Set &ASTAP path…", self)
        astap_act.setToolTip(
            "Browse for astap.exe. Use this if Seestack can't auto-find your "
            "ASTAP install. The path is saved per-project."
        )
        astap_act.triggered.connect(self._on_set_astap_path)
        settings_menu.addAction(astap_act)

        help_menu = m.addMenu("&Help")
        glossary_act = QAction("&Glossary…", self)
        glossary_act.setShortcut("F1")
        glossary_act.setToolTip(
            "Open the term-by-term glossary. Every metric, option, and astro "
            "term in the GUI is explained in plain language."
        )
        glossary_act.triggered.connect(self._on_open_glossary)
        help_menu.addAction(glossary_act)
        help_menu.addSeparator()
        about_act = QAction("&About", self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

    # ---- welcome screen -----------------------------------------------

    def _build_welcome_page(self) -> QWidget:
        """Friendly first-launch panel with three big CTA cards. Shown
        whenever no project is open so the user always knows where to go
        next instead of staring at an empty splitter."""
        from seestack.gui.theme import (
            ACCENT, FG_PRIMARY, FG_SECONDARY, BG_PANEL, BG_DIVIDER,
        )

        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch(1)

        # Big title.
        title = QLabel(f"<span style='color:{ACCENT}'>★</span> Seestack")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 42px; font-weight: 600; color: {FG_PRIMARY};")
        outer.addWidget(title)

        subtitle = QLabel(f"Astrophotography stacker for the ZWO Seestar — and anything "
                          f"else that produces FITS frames")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {FG_SECONDARY}; font-size: 14px; "
                               f"padding-bottom: 24px;")
        outer.addWidget(subtitle)

        # Three cards.
        cards_row = QHBoxLayout()
        cards_row.setSpacing(18)
        cards_row.addStretch(1)

        def _card(glyph: str, title_text: str, body: str, action) -> QWidget:
            card = QFrame()
            card.setFixedSize(280, 180)
            card.setStyleSheet(
                f"QFrame {{"
                f"  background-color: {BG_PANEL};"
                f"  border: 1px solid {BG_DIVIDER};"
                f"  border-radius: 10px;"
                f"}}"
                f"QFrame:hover {{ border-color: {ACCENT}; }}"
            )
            v = QVBoxLayout(card)
            v.setContentsMargins(18, 18, 18, 18)
            g = QLabel(glyph)
            g.setStyleSheet(f"color: {ACCENT}; font-size: 32px; background: transparent;")
            v.addWidget(g)
            t = QLabel(title_text)
            t.setStyleSheet(f"color: {FG_PRIMARY}; font-size: 16px; "
                            f"font-weight: 600; background: transparent;")
            v.addWidget(t)
            b = QLabel(body)
            b.setWordWrap(True)
            b.setStyleSheet(f"color: {FG_SECONDARY}; font-size: 12px; "
                            f"background: transparent;")
            v.addWidget(b)
            v.addStretch(1)
            btn = QPushButton("Open →")
            btn.setProperty("primary", True)
            btn.clicked.connect(action)
            v.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft)
            return card

        cards_row.addWidget(_card(
            "🌌", "Library",
            "Scan a folder of Seestar sub-folders into many targets, QC and "
            "solve them all, then view the campaign all-sky map.",
            self._on_open_library,
        ))
        cards_row.addWidget(_card(
            "★", "New project",
            "Single-target workflow — pick a folder, ingest your raws, "
            "and stack.",
            self._on_new_project,
        ))
        cards_row.addWidget(_card(
            "▸", "Open project",
            "Re-open an existing Seestack project folder. All your QC "
            "and stack settings are preserved.",
            self._on_open_project,
        ))
        cards_row.addStretch(1)
        outer.addLayout(cards_row)

        outer.addSpacing(28)
        tip = QLabel(
            "💡 New to Seestack?  Try <b>Library → New library…</b>, then "
            "“Scan a folder” and point it at your Seestar save folder — every "
            "sub-folder becomes a target, QC'd and plate-solved automatically."
        )
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {FG_SECONDARY}; font-size: 12px;")
        outer.addWidget(tip)

        outer.addStretch(1)
        return page

    # ---- project ------------------------------------------------------

    def _set_project(self, project: Project) -> None:
        if self._project is not None:
            self._project.close()
        self._project = project
        self._cache = CacheManager(project.project_dir)
        self._cache.ensure_dirs()
        ensure_thumb_cache_current(project.project_dir)
        self._model.set_project(project)
        self._preview.set_project_dir(project.project_dir)
        self._history.set_project(project)
        self._btn_ingest.setEnabled(True)
        has_rows = self._model.rowCount() > 0
        self._btn_qc.setEnabled(has_rows)
        self._btn_solve.setEnabled(has_rows)
        self._btn_stack.setEnabled(self._has_solved_frames())
        self._update_window_title()
        self._refresh_histograms()
        self._refresh_footprints()
        self._refresh_astap_status()
        # Switch away from the welcome card.
        self._central_stack.setCurrentIndex(1)

    def _has_solved_frames(self) -> bool:
        if self._project is None:
            return False
        for f in self._model._rows:
            if f.accept and f.wcs_json:
                return True
        return False

    def _astap_path(self) -> Path | None:
        """Effective ASTAP path: project setting wins, otherwise auto-find."""
        if self._project is not None:
            user = self._project.get_meta("astap_path")
            if user:
                p = Path(user)
                if p.exists():
                    return p
        return find_astap()

    def _astap_status_text(self) -> str:
        p = self._astap_path()
        if p is None:
            return "⊘  ASTAP: not found"
        return f"⊕  ASTAP: {p.name}"

    def _refresh_astap_status(self) -> None:
        self._status_astap.setText(self._astap_status_text())
        self._status_astap.setToolTip(
            "Plate-solving works when ASTAP is installed.\n"
            "Install it from https://www.hnsky.org/astap.htm and either let "
            "Seestack auto-find it or set the path under Settings → Set ASTAP path…"
        )
        # The button is enabled if there are frames, regardless of ASTAP — so
        # the user can click it and get a clear message about installing/setting
        # the path. (Greyed-out buttons are mysterious; warn at click time.)
        if self._project is not None:
            self._btn_solve.setEnabled(self._model.rowCount() > 0)

    def _update_window_title(self) -> None:
        if self._project is None:
            self.setWindowTitle(f"Seestack {__version__}")
            self._status_project.setText("◌  no project")
            self._status_project.setProperty("role", "muted")
        else:
            name = self._project.get_meta("name") or self._project.project_dir.name
            target = self._project.get_meta("target_id")
            title_suffix = f"{name} — {target}" if target else name
            self.setWindowTitle(f"Seestack {__version__} — {title_suffix}")
            n_total = self._model.rowCount()
            n_accept = self._project.count(accepted_only=True)
            label = f"★  {name}  ·  {n_total} frames ({n_accept} accepted)"
            if target:
                label += f"  ·  {target}"
            self._status_project.setText(label)
            self._status_project.setProperty("role", None)
        # Re-polish so the role-change visual is applied immediately.
        self._status_project.style().unpolish(self._status_project)
        self._status_project.style().polish(self._status_project)

    # ---- file menu actions --------------------------------------------

    def _on_new_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose a folder for the new project"
        )
        if not directory:
            return
        directory = Path(directory)
        if (directory / "project.sqlite").exists():
            QMessageBox.warning(
                self, "Already a project",
                f"{directory} already contains a Seestack project. Use Open instead."
            )
            return
        name, ok = QInputDialog.getText(
            self, "Project name", "Name for this project:", text=directory.name
        )
        if not ok or not name.strip():
            return
        project = Project.create(directory, name=name.strip())
        self._set_project(project)

    def _on_open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open Seestack project folder")
        if not directory:
            return
        try:
            project = Project.open(Path(directory))
        except FileNotFoundError:
            QMessageBox.warning(
                self, "Not a project",
                f"{directory} doesn't contain a Seestack project. Use 'New project…' to create one."
            )
            return
        self._set_project(project)

    # ---- library --------------------------------------------------

    def _on_new_library(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Pick a folder for the new library")
        if not d:
            return
        try:
            from seestack.io.library import Library
            lib = Library.create(Path(d))
            lib.close()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not create library", str(exc))
            return
        self._library_root = Path(d)
        self._on_manage_library()

    def _on_open_library(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Open an existing library folder")
        if not d:
            return
        try:
            from seestack.io.library import Library
            lib = Library.open(Path(d))
            lib.close()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not open library", str(exc))
            return
        self._library_root = Path(d)
        self._on_manage_library()

    def _on_manage_library(self) -> None:
        if self._library_root is None:
            QMessageBox.information(
                self, "No library open",
                "Use Library → New library… or Open library… first.",
            )
            return
        try:
            from seestack.io.library import Library
            from seestack.gui.library_dialog import LibraryDialog
        except ImportError as exc:
            QMessageBox.warning(self, "Library unavailable", str(exc))
            return
        try:
            lib = Library.open(self._library_root)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not open library", str(exc))
            self._library_root = None
            return
        dlg = LibraryDialog(lib, parent=self)
        dlg.open_target_requested.connect(self._open_library_target)
        try:
            dlg.exec()
        finally:
            lib.close()
            # The dialog is parented to the main window, so Qt would keep it
            # (and its dead Library reference) alive until the app closes.
            # Schedule deletion so repeated opens don't accumulate dialogs.
            dlg.deleteLater()

    def _open_library_target(self, project_dir) -> None:
        """Called when the user double-clicks a target in the library
        manager — close the manager and load that target as the active
        project so they can run QC / stack / etc on it."""
        try:
            project = Project.open(Path(project_dir))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not open target", str(exc))
            return
        self._set_project(project)

    def _on_run_plan_dialog(self) -> None:
        # Pre-populate with the current project if one is open.
        initial = None
        if self._project is not None:
            from seestack.plan import IngestStep, Plan, QCStep, SolveStep, StackStep
            initial = Plan(
                project_dir=str(self._project.project_dir),
                project_name=self._project.get_meta("name") or "",
                ingest=IngestStep(enabled=False),
                qc=QCStep(enabled=True),
                solve=SolveStep(enabled=True),
                stack=StackStep(enabled=True),
            )
        editor = PlanEditor(self, plan=initial)
        if editor.exec() != editor.DialogCode.Accepted:
            return
        plan = editor.get_plan()
        if plan is None:
            return
        self._launch_plan(plan)

    def _on_load_run_plan(self) -> None:
        from seestack.plan import Plan
        path, _ = QFileDialog.getOpenFileName(
            self, "Load plan", "", "Seestack plan (*.seestackplan);;All files (*.*)",
        )
        if not path:
            return
        try:
            plan = Plan.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Could not load plan", str(exc))
            return
        self._launch_plan(plan)

    def _launch_plan(self, plan) -> None:
        # Close any currently-open project so the runner can take exclusive
        # SQLite access on its own thread.
        if self._project is not None:
            self._project.close()
            self._project = None
            self._model.set_project(None)
        runner = PlanRunner(self, plan)
        runner.exec()
        result = runner.get_result()
        failure = runner.get_failure()
        if failure:
            QMessageBox.critical(self, "Plan failed", failure)
        elif result is not None:
            steps = ", ".join(result.steps_run) or "(no steps run)"
            text = f"<b>Plan finished.</b><br>Steps run: {steps}."
            if result.stack_result is not None:
                sr = result.stack_result
                text += (
                    f"<br>Stack: {sr.n_frames_used} frames into "
                    f"{sr.canvas_shape[1]}×{sr.canvas_shape[0]}."
                )
            if result.errors:
                text += f"<br><i>{len(result.errors)} errors — see log for details.</i>"
            notify_user(
                "Plan complete",
                f"Steps: {steps}",
                success=not result.errors,
            )
            QMessageBox.information(self, "Plan complete", text)
        # Re-open the project (the runner closed its own copy).
        from seestack.io.project import Project
        try:
            self._set_project(Project.open(Path(plan.project_dir)))
        except Exception as exc:  # noqa: BLE001
            log.warning("could not re-open project after plan: %s", exc)

    def _on_restore_frame(self, frame_id: int) -> None:
        if self._project is None:
            return
        self._project.update_frame(
            frame_id, accept=True, reject_reason=None, user_override=True,
        )
        self._model.update_frame(
            frame_id, accept=True, reject_reason=None, user_override=True,
        )
        self._update_window_title()

    def _on_reject_frame(self, frame_id: int) -> None:
        if self._project is None:
            return
        self._project.update_frame(
            frame_id, accept=False, reject_reason="user", user_override=True,
        )
        self._model.update_frame(
            frame_id, accept=False, reject_reason="user", user_override=True,
        )
        self._update_window_title()

    def _on_open_glossary(self) -> None:
        GlossaryDialog(self).exec()

    def _on_compare_stacks(self) -> None:
        from seestack.gui.compare_dialog import CompareDialog
        dlg = CompareDialog(self)
        dlg.exec()

    def _on_merge_project(self) -> None:
        if self._project is None:
            QMessageBox.information(
                self, "Open a project first",
                "Open the destination project before merging another into it.",
            )
            return
        source_dir = QFileDialog.getExistingDirectory(
            self, "Choose source project to merge from",
        )
        if not source_dir:
            return
        if not (Path(source_dir) / "project.sqlite").exists():
            QMessageBox.warning(
                self, "Not a Seestack project",
                f"{source_dir} doesn't contain a project.sqlite file.",
            )
            return
        from seestack.io.merge import merge_projects

        added_total = dup_total = missing_total = 0
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
        try:
            for result in merge_projects(self._project, [source_dir]):
                added_total += result.n_added
                dup_total += result.n_skipped_duplicate
                missing_total += result.n_skipped_missing_file
        finally:
            QApplication.restoreOverrideCursor()

        # Reload the model so the merged frames show up.
        self._model.set_project(self._project)
        self._refresh_histograms()
        self._refresh_footprints()
        self._update_window_title()
        QMessageBox.information(
            self, "Merge complete",
            f"<b>{added_total}</b> frames added.<br>"
            f"{dup_total} duplicates skipped.<br>"
            f"{missing_total} frames lacked a cached copy.",
        )

    def _on_identify_target(self) -> None:
        if self._project is None:
            return
        # Median RA/Dec across solved frames.
        ras = []
        decs = []
        for f in self._project.iter_frames(accepted_only=True):
            if f.ra_center_deg is not None and f.dec_center_deg is not None:
                ras.append(f.ra_center_deg)
                decs.append(f.dec_center_deg)
        if not ras:
            QMessageBox.information(
                self, "No plate-solved frames",
                "Run Plate Solve first — target identification needs the "
                "sky coordinates of your frames.",
            )
            return
        ras.sort()
        decs.sort()
        ra_med = ras[len(ras) // 2]
        dec_med = decs[len(decs) // 2]
        # Lookup might take a few seconds — show a wait cursor.
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
        try:
            from seestack.post.target_id import identify_target

            result = identify_target(ra_med, dec_med)
        finally:
            QApplication.restoreOverrideCursor()

        if result.error:
            QMessageBox.warning(
                self, "Lookup failed",
                f"Could not identify target.\n\n{result.error}\n\n"
                "Make sure astroquery is installed (pip install astroquery) "
                "and you have internet access.",
            )
            return
        title = result.identifier or "(no name)"
        otype = result.object_type_name or result.object_type or "(unknown type)"
        body = f"<b>{title}</b> — {otype}"
        if result.bg_mode_hint:
            body += (
                f"<br><br><b>Suggested bg-flatten mode:</b> "
                f"<code>{result.bg_mode_hint}</code><br>"
                f"<i>{result.hint_reason}</i><br><br>"
                "Use this in the Stack dialog → Sky gradient removal dropdown."
            )
        QMessageBox.information(self, "Target identified", body)
        # Stash the hint in project_meta so the stack dialog can pre-select it.
        if result.bg_mode_hint:
            self._project.set_meta("suggested_bg_mode", result.bg_mode_hint)
        if result.identifier:
            self._project.set_meta("target_id", result.identifier)
        self._update_window_title()

    def _on_load_history_settings(self, opts) -> None:
        """User picked 'Load these settings' from the History panel."""
        if self._project is None:
            return
        n = sum(1 for f in self._model._rows if f.accept and f.wcs_json)
        dlg = StackOptionsDialog(self, n_frames=n)
        dlg._apply_options(opts)  # protected access on purpose
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        # Reuse existing run-stack flow by stashing the dialog's options.
        self._stack_thread = _StackThread(self._project.project_dir, dlg.options(), self)
        self._stack_thread.progress.connect(self._on_stack_progress)
        self._stack_thread.finished_with.connect(self._on_stack_finished)
        self._stack_thread.failed.connect(self._on_stack_failed)
        self._btn_qc.setEnabled(False)
        self._btn_solve.setEnabled(False)
        self._btn_stack.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._status_progress.setVisible(True)
        self._stack_thread.start()

    # ---- drag-and-drop folder ingest ---------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Accept a folder drop only if a project is open and the drop is a directory."""
        md = event.mimeData()
        if self._project is None or not md.hasUrls():
            return
        for url in md.urls():
            if url.isLocalFile() and Path(url.toLocalFile()).is_dir():
                event.acceptProposedAction()
                return

    def dropEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._project is None or self._cache is None:
            return
        md = event.mimeData()
        if not md.hasUrls():
            return
        # Take the first dropped directory.
        for url in md.urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if p.is_dir():
                event.acceptProposedAction()
                self._ingest_directory(p)
                return

    def _ingest_directory(self, directory: Path) -> None:
        """Run ingest on the given directory (shared by drag-drop + button)."""
        from seestack.io.ingest import find_fits_files, ingest_files
        files = find_fits_files(directory)
        if not files:
            QMessageBox.information(self, "No FITS files",
                                    f"No .fit / .fits files found in {directory}.")
            return
        self._status_progress.setRange(0, len(files))
        self._status_progress.setValue(0)
        self._status_progress.setVisible(True)
        added = 0
        for i, result in enumerate(ingest_files(self._project, self._cache, files)):
            self._status_progress.setValue(i + 1)
            if result.frame_id is not None:
                row = self._project.get_frame(result.frame_id)
                if row is not None:
                    self._model.add_frame(row)
                    added += 1
            if (i + 1) % 50 == 0:
                self._status_progress.repaint()
        self._status_progress.setVisible(False)
        self._update_window_title()
        self._refresh_histograms()
        self._refresh_footprints()
        has_rows = self._model.rowCount() > 0
        self._btn_qc.setEnabled(has_rows)
        self._btn_solve.setEnabled(has_rows)
        self._btn_stack.setEnabled(self._has_solved_frames())
        QMessageBox.information(
            self, "Ingest complete",
            f"Added {added} new frames from {directory}."
        )

    def _on_about(self) -> None:
        from seestack.gui.theme import ACCENT, FG_SECONDARY
        QMessageBox.about(
            self, "About Seestack",
            f"<h2 style='color:{ACCENT}'>★ Seestack {__version__}</h2>"
            "<p>An astrophotography stacker built for the ZWO Seestar — and "
            "anything else that produces FITS frames.</p>"
            f"<p style='color:{FG_SECONDARY}'>Compute backend: "
            f"<b>{device_summary()}</b></p>"
            f"<p style='color:{FG_SECONDARY}'>"
            "Built with astropy, photutils, PySide6, numpy, scipy. "
            "Optional GPU acceleration via CuPy."
            "</p>"
        )

    def _on_set_astap_path(self) -> None:
        """Let the user browse for astap.exe and store the path in the project."""
        if self._project is None:
            QMessageBox.information(
                self, "Open a project first",
                "Open or create a Seestack project before setting the ASTAP path."
            )
            return
        current = self._project.get_meta("astap_path") or ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Locate astap.exe",
            current or "C:/Program Files/astap",
            "ASTAP executable (astap.exe);;All files (*.*)",
        )
        if not path:
            return
        p = Path(path)
        if not p.exists():
            QMessageBox.warning(self, "Not found", f"{p} does not exist.")
            return
        self._project.set_meta("astap_path", str(p))
        self._refresh_astap_status()
        QMessageBox.information(
            self, "ASTAP set",
            f"ASTAP path saved: {p}\n\nYou can now use Plate Solve."
        )

    # ---- ingest -------------------------------------------------------

    def _on_ingest(self) -> None:
        if self._project is None or self._cache is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self, "Choose a folder of Seestar .fit raws to add"
        )
        if not directory:
            return
        # Reuse the drag-drop path so behaviour is identical.
        self._ingest_directory(Path(directory))

    # ---- QC -----------------------------------------------------------

    def _on_run_qc(self) -> None:
        if self._project is None:
            return
        args = build_qc_arglist(self._project)
        if not args:
            QMessageBox.information(self, "Nothing to do", "No frames have a readable file path.")
            return

        self._qc_runner = JobRunner(parent=self)
        self._qc_runner.progress.connect(self._on_qc_progress)
        self._qc_runner.result.connect(self._on_qc_result)
        self._qc_runner.finished.connect(self._on_qc_finished)
        self._btn_qc.setEnabled(False)
        self._btn_solve.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._status_progress.setRange(0, len(args))
        self._status_progress.setValue(0)
        self._status_progress.setVisible(True)
        self._qc_runner.run(compute_for_db_row, args)

    def _on_cancel_job(self) -> None:
        if self._qc_runner is not None:
            self._qc_runner.cancel()
        if self._solve_runner is not None:
            self._solve_runner.cancel()
        if self._stack_thread is not None:
            self._stack_thread.request_cancel()

    def _on_qc_progress(self, done: int, total: int) -> None:
        self._status_progress.setRange(0, total)
        self._status_progress.setValue(done)

    def _on_qc_result(self, jr: JobResult) -> None:
        if self._project is None:
            return
        if jr.error is not None or not isinstance(jr.value, QCResult):
            return
        result: QCResult = jr.value
        apply_qc_result_to_db(self._project, result)
        # Patch the in-memory model row.
        if result.metrics is not None:
            m = result.metrics
            self._model.update_frame(
                result.frame_id,
                fwhm_px=m.fwhm_px,
                star_count=m.star_count,
                sky_adu_median=m.sky_adu_median,
                eccentricity_median=m.eccentricity_median,
                streak_detected=m.streak_detected,
                streak_count=m.streak_count,
            )

    def _on_qc_finished(self) -> None:
        self._status_progress.setVisible(False)
        self._btn_qc.setEnabled(True)
        self._btn_solve.setEnabled(self._model.rowCount() > 0)
        self._btn_cancel.setEnabled(False)
        self._qc_runner = None
        self._refresh_histograms()
        self._update_window_title()

    # ---- Plate solve --------------------------------------------------

    def _on_run_solve(self) -> None:
        if self._project is None:
            return
        astap = self._astap_path()
        if astap is None:
            ret = QMessageBox.warning(
                self, "ASTAP not found",
                "<p>Plate solving requires <b>ASTAP</b>, a free local tool.</p>"
                "<ol>"
                "<li>Download ASTAP from "
                "<a href='https://www.hnsky.org/astap.htm'>hnsky.org/astap.htm</a> "
                "and install it.</li>"
                "<li>Also grab one of the star databases from the same page "
                "(H17 is the smallest and works fine for the Seestar).</li>"
                "<li>Click <b>OK</b> and use <i>Settings → Set ASTAP path…</i> "
                "to point Seestack at your <code>astap.exe</code>.</li>"
                "</ol>"
                "<p>Already installed? Try setting the path manually — Seestack "
                "auto-finds ASTAP only in standard install locations.</p>",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if ret == QMessageBox.StandardButton.Ok:
                self._on_set_astap_path()
            return
        # Make the project-stored path visible to the solve runner.
        self._project.set_meta("astap_path", str(astap))

        args = build_solve_arglist(self._project)
        if not args:
            QMessageBox.information(
                self, "Nothing to solve",
                "All frames are already plate-solved. Delete WCS data to redo any."
            )
            return

        self._solve_runner = JobRunner(parent=self)
        self._solve_runner.progress.connect(self._on_solve_progress)
        self._solve_runner.result.connect(self._on_solve_result)
        self._solve_runner.finished.connect(self._on_solve_finished)
        self._btn_qc.setEnabled(False)
        self._btn_solve.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._status_progress.setRange(0, len(args))
        self._status_progress.setValue(0)
        self._status_progress.setVisible(True)
        self._solve_runner.run(solve_one, args)

    def _on_solve_progress(self, done: int, total: int) -> None:
        self._status_progress.setRange(0, total)
        self._status_progress.setValue(done)

    def _on_solve_result(self, jr: JobResult) -> None:
        if self._project is None:
            return
        if jr.error is not None or not isinstance(jr.value, SolveResult):
            return
        result: SolveResult = jr.value
        apply_solve_result_to_db(self._project, result)
        # Patch in-memory row so the footprint view picks it up.
        self._model.update_frame(
            result.frame_id,
            wcs_json=result.wcs_text,
            ra_center_deg=result.ra_center_deg,
            dec_center_deg=result.dec_center_deg,
            pixscale_arcsec=result.pixscale_arcsec,
            rotation_deg=result.rotation_deg,
            reject_reason=None if result.solved else f"solve_failed:{(result.error or '')[:80]}",
        )

    def _on_solve_finished(self) -> None:
        self._status_progress.setVisible(False)
        self._btn_qc.setEnabled(True)
        self._btn_solve.setEnabled(self._model.rowCount() > 0)
        self._btn_stack.setEnabled(self._has_solved_frames())
        self._btn_cancel.setEnabled(False)
        self._solve_runner = None
        self._refresh_footprints()
        self._refresh_astap_status()
        self._update_window_title()

    # ---- Stack -------------------------------------------------------

    def _on_run_stack(self) -> None:
        if self._project is None:
            return
        n = sum(1 for f in self._model._rows if f.accept and f.wcs_json)
        if n < 2:
            QMessageBox.information(
                self, "Not enough frames",
                "Need at least 2 accepted, plate-solved frames to stack."
            )
            return
        dlg = StackOptionsDialog(self, n_frames=n)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        options = dlg.options()
        # The stack worker thread opens its own DB connection — SQLite handles
        # are tied to the thread that created them.
        self._stack_thread = _StackThread(self._project.project_dir, options, self)
        self._stack_thread.progress.connect(self._on_stack_progress)
        self._stack_thread.finished_with.connect(self._on_stack_finished)
        self._stack_thread.failed.connect(self._on_stack_failed)
        self._btn_qc.setEnabled(False)
        self._btn_solve.setEnabled(False)
        self._btn_stack.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._status_progress.setRange(0, 1)
        self._status_progress.setValue(0)
        self._status_progress.setVisible(True)
        self._stack_thread.start()

    def _on_stack_progress(self, phase: str, done: int, total: int) -> None:
        self._status_progress.setRange(0, max(total, 1))
        self._status_progress.setValue(done)
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(f"{phase}: {done}/{total}", 0)

    def _on_stack_finished(self, result: object) -> None:
        # Qt signal can't carry arbitrary types; we cast back.
        result_obj: StackResult = result  # type: ignore[assignment]
        self._stack_post_run()
        # Refresh history panel so the new run appears.
        self._history.reload()
        if result_obj.cancelled:
            QMessageBox.information(self, "Stack cancelled", "Stacking was cancelled.")
            return
        # System notification — useful for unattended runs.
        notify_user(
            "Stack complete",
            f"{result_obj.n_frames_used} frames → "
            f"{result_obj.canvas_shape[1]}×{result_obj.canvas_shape[0]} canvas",
        )
        msg = (
            f"<h3>Stack complete</h3>"
            f"<p>{result_obj.n_frames_used} frames combined into a "
            f"{result_obj.canvas_shape[1]}×{result_obj.canvas_shape[0]} canvas.</p>"
            f"<p>Coverage: {result_obj.coverage_min}–{result_obj.coverage_max} frames per pixel.</p>"
            f"<p><b>Files:</b><br>"
            f"{result_obj.fits_path.name} (32-bit data)<br>"
            f"{result_obj.tiff_path.name} (16-bit autostretched)<br>"
            f"{result_obj.preview_path.name} (preview)</p>"
        )
        if result_obj.errors:
            msg += f"<p><i>{len(result_obj.errors)} frames had errors during alignment.</i></p>"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Stack complete")
        box.setText(msg)
        open_btn = box.addButton("Open output folder", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(result_obj.output_dir)))

    def _on_stack_failed(self, message: str) -> None:
        self._stack_post_run()
        notify_user("Stack failed", message, success=False)
        QMessageBox.critical(self, "Stack failed", message)

    def _stack_post_run(self) -> None:
        self._status_progress.setVisible(False)
        self._btn_qc.setEnabled(True)
        self._btn_solve.setEnabled(self._model.rowCount() > 0)
        self._btn_stack.setEnabled(self._has_solved_frames())
        self._btn_cancel.setEnabled(False)
        self._stack_thread = None
        sb = self.statusBar()
        if sb is not None:
            sb.clearMessage()

    # ---- selection / preview -----------------------------------------

    def _on_selection_changed(self, *_args) -> None:
        proxy = self._table.model()  # QSortFilterProxyModel
        idxs = self._table.selectionModel().selectedRows()
        if not idxs or proxy is None:
            self._preview.clear()
            self._footprints.set_selected(None)
            return
        src_idx = proxy.mapToSource(idxs[0])
        row = src_idx.row()
        if 0 <= row < len(self._model._rows):
            frame = self._model._rows[row]
            self._preview.show_frame(frame)
            self._footprints.set_selected(frame.id)

    def _on_footprint_clicked(self, frame_id: int) -> None:
        """User clicked a footprint — select that frame in the table."""
        proxy = self._table.model()
        if proxy is None:
            return
        # Find the source row for this id.
        src_row = self._model._row_index.get(frame_id)
        if src_row is None:
            return
        proxy_idx = proxy.mapFromSource(self._model.index(src_row, 0))
        self._table.selectRow(proxy_idx.row())
        self._table.scrollTo(proxy_idx)

    # ---- histograms --------------------------------------------------

    def _refresh_histograms(self) -> None:
        rows = self._model._rows
        self._hist_fwhm.set_data(
            [r.fwhm_px for r in rows if r.fwhm_px is not None],
            title="FWHM", unit="px",
        )
        self._hist_stars.set_data(
            [r.star_count for r in rows if r.star_count is not None],
            title="Star count",
        )
        self._hist_sky.set_data(
            [r.sky_adu_median for r in rows if r.sky_adu_median is not None],
            title="Sky background", unit="ADU",
        )
        self._hist_ecc.set_data(
            [r.eccentricity_median for r in rows if r.eccentricity_median is not None],
            title="Eccentricity",
        )

    # ---- footprints --------------------------------------------------

    def _refresh_footprints(self) -> None:
        """Rebuild the footprint view from the current set of solved frames."""
        rows = self._model._rows
        fps: list[Footprint] = []
        for r in rows:
            if not r.wcs_json or r.width_px is None or r.height_px is None:
                continue
            wcs = wcs_from_text(r.wcs_json)
            corners = footprint_radec_deg(wcs, r.width_px, r.height_px)
            if not corners:
                continue
            fps.append(Footprint(
                frame_id=r.id or -1,
                corners_radec_deg=corners,
                accepted=r.accept,
            ))
        self._footprints.set_footprints(fps)

    # ---- shutdown ----------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._qc_runner is not None:
            self._qc_runner.cancel()
        if self._solve_runner is not None:
            self._solve_runner.cancel()
        if self._stack_thread is not None and self._stack_thread.isRunning():
            self._stack_thread.request_cancel()
            self._stack_thread.wait(5000)
        # Let in-flight thumbnail workers finish so they aren't GC'd mid-run.
        self._preview.shutdown()
        if self._project is not None:
            self._project.close()
        super().closeEvent(event)


class _StackThread(QThread):
    """
    Background thread that runs ``stack.run_stack`` and emits Qt signals.

    Opens its own ``Project`` on this thread because SQLite connections can't
    be shared across threads — the GUI thread keeps its own handle, this
    worker uses a separate one.
    """

    progress = Signal(str, int, int)
    finished_with = Signal(object)  # StackResult
    failed = Signal(str)

    def __init__(self, project_dir: Path, options: StackOptions, parent=None) -> None:
        super().__init__(parent)
        self._project_dir = project_dir
        self._options = options
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            project = Project.open(self._project_dir)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"could not open project: {exc}")
            return
        try:
            result = run_stack(
                project,
                self._options,
                progress=lambda phase, done, total: self.progress.emit(phase, done, total),
                cancel=lambda: self._cancel_requested,
            )
            self.finished_with.emit(result)
        except Exception as exc:  # noqa: BLE001
            log.exception("stack failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            project.close()
