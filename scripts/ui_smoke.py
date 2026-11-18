"""Exercise actual Qt widgets offscreen and capture the app's own rendering."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from label_editor.ui import MainWindow, configure_app


def main():
    app = QApplication([])
    configure_app(app)
    out = ROOT / "tmp" / "qa"
    out.mkdir(parents=True, exist_ok=True)
    window = MainWindow()
    errors = []
    window.show_error = lambda text: errors.append(str(text))
    window.show()
    QTest.qWait(100)
    window.grab().save(str(out / "welcome.png"))
    window.open_sample()
    QTest.qWait(200)
    assert window.session and window.session.original.page_count == 2
    run = next(r for r in window.session.runs(0) if r.text == "138 0000 1234")
    # Click the real viewport using PDF scene coordinates.
    center = QPoint(int((run.bbox[0] + run.bbox[2]) / 2), int((run.bbox[1] + run.bbox[3]) / 2))
    point = window.view.mapFromScene(center.x(), center.y())
    QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.qWait(100)
    assert window.selected and window.selected.key == run.key
    window.text_edit.setPlainText("139 5555 6789")
    assert window.pending
    QTest.mouseClick(window.apply_btn, Qt.MouseButton.LeftButton)
    QTest.qWait(100)
    assert not errors, errors
    assert "139 5555 6789" in window.session.preview()[0].get_text()
    window.grab().save(str(out / "editor.png"))
    QTest.mouseClick(window.compare_btn, Qt.MouseButton.LeftButton)
    assert window.compare_btn.isChecked() and not window.text_edit.isEnabled()
    QTest.mouseClick(window.compare_btn, Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.undo_btn, Qt.MouseButton.LeftButton)
    assert not window.session.changes
    QTest.mouseClick(window.redo_btn, Qt.MouseButton.LeftButton)
    assert window.session.changes
    window.pages.setCurrentRow(1)
    QTest.qWait(100)
    assert window.page_number == 1
    window.pages.setCurrentRow(0)
    QFileDialog.getSaveFileName = lambda *a, **k: (str(out / "ui-export.pdf"), "PDF")
    QMessageBox.information = lambda *a, **k: QMessageBox.StandardButton.Ok
    assert window.save()
    assert not window.session.dirty
    window.close()
    assert not errors, errors
    print("UI smoke passed: open, select, edit, apply, compare, undo, redo, pages, save.")


if __name__ == "__main__":
    main()
