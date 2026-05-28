"""Construct the main window offscreen to confirm everything wires up."""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
print("step 1: env set", flush=True)

from PySide6.QtWidgets import QApplication
print("step 2: QApplication imported", flush=True)

from seestack.gui.main_window import MainWindow
print("step 3: MainWindow imported", flush=True)

app = QApplication(sys.argv)
print("step 4: QApplication created", flush=True)

win = MainWindow()
print("step 5: MainWindow constructed", flush=True)

win.show()
print("step 6: shown", flush=True)

app.processEvents()
print("step 7: events processed", flush=True)

print("size:", win.size().width(), "x", win.size().height())
print("title:", win.windowTitle())
print("row count:", win._model.rowCount())
win.close()
print("step 8: closed", flush=True)
