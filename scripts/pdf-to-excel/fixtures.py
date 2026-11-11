"""Reviewed synthetic fixtures: no private data. Explicit expected cells, not engine output."""

import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader, PdfWriter
import io


def generate(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Embed the repository's reviewed CJK font so Linux/macOS generate the same
    # readable scan; an unembedded CID font depends on host font installation.
    pdfmetrics.registerFont(
        TTFont(
            "FixtureCJK",
            str(
                Path(__file__).resolve().parents[2]
                / "vendor-fonts/NotoSansSC-variable.ttf"
            ),
        )
    )
    manifest = []
    for name in [
        "ruled",
        "borderless",
        "merged",
        "multiline",
        "chinese",
        "numbers",
        "multipage",
        "landscape",
        "rotated",
        "no-table",
        "blank",
        "scan",
        "scan-merged",
        "scan-chinese",
        "rowspan",
        "scan-rowspan",
        "mixed",
    ]:
        file = root / (name + ".pdf")
        c = canvas.Canvas(
            str(file), pagesize=(700, 500) if name == "landscape" else (595, 842)
        )
        data = [
            ["Code", "Product", "Amount"],
            ["00123", "Widget A", "1,234.50"],
            ["00987", "Widget B", "-12.00"],
        ]
        if "chinese" in name:
            data = [
                ["编号", "产品", "金额"],
                ["00123", "测试产品", "1234.50"],
                ["00987", "中文表格", "-12.00"],
            ]
        if name == "numbers":
            data = [
                ["ID", "Value", "Text"],
                ["00123", "12345678901234567890", "=1+1"],
                ["00987", "1.234,50", "@SUM(A1)"],
            ]
        if "rowspan" in name:
            data[2][0] = ""
        if name == "multiline":
            data[1][1] = "Widget A\nSecond line"

        def page(scan=False):
            if name == "blank":
                c.showPage()
                return
            if name == "no-table":
                c.drawString(50, 750, "A paragraph without any tabular data.")
                c.showPage()
                return
            target = c
            buf = None
            if scan:
                buf = io.BytesIO()
                target = canvas.Canvas(buf, pagesize=(595, 842))
            top = 420 if name == "landscape" else 720
            target.setFont("FixtureCJK" if "chinese" in name else "Helvetica", 12)
            if name in ["merged", "scan-merged"]:
                target.drawString(55, top + 20, "Quarterly report")
                target.rect(50, top, 450, 40)
            if name != "borderless":
                for x in [50, 180, 370, 500]:
                    target.line(x, top, x, top - 120)
                for y in range(4):
                    target.line(
                        180 if "rowspan" in name and y == 2 else 50,
                        top - y * 40,
                        500,
                        top - y * 40,
                    )
            for r, row in enumerate(data):
                for col, text in enumerate(row):
                    for line, t in enumerate(text.split("\n")):
                        target.drawString(
                            [55, 185, 375][col], top - r * 40 - 18 - line * 14, t
                        )
            if scan:
                target.showPage()
                target.save()
                buf.seek(0)
                import pypdfium2 as pdfium

                doc = pdfium.PdfDocument(buf.getvalue())
                im = doc[0].render(scale=2).to_pil()
                c.drawImage(ImageReader(im), 0, 0, 595, 842)
            c.showPage()

        page(name.startswith("scan"))
        if name in ["multipage", "mixed"]:
            page(name == "mixed")
        c.save()
        if name == "rotated":
            w = PdfWriter()
            w.add_page(PdfReader(file).pages[0])
            w.pages[0].rotate(90)
            w.write(file)
        manifest.append(
            {
                "id": name,
                "file": file.name,
                "cells": data if name not in ["blank", "no-table"] else [],
                "expect": (
                    "no-tables"
                    if name in ["blank", "no-table"]
                    else "ocr-required" if name in ["scan", "mixed"] else "table"
                ),
            }
        )
    w = PdfWriter()
    w.add_page(PdfReader(root / "ruled.pdf").pages[0])
    w.encrypt("test-secret")
    w.write(root / "encrypted.pdf")
    (root / "corrupted.pdf").write_bytes(b"%PDF-1.7\ncorrupt")
    (root / "empty.pdf").write_bytes(b"")
    (root / "expected.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    return manifest


if __name__ == "__main__":
    import sys

    generate(sys.argv[1])
