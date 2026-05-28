"""
Glossary viewer.

A simple read-only panel that renders ``docs/glossary.md`` (which lives next
to the source tree). Used from the Help menu as the one-stop reference for
every term used in the GUI.

Markdown is rendered via Qt's built-in ``setMarkdown`` — no extra dependency.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QTextBrowser,
    QVBoxLayout,
)


def find_glossary_path() -> Path | None:
    """Return the path to docs/glossary.md if we can find it; else None."""
    # Source layout: <root>/docs/glossary.md, this file at <root>/seestack/gui/.
    here = Path(__file__).resolve()
    for candidate in (
        here.parent.parent.parent / "docs" / "glossary.md",
        here.parent.parent / "docs" / "glossary.md",
    ):
        if candidate.exists():
            return candidate
    return None


class GlossaryDialog(QDialog):
    """Display the glossary with a simple text search."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Seestack glossary")
        self.resize(720, 640)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "<i>Every term used in the Seestack interface, with plain-language "
            "explanations. Use the search box to jump to a term.</i>"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Find… (e.g. drizzle, FWHM, sigma clipping)")
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        self._text = QTextBrowser()
        self._text.setOpenExternalLinks(True)
        self._text.setFont(QFont("Segoe UI"))
        layout.addWidget(self._text)

        path = find_glossary_path()
        if path is None:
            self._text.setMarkdown(
                "# Glossary unavailable\n\n"
                "Couldn't find `docs/glossary.md` next to the Seestack install.\n\n"
                "If you installed from source, this file should be in the "
                "repository root. Check that the docs folder hasn't been moved."
            )
        else:
            try:
                self._text.setMarkdown(path.read_text(encoding="utf-8"))
            except OSError as exc:
                self._text.setMarkdown(f"# Could not load glossary\n\n`{exc}`")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _on_search(self, text: str) -> None:
        if not text:
            # Reset cursor to the top.
            cursor = self._text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self._text.setTextCursor(cursor)
            return
        # Qt's find() moves forward from the current cursor; fall back to a
        # second find from the start if it returns False.
        if not self._text.find(text):
            cursor = self._text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self._text.setTextCursor(cursor)
            self._text.find(text)
