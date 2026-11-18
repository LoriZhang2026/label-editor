from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pymupdf as fitz
import pytest
from fontTools import subset
from fontTools.ttLib import TTFont, TTCollection
from label_editor.core import PdfSession, FontUnavailable
from label_editor.fonts import bundled_font_dir, identity, local_faces, matches


def arimo(style="Regular"):
    return bundled_font_dir() / "Arimo" / f"Arimo-{style}.ttf"


def limited_font(chars, style="Regular", family=None):
    font = TTFont(arimo(style))
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    sub = subset.Subsetter(options=options)
    sub.populate(text=chars)
    sub.subset(font)
    if family:
        for record in font["name"].names:
            if record.nameID in (1, 3, 4, 6, 16):
                record.string = family.encode(record.getEncoding())
    stream = BytesIO()
    font.save(stream)
    font.close()
    return stream.getvalue()


def make_fixture(path, style="Regular", family=None, extra_page=None):
    doc = fitz.open()
    p = doc.new_page(width=283, height=300)
    p.insert_font(fontname="original", fontbuffer=limited_font("7.340 KG", style, family))
    p.insert_text((170, 70), "7.340 KG", fontname="original", fontsize=7.11)
    p.draw_rect(fitz.Rect(15, 20, 265, 280), width=.5)
    p.insert_text((15, 110), "ORDER 58723158263283743", fontsize=9)
    if extra_page:
        p = doc.new_page(width=283, height=300)
        p.insert_font(fontname="other", fontbuffer=limited_font(extra_page, style, family))
        p.insert_text((20, 70), extra_page, fontname="other", fontsize=7.11)
    doc.save(path)
    doc.close()


@pytest.mark.parametrize("style", ["Regular", "Bold", "Italic", "BoldItalic"])
def test_arimo_missing_digit_automatically_uses_same_face(tmp_path, style):
    path = tmp_path / "original.pdf"
    make_fixture(path, style)
    s = PdfSession(path)
    try:
        run = s.runs(0)[0]
        edit = replace(s.default_edit(run), text="7.570 KG")
        # Prime the resolver with the smaller subset first (regression for caching).
        first = s.resolve_font(run, s.default_edit(run))
        assert not first.font.has_glyph(ord("5"))
        choice = s.resolve_font(run, edit)
        assert choice.source == "内置同款字体"
        assert "Arimo" in choice.font.name
        expected = identity(TTFont(arimo(style)))
        actual = identity(TTFont(BytesIO(choice.buffer)))
        assert actual.weight == expected.weight and actual.italic == expected.italic
        s.apply(run, edit)
        dest = s.save_as(tmp_path / "changed.pdf")
        with fitz.open(dest) as out:
            text = out[0].get_text().replace("\xa0", " ")
            assert "7.570 KG" in text and "7.340 KG" not in text
            new = next(sp for b in out[0].get_text("dict")["blocks"] for ln in b.get("lines", [])
                       for sp in ln["spans"] if "7.570" in sp["text"])
            assert new["font"] == run.font
            assert new["size"] == pytest.approx(run.size)
            assert new["origin"] == pytest.approx(run.origin, abs=.001)
            # Compare to rendering produced by the full original face, independently
            # of the editor's font resolver and replacement logic.
            reference = fitz.open()
            page = reference.new_page(width=283, height=300)
            page.insert_font(fontname="truth", fontfile=str(arimo(style)))
            page.insert_text(run.origin, edit.text, fontname="truth", fontsize=run.size)
            clip = fitz.Rect(169, 60, 220, 75)
            assert out[0].get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip).samples == \
                page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip).samples
            reference.close()
            clip = fitz.Rect(0, 80, 283, 300)
            assert out[0].get_pixmap(clip=clip).samples == s.original[0].get_pixmap(clip=clip).samples
    finally:
        s.close()


def test_reuse_same_font_from_other_page_before_local_catalog(tmp_path):
    path = tmp_path / "other-page.pdf"
    make_fixture(path, family="PrivateLabelFace", extra_page="7.570 KG")
    s = PdfSession(path)
    try:
        run = s.runs(0)[0]
        edit = replace(s.default_edit(run), text="7.570 KG")
        choice = s.resolve_font(run, edit)
        assert choice.source == "PDF 其他页面同款字体"
        s.apply(run, edit)
        assert "7.570 KG" in s.preview()[0].get_text().replace("\xa0", " ")
    finally:
        s.close()


def test_never_silently_substitute_unavailable_family(tmp_path):
    path = tmp_path / "private.pdf"
    make_fixture(path, family="PrivateLabelFace")
    s = PdfSession(path)
    try:
        run = s.runs(0)[0]
        with pytest.raises(FontUnavailable, match="未改用其他字体"):
            s.apply(run, replace(s.default_edit(run), text="7.570 KG"))
        assert not s.changes
    finally:
        s.close()


def test_missing_arimo_char_does_not_switch_to_another_family(tmp_path):
    path = tmp_path / "arimo.pdf"
    make_fixture(path)
    s = PdfSession(path)
    try:
        run = s.runs(0)[0]
        with pytest.raises(FontUnavailable, match="未改用其他字体"):
            s.resolve_font(run, replace(s.default_edit(run), text="中文"))
    finally:
        s.close()


def test_automatic_ttc_matching_selects_the_correct_face(tmp_path, monkeypatch):
    from label_editor import fonts
    collection = TTCollection()
    collection.fonts = [TTFont(arimo("Regular")), TTFont(arimo("Bold"))]
    collection.save(tmp_path / "Test.ttc")
    collection.close()
    monkeypatch.setattr(fonts, "system_font_dirs", lambda: [tmp_path])
    local_faces.cache_clear()
    faces = [f for f in local_faces() if f.path.name == "Test.ttc"]
    local_faces.cache_clear()
    assert len(faces) == 2
    second = faces[1]
    result = identity(TTFont(BytesIO(second.read())))
    assert result.family == second.identity.family
    assert result.weight == 700 and faces[0].identity.weight == 400


def test_macos_font_search_roots(monkeypatch):
    from label_editor import fonts
    monkeypatch.setattr(fonts.sys, "platform", "darwin")
    roots = fonts.system_font_dirs()
    assert Path("/System/Library/Fonts") in roots
    assert Path("/Library/Fonts") in roots
    assert Path.home() / "Library/Fonts" in roots
