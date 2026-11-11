"""Frozen original synthetic corpus. Generates files only in the caller's directory."""

from __future__ import annotations

import io
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter


def table(rows, page=1, sheet="Table_1", merges=(), **drawing):
    return {
        "page": page,
        "sheet": sheet,
        "rows": rows,
        "merges": list(merges),
        **drawing,
    }


def cases():
    basic = [
        ["Product", "Quantity", "Amount"],
        ["Widget A", "2", "19.90"],
        ["Widget B", "5", "100.00"],
    ]
    second = [
        ["Other item", "Code", "Total"],
        ["Unique C", "7", "231.49"],
        ["Unique D", "9", "847.23"],
        ["Unique E", "1", "0.01"],
    ]
    result = [
        {"id": "ruled-basic", "pages": 1, "tables": [table(basic)]},
        {
            "id": "empty-cells",
            "pages": 1,
            "tables": [
                table(
                    [
                        ["Item", "Code", "Amount"],
                        ["Alpha", "", "10"],
                        ["", "B02", ""],
                        ["Gamma", "", "30"],
                    ]
                )
            ],
        },
        {
            "id": "multiline-cells",
            "pages": 1,
            "tables": [
                table(
                    [
                        ["Description", "Qty", "Note"],
                        ["First line\nSecond line", "2", "Wrapped\nvalue"],
                        ["Other", "3", "End"],
                    ]
                )
            ],
        },
        {
            "id": "merged-header",
            "pages": 1,
            "tables": [
                table(
                    [
                        ["Quarterly totals", "", ""],
                        ["North", "2", "10.00"],
                        ["South", "3", "15.00"],
                    ],
                    merges=["A1:C1"],
                )
            ],
        },
        {
            "id": "literal-values",
            "pages": 1,
            "tables": [
                table(
                    [
                        ["Identifier", "Literal", "Locale"],
                        ["0000123", "=1+1", "1.234,56"],
                        ["12345678901234567", "+SUM(A1:A2)", "1,234.56"],
                        ["01/02/2026", "@value", "12%"],
                        ["1E20", "-000123", "(100.00)"],
                    ],
                    widths=[160, 150, 150],
                )
            ],
        },
        {
            "id": "unicode-chinese",
            "pages": 1,
            "tables": [
                table(
                    [
                        ["产品", "数量", "金额"],
                        ["测试甲", "2", "19.90"],
                        ["测试乙", "5", "100.00"],
                    ],
                    font="STSong-Light",
                )
            ],
        },
        {
            "id": "unicode-japanese",
            "pages": 1,
            "tables": [
                table(
                    [
                        ["商品", "数量", "金額"],
                        ["テスト甲", "2", "19.90"],
                        ["テスト乙", "5", "100.00"],
                    ],
                    font="HeiseiMin-W3",
                )
            ],
        },
        {
            "id": "two-tables",
            "pages": 1,
            "tables": [table(basic), table(second, sheet="Table_2", top=360)],
        },
        {
            "id": "multipage",
            "pages": 2,
            "tables": [table(basic), table(second, page=2, sheet="Table_2")],
        },
        {"id": "landscape", "pages": 1, "size": [842, 595], "tables": [table(basic)]},
        {"id": "blank-page", "pages": 2, "tables": [table(basic, page=2)]},
        {
            "id": "narrative-page",
            "pages": 2,
            "narrative": {2: "Synthetic note: totals exclude delivery."},
            "tables": [table(basic)],
        },
        {"id": "borderless", "pages": 1, "tables": [table(basic, ruled=False)]},
        {
            "id": "scanned-table",
            "pages": 1,
            "scan_pages": [1],
            "tables": [table(basic)],
        },
        {
            "id": "mixed-native-scan",
            "pages": 2,
            "scan_pages": [2],
            "tables": [table(basic), table(second, page=2, sheet="Table_2")],
        },
        {"id": "rotated-page", "pages": 1, "rotation": 90, "tables": [table(basic)]},
        {
            "id": "password-protected",
            "pages": 1,
            "refusal": "encrypted",
            "tables": [table(basic)],
        },
        {"id": "corrupted", "pages": 0, "refusal": "invalid_pdf", "tables": []},
        {"id": "empty-input", "pages": 0, "refusal": "invalid_pdf", "tables": []},
    ]
    for case in result:
        if "refusal" not in case:
            case["page_expectations"] = []
            for page in range(1, case["pages"] + 1):
                expectation = {
                    "page": page,
                    "status": "converted"
                    if any(table["page"] == page for table in case["tables"])
                    else "blank",
                }
                if page in case.get("narrative", {}):
                    expectation.update(
                        status="non_tabular", non_table_text=case["narrative"][page]
                    )
                case["page_expectations"].append(expectation)
    return result


def draw_table(canvas, item, page_height):
    rows = item["rows"]
    widths = item.get("widths", [145] * len(rows[0]))
    xs = [48]
    for width in widths:
        xs.append(xs[-1] + width)
    top = page_height - item.get("top", 90)
    height = 42
    font = item.get("font", "Helvetica")
    if font != "Helvetica" and font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    canvas.setFont(font, 10)
    if item.get("ruled", True):
        for row in range(len(rows) + 1):
            canvas.line(xs[0], top - row * height, xs[-1], top - row * height)
        for index, x in enumerate(xs):
            merged = item["merges"] == ["A1:C1"] and index not in (0, len(xs) - 1)
            canvas.line(x, top - (height if merged else 0), x, top - len(rows) * height)
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            for line_index, line in enumerate(value.split("\n")):
                canvas.drawString(
                    xs[col_index] + 6,
                    top - row_index * height - 16 - line_index * 12,
                    line,
                )


def generate(case, path):
    path = Path(path)
    if case["id"] == "empty-input":
        path.write_bytes(b"")
        return
    if case["id"] == "corrupted":
        path.write_bytes(b"%PDF-1.7\nnot a document\n%%EOF")
        return
    size = tuple(case.get("size", [595, 842]))
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=size, invariant=1, pageCompression=1)
    canvas.setTitle("Original synthetic PDF to Excel quality case")
    for page in range(1, case["pages"] + 1):
        page_tables = [t for t in case["tables"] if t["page"] == page]
        if page in case.get("scan_pages", []):
            # Original generated pixels, not a private scan or third-party PDF.
            picture = Image.new("RGB", (1190, 1684), "white")
            draw = ImageDraw.Draw(picture)
            for item in page_tables:
                for row, values in enumerate(item["rows"]):
                    for col, value in enumerate(values):
                        x, y = 96 + col * 290, 180 + row * 84
                        draw.rectangle(
                            [x, y, x + 290, y + 84], outline="black", width=2
                        )
                        draw.text((x + 12, y + 24), value, fill="black", font_size=20)
            canvas.drawImage(ImageReader(picture), 0, 0, width=size[0], height=size[1])
        else:
            for item in page_tables:
                draw_table(canvas, item, size[1])
        if page in case.get("narrative", {}):
            canvas.setFont("Helvetica", 10)
            canvas.drawString(48, size[1] - 90, case["narrative"][page])
        canvas.showPage()
    canvas.save()
    data = stream.getvalue()
    if case.get("rotation") or case.get("refusal") == "encrypted":
        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(data)).pages:
            if case.get("rotation"):
                page.rotate(case["rotation"])
            writer.add_page(page)
        if case.get("refusal") == "encrypted":
            writer.encrypt("synthetic-test-only")
        out = io.BytesIO()
        writer.write(out)
        data = out.getvalue()
    path.write_bytes(data)
