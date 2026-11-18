"""Packaged-runtime verification; invoked only by --self-test <output-directory>."""
import json
from dataclasses import replace
from pathlib import Path
import sys
import platform
from . import __version__

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .ui import MainWindow, configure_app
from .core import PdfSession


def run(output: str):
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    configure_app(app)
    window = MainWindow()
    errors = []
    window.show_error = lambda message: errors.append(str(message))
    window.show()
    result = {"ok": False, "version": __version__, "platform": sys.platform, "architecture": platform.machine()}

    def check():
        try:
            window.open_sample()
            assert window.session, errors
            app.processEvents()
            s = window.session
            run = next(r for r in s.runs(0) if r.text == "收件人：张三")
            window.select_run(run)
            app.processEvents()
            window.text_edit.setPlainText("收件人：李四")
            assert window.apply(), errors
            assert not errors, errors
            assert "收件人：李四" in s.preview()[0].get_text()
            destination = s.save_as(out / "packaged-export.pdf")
            assert s.original[1].get_pixmap().samples == s.preview()[1].get_pixmap().samples
            reopened = PdfSession(destination)
            assert "收件人：李四" in reopened.original[0].get_text()
            reopened.close()
            window.fit_page()
            app.processEvents()
            window.grab().save(str(out / "packaged-app.png"))
            original_pages = s.original.page_count
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
            window.open_pdf(base / "assets/font-check.pdf")
            app.processEvents()
            font_run = next(r for r in window.session.runs(0) if r.text == "7.340 KG")
            window.select_run(font_run)
            app.processEvents()
            window.text_edit.setPlainText("7.570 KG")
            assert window.apply(), errors
            edit = window.session.get_edit(font_run)
            choice = window.session.resolve_font(font_run, edit)
            assert choice.label == "Arimo-Regular" or choice.label == "Arimo"
            assert choice.source == "内置同款字体"
            assert edit.font == "original"
            window.session.save_as(out / "arimo-auto-font.pdf")
            window.fit_page()
            app.processEvents()
            window.grab().save(str(out / "arimo-auto-font.png"))
            result.update(ok=True, pages=original_pages, export=str(destination),
                          checks=["bundled sample", "Qt UI", "Chinese subset font reuse", "PDF export",
                                  "reopen output", "unmodified page pixels", "automatic Arimo completion offline"])
        except Exception as exc:
            import traceback
            result.update(error=str(exc), traceback=traceback.format_exc(), ui_errors=errors)
        finally:
            (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            window.pending = False
            if window.session:
                window.session.saved_changes = dict(window.session.changes)
            window.close()
            app.quit()

    QTimer.singleShot(100, check)
    app.exec()
    return 0 if result["ok"] else 1
