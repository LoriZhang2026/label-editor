from dataclasses import replace
from pathlib import Path
import hashlib
import math

import pymupdf as fitz
import pytest

from label_editor.core import PdfSession, EditError, FontUnavailable, TextOverflow


def make_pdf(path, rotated=False, embedded=False):
    doc = fitz.open()
    page = doc.new_page(width=283, height=425)
    page.draw_rect(fitz.Rect(5, 5, 278, 420), color=(0, 0, 0))
    page.draw_rect(fitz.Rect(15, 40, 260, 65), color=None, fill=(.95, .97, 1))
    font = "helv"
    if embedded:
        page.insert_font(fontname="custom", fontfile="C:/Windows/Fonts/arial.ttf")
        font = "custom"
    page.insert_text((20, 58), "138 0000 1234", fontname=font, fontsize=11)
    page.insert_text((20, 95), "KEEP THIS CONTENT", fontsize=10)
    for i in range(30):
        page.draw_rect(fitz.Rect(20 + i * 5, 200, 22 + i * 5, 245), fill=(0, 0, 0), color=None)
    page.insert_text((20, 270), "BARCODE-1234", fontsize=10)
    annot = page.add_text_annot((260, 350), "Preserve annotation")
    if rotated:
        page.set_rotation(90)
    doc.new_page(width=283, height=425).insert_text((30, 50), "SECOND PAGE UNCHANGED")
    doc.set_metadata({"title": "Regression fixture", "author": "Test"})
    doc.set_toc([[1, "Page one", 1], [1, "Page two", 2]])
    doc.save(path)
    doc.close()


@pytest.fixture
def session(tmp_path):
    path = tmp_path / "source.pdf"
    make_pdf(path)
    s = PdfSession(path)
    yield s
    s.close()


def number_run(session):
    return next(r for r in session.runs(0) if r.text.replace("\xa0", " ") == "138 0000 1234")


