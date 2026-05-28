"""
Seestack visual theme.

A single source of truth for colours, spacing, and the application-wide Qt
stylesheet. Importing this module is cheap (no Qt imports at module scope);
``apply_theme(app)`` does the actual installation.

Design rationale
----------------
This is an astrophotography tool — users will look at it side-by-side with
night-sky imagery for hours at a time. So:

  * **Dark by default.** A bright UI next to a dark astro image is fatiguing
    and would also wash out the preview pane.
  * **Warm amber accent** rather than the usual cool blue. Matches the
    Galactic-plane / star-marker colours on the all-sky map for visual
    cohesion across panels.
  * **Status colour code is consistent everywhere.** Accept = green, reject /
    error = red, warning = amber, "in progress" = blue. The frame table,
    library manager, and history panel all reuse the same palette.
  * **Just enough contrast.** WCAG AA against the panel background for
    primary text; secondary text drops to ~5:1 so it visually recedes.

This is the only place colours should be defined — never inline a hex code
in widget code. That way one theme tweak ripples through the whole app.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---- Palette ----------------------------------------------------------

# Backgrounds — three tiers so we can build visual hierarchy.
BG_DEEP     = "#0a0e1a"   # window background (matches sky-map dark theme)
BG_PANEL    = "#141a2c"   # tabs / dialogs / boxes
BG_RAISED   = "#1d2540"   # buttons, table headers, hover
BG_HOVER    = "#283155"   # interactive hover state
BG_SUNKEN   = "#070a14"   # text inputs, table interior
BG_DIVIDER  = "#2a3354"   # subtle borders

# Text.
FG_PRIMARY    = "#e7ecf5"   # body text
FG_SECONDARY  = "#a0a8bb"   # caption / hint
FG_DISABLED   = "#5a627a"
FG_INVERSE    = "#0a0e1a"   # on bright accents

# Accents.
ACCENT        = "#ff9a44"   # warm amber — primary action, sky-map markers
ACCENT_HOVER  = "#ffb070"
ACCENT_PRESS  = "#e07d2a"
LINK          = "#7aa9ff"   # cool blue for hyperlinks / mosaic outlines

# Semantic colours (status / metrics).
SUCCESS       = "#5dd39e"   # accepted frames, OK
WARNING       = "#f5c14a"   # caution
DANGER        = "#ef6f6c"   # rejected / errors
INFO          = "#69a8ff"   # progress / informational
MUTED         = "#6c7a99"   # neutral

# Convenience: colour for the various status states the GUI displays.
STATUS_COLORS = {
    "ok":      SUCCESS,
    "good":    SUCCESS,
    "accepted": SUCCESS,
    "warn":    WARNING,
    "warning": WARNING,
    "bad":     DANGER,
    "error":   DANGER,
    "rejected": DANGER,
    "info":    INFO,
    "running": INFO,
    "neutral": MUTED,
}


@dataclass(frozen=True)
class Spacing:
    """4-px base grid — same everywhere so the GUI feels consistent."""
    xs: int = 2
    sm: int = 4
    md: int = 8
    lg: int = 12
    xl: int = 18


S = Spacing()


# ---- Stylesheet -------------------------------------------------------

def stylesheet() -> str:
    """The application-wide Qt stylesheet. Built from the palette so
    tweaking a single colour above propagates everywhere."""
    return f"""
/* ----- base ------------------------------------------------------- */
QWidget {{
    background-color: {BG_DEEP};
    color: {FG_PRIMARY};
    font-family: "Segoe UI", "Inter", "Roboto", sans-serif;
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: {FG_INVERSE};
}}
QMainWindow, QDialog {{
    background-color: {BG_DEEP};
}}

