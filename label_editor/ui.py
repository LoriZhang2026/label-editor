from __future__ import annotations

import sys
from pathlib import Path

import pymupdf as fitz
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGraphicsPixmapItem, QGraphicsRectItem,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from .core import Edit, EditError, PdfSession, SYSTEM_FONTS, TextRun
from . import __version__
from .fonts import system_font_dirs


STYLE = """
QMainWindow, QWidget { font-family: 'Microsoft YaHei'; font-size: 13px; color: #263549; }
QMainWindow { background: #f4f6f9; }
QFrame#header { background: white; border-bottom: 1px solid #e3e8f0; }
QLabel#brand { font-size: 20px; font-weight: 700; color: #122b42; }
QLabel#muted { color: #7b8797; font-size: 12px; }
QLabel#section { font-size: 15px; font-weight: 600; color: #183347; }
QLabel#eyebrow { color: #078371; font-size: 12px; font-weight: 700; }
QLabel#hero { font-size: 32px; font-weight: 700; color: #173349; }
QLabel#notice { background: #edf7f5; color: #367064; padding: 12px; border-radius: 8px; font-size: 12px; }
QPushButton { background: white; border: 1px solid #dbe2eb; border-radius: 7px; padding: 8px 13px; }
QPushButton:hover { background: #edf5f6; border-color: #8bbfb6; }
QPushButton:pressed { background: #d9eee9; }
QPushButton:checked { background: #e3f3ef; border-color: #048773; color: #047663; }
QPushButton:disabled { color: #a9b1bc; background: #f6f7fa; border-color: #e7ebf0; }
QPushButton#primary { background: #087f70; color: white; border: 1px solid #087f70; font-weight: 600; }
QPushButton#primary:hover { background: #056c5f; }
QPushButton#primary:disabled { background: #a7ccc5; border-color: #a7ccc5; }
QTextEdit, QDoubleSpinBox, QComboBox { background: white; border: 1px solid #dbe2eb; border-radius: 6px; padding: 7px; }
QTextEdit:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #078371; }
QTextEdit:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { background: #f4f6f9; color: #98a3af; }
QComboBox { min-height: 20px; }
QListWidget { background: #f7f9fc; border: none; padding: 6px; outline: none; }
QListWidget::item { padding: 10px 6px; margin: 5px; border-radius: 7px; border: 1px solid transparent; }
QListWidget::item:selected { background: #e0f1ed; border: 1px solid #63ae9f; color: #086e5f; }
QListWidget::item:hover { background: #eaf0f6; }
QGraphicsView { border: none; background: #e9edf3; }
QSplitter::handle { background: #e1e6ee; width: 1px; }
QStatusBar { background: white; border-top: 1px solid #e3e8f0; color: #778393; }
QScrollArea { border: none; background: white; }
QToolTip { background: #183347; color: white; border: none; padding: 6px; }
"""


def pixmap_for(page, scale=1.5):
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(image)


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback=None, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    if callback:
        widget.clicked.connect(callback)
    return widget


class TextOverlay(QGraphicsRectItem):
    def __init__(self, rect, run, callback, selected=False, changed=False, locked=False):
        super().__init__(rect.x0, rect.y0, rect.width, rect.height)
        self.run = run
        self.callback = callback
        self.selected = selected
        self.changed = changed
        self.locked = locked
        self.setZValue(2)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.ForbiddenCursor if locked else Qt.CursorShape.IBeamCursor)
        self.setToolTip(run.reason or "点击编辑这段文字")
        self.paint_state(False)

    def paint_state(self, hover):
        color = "#058471" if self.selected else "#d99a25" if self.changed else "#8294a7"
        pen = QPen(QColor(color))
        pen.setCosmetic(True)
        pen.setWidth(2 if self.selected else 1)
        pen.setStyle(Qt.PenStyle.SolidLine if self.selected or self.changed else Qt.PenStyle.DotLine)
        self.setPen(pen if self.selected or self.changed or hover else QPen(Qt.PenStyle.NoPen))
        fill = QColor(color)
        fill.setAlpha(22 if hover or self.selected else 8 if self.changed else 0)
        self.setBrush(fill)

    def hoverEnterEvent(self, event):
        self.paint_state(True)

    def hoverLeaveEvent(self, event):
        self.paint_state(False)

    def mousePressEvent(self, event):
        self.callback(self.run)
        event.accept()


