"""
Side-by-side stack comparison dialog.

Pick two FITS or TIFF stack outputs, view them at matched stretch with a
synchronized split view. Useful for answering "did changing X actually help?"

Implementation notes:
  - Loads small previews (downsampled to fit the window) so memory stays
    modest even for drizzle-3× outputs.
  - Uses the same STF autostretch as the GUI's preview pane so both halves
    are visually comparable.
  - Side-by-side is preferred over A/B-overlay because slight scale
    differences (e.g. drizzle on vs off) would make overlay misleading.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

log = logging.getLogger(__name__)


class CompareDialog(QDialog):
    """Modal viewer comparing two stack outputs at matched autostretch."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare stacks")
        self.resize(1400, 800)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "<i>Both images are autostretched with the same parameters so "
            "you can spot real differences (sky cleanliness, star tightness, "
            "faint nebulosity) without being misled by different stretches.</i>"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        controls = QHBoxLayout()
        self._left_btn = QPushButton("Left: pick file…")
        self._left_btn.clicked.connect(lambda: self._pick("left"))
        self._right_btn = QPushButton("Right: pick file…")
        self._right_btn.clicked.connect(lambda: self._pick("right"))
        controls.addWidget(self._left_btn)
        controls.addWidget(self._right_btn)
        controls.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        controls.addWidget(close_btn)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._left_view = _ImagePane("Left")
        self._right_view = _ImagePane("Right")
        splitter.addWidget(self._left_view)
        splitter.addWidget(self._right_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

    def set_paths(self, left: str | None = None, right: str | None = None) -> None:
        """Programmatic loader — used from the History panel context."""
        if left:
            self._left_view.load(Path(left))
        if right:
            self._right_view.load(Path(right))

    def _pick(self, side: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose stack output",
            "", "Stack output (*.fits *.fit *.tif *.tiff);;All files (*.*)",
        )
        if not path:
            return
        pane = self._left_view if side == "left" else self._right_view
        try:
            pane.load(Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not load image", str(exc))


class _ImagePane(QLabel):
    """One half of the comparison. Loads + autostretches a FITS or TIFF."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self._label = label
        from seestack.gui.theme import BG_SUNKEN, FG_SECONDARY, BG_DIVIDER
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 400)
        self.setStyleSheet(
            f"background:{BG_SUNKEN}; color:{FG_SECONDARY}; "
            f"border: 1px solid {BG_DIVIDER}; border-radius: 6px;"
        )
        self.setText(f"<i>{label}: drop a file or click pick.</i>")
        self._caption = ""

    def load(self, path: Path) -> None:
        rgb = _read_to_rgb_float(path)
        from seestack.gui.thumbnail import autostretch

        stretched = autostretch(rgb)
        u8 = (np.clip(stretched, 0.0, 1.0) * 255).astype(np.uint8)
        h, w = u8.shape[:2]
        # Downsize for display.
        if w > 1200 or h > 1200:
            scale = min(1200 / w, 1200 / h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            from PIL import Image as _Image

            u8 = np.asarray(
                _Image.fromarray(u8, "RGB").resize((new_w, new_h), _Image.BOX)
            )
        from PySide6.QtGui import QImage

        qimg = QImage(u8.data, u8.shape[1], u8.shape[0],
                      u8.shape[1] * 3, QImage.Format.Format_RGB888)
        # QImage references the buffer, so we copy it before the temporary
        # numpy array is freed.
        pix = QPixmap.fromImage(qimg.copy())
        self.setPixmap(pix.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        self.setToolTip(f"{path}\n{w}×{h}")

    def resizeEvent(self, ev) -> None:  # noqa: N802
        # Keep the pixmap fit to the pane after resize.
        pix = self.pixmap()
        if pix and not pix.isNull():
            self.setPixmap(pix.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        super().resizeEvent(ev)


def _read_to_rgb_float(path: Path) -> np.ndarray:
    """Load a FITS or TIFF and return an (H, W, 3) float32 RGB array."""
    suffix = path.suffix.lower()
    if suffix in {".fit", ".fits"}:
        from astropy.io import fits

        with fits.open(path, memmap=True) as hdul:
            data = np.asarray(hdul[0].data, dtype=np.float32)
        if data.ndim == 3 and data.shape[0] == 3:
            # (channels, H, W) → (H, W, 3)
            data = np.transpose(data, (1, 2, 0))
        elif data.ndim == 2:
            data = np.stack([data, data, data], axis=-1)
        return data
    # TIFF / PNG / JPG fallback via tifffile or PIL.
    if suffix in {".tif", ".tiff"}:
        import tifffile

        arr = tifffile.imread(str(path))
    else:
        from PIL import Image

        arr = np.asarray(Image.open(path).convert("RGB"))
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    return arr.astype(np.float32)