/* ----- typography helpers ----------------------------------------- */
QLabel {{ background: transparent; }}
QLabel[role="h1"] {{
    font-size: 20px;
    font-weight: 600;
    color: {FG_PRIMARY};
    padding: {S.md}px 0px;
}}
QLabel[role="h2"] {{
    font-size: 16px;
    font-weight: 600;
    color: {FG_PRIMARY};
    padding: {S.sm}px 0px;
}}
QLabel[role="caption"] {{
    color: {FG_SECONDARY};
    font-size: 12px;
}}
QLabel[role="muted"]   {{ color: {FG_SECONDARY}; }}
QLabel[role="success"] {{ color: {SUCCESS}; font-weight: 600; }}
QLabel[role="warning"] {{ color: {WARNING}; font-weight: 600; }}
QLabel[role="danger"]  {{ color: {DANGER};  font-weight: 600; }}
QLabel[role="accent"]  {{ color: {ACCENT};  font-weight: 600; }}

/* ----- buttons ---------------------------------------------------- */
QPushButton {{
    background-color: {BG_RAISED};
    color: {FG_PRIMARY};
    border: 1px solid {BG_DIVIDER};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 22px;
}}
QPushButton:hover     {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QPushButton:pressed   {{ background-color: {BG_SUNKEN}; }}
QPushButton:disabled  {{ background-color: {BG_PANEL}; color: {FG_DISABLED}; border-color: {BG_PANEL}; }}
QPushButton:default,
QPushButton[primary="true"] {{
    background-color: {ACCENT};
    color: {FG_INVERSE};
    font-weight: 600;
    border: 1px solid {ACCENT};
}}
QPushButton[primary="true"]:hover   {{ background-color: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[primary="true"]:pressed {{ background-color: {ACCENT_PRESS}; }}
QPushButton[primary="true"]:disabled {{
    background-color: {BG_PANEL};
    color: {FG_DISABLED};
    border-color: {BG_PANEL};
}}
QPushButton[danger="true"] {{
    background-color: transparent;
    color: {DANGER};
    border: 1px solid {DANGER};
}}
QPushButton[danger="true"]:hover {{
    background-color: {DANGER};
    color: {FG_INVERSE};
}}

/* ----- inputs ----------------------------------------------------- */
QLineEdit, QPlainTextEdit, QTextEdit,
QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {BG_SUNKEN};
    color: {FG_PRIMARY};
    border: 1px solid {BG_DIVIDER};
    border-radius: 5px;
    padding: 4px 8px;
    selection-background-color: {ACCENT};
    selection-color: {FG_INVERSE};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    color: {FG_PRIMARY};
    border: 1px solid {BG_DIVIDER};
    selection-background-color: {BG_HOVER};
    selection-color: {FG_PRIMARY};
    padding: 4px;
}}

/* ----- check / radio --------------------------------------------- */
/* We deliberately do NOT restyle ::indicator. Once a stylesheet touches
   the indicator sub-control, Qt drops the native check/dot glyph and you
   must supply your own image — a styled-but-empty box is worse than the
   Fusion-drawn one, which already follows our dark palette (Highlight =
   accent). So we only set spacing here. */
QCheckBox, QRadioButton {{
    background: transparent;
    spacing: 6px;
}}
QCheckBox:disabled, QRadioButton:disabled {{ color: {FG_DISABLED}; }}

/* ----- group box -------------------------------------------------- */
QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BG_DIVIDER};
    border-radius: 7px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {ACCENT};
    background: transparent;
}}

