"""PDF editing independent of the UI. Source bytes are always immutable.

Edits remove only selected text, then insert replacement text. Images and vector
graphics are explicitly excluded from redaction. Ambiguous overlaps are refused.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import os
import sys
import re
import tempfile
from io import BytesIO

import pymupdf as fitz
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from .fonts import normalize, buffer_identity, matches, local_faces


class EditError(Exception):
    pass


class FontUnavailable(EditError):
    pass


class TextOverflow(EditError):
    pass


@dataclass(frozen=True)
class TextRun:
    key: str
    page: int
    text: str
    bbox: tuple
    origin: tuple
    font: str
    size: float
    color: int
    alpha: int
    chars: tuple
    direction: tuple
    reason: str = ""
    flags: int = 0


@dataclass(frozen=True)
class Edit:
    text: str
    size: float
    width: float
    height: float
    font: str = "original"
    wrap: bool = False


@dataclass
class FontChoice:
    font: fitz.Font
    label: str
    builtin: str | None = None
    buffer: bytes | None = None
    source: str = "PDF 原字体"


def normalized_font(name: str) -> str:
    return normalize(name)


BASE_FONTS = {
    "helvetica": "helv", "helveticabold": "hebo",
    "helveticaoblique": "heit", "helveticaboldoblique": "hebi",
    "timesroman": "tiro", "timesbold": "tibo", "timesitalic": "tiit",
    "timesbolditalic": "tibi", "courier": "cour", "courierbold": "cobo",
    "courieroblique": "coit", "courierboldoblique": "cobi",
}
FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
SYSTEM_FONTS = {
    "yahei": ("微软雅黑", FONT_DIR / "msyh.ttc"),
    "simsun": ("宋体", FONT_DIR / "simsun.ttc"),
    "simhei": ("黑体", FONT_DIR / "simhei.ttf"),
    "arial": ("Arial", FONT_DIR / "arial.ttf"),
}
if sys.platform == "darwin":
    SYSTEM_FONTS = {
        "pingfang": ("苹方 / PingFang", Path("/System/Library/Fonts/PingFang.ttc")),
        "songti": ("宋体 / Songti", Path("/System/Library/Fonts/Supplemental/Songti.ttc")),
        "arial": ("Arial", Path("/System/Library/Fonts/Supplemental/Arial.ttf")),
    }


class PdfSession:
    def __init__(self, path: str | Path, password: str = ""):
        self.path = Path(path).resolve()
        self.source = self.path.read_bytes()
        self.password = password
        self.original = self._open_source()
        if not self.original.is_pdf:
            self.original.close()
            raise EditError("请选择 PDF 文件。")
        if self.original.page_count == 0:
            raise EditError("这份 PDF 没有页面。")
        self.signed = self.original.get_sigflags() > 0
        self.changes: dict[str, Edit] = {}
        self.saved_changes: dict[str, Edit] = {}
        self.undo_stack: list[dict[str, Edit]] = []
        self.redo_stack: list[dict[str, Edit]] = []
        self._runs: dict[int, list[TextRun]] = {}
        self._fonts: dict[tuple, FontChoice] = {}
        self._embedded: dict[tuple, list[FontChoice]] = {}
        self._preview: fitz.Document | None = None

    def _open_source(self):
        doc = fitz.open(stream=self.source, filetype="pdf")
        if doc.needs_pass and not doc.authenticate(self.password):
            doc.close()
            raise EditError("需要密码或密码不正确。")
        return doc

    @property
    def dirty(self):
        return self.changes != self.saved_changes

    def close(self):
        if self._preview is not None:
            self._preview.close()
        self.original.close()

    def runs(self, page_number: int) -> list[TextRun]:
        if page_number in self._runs:
            return self._runs[page_number]
        page = self.original[page_number]
        runs = []
        images = [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
        annots = list(page.annots() or [])
        existing_redactions = any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in annots)
        invisible = [fitz.Rect(t["bbox"]) for t in page.get_texttrace()
                     if t.get("type") == 3 or t.get("opacity", 1) == 0]
        for bi, block in enumerate(page.get_text("rawdict", flags=fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES)["blocks"]):
            for li, line in enumerate(block.get("lines", [])):
                for si, span in enumerate(line["spans"]):
                    text = "".join(c["c"] for c in span["chars"])
                    if not text.strip():
                        continue
                    bbox = fitz.Rect(span["bbox"])
                    reason = ""
                    if self.signed:
                        reason = "此文件带有数字签名，第一版仅支持查看。"
                    elif not self.original.permissions & fitz.PDF_PERM_MODIFY:
                        reason = "此文件设置了禁止修改权限。"
                    elif existing_redactions:
                        reason = "此页含有未执行的涂黑批注，为避免误处理，暂不支持编辑。"
                    elif tuple(line["dir"]) != (1.0, 0.0) or line.get("wmode", 0):
                        reason = "第一版支持横排文字；此段为旋转或竖排文字。"
                    elif any((bbox & r).get_area() > bbox.get_area() * .8 for r in invisible):
                        reason = "这段是隐藏文字层，修改它无法改变面单图片。"
                    elif any((bbox & r).get_area() > bbox.get_area() * .8 for r in images):
                        reason = "文字与图片重叠，可能是扫描件的识别层，暂不支持直接修改。"
                    elif span.get("alpha", 255) == 0:
                        reason = "这段文字不可见，暂不支持修改。"
                    runs.append(TextRun(
                        f"{page_number}:{bi}:{li}:{si}", page_number, text,
                        tuple(bbox), tuple(span["origin"]), span["font"],
                        span["size"], span["color"], span.get("alpha", 255),
                        tuple(tuple(c["bbox"]) for c in span["chars"]),
                        tuple(line["dir"]), reason, span.get("flags", 0)))
        self._runs[page_number] = runs
        return runs

    def default_edit(self, run: TextRun) -> Edit:
        rect = fitz.Rect(run.bbox)
        return Edit(run.text, run.size, rect.width, rect.height)

    def get_edit(self, run: TextRun) -> Edit:
        return self.changes.get(run.key, self.default_edit(run))

    def _recover_unicode_font(self, data: bytes, xref: int, name: str) -> bytes:
        """Repair remapped subset cmaps without changing the embedded outlines.

        Some PDF producers put Chinese glyphs at arbitrary byte-code positions.
        Text traces provide the original Unicode -> glyph ID relationship. Reuse
        that relationship across pages referencing this exact font object.
        """
        font = fitz.Font(fontbuffer=data)
        mapping = {}
        for pn in range(self.original.page_count):
            if not any(f[0] == xref for f in self.original.get_page_fonts(pn, full=True)):
                continue
            for trace in self.original[pn].get_texttrace():
                if normalized_font(trace["font"]) != normalized_font(name):
                    continue
                for codepoint, glyph, *_ in trace["chars"]:
                    if glyph > 0 and 0 < codepoint <= 0x10FFFF and codepoint != 0xFFFD:
                        if codepoint in mapping and mapping[codepoint] != glyph:
                            raise FontUnavailable("原字体的字符映射不唯一，请选择替代字体。")
                        mapping[codepoint] = glyph
        if all(font.has_glyph(codepoint) == glyph for codepoint, glyph in mapping.items()):
            return data
        try:
            tt = TTFont(BytesIO(data), recalcTimestamp=False)
            glyphs = tt.getGlyphOrder()
            cmap = dict(tt.getBestCmap() or {})
            cmap.update({codepoint: glyphs[gid] for codepoint, gid in mapping.items() if gid < len(glyphs)})
            table = newTable("cmap")
            table.tableVersion = 0
            subtable = CmapSubtable.newSubtable(12)
            subtable.platformID = 3
            subtable.platEncID = 10
            subtable.language = 0
            subtable.cmap = cmap
            table.tables = [subtable]
            tt["cmap"] = table
            stream = BytesIO()
            tt.save(stream)
            tt.close()
            return stream.getvalue()
        except Exception:
            # Unsupported non-SFNT fonts remain subject to explicit glyph checks.
            return data

    @staticmethod
    def missing_chars(choice: FontChoice, text: str):
        return sorted({c for c in text if c not in "\n\r\t" and not choice.font.has_glyph(ord(c))})

    def embedded_fonts(self, run: TextRun) -> list[FontChoice]:
        """Search all same-face subsets, retaining current-page resources first."""
        key = (run.page, run.font, run.flags)
        if key in self._embedded:
            return self._embedded[key]
        choices, seen = [], set()
        target = normalized_font(run.font)
        reference = None
        for pn in [run.page] + [n for n in range(self.original.page_count) if n != run.page]:
            for xref, ext, kind, base, resource, *rest in self.original.get_page_fonts(pn, full=True):
                if not xref or xref in seen:
                    continue
                seen.add(xref)
                try:
                    data = self.original.extract_font(xref)[3]
                    if not data:
                        continue
                    info = buffer_identity(data)
                    exact = normalized_font(base) == target
                    if info is not None:
                        if not matches(info, run.font, run.flags, reference):
                            continue
                    elif not exact:
                        continue
                    if pn == run.page and reference is None and info is not None:
                        reference = info
                    data = self._recover_unicode_font(data, xref, run.font)
                    choices.append(FontChoice(fitz.Font(fontbuffer=data), run.font, buffer=data,
                        source="PDF 原字体" if pn == run.page else "PDF 其他页面同款字体"))
                except Exception:
                    continue
        self._embedded[key] = choices
        return choices

    def resolve_font(self, run: TextRun, edit: Edit) -> FontChoice:
        # Coverage is part of the cache key: a previously used subset must not
        # prevent automatic completion when the next edit introduces new glyphs.
        key = (run.page, run.font, run.flags, edit.font, frozenset(edit.text))
        if key in self._fonts:
            return self._fonts[key]
        if edit.font != "original":
            label, path = SYSTEM_FONTS.get(edit.font, (Path(edit.font).stem, Path(edit.font)))
            try:
                data = path.read_bytes()
                choice = FontChoice(fitz.Font(fontbuffer=data), label, buffer=data, source="手动指定字体")
            except Exception as exc:
                raise FontUnavailable(f"无法载入字体「{label}」。请选择另一个字体文件。") from exc
            missing = self.missing_chars(choice, edit.text)
            if missing:
                raise FontUnavailable(f"字体「{choice.label}」不包含这些字符：{' '.join(missing[:8])}。")
        else:
            choice = None
            target = normalized_font(run.font)
            embedded = self.embedded_fonts(run)
            for candidate in embedded:
                if not self.missing_chars(candidate, edit.text):
                    choice = candidate
                    break
            if choice is None and target in BASE_FONTS:
                name = BASE_FONTS[target]
                candidate = FontChoice(fitz.Font(fontname=name), run.font, builtin=name)
                if not self.missing_chars(candidate, edit.text):
                    choice = candidate
            if choice is None:
                reference = buffer_identity(embedded[0].buffer) if embedded else None
                for face in local_faces():
                    if not matches(face.identity, run.font, run.flags, reference):
                        continue
                    try:
                        data = face.read()
                        candidate = FontChoice(fitz.Font(fontbuffer=data), run.font, buffer=data, source=face.source)
                        if not self.missing_chars(candidate, edit.text):
                            choice = candidate
                            break
                    except Exception:
                        continue
            if choice is None:
                raise FontUnavailable(f"未找到能显示全部新文字的完整「{run.font}」字体。\n"
                    "已检查 PDF 全部页面、本机和内置字库，未改用其他字体。\n"
                    "请安装该字体的完整版本后重新打开程序，或通过「补充字体文件」提供同款字体。")
        self._fonts[key] = choice
        return choice

    def layout(self, run: TextRun, edit: Edit):
        if not edit.text:
            return None, [], fitz.Rect(run.bbox)
        choice = self.resolve_font(run, edit)
        if not 3 <= edit.size <= 144 or edit.width <= 0 or edit.height <= 0:
            raise EditError("字号须在 3–144 pt 之间，编辑区域宽高须大于 0。")
        if any(ord(c) < 32 and c not in "\n\r" for c in edit.text):
            raise EditError("文字包含不支持的控制字符，请删除制表符等特殊字符。")
        x, y = run.origin
        original = fitz.Rect(run.bbox)
        # Preserve the original baseline. Replacement line spacing follows the font.
        ascent = max(.5, choice.font.ascender)
        descent = max(.1, -choice.font.descender)
        line_height = max(1.2, ascent + descent) * edit.size
        lines = []
        for paragraph in edit.text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if not edit.wrap or not paragraph:
                lines.append(paragraph)
                continue
            current = ""
            for char in paragraph:
                if current and choice.font.text_length(current + char, fontsize=edit.size) > edit.width + .1:
                    lines.append(current)
                    current = char
                else:
                    current += char
            lines.append(current)
        widths = [choice.font.text_length(t, fontsize=edit.size) for t in lines]
        if max(widths, default=0) > edit.width + .25:
            raise TextOverflow("新文字超出编辑区域宽度。请增加宽度、启用换行，或点击「缩小至适合」。")
        bottom = y + (len(lines) - 1) * line_height + descent * edit.size
        if bottom > original.y0 + edit.height + .6:
            raise TextOverflow("新文字超出编辑区域高度。请增加高度或缩小字号。")
        rect = fitz.Rect(x, min(original.y0, y - ascent * edit.size),
                         x + max(widths, default=0), bottom)
        page = self.original[run.page]
        bounds = page.rect * page.derotation_matrix
        if not fitz.Rect(bounds.x0 - .5, bounds.y0 - .5, bounds.x1 + .5, bounds.y1 + .5).contains(rect):
            raise TextOverflow("修改后的文字超出了页面边界。")
        return choice, [(fitz.Point(x, y + i * line_height), t) for i, t in enumerate(lines)], rect

    def validate(self, run: TextRun, edit: Edit, changes=None):
        if run.reason:
            raise EditError(run.reason)
        if edit == self.default_edit(run):
            return
        changes = self.changes if changes is None else changes
        choice, lines, new_rect = self.layout(run, edit)
        old_rect = fitz.Rect(run.bbox)
        # Any neighbouring glyph intersecting the removal rectangle could be lost.
        for other in self.runs(run.page):
            if other.key == run.key:
                continue
            if any((old_rect & fitz.Rect(c)).get_area() > .02 for c in other.chars):
                raise EditError("原文字与其他文字重叠，无法安全单独替换这段内容。")
            other_rect = fitz.Rect(other.bbox)
            if other.key in changes:
                _, _, other_rect = self.layout(other, changes[other.key])
            if edit.text and (new_rect & other_rect).get_area() > .2:
                raise EditError("新文字会与附近文字重叠。请缩小字号或调整编辑区域。")
        page = self.original[run.page]
        for image in page.get_image_info():
            if edit.text and (new_rect & fitz.Rect(image["bbox"])).get_area() > .2:
                raise EditError("新文字会覆盖图片或条码，请缩小字号或减少文字。")
        for drawing in page.get_drawings():
            fill = drawing.get("fill")
            if fill is not None and sum(fill[:3]) / len(fill[:3]) < .7:
                rect = fitz.Rect(drawing["rect"])
                if edit.text and (new_rect & rect).get_area() > .3:
                    raise EditError("新文字与深色图形或条码重叠，已阻止修改。")
        affected = old_rect | new_rect if edit.text else old_rect
        for a in page.annots() or []:
            if (affected & a.rect).get_area() > .2:
                raise EditError("编辑区域与批注重叠，暂不支持修改。")
        for link in page.get_links():
            if (affected & link["from"]).get_area() > .2:
                raise EditError("编辑区域与链接重叠，暂不支持修改。")
        for widget in page.widgets() or []:
            if (affected & widget.rect).get_area() > .2:
                raise EditError("编辑区域与表单控件重叠，暂不支持修改。")

    def shrink(self, run: TextRun, edit: Edit) -> Edit:
        for tenth in range(round(edit.size * 10), 29, -1):
            candidate = replace(edit, size=tenth / 10)
            try:
                self.layout(run, candidate)
                return candidate
            except TextOverflow:
                continue
        raise TextOverflow("缩小至 3 pt 仍无法放入，请扩大编辑区域或减少内容。")

    def apply(self, run: TextRun, edit: Edit):
        if edit == self.get_edit(run):
            return
        self.validate(run, edit)
        updated = dict(self.changes)
        if edit == self.default_edit(run):
            updated.pop(run.key, None)
        else:
            updated[run.key] = edit
        # Render the actual export document before committing the history entry.
        preview = self.build(updated)
        self.undo_stack.append(dict(self.changes))
        self.redo_stack.clear()
        self.changes = updated
        self._invalidate()
        self._preview = preview

    def _invalidate(self):
        if self._preview is not None:
            self._preview.close()
        self._preview = None

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(dict(self.changes))
            self.changes = self.undo_stack.pop()
            self._invalidate()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(dict(self.changes))
            self.changes = self.redo_stack.pop()
            self._invalidate()

    def build(self, changes=None):
        changes = self.changes if changes is None else changes
        doc = self._open_source()
        try:
            page_numbers = sorted({int(k.split(":")[0]) for k in changes})
            for pn in page_numbers:
                page = doc[pn]
                selected = [r for r in self.runs(pn) if r.key in changes]
                layouts = []
                for run in selected:
                    edit = changes[run.key]
                    self.validate(run, edit, changes)
                    choice, lines, rect = self.layout(run, edit)
                    layouts.append((run, edit, choice, lines))
                    page.add_redact_annot(fitz.Rect(run.bbox), fill=False, cross_out=False)
                page.apply_redactions(images=0, graphics=0, text=0)
                for i, (run, edit, choice, lines) in enumerate(layouts):
                    if choice is None:
                        continue
                    name = choice.builtin or f"LEFont{pn}_{i}"
                    if not choice.builtin:
                        existing_names = {f[4] for f in page.get_fonts(full=True)}
                        while name in existing_names:
                            name += "x"
                        page.insert_font(fontname=name, fontbuffer=choice.buffer)
                    color = ((run.color >> 16 & 255) / 255,
                             (run.color >> 8 & 255) / 255, (run.color & 255) / 255)
                    for point, text in lines:
                        if text:
                            page.insert_text(point, text, fontsize=edit.size, fontname=name,
                                             color=color, fill_opacity=run.alpha / 255,
                                             overlay=True)
            return doc
        except Exception:
            doc.close()
            raise

    def preview(self):
        if self._preview is None:
            self._preview = self.build()
        return self._preview

    def save_as(self, destination: str | Path):
        destination = Path(destination).resolve()
        if destination == self.path or (destination.exists() and os.path.samefile(destination, self.path)):
            raise EditError("请使用新的文件名保存，原文件会始终保留。")
        doc = self.preview()
        fd, temp = tempfile.mkstemp(prefix=".label-editor-", suffix=".pdf", dir=destination.parent)
        os.close(fd)
        try:
            if not self.changes:
                # A plain copy must also preserve any existing digital signature.
                Path(temp).write_bytes(self.source)
            else:
                doc.save(temp, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            with fitz.open(temp) as check:
                if check.needs_pass and not check.authenticate(self.password):
                    raise EditError("导出验证失败：无法重新打开加密文件。")
                if check.page_count != self.original.page_count:
                    raise EditError("导出验证失败：页数发生变化。")
                for pn in range(check.page_count):
                    if check[pn].rect != self.original[pn].rect:
                        raise EditError("导出验证失败：页面尺寸发生变化。")
            os.replace(temp, destination)
            self.saved_changes = dict(self.changes)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return destination