class PageView(QGraphicsView):
    zoomRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomRequested.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
        else:
            super().wheelEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.session: PdfSession | None = None
        self.page_number = 0
        self.selected: TextRun | None = None
        self.loading_form = False
        self.pending = False
        self.zoom = 1.6
        self.thumbs = []
        self.setWindowTitle(f"面单工坊 {__version__} · PDF 内容编辑器")
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        self.setWindowIcon(QIcon(str(base / "assets" / "app.svg")))
        self.resize(1360, 900)
        self.setMinimumSize(1050, 700)
        self.setAcceptDrops(True)
        self.create_ui()
        self.create_actions()
        self.update_state()

    def create_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        bar = QHBoxLayout(header)
        bar.setContentsMargins(24, 15, 24, 15)
        brand = QVBoxLayout()
        brand.setSpacing(2)
        brand.addWidget(label("面单工坊", "brand"))
        brand.addWidget(label(f"v{__version__}  /  PDF 内容编辑器 · 本地处理", "muted"))
        bar.addLayout(brand)
        bar.addStretch()
        self.open_btn = button("打开 PDF", self.open_dialog)
        self.undo_btn = button("撤销", self.undo)
        self.redo_btn = button("重做", self.redo)
        self.compare_btn = button("查看原稿")
        self.compare_btn.setCheckable(True)
        self.compare_btn.toggled.connect(self.toggle_compare)
        self.save_btn = button("另存为 PDF", self.save, True)
        for widget in [self.open_btn, self.undo_btn, self.redo_btn, self.compare_btn, self.save_btn]:
            bar.addWidget(widget)
        layout.addWidget(header)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.create_welcome()
        self.create_editor()
        self.setCentralWidget(root)
        self.statusBar().showMessage("就绪 · 文件仅在本机处理")

    def create_welcome(self):
        welcome = QWidget()
        box = QVBoxLayout(welcome)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setSpacing(20)
        for w in [label("LOCAL PDF EDITOR", "eyebrow"),
                  label("面单改字，保持原样。", "hero"),
                  label("打开一份 PDF，点击文字即可修改。\n沿用原有字体与位置，原文件始终保留。", "muted")]:
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(w)
        drop = QFrame()
        drop.setFixedSize(580, 240)
        drop.setStyleSheet("QFrame { background: white; border: 2px dashed #b8d1cf; border-radius: 16px; } QLabel { border: none; }")
        drop_layout = QVBoxLayout(drop)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = label("将 PDF 文件拖到这里", "section")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(title)
        drop_layout.addWidget(label("支持多页 PDF · 支持中文面单", "muted"), 0, Qt.AlignmentFlag.AlignCenter)
        open_button = button("选择 PDF 文件", self.open_dialog, True)
        open_button.setFixedWidth(190)
        drop_layout.addSpacing(18)
        drop_layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignCenter)
        box.addWidget(drop, 0, Qt.AlignmentFlag.AlignCenter)
        sample = button("打开示例面单，体验编辑", self.open_sample)
        box.addWidget(sample, 0, Qt.AlignmentFlag.AlignCenter)
        note = label("文字型 PDF 可直接编辑。扫描件、图片文字和签名文件暂仅支持查看。", "muted")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(note)
        self.stack.addWidget(welcome)

    def create_editor(self):
        editor = QWidget()
        body = QVBoxLayout(editor)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(20, 9, 20, 9)
        self.filename = label("", "section")
        self.filename.setMaximumWidth(410)
        self.file_status = label("", "muted")
        row.addWidget(self.filename)
        row.addSpacing(10)
        row.addWidget(self.file_status)
        row.addStretch()
        row.addWidget(button("−", lambda: self.change_zoom(-1)))
        self.zoom_label = label("160%", "muted")
        self.zoom_label.setMinimumWidth(45)
        row.addWidget(self.zoom_label)
        row.addWidget(button("+", lambda: self.change_zoom(1)))
        row.addWidget(button("适合页面", self.fit_page))
        body.addLayout(row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.pages = QListWidget()
        self.pages.setMinimumWidth(145)
        self.pages.setMaximumWidth(210)
        self.pages.setIconSize(QSize(125, 168))
        self.pages.setViewMode(QListWidget.ViewMode.IconMode)
        self.pages.setFlow(QListWidget.Flow.TopToBottom)
        self.pages.setWrapping(False)
        self.pages.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.pages.setMovement(QListWidget.Movement.Static)
        self.pages.currentRowChanged.connect(self.change_page)
        self.view = PageView()
        self.view.zoomRequested.connect(self.change_zoom)
        splitter.addWidget(self.pages)
        splitter.addWidget(self.view)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(310)
        scroll.setMaximumWidth(365)
        panel = QWidget()
        panel.setObjectName("editPanel")
        panel.setStyleSheet("QWidget#editPanel { background: white; }")
        self.panel = panel
        right = QVBoxLayout(panel)
        right.setContentsMargins(22, 22, 22, 22)
        right.setSpacing(10)
        right.addWidget(label("编辑文字", "section"))
        self.selection_hint = label("点击页面上的文字开始编辑。", "muted", True)
        right.addWidget(self.selection_hint)
        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlaceholderText("在页面中选择一段文字")
        self.text_edit.setFixedHeight(120)
        self.text_edit.textChanged.connect(self.form_changed)
        right.addWidget(self.text_edit)
        self.font_info = label("原字体：—", "muted", True)
        right.addWidget(self.font_info)
        self.font_combo = QComboBox()
        self.font_combo.addItem("自动沿用原字体（含字库补全）", "original")
        for key, (name, path) in SYSTEM_FONTS.items():
            if path.exists():
                self.font_combo.addItem(name, key)
        self.font_combo.currentIndexChanged.connect(self.form_changed)
        right.addWidget(self.font_combo)
        self.font_file_btn = button("补充字体文件…", self.choose_font)
        right.addWidget(self.font_file_btn)
        form = QFormLayout()
        form.setSpacing(10)
        self.size_input = QDoubleSpinBox()
        self.size_input.setRange(3, 144)
        self.size_input.setDecimals(2)
        self.size_input.setSuffix(" pt")
        self.width_input = QDoubleSpinBox()
        self.width_input.setRange(.1, 5000)
        self.width_input.setDecimals(2)
        self.width_input.setSuffix(" pt")
        self.height_input = QDoubleSpinBox()
        self.height_input.setRange(.1, 5000)
        self.height_input.setDecimals(2)
        self.height_input.setSuffix(" pt")
        for title, widget in [("字号", self.size_input), ("区域宽度", self.width_input), ("区域高度", self.height_input)]:
            widget.valueChanged.connect(self.form_changed)
            form.addRow(title, widget)
        right.addLayout(form)
        self.wrap_check = QCheckBox("按编辑区域宽度自动换行")
        self.wrap_check.toggled.connect(self.form_changed)
        right.addWidget(self.wrap_check)
        self.shrink_btn = button("缩小至适合", self.shrink)
        right.addWidget(self.shrink_btn)
        self.apply_btn = button("应用修改", self.apply, True)
        right.addWidget(self.apply_btn)
        operations = QHBoxLayout()
        self.restore_btn = button("恢复原文", self.restore)
        self.delete_btn = button("删除文字", lambda: self.text_edit.setPlainText(""))
        operations.addWidget(self.restore_btn)
        operations.addWidget(self.delete_btn)
        right.addLayout(operations)
        self.edit_hint = label("修改后点击「应用修改」查看效果。", "muted", True)
        right.addWidget(self.edit_hint)
        right.addStretch()
        right.addWidget(label("操作提示\n\nCtrl + 滚轮缩放；拖动空白处移动页面。\n橙色边框表示已修改，导出时不包含边框。\n\n修改单号文字不会自动更新条码。", "notice", True))
        scroll.setWidget(panel)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([170, 830, 340])
        body.addWidget(splitter, 1)
        self.stack.addWidget(editor)
        self.form_widgets = [self.text_edit, self.font_combo, self.font_file_btn,
                             self.size_input, self.width_input, self.height_input,
                             self.wrap_check, self.shrink_btn, self.apply_btn,
                             self.restore_btn, self.delete_btn]

    def create_actions(self):
        for title, shortcut, callback in [
            ("打开", "Ctrl+O", self.open_dialog), ("另存为", "Ctrl+Shift+S", self.save),
            ("保存", "Ctrl+S", self.save), ("应用修改", "Ctrl+Return", self.apply),
        ]:
            action = QAction(title, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.addAction(action)
        # QTextEdit keeps its native undo while focused; document undo uses buttons.
        for title, shortcut, callback in [("撤销文档修改", "Alt+Left", self.undo),
                                          ("重做文档修改", "Alt+Right", self.redo)]:
            action = QAction(title, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.addAction(action)

    def show_error(self, text):
        QMessageBox.warning(self, "暂时无法完成", str(text))

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 PDF 面单", "", "PDF 文件 (*.pdf)")
        if path:
            self.open_pdf(path)

    def open_sample(self):
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        path = base / "assets" / "示例面单.pdf"
        if path.exists():
            self.open_pdf(path)
        else:
            self.show_error("未找到示例面单，请打开自己的 PDF 文件。")

    def open_pdf(self, path):
        if not self.confirm_leave():
            return
        candidate = None
        try:
            candidate = PdfSession(path)
        except Exception as exc:
            if "密码" in str(exc):
                password, ok = QInputDialog.getText(self, "加密 PDF", "请输入文件密码：", QLineEditEchoMode())
                if not ok:
                    return
                try:
                    candidate = PdfSession(path, password)
                except Exception as second:
                    self.show_error(second)
                    return
            else:
                self.show_error(f"无法打开文件：{exc}")
                return
        if self.session:
            self.session.close()
        self.session = candidate
        self.selected = None
        self.pending = False
        self.page_number = 0
        self.compare_btn.blockSignals(True)
        self.compare_btn.setChecked(False)
        self.compare_btn.setText("查看原稿")
        self.compare_btn.blockSignals(False)
        self.pages.blockSignals(True)
        self.pages.clear()
        for pn in range(candidate.original.page_count):
            item = QListWidgetItem(f"第 {pn + 1} 页")
            item.setSizeHint(QSize(135, 195))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pages.addItem(item)
        self.pages.setCurrentRow(0)
        self.pages.blockSignals(False)
        self.thumbs = list(range(candidate.original.page_count))
        self.filename.setText(candidate.path.name)
        self.filename.setToolTip(str(candidate.path))
        self.stack.setCurrentIndex(1)
        self.populate_form()
        self.render_page()
        QTimer.singleShot(0, self.fit_page)
        QTimer.singleShot(0, self.load_thumbnail)

    def load_thumbnail(self):
        if not self.session or not self.thumbs:
            return
        pn = self.thumbs.pop(0)
        try:
            page = self.session.original[pn]
            scale = min(125 / page.rect.width, 168 / page.rect.height)
            self.pages.item(pn).setIcon(QIcon(pixmap_for(page, scale)))
        except Exception:
            pass
        if self.thumbs:
            QTimer.singleShot(10, self.load_thumbnail)

    def change_page(self, pn):
        if not self.session or pn < 0 or pn == self.page_number:
            return
        if not self.confirm_pending():
            self.pages.blockSignals(True)
            self.pages.setCurrentRow(self.page_number)
            self.pages.blockSignals(False)
            return
        self.page_number = pn
        self.selected = None
        self.populate_form()
        self.render_page()

    def render_page(self):
        if not self.session:
            return
        try:
            original = self.compare_btn.isChecked()
            doc = self.session.original if original else self.session.preview()
            page = doc[self.page_number]
            scene = self.view.scene()
            # Produce the image before clearing the scene, so rendering errors keep the old view.
            pixmap = pixmap_for(page, 2)
            scene.clear()
            item = QGraphicsPixmapItem(pixmap)
            item.setScale(.5)
            scene.addItem(item)
            scene.setSceneRect(-20, -20, page.rect.width + 40, page.rect.height + 40)
            if not original:
                for run in self.session.runs(self.page_number):
                    rect = fitz.Rect(run.bbox)
                    changed = run.key in self.session.changes
                    if changed and self.session.changes[run.key].text:
                        _, _, new_rect = self.session.layout(run, self.session.changes[run.key])
                        rect = rect | new_rect
                    rect = rect * page.rotation_matrix
                    overlay = TextOverlay(rect, run, self.select_run,
                                          self.selected is not None and run.key == self.selected.key,
                                          changed, bool(run.reason))
                    scene.addItem(overlay)
            self.view.resetTransform()
            self.view.scale(self.zoom, self.zoom)
            runs = self.session.runs(self.page_number)
            editable = sum(not r.reason for r in runs)
            size_text = f"{page.rect.width * 25.4 / 72:.1f} × {page.rect.height * 25.4 / 72:.1f} mm"
            mode = "原稿预览" if original else f"{editable} 段可编辑文字"
            self.statusBar().showMessage(f"第 {self.page_number + 1} / {doc.page_count} 页  ·  {size_text}  ·  {mode}  ·  本地处理")
            if not runs:
                self.selection_hint.setText("此页没有可直接编辑的文字，可能是扫描件或文字已转成图形。")
            elif editable == 0 and not self.selected:
                self.selection_hint.setText(runs[0].reason or "此页暂不支持直接编辑。")
            self.update_state()
        except Exception as exc:
            self.show_error(f"无法显示页面：{exc}")

    def select_run(self, run):
        if self.selected and self.selected.key == run.key:
            return
        if not self.confirm_pending():
            return
        self.selected = run
        self.populate_form()
        # Defer: the clicked graphics item must survive its own event handler.
        QTimer.singleShot(0, self.render_page)
        if not run.reason:
            self.text_edit.setFocus()

    def populate_form(self):
        self.loading_form = True
        self.pending = False
        run = self.selected
        if run:
            edit = self.session.get_edit(run)
            self.text_edit.setPlainText(edit.text)
            self.size_input.setValue(edit.size)
            self.width_input.setValue(edit.width)
            self.height_input.setValue(edit.height)
            self.font_combo.setCurrentIndex(max(0, self.font_combo.findData(edit.font)))
            self.wrap_check.setChecked(edit.wrap)
            self.font_info.setText(f"原字体：{run.font}\n原字号：{run.size:.2f} pt · 位置保持原样")
            self.selection_hint.setText(run.reason or "已选中文字 · 在下方修改内容")
        else:
            self.text_edit.clear()
            self.font_info.setText("原字体：—")
            self.selection_hint.setText("点击页面上的文字开始编辑。")
        self.edit_hint.setText("修改后点击「应用修改」查看效果。")
        self.loading_form = False
        self.update_state()

    def read_form(self):
        return Edit(self.text_edit.toPlainText(), self.size_input.value(), self.width_input.value(),
                    self.height_input.value(), self.font_combo.currentData(), self.wrap_check.isChecked())

    def form_changed(self, *_):
        if self.loading_form or not self.selected:
            return
        current = self.session.get_edit(self.selected)
        form = self.read_form()
        # UI precision should not create a change merely by selecting a text run.
        self.pending = (form.text != current.text or form.font != current.font or form.wrap != current.wrap
                        or any(abs(a - b) > .011 for a, b in [(form.size, current.size),
                                   (form.width, current.width), (form.height, current.height)]))
        self.edit_hint.setText("内容尚未应用 · Ctrl + Enter 应用修改" if self.pending else "当前内容已应用。")
        self.update_state()

    def choose_font(self):
        initial = next((p for p in system_font_dirs() if p.is_dir()), Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "选择字体", str(initial), "字体文件 (*.ttf *.otf *.ttc *.otc)")
        if path:
            index = self.font_combo.findData(path)
            if index < 0:
                self.font_combo.addItem(Path(path).name, path)
                index = self.font_combo.count() - 1
            self.font_combo.setCurrentIndex(index)

    def apply(self):
        if not self.session or not self.selected or not self.pending:
            return True
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        error = None
        try:
            self.session.apply(self.selected, self.read_form())
        except Exception as exc:
            error = exc
        finally:
            QApplication.restoreOverrideCursor()
        if error:
            self.show_error(error)
            return False
        self.populate_form()
        self.render_page()
        if self.session.get_edit(self.selected).text:
            choice = self.session.resolve_font(self.selected, self.session.get_edit(self.selected))
            self.edit_hint.setText(f"已应用 · {choice.label}\n字体来源：{choice.source}；字号和位置按当前设置保留。")
        else:
            self.edit_hint.setText("已删除选中文字。")
        return True

    def shrink(self):
        if not self.selected:
            return
        try:
            edit = self.session.shrink(self.selected, self.read_form())
            self.size_input.setValue(edit.size)
            self.edit_hint.setText(f"已调整至 {edit.size:.1f} pt，请点击「应用修改」。")
        except Exception as exc:
            self.show_error(exc)

    def restore(self):
        if not self.selected:
            return
        try:
            self.session.apply(self.selected, self.session.default_edit(self.selected))
            self.populate_form()
            self.render_page()
        except Exception as exc:
            self.show_error(exc)

    def undo(self):
        if self.session and self.confirm_pending():
            self.session.undo()
            self.populate_form()
            self.render_page()

    def redo(self):
        if self.session and self.confirm_pending():
            self.session.redo()
            self.populate_form()
            self.render_page()

    def toggle_compare(self, checked):
        if checked and not self.confirm_pending():
            self.compare_btn.blockSignals(True)
            self.compare_btn.setChecked(False)
            self.compare_btn.blockSignals(False)
            return
        self.compare_btn.setText("返回修改稿" if checked else "查看原稿")
        self.render_page()

    def change_zoom(self, direction):
        if not self.session:
            return
        self.zoom = max(.3, min(5, self.zoom * (1.2 if direction > 0 else 1 / 1.2)))
        self.view.resetTransform()
        self.view.scale(self.zoom, self.zoom)
        self.zoom_label.setText(f"{self.zoom:.0%}")

    def fit_page(self):
        if not self.session:
            return
        rect = self.session.original[self.page_number].rect
        self.zoom = max(.1, min(4, (self.view.viewport().width() - 60) / rect.width,
                               (self.view.viewport().height() - 60) / rect.height))
        self.view.resetTransform()
        self.view.scale(self.zoom, self.zoom)
        self.view.centerOn(rect.width / 2, rect.height / 2)
        self.zoom_label.setText(f"{self.zoom:.0%}")

    def update_state(self):
        active = self.session is not None
        self.save_btn.setEnabled(active)
        self.compare_btn.setEnabled(active)
        self.undo_btn.setEnabled(active and bool(self.session.undo_stack))
        self.redo_btn.setEnabled(active and bool(self.session.redo_stack))
        editable = active and self.selected is not None and not self.selected.reason and not self.compare_btn.isChecked()
        for widget in getattr(self, "form_widgets", []):
            widget.setEnabled(bool(editable))
        self.apply_btn.setEnabled(bool(editable and self.pending))
        if active:
            count = len(self.session.changes)
            self.file_status.setText(f"{self.session.original.page_count} 页  ·  已修改 {count} 处")
            dirty = self.session.dirty or self.pending
            self.setWindowTitle(f"{'* ' if dirty else ''}{self.session.path.name} — 面单工坊 {__version__}")
            self.save_btn.setText("另存为 PDF" + (" *" if dirty else ""))

    def confirm_pending(self):
        if not self.pending:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("当前文字尚未应用")
        box.setText("要先应用右侧正在编辑的文字吗？")
        apply_button = box.addButton("应用修改", QMessageBox.ButtonRole.AcceptRole)
        discard_button = box.addButton("放弃这次输入", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == apply_button:
            return self.apply()
        if box.clickedButton() == discard_button:
            self.populate_form()
            return True
        return False

    def confirm_leave(self):
        if not self.confirm_pending():
            return False
        if not self.session or not self.session.dirty:
            return True
        answer = QMessageBox.question(self, "尚有未保存的修改", "是否将修改另存为 PDF？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def save(self):
        if not self.session or not self.confirm_pending():
            return False
        suggested = self.session.path.with_name(self.session.path.stem + "_已修改.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "另存为 PDF（保留原文件）", str(suggested), "PDF 文件 (*.pdf)")
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        error = None
        try:
            destination = self.session.save_as(path)
        except Exception as exc:
            error = exc
        finally:
            QApplication.restoreOverrideCursor()
        if error:
            self.show_error(f"保存失败：{error}")
            return False
        self.update_state()
        self.statusBar().showMessage(f"已保存：{destination}")
        QMessageBox.information(self, "保存完成", f"修改后的 PDF 已保存：\n{destination}\n\n原文件已保留。")
        return True

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile().lower().endswith(".pdf")]
        if paths:
            self.open_pdf(paths[0])
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.confirm_leave():
            if self.session:
                self.session.close()
            event.accept()
        else:
            event.ignore()


def QLineEditEchoMode():
    from PySide6.QtWidgets import QLineEdit
    return QLineEdit.EchoMode.Password


def configure_app(app):
    # Explicit registration also supports rendering with Qt's offscreen platform.
    for filename in ["msyh.ttc", "msyhbd.ttc"]:
        path = Path("C:/Windows/Fonts") / filename
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setApplicationName("面单工坊")
    app.setOrganizationName("LabelEditor")
    app.setStyle("Fusion")
    family = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei"
    app.setFont(QFont(family, 10))
    app.setStyleSheet(STYLE.replace("Microsoft YaHei", family))


def run_app():
    app = QApplication(sys.argv)
    configure_app(app)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        QTimer.singleShot(0, lambda: window.open_pdf(sys.argv[1]))
    return app.exec()
