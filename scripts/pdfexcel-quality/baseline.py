"""Deliberately limited local evaluation adapter, never an upload service.

The adapter measures a transparent pdfplumber ruled-table baseline. It must not
be presented as the PDF-to-Excel product, a security boundary or a general-
coverage converter. See README.md for unimplemented release requirements.
"""

from __future__ import annotations
import io

import pdfplumber
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError
from pdfminer.psparser import PSEOF
from pdfplumber.utils.exceptions import PdfminerException


def evaluate_pdf(path):
    report = {"pages": [], "tables": []}
    workbook = Workbook()
    workbook.remove(workbook.active)
    try:
        with pdfplumber.open(path) as document:
            if document.doc.encryption:
                return {"refusal": "encrypted"}, None
            for number, page in enumerate(document.pages, 1):
                if page.rotation:
                    report["pages"].append(
                        {"page": number, "status": "unsupported_rotation"}
                    )
                    continue
                tables = page.find_tables()
                status = (
                    "converted"
                    if tables
                    else (
                        "needs_ocr"
                        if page.images
                        else ("no_table" if page.chars else "blank")
                    )
                )
                report["pages"].append({"page": number, "status": status})
                for table in sorted(tables, key=lambda t: (t.bbox[1], t.bbox[0])):
                    xs = sorted({x for cell in table.cells for x in (cell[0], cell[2])})
                    ys = sorted({y for cell in table.cells for y in (cell[1], cell[3])})
                    name = f"Table_{len(report['tables']) + 1}"
                    sheet = workbook.create_sheet(name)
                    for bbox in table.cells:
                        x0, top, x1, bottom = bbox
                        row, column = ys.index(top) + 1, xs.index(x0) + 1
                        last_row, last_column = ys.index(bottom), xs.index(x1)
                        chars = [
                            char
                            for char in page.chars
                            if x0 <= (char["x0"] + char["x1"]) / 2 < x1
                            and top <= (char["top"] + char["bottom"]) / 2 < bottom
                        ]
                        text = pdfplumber.utils.extract_text(chars) if chars else ""
                        cell = sheet.cell(row, column, text)
                        # Setting an explicit string type is essential: '=...' is
                        # source data, not a formula, and long IDs stay exact.
                        cell.data_type = "s"
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
                        if last_row > row or last_column > column:
                            sheet.merge_cells(
                                start_row=row,
                                start_column=column,
                                end_row=last_row,
                                end_column=last_column,
                            )
                    for column in range(1, len(xs)):
                        sheet.column_dimensions[get_column_letter(column)].width = 24
                    report["tables"].append({"sheet": name, "page": number})
                page.close()
    except PdfminerException as error:
        cause = error.args[0] if error.args else None
        if isinstance(cause, PDFPasswordIncorrect):
            return {"refusal": "encrypted"}, None
        if isinstance(cause, (PDFSyntaxError, PSEOF)):
            return {"refusal": "invalid_pdf"}, None
        raise
    if not workbook.sheetnames:
        return report, None
    stream = io.BytesIO()
    workbook.save(stream)
    return report, stream.getvalue()
