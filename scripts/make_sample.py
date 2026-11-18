"""Create a fictitious shipping label for the bundled demo and regression tests."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.barcode import code128, qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

ROOT = Path(__file__).resolve().parents[1]


def make_sample(path=None):
    path = path or ROOT / "assets" / "示例面单.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("DemoChinese", "C:/Windows/Fonts/msyh.ttc", subfontIndex=0))
    c = canvas.Canvas(str(path), pagesize=(100 * mm, 150 * mm))
    c.setTitle("面单工坊 · 示例面单（虚构数据）")
    c.setAuthor("Label Editor Demo")
    for pn in range(2):
        c.setStrokeColorRGB(.16, .16, .16)
        c.setLineWidth(.6)
        c.rect(4 * mm, 4 * mm, 92 * mm, 142 * mm)
        c.setFont("DemoChinese", 15)
        c.drawString(8 * mm, 135 * mm, "面单工坊")
        c.setFont("DemoChinese", 9)
        c.drawRightString(92 * mm, 135 * mm, "标准快递 · 示例")
        c.line(4 * mm, 129 * mm, 96 * mm, 129 * mm)
        c.setFont("DemoChinese", 20)
        c.drawString(8 * mm, 116 * mm, "沪  A-018")
        c.setFont("DemoChinese", 9)
        c.drawRightString(92 * mm, 117 * mm, "签收联")
        c.line(4 * mm, 110 * mm, 96 * mm, 110 * mm)
        c.setFont("DemoChinese", 11)
        c.drawString(8 * mm, 101 * mm, "收件人：张三" if pn == 0 else "收件人：李四")
        c.setFont("Helvetica", 11)
        c.drawString(8 * mm, 93 * mm, "138 0000 1234" if pn == 0 else "139 0000 5678")
        c.setFont("DemoChinese", 10)
        c.drawString(8 * mm, 84 * mm, "上海市 浦东新区")
        c.drawString(8 * mm, 77 * mm, "示例路 100 号 2 栋 301 室")
        c.line(4 * mm, 71 * mm, 96 * mm, 71 * mm)
        c.setFont("DemoChinese", 9)
        c.drawString(8 * mm, 64 * mm, "商品：收纳盒 × 2")
        c.drawString(8 * mm, 57 * mm, "备注：请轻放")
        barcode = code128.Code128("DEMO1234567890", barHeight=13 * mm, barWidth=.28 * mm)
        barcode.drawOn(c, 7 * mm, 35 * mm)
        c.setFont("Helvetica", 10)
        c.drawCentredString(50 * mm, 29 * mm, "DEMO1234567890")
        c.line(4 * mm, 25 * mm, 96 * mm, 25 * mm)
        code = qr.QrCodeWidget("LABEL-EDITOR-DEMO-ONLY")
        bounds = code.getBounds()
        d = Drawing(15 * mm, 15 * mm, transform=[15 * mm / (bounds[2] - bounds[0]), 0, 0,
                                                       15 * mm / (bounds[3] - bounds[1]), 0, 0])
        d.add(code)
        renderPDF.draw(d, c, 7 * mm, 7 * mm)
        c.setFont("DemoChinese", 8)
        c.drawString(27 * mm, 17 * mm, "仅用于编辑测试 · 不可寄件")
        c.drawString(27 * mm, 11 * mm, f"第 {pn + 1} 页 / 共 2 页")
        c.showPage()
    c.save()
    return path


if __name__ == "__main__":
    print(make_sample())
