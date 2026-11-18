"""Build a small embedded-subset regression fixture for the offline exe test."""
from pathlib import Path
from io import BytesIO
import pymupdf as fitz
from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]


def make_sample():
    doc = fitz.open()
    for style in ["Regular", "Bold", "Italic", "BoldItalic"]:
        tt = TTFont(ROOT / "assets/fonts/Arimo" / f"Arimo-{style}.ttf")
        options = subset.Options()
        options.name_IDs = ["*"]
        reducer = subset.Subsetter(options=options)
        reducer.populate(text="7.340 KG")
        reducer.subset(tt)
        stream = BytesIO()
        tt.save(stream)
        tt.close()
        page = doc.new_page(width=283, height=180)
        page.insert_text((20, 30), f"Arimo {style}", fontsize=15)
        page.draw_rect(fitz.Rect(20, 50, 263, 90), width=.5)
        page.insert_text((30, 70), "Weight:", fontsize=10)
        page.insert_font(fontname="original", fontbuffer=stream.getvalue())
        page.insert_text((170, 70), "7.340 KG", fontname="original", fontsize=7.11)
        page.insert_text((20, 115), "Only the original glyphs are embedded.", fontsize=9)
        page.insert_text((20, 135), "Edit the weight to 7.570 KG to test completion.", fontsize=9)
    doc.save(ROOT / "assets/font-check.pdf")
    doc.close()


if __name__ == "__main__":
    make_sample()