def test_export_changes_only_target_and_preserves_original(session, tmp_path):
    before_hash = hashlib.sha256(session.path.read_bytes()).hexdigest()
    run = number_run(session)
    edit = replace(session.default_edit(run), text="139 5555 6789")
    session.apply(run, edit)
    output = session.save_as(tmp_path / "edited.pdf")
    assert hashlib.sha256(session.path.read_bytes()).hexdigest() == before_hash
    with fitz.open(output) as saved:
        assert "139 5555 6789" in saved[0].get_text()
        assert "138 0000 1234" not in saved[0].get_text()
        assert "KEEP THIS CONTENT" in saved[0].get_text()
        assert saved.metadata["title"] == "Regression fixture"
        assert saved.get_toc() == session.original.get_toc()
        assert len(list(saved[0].annots())) == 1
        assert saved[1].get_pixmap().samples == session.original[1].get_pixmap().samples
        before = session.original[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        after = saved[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        _, _, region = session.layout(run, edit)
        region = (region | fitz.Rect(run.bbox)) + (-2, -2, 2, 2)
        left, top, right, bottom = [int(v * 2) for v in region]
        a, b = before.samples, after.samples
        changed_pixels = 0
        for y in range(before.height):
            for x in range(before.width):
                offset = (y * before.width + x) * 3
                if a[offset:offset + 3] != b[offset:offset + 3]:
                    changed_pixels += 1
                    assert left <= x <= right and top <= y <= bottom, (x, y)
        assert changed_pixels > 0


def test_undo_redo_and_saved_state(session, tmp_path):
    run = number_run(session)
    session.apply(run, replace(session.default_edit(run), text="139 5555 6789"))
    assert session.dirty
    session.undo()
    assert not session.dirty
    assert "138 0000 1234" in session.preview()[0].get_text()
    session.redo()
    assert session.dirty
    session.save_as(tmp_path / "edited.pdf")
    assert not session.dirty
    session.undo()
    assert session.dirty
    session.redo()
    assert not session.dirty


def test_overflow_and_shrink(session):
    run = number_run(session)
    edit = replace(session.default_edit(run), text="139 5555 6789 EXTENSION")
    with pytest.raises(TextOverflow):
        session.apply(run, edit)
    assert not session.changes
    smaller = session.shrink(run, edit)
    assert smaller.size < edit.size
    session.apply(run, smaller)


def test_missing_glyph_is_explicit_and_replacement_is_supported(session):
    run = number_run(session)
    edit = replace(session.default_edit(run), text="张三")
    with pytest.raises(FontUnavailable):
        session.apply(run, edit)
    session.apply(run, replace(edit, font="yahei", height=25))
    assert "张三" in session.preview()[0].get_text()


def test_no_overwrite_or_hardlink_overwrite(session, tmp_path):
    with pytest.raises(EditError):
        session.save_as(session.path)
    alias = tmp_path / "alias.pdf"
    alias.hardlink_to(session.path)
    with pytest.raises(EditError):
        session.save_as(alias)


def test_deletion_removes_text_not_background(session):
    run = number_run(session)
    session.apply(run, replace(session.default_edit(run), text=""))
    assert "138 0000 1234" not in session.preview()[0].get_text()
    before = session.original[0].get_pixmap(clip=fitz.Rect(15, 40, 260, 45)).samples
    after = session.preview()[0].get_pixmap(clip=fitz.Rect(15, 40, 260, 45)).samples
    assert before == after


def test_rotated_page_and_embedded_font(tmp_path):
    path = tmp_path / "rotated.pdf"
    make_pdf(path, rotated=True, embedded=True)
    s = PdfSession(path)
    try:
        run = number_run(s)
        s.apply(run, replace(s.default_edit(run), text="139 5555 6789"))
        dest = s.save_as(tmp_path / "rotated-edited.pdf")
        with fitz.open(dest) as doc:
            assert doc[0].rotation == 90
            assert "139 5555 6789" in doc[0].get_text().replace("\xa0", " ")
            new_run = next(sp for b in doc[0].get_text("dict")["blocks"] for l in b.get("lines", [])
                           for sp in l["spans"] if "139" in sp["text"])
            assert new_run["font"] == run.font
    finally:
        s.close()


def test_protect_neighboring_text_and_barcode(session):
    run = number_run(session)
    with pytest.raises(EditError, match="重叠"):
        session.apply(run, replace(session.default_edit(run), text="1\n2\n3\n4", height=90))
    barcode_label = next(r for r in session.runs(0) if r.text == "BARCODE-1234")
    with pytest.raises(EditError):
        session.apply(barcode_label, replace(session.default_edit(barcode_label), size=60, width=260, height=70))


def test_existing_redactions_are_not_executed(tmp_path):
    p = tmp_path / "redaction.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((20, 40), "Text to keep")
    page.add_redact_annot(fitz.Rect(20, 30, 90, 45))
    doc.save(p)
    doc.close()
    s = PdfSession(p)
    try:
        run = s.runs(0)[0]
        assert run.reason
        with pytest.raises(EditError):
            s.apply(run, replace(s.default_edit(run), text="Replaced"))
        assert "Text to keep" in s.preview()[0].get_text()
    finally:
        s.close()


def test_scanned_pdf_readonly(tmp_path):
    p = tmp_path / "scan.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 40), "Scanned text")
    image = page.get_pixmap().tobytes("png")
    page.insert_image(page.rect, stream=image)
    doc.save(p)
    doc.close()
    s = PdfSession(p)
    try:
        run = s.runs(0)[0]
        assert run.reason
    finally:
        s.close()


def test_encrypted_export_keeps_password(tmp_path):
    p = tmp_path / "encrypted.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((20, 40), "12345")
    doc.save(p, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret",
             permissions=fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_PRINT)
    doc.close()
    with pytest.raises(EditError):
        PdfSession(p)
    s = PdfSession(p, "secret")
    try:
        r = s.runs(0)[0]
        s.apply(r, replace(s.default_edit(r), text="67890"))
        dest = s.save_as(tmp_path / "encrypted-edited.pdf")
        with fitz.open(dest) as check:
            assert check.needs_pass
            assert check.authenticate("secret")
            assert "67890" in check[0].get_text()
    finally:
        s.close()


def test_chinese_subset_font_reuses_actual_embedded_glyphs(tmp_path):
    sample = Path(__file__).resolve().parents[1] / "assets" / "示例面单.pdf"
    s = PdfSession(sample)
    try:
        run = next(r for r in s.runs(0) if r.text == "收件人：张三")
        edit = replace(s.default_edit(run), text="收件人：李四")
        choice = s.resolve_font(run, edit)
        assert choice.buffer and choice.label == run.font
        s.apply(run, edit)
        out = s.save_as(tmp_path / "chinese.pdf")
        with fitz.open(out) as check:
            assert "收件人：李四" in check[0].get_text()
            assert "收件人：张三" not in check[0].get_text()
            assert check[1].get_pixmap().samples == s.original[1].get_pixmap().samples
        # Previously missing subset glyphs are completed from the same installed face.
        completed = s.resolve_font(run, replace(edit, text="收件人：龘"))
        assert completed.source == "本机同款字体"
        assert "YaHei" in completed.font.name
    finally:
        s.close()


def test_unmodified_export_is_exact_copy(session, tmp_path):
    output = session.save_as(tmp_path / "copy.pdf")
    assert output.read_bytes() == session.path.read_bytes()


def test_reopening_export_does_not_reuse_wrong_font_resource(session, tmp_path):
    run = number_run(session)
    session.apply(run, replace(session.default_edit(run), text="张三", font="yahei", height=25))
    dest = session.save_as(tmp_path / "first.pdf")
    second = PdfSession(dest)
    try:
        other = next(r for r in second.runs(0) if r.text == "KEEP THIS CONTENT")
        second.apply(other, replace(second.default_edit(other), text="李四", font="simsun", height=25))
        text = second.preview()[0].get_text()
        assert "张三" in text and "李四" in text
        names = [sp["font"] for b in second.preview()[0].get_text("dict")["blocks"]
                 for l in b.get("lines", []) for sp in l["spans"] if sp["text"] == "李四"]
        assert names and "simsun" in names[0].lower()
    finally:
        second.close()
