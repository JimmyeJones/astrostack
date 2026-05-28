"""
Plan wizard dialog.

A short, single-pane dialog (no multi-step wizard — too clicky for what's
really just "tick what you want and pick options"). Lets the user:

  - choose / create a project directory
  - tick which steps to run (ingest / QC / solve / stack)
  - drill into stack options via the existing ``StackOptionsDialog``
  - save the plan to disk or run it immediately

The runner uses a worker ``QThread`` so the GUI stays responsive while a
plan is executing (often hours for big projects).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from seestack.gui.stack_dialog import StackOptionsDialog
from seestack.plan import (
    IngestStep,
    Plan,
    PlanProgress,
    PlanResult,
    QCStep,
    SolveStep,
    StackStep,
    run_plan,
)
from seestack.stack.stacker import StackOptions

log = logging.getLogger(__name__)


class PlanEditor(QDialog):
    """Build / edit a plan, then save it or hit Run."""

    def __init__(self, parent=None, plan: Plan | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plan & batch run")
        self.setMinimumWidth(560)

        self._plan = plan or Plan(project_dir="")
        # Stash full StackOptions separately so the user's tweaks persist
        # across "Edit stack settings…" trips.
        self._stack_options: StackOptions = self._plan.stack.options

        layout = QVBoxLayout(self)
        intro = QLabel(
            "<p>Build a plan: tick the steps to run, pick options, then "
            "<b>Run now</b> or <b>Save plan</b> for later.</p>"
            "<p>Plans are JSON files (<code>*.seestackplan</code>). Save one "
            "for a target you stack regularly and re-run it on each session's "
            "new frames.</p>"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()

        # Project
        proj_row = QHBoxLayout()
        self._proj_dir = QLineEdit(self._plan.project_dir)
        self._proj_dir.setPlaceholderText("Pick or create a project folder…")
        proj_browse = QPushButton("Browse…")
        proj_browse.clicked.connect(self._pick_project_dir)
        proj_row.addWidget(self._proj_dir)
        proj_row.addWidget(proj_browse)
        form.addRow("Project folder:", proj_row)

        # Ingest
        self._ingest_enabled = QCheckBox("Ingest raw frames")
        self._ingest_enabled.setChecked(self._plan.ingest.enabled)
        form.addRow("", self._ingest_enabled)

        ingest_row = QHBoxLayout()
        self._ingest_src = QLineEdit(self._plan.ingest.source_dir)
        self._ingest_src.setPlaceholderText("Folder of Seestar .fit raws to ingest…")
        ingest_browse = QPushButton("Browse…")
        ingest_browse.clicked.connect(self._pick_ingest_dir)
        ingest_row.addWidget(self._ingest_src)
        ingest_row.addWidget(ingest_browse)
        form.addRow("Source folder:", ingest_row)

        # QC
        self._qc_enabled = QCheckBox("Run quality-control pass")
        self._qc_enabled.setChecked(self._plan.qc.enabled)
        self._qc_enabled.setToolTip(
            "Compute per-frame metrics (FWHM, star count, streak detection) "
            "and auto-reject streaked frames."
        )
        form.addRow("", self._qc_enabled)

        # Solve
        self._solve_enabled = QCheckBox("Run plate solving (ASTAP)")
        self._solve_enabled.setChecked(self._plan.solve.enabled)
        form.addRow("", self._solve_enabled)

        # Stack
        self._stack_enabled = QCheckBox("Stack")
        self._stack_enabled.setChecked(self._plan.stack.enabled)
        form.addRow("", self._stack_enabled)

        stack_btn = QPushButton("Edit stack settings…")
        stack_btn.clicked.connect(self._edit_stack_options)
        form.addRow("", stack_btn)

        layout.addLayout(form)

        # Buttons
        self._buttons = QDialogButtonBox()
        self._save_btn = self._buttons.addButton("Save plan…", QDialogButtonBox.ButtonRole.ActionRole)
        self._run_btn = self._buttons.addButton("Run now", QDialogButtonBox.ButtonRole.AcceptRole)
        self._cancel_btn = self._buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._save_btn.clicked.connect(self._on_save)
        self._run_btn.clicked.connect(self._on_run)
        self._cancel_btn.clicked.connect(self.reject)
        layout.addWidget(self._buttons)

    # ---- helpers -----------------------------------------------------

    def _pick_project_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose project folder")
        if d:
            self._proj_dir.setText(d)

    def _pick_ingest_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose raw-frame folder")
        if d:
            self._ingest_src.setText(d)

    def _edit_stack_options(self) -> None:
        dlg = StackOptionsDialog(self, n_frames=0)
        # TODO: prepopulate from self._stack_options once StackOptionsDialog supports it.
        if dlg.exec() == dlg.DialogCode.Accepted:
            self._stack_options = dlg.options()

    def _collect_plan(self) -> Plan | None:
        project_dir = self._proj_dir.text().strip()
        if not project_dir:
            QMessageBox.warning(self, "Project folder needed", "Pick a project folder.")
            return None
        if self._ingest_enabled.isChecked() and not self._ingest_src.text().strip():
            QMessageBox.warning(self, "Ingest source needed",
                                "Ingest is enabled but no source folder is set.")
            return None
        return Plan(
            project_dir=project_dir,
            project_name=Path(project_dir).name,
            ingest=IngestStep(
                enabled=self._ingest_enabled.isChecked(),
                source_dir=self._ingest_src.text().strip(),
            ),
            qc=QCStep(enabled=self._qc_enabled.isChecked()),
            solve=SolveStep(enabled=self._solve_enabled.isChecked()),
            stack=StackStep(
                enabled=self._stack_enabled.isChecked(),
                options=self._stack_options,
            ),
        )

    # ---- actions -----------------------------------------------------

    def _on_save(self) -> None:
        plan = self._collect_plan()
        if plan is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save plan", "", "Seestack plan (*.seestackplan);;All files (*.*)",
        )
        if not path:
            return
        if not path.endswith(".seestackplan"):
            path += ".seestackplan"
        try:
            plan.save(path)
            QMessageBox.information(self, "Plan saved", f"Plan written to {path}.")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _on_run(self) -> None:
        plan = self._collect_plan()
        if plan is None:
            return
        # Pass the plan back via accepted()
        self.plan = plan
        self.accept()

    # ---- read result -------------------------------------------------

    def get_plan(self) -> Plan | None:
        return getattr(self, "plan", None)


class PlanRunner(QDialog):
    """Modal progress dialog that runs the plan in a worker thread."""

    def __init__(self, parent, plan: Plan) -> None:
        super().__init__(parent)
        self.setWindowTitle("Running plan…")
        self.setModal(True)
        self.resize(540, 220)
        self._plan = plan
        self._cancelled = False
        self._result: PlanResult | None = None
        self._failure: str | None = None

        layout = QVBoxLayout(self)
        self._step_label = QLabel("Starting…")
        self._step_label.setStyleSheet("font-weight:bold;")
        layout.addWidget(self._step_label)

        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        layout.addWidget(self._detail_label)

        self._sub_bar = QProgressBar()
        layout.addWidget(self._sub_bar)

        self._overall_bar = QProgressBar()
        layout.addWidget(QLabel("Overall progress:"))
        layout.addWidget(self._overall_bar)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._thread = _PlanThread(plan, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_with.connect(self._on_finished)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_progress(self, p: PlanProgress) -> None:
        self._step_label.setText(
            f"Step {p.step_index + 1}/{p.n_steps}: {p.step.title()}"
        )
        self._detail_label.setText(p.detail or "")
        self._sub_bar.setRange(0, max(p.sub_total, 1))
        self._sub_bar.setValue(p.sub_done)
        self._overall_bar.setRange(0, max(p.n_steps, 1))
        self._overall_bar.setValue(p.step_index)

    def _on_finished(self, result_obj: object) -> None:
        self._result = result_obj  # type: ignore[assignment]
        if self._cancelled or (self._result and self._result.cancelled):
            self.reject()
        else:
            self.accept()

    def _on_failed(self, msg: str) -> None:
        self._failure = msg
        self.reject()

    def _on_cancel(self) -> None:
        self._cancelled = True
        self._thread.request_cancel()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("Cancelling…")

    def get_result(self) -> PlanResult | None:
        return self._result

    def get_failure(self) -> str | None:
        return self._failure


class _PlanThread(QThread):
    progress = Signal(object)  # PlanProgress
    finished_with = Signal(object)  # PlanResult
    failed = Signal(str)

    def __init__(self, plan: Plan, parent=None) -> None:
        super().__init__(parent)
        self._plan = plan
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = run_plan(
                self._plan,
                progress=lambda p: self.progress.emit(p),
                cancel=lambda: self._cancel,
            )
            self.finished_with.emit(result)
        except Exception as exc:  # noqa: BLE001
            log.exception("Plan execution failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}")