/* ----- tabs ------------------------------------------------------- */
QTabWidget::pane {{
    border: 1px solid {BG_DIVIDER};
    border-radius: 6px;
    background-color: {BG_PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {FG_SECONDARY};
    padding: 7px 16px;
    margin-right: 2px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    border: 1px solid transparent;
}}
QTabBar::tab:hover {{ color: {FG_PRIMARY}; }}
QTabBar::tab:selected {{
    background-color: {BG_PANEL};
    color: {ACCENT};
    border-color: {BG_DIVIDER};
    border-bottom-color: {BG_PANEL};
    font-weight: 600;
}}

/* ----- tables ----------------------------------------------------- */
QTableView, QTableWidget {{
    background-color: {BG_SUNKEN};
    alternate-background-color: {BG_PANEL};
    color: {FG_PRIMARY};
    gridline-color: {BG_DIVIDER};
    border: 1px solid {BG_DIVIDER};
    border-radius: 5px;
    selection-background-color: {BG_HOVER};
    selection-color: {FG_PRIMARY};
}}
QHeaderView::section {{
    background-color: {BG_RAISED};
    color: {FG_PRIMARY};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {BG_DIVIDER};
    border-bottom: 1px solid {BG_DIVIDER};
    font-weight: 600;
}}
QHeaderView::section:hover {{ background-color: {BG_HOVER}; }}
QTableCornerButton::section {{ background-color: {BG_RAISED}; border: none; }}

/* ----- scrollbars ------------------------------------------------- */
QScrollBar:vertical {{
    background: {BG_DEEP};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BG_RAISED};
    border-radius: 5px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {BG_DEEP};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BG_RAISED};
    border-radius: 5px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ----- menus ----------------------------------------------------- */
QMenuBar {{
    background-color: {BG_PANEL};
    color: {FG_PRIMARY};
    border-bottom: 1px solid {BG_DIVIDER};
    padding: 2px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{ background-color: {BG_HOVER}; }}
QMenu {{
    background-color: {BG_PANEL};
    color: {FG_PRIMARY};
    border: 1px solid {BG_DIVIDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 18px 5px 10px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {BG_HOVER};
    color: {ACCENT};
}}
QMenu::separator {{
    height: 1px;
    background: {BG_DIVIDER};
    margin: 4px 6px;
}}

/* ----- status bar ------------------------------------------------- */
QStatusBar {{
    background-color: {BG_PANEL};
    color: {FG_SECONDARY};
    border-top: 1px solid {BG_DIVIDER};
}}
QStatusBar QLabel {{ padding: 0 6px; }}

/* ----- splitter --------------------------------------------------- */
QSplitter::handle {{
    background-color: {BG_DIVIDER};
}}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:vertical   {{ height: 3px; }}
QSplitter::handle:hover {{ background-color: {ACCENT}; }}

/* ----- progress bar ---------------------------------------------- */
QProgressBar {{
    background-color: {BG_SUNKEN};
    border: 1px solid {BG_DIVIDER};
    border-radius: 4px;
    text-align: center;
    color: {FG_PRIMARY};
    height: 16px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}

/* ----- tooltips --------------------------------------------------- */
QToolTip {{
    background-color: {BG_PANEL};
    color: {FG_PRIMARY};
    border: 1px solid {ACCENT};
    border-radius: 4px;
    padding: 6px 8px;
    opacity: 240;
}}
"""


# ---- Programmatic helpers --------------------------------------------

def status_color(status: str) -> str:
    """Hex string for a named status. Falls back to the neutral muted tone."""
    return STATUS_COLORS.get(status.lower(), MUTED)


def apply_theme(app) -> None:
    """Install the stylesheet on a ``QApplication`` and tweak the palette."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPalette
    except ImportError:
        return

    app.setStyle("Fusion")  # most consistent base under our QSS overrides
    app.setStyleSheet(stylesheet())

    # Set palette too so non-styled native widgets (file dialogs on some
    # platforms) inherit the right colours.
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG_DEEP))
    pal.setColor(QPalette.WindowText, QColor(FG_PRIMARY))
    pal.setColor(QPalette.Base, QColor(BG_SUNKEN))
    pal.setColor(QPalette.AlternateBase, QColor(BG_PANEL))
    pal.setColor(QPalette.Text, QColor(FG_PRIMARY))
    pal.setColor(QPalette.Button, QColor(BG_RAISED))
    pal.setColor(QPalette.ButtonText, QColor(FG_PRIMARY))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor(FG_INVERSE))
    pal.setColor(QPalette.ToolTipBase, QColor(BG_PANEL))
    pal.setColor(QPalette.ToolTipText, QColor(FG_PRIMARY))
    pal.setColor(QPalette.Link, QColor(LINK))
    pal.setColor(QPalette.PlaceholderText, QColor(FG_DISABLED))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(FG_DISABLED))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(FG_DISABLED))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(FG_DISABLED))
    app.setPalette(pal)
