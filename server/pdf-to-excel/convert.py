"""Bounded PDF table extraction. Source strings stay strings, never Excel formulas."""

from __future__ import annotations
import io, json, os, re, sys, urllib.request, zipfile
import math, unicodedata
from statistics import median
from pathlib import Path
from copy import copy
import pdfplumber
from pypdf import PdfReader, PdfWriter
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Side, Font, PatternFill
from openpyxl.utils import get_column_letter
from text_tables import aligned_tables, conservative_aligned_tables
from layout_tables import extract_layout_tables, LayoutError

MAX_BYTES = 30 * 1024 * 1024
MAX_CELLS = 250000


class ConversionError(Exception):
    pass


def pages_for(value, count):
    if not isinstance(value, str) or len(value) > 1000:
        raise ConversionError("Invalid page range.")
    if value.strip().lower() in ("", "all"):
        return list(range(count))
    pages = set()
    for part in value.split(","):
        match = re.fullmatch(r"\s*([1-9]\d*)(?:\s*-\s*([1-9]\d*))?\s*", part)
        if not match:
            raise ConversionError("Use page numbers such as 1-3,5.")
        start = int(match[1])
        end = int(match[2] or start)
        if start > end or end > count:
            raise ConversionError("The page range is outside this PDF.")
        pages.update(range(start - 1, end))
    return sorted(pages)


def clean(text):
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > 32767:
        raise ConversionError("A cell exceeds the Excel text limit.")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


def table_from_pdf(table):
    cells = table.cells
    xs = sorted(set(round(x, 2) for b in cells for x in (b[0], b[2])))
    ys = sorted(set(round(y, 2) for b in cells for y in (b[1], b[3])))
    if len(xs) < 3 or len(ys) < 3:
        return None
    if (len(xs) - 1) * (len(ys) - 1) > MAX_CELLS:
        raise ConversionError("The table is too large.")
    values = table.extract(x_tolerance=2, y_tolerance=3)
    entries = []
    for ri, row in enumerate(table.rows):
        for ci, b in enumerate(row.cells):
            if b is None:
                continue
            r = ys.index(round(b[1], 2))
            col = xs.index(round(b[0], 2))
            entries.append(
                {
                    "r": r,
                    "c": col,
                    "rs": ys.index(round(b[3], 2)) - r,
                    "cs": xs.index(round(b[2], 2)) - col,
                    "text": clean(values[ri][ci]),
                }
            )
    occupied = set()
    for entry in entries:
        region = {
            (r, c)
            for r in range(entry["r"], entry["r"] + entry["rs"])
            for c in range(entry["c"], entry["c"] + entry["cs"])
        }
        if occupied & region:
            raise ConversionError(
                "Overlapping table cells could not be reconstructed reliably. Try selecting simpler pages."
            )
        occupied.update(region)
    # Text strategy invents spacer rows. Remove only wholly empty rows with no spans.
    if not any(e["rs"] > 1 for e in entries):
        used = sorted({e["r"] for e in entries if e["text"].strip()})
        if len(used) < len(ys) - 1:
            entries = [dict(e, r=used.index(e["r"])) for e in entries if e["r"] in used]
            heights = [ys[r + 1] - ys[r] for r in used]
        else:
            heights = [b - a for a, b in zip(ys, ys[1:])]
    else:
        heights = [b - a for a, b in zip(ys, ys[1:])]
    if len(heights) < 2:
        return None
    if sum(bool(e["text"].strip()) for e in entries) < 4:
        return None
    return {
        "widths": [b - a for a, b in zip(xs, xs[1:])],
        "heights": heights,
        "cells": entries,
        "method": "text",
        "bbox": list(table.bbox),
    }


def ruled_tables(page):
    found = page.find_tables()
    return [t for t in (table_from_pdf(t) for t in found) if t]


def native_tables(page):
    tables = ruled_tables(page)
    if tables:
        return tables
    # Shared word starts in prose do not establish table columns. Require
    # repeated rows separated by actual horizontal whitespace instead.
    return aligned_tables(page)


def stirling_tables(source, page_index):
    base = os.environ.get("STIRLING_URL", "").rstrip("/")
    if not base:
        return []
    w = PdfWriter()
    w.add_page(PdfReader(source).pages[page_index])
    buf = io.BytesIO()
    w.write(buf)
    boundary = "SmartPDFExcelBoundary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="fileInput"; filename="input.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
        + buf.getvalue()
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="useStirlingOfficeConvert"\r\n\r\ntrue\r\n--{boundary}--\r\n'.encode()
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if os.environ.get("STIRLING_API_KEY"):
        headers["X-API-KEY"] = os.environ["STIRLING_API_KEY"]
    req = urllib.request.Request(
        base + "/api/v1/convert/pdf/xlsx", data=body, headers=headers
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        data = response.read(MAX_BYTES + 1)
        if response.status == 204:
            return []
    if len(data) > MAX_BYTES:
        raise ConversionError("The converted workbook is too large.")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > 100 * 1024 * 1024:
            raise ConversionError("The converted workbook is too large.")
    book = load_workbook(io.BytesIO(data), keep_links=False)
    tables = []
    for s in book:
        if s.max_row * s.max_column > MAX_CELLS:
            raise ConversionError("The table is too large.")
        entries = []
        merges = {(m.min_row, m.min_col): m for m in s.merged_cells}
        for row in s:
            for cell in row:
                if cell.value is None:
                    continue
                m = merges.get((cell.row, cell.column))
                # Stirling is used only for rotated tables; preserve displayed decimals.
                value = cell.value
                if isinstance(value, (int, float)):
                    fmt = cell.number_format
                    match = re.search(r"\.([0#]+)", fmt)
                    value = (
                        f"{value:,.{len(match[1])}f}"
                        if match and "," in fmt
                        else f"{value:.{len(match[1])}f}" if match else str(value)
                    )
                entries.append(
                    {
                        "r": cell.row - 1,
                        "c": cell.column - 1,
                        "rs": m.max_row - m.min_row + 1 if m else 1,
                        "cs": m.max_col - m.min_col + 1 if m else 1,
                        "text": clean(value),
                    }
                )
        if entries:
            tables.append(
                {
                    "widths": [
                        max(
                            35,
                            (s.column_dimensions[get_column_letter(i)].width or 15) * 7,
                        )
                        for i in range(1, s.max_column + 1)
                    ],
                    "heights": [
                        s.row_dimensions[i].height or 20
                        for i in range(1, s.max_row + 1)
                    ],
                    "cells": entries,
                    "method": "stirling",
                }
            )
    return tables


_ocr = None


def scan_tables(page):
    global _ocr
    try:
        import cv2, numpy as np
        import onnxruntime

        onnxruntime.disable_telemetry_events()
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise ConversionError(
            "This page needs OCR, which is unavailable on this server."
        )
    if page.width * page.height * 4 > 20_000_000:
        raise ConversionError("The scanned page is too large for OCR.")
    im = np.asarray(page.to_image(resolution=144).original.convert("RGB"))
    if _ocr is None:
        _ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
    result, _ = _ocr(im)
    if not result:
        return []
    gray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    horizontal = cv2.morphologyEx(
        bw,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, im.shape[1] // 30), 1)),
    )
    vertical = cv2.morphologyEx(
        bw,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, im.shape[0] // 30))),
    )
    contours, _ = cv2.findContours(
        horizontal | vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    tables = []

    def groups(values):
        out = []
        for v in values:
            if not out or v - out[-1][-1] > 3:
                out.append([int(v)])
            else:
                out[-1].append(int(v))
        return [round(sum(g) / len(g)) for g in out]

    for contour in sorted(contours, key=lambda c: cv2.boundingRect(c)[1]):
        x, y, w, h = cv2.boundingRect(contour)
        if w < 100 or h < 40:
            continue
        xs = groups(
            np.where((vertical[y : y + h, x : x + w] > 0).sum(axis=0) > h * 0.35)[0] + x
        )
        ys = groups(
            np.where((horizontal[y : y + h, x : x + w] > 0).sum(axis=1) > w * 0.35)[0]
            + y
        )
        if len(xs) < 3 or len(ys) < 3:
            continue
        if (len(xs) - 1) * (len(ys) - 1) > MAX_CELLS:
            raise ConversionError("The scanned table is too large.")
        nr, nc = len(ys) - 1, len(xs) - 1
        parent = list(range(nr * nc))

        def find(v):
            while parent[v] != v:
                parent[v] = parent[parent[v]]
                v = parent[v]
            return v

        def join(a, b):
            parent[find(a)] = find(b)

        for r, (a, b) in enumerate(zip(ys, ys[1:])):
            for col, (left, right) in enumerate(zip(xs, xs[1:])):
                node = r * nc + col
                if col + 1 < nc:
                    strip = vertical[a + 3 : b - 2, max(0, right - 2) : right + 3]
                    if strip.size and (strip > 0).any(axis=1).mean() < 0.5:
                        join(node, node + 1)
                if r + 1 < nr:
                    strip = horizontal[max(0, b - 2) : b + 3, left + 3 : right - 2]
                    if strip.size and (strip > 0).any(axis=0).mean() < 0.5:
                        join(node, node + nc)
        regions = {}
        for r in range(nr):
            for col in range(nc):
                regions.setdefault(find(r * nc + col), []).append((r, col))
        entries = []
        for region in regions.values():
            r = min(v[0] for v in region)
            last_r = max(v[0] for v in region)
            col = min(v[1] for v in region)
            last_c = max(v[1] for v in region)
            if (last_r - r + 1) * (last_c - col + 1) != len(region):
                raise ConversionError(
                    "A scanned table has ambiguous merged cells. Try a clearer scan."
                )
            words = []
            for box, text, score in result:
                cx = sum(p[0] for p in box) / 4
                cy = sum(p[1] for p in box) / 4
                if xs[col] <= cx < xs[last_c + 1] and ys[r] <= cy < ys[last_r + 1]:
                    words.append((cy, min(p[0] for p in box), text, float(score)))
            words.sort(key=lambda v: (round(v[0] / 12), v[1]))
            entries.append(
                {
                    "r": r,
                    "c": col,
                    "rs": last_r - r + 1,
                    "cs": last_c - col + 1,
                    "text": clean(" ".join(v[2] for v in words)),
                    "confidence": min((v[3] for v in words), default=1),
                }
            )
        if any(e["text"] for e in entries):
            tables.append(
                {
                    "widths": [(b - a) / 2 for a, b in zip(xs, xs[1:])],
                    "heights": [(b - a) / 2 for a, b in zip(ys, ys[1:])],
                    "cells": entries,
                    "method": "ocr",
                }
            )
    return tables


def readable_heights(table, widths, font_size):
    heights = [min(409, max(20, h)) for h in table["heights"]]

    def width(text):
        total = 0
        for char in text:
            if unicodedata.east_asian_width(char) in ("W", "F"):
                factor = 1.05
            elif char == "\t":
                factor = 1.32
            elif char.isspace():
                factor = 0.33
            elif char in "ilI.,'|!:;":
                factor = 0.32
            elif char in "MW@%&#":
                factor = 0.95
            elif char.isupper():
                factor = 0.72
            else:
                factor = 0.61
            total += factor * font_size
        return total

    for cell in table["cells"]:
        available = max(12, sum(widths[cell["c"] : cell["c"] + cell["cs"]]) * 5.25 - 8)
        if cell["r"] == 0:
            available /= 1.08
        lines = 0
        for paragraph in cell["text"].split("\n"):
            lines += 1
            used = 0
            for token in re.findall(r"\S+|\s+", paragraph):
                measured = width(token)
                if token.isspace():
                    used += measured
                    continue
                if used and used + measured > available:
                    lines += 1
                    used = 0
                if measured > available:
                    count = math.ceil(measured / available)
                    lines += count - 1
                    used = measured - (count - 1) * available
                else:
                    used += measured
        required = lines * font_size * 1.32 + 6
        indices = range(cell["r"], cell["r"] + cell["rs"])
        if required > 409 * cell["rs"]:
            raise ConversionError(
                "A cell contains more text than Excel can display at a readable size. Try selecting a smaller table."
            )
        remaining = max(0, required - sum(heights[r] for r in indices))
        for r in indices:
            increase = min(409 - heights[r], remaining)
            heights[r] += increase
            remaining -= increase
    return heights


def write_workbook(tables, output, layout):
    book = Workbook()
    book.remove(book.active)
    thin = Side(style="thin", color="CED8D3")
    preview = []
    offset = 0
    for i, t in enumerate(tables):
        s = (
            book.active
            if layout == "single" and book.worksheets
            else book.create_sheet(
                "Tables"
                if layout == "single"
                else f'Page {t["page"]} Table {t["index"]}'
            )
        )
        offset = offset if layout == "single" else 0
        if layout == "single":
            s.cell(offset + 1, 1, f'Page {t["page"]} · Table {t["index"]}')
            offset += 1
        rows = len(t["heights"])
        cols = len(t["widths"])
        if offset + rows > 1048576 or cols > 16384:
            raise ConversionError("The result exceeds Excel worksheet limits.")
        for col, width in enumerate(t["widths"], 1):
            key = get_column_letter(col)
            s.column_dimensions[key].width = max(
                s.column_dimensions[key].width or 0, min(80, max(8, width / 5.25))
            )
        font_size = t.get("fontSize", 11)
        heights = readable_heights(
            t,
            [
                s.column_dimensions[get_column_letter(i)].width
                for i in range(1, cols + 1)
            ],
            font_size,
        )
        for r, height in enumerate(heights, offset + 1):
            s.row_dimensions[r].height = height
        values = [[""] * cols for _ in range(min(rows, 12))]
        for e in t["cells"]:
            c = s.cell(offset + e["r"] + 1, e["c"] + 1, clean(e["text"]))
            c.data_type = "s"
            c.number_format = "@"
            c.font = Font(
                name=(
                    "Noto Sans CJK SC"
                    if re.search(r"[\u3400-\u9fff]", e["text"])
                    else "Arial"
                ),
                size=font_size,
            )
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            if e["r"] == 0:
                c.font = Font(
                    name=c.font.name, size=font_size, bold=True, color="174B39"
                )
                c.fill = PatternFill("solid", fgColor="EDF5EF")
            if e["rs"] > 1 or e["cs"] > 1:
                s.merge_cells(
                    start_row=c.row,
                    start_column=c.column,
                    end_row=c.row + e["rs"] - 1,
                    end_column=c.column + e["cs"] - 1,
                )
            if e["r"] < 12 and e["c"] < cols:
                values[e["r"]][e["c"]] = e["text"][:250]
        s.freeze_panes = "A2"
        s.sheet_view.showGridLines = False
        s.sheet_properties.pageSetUpPr.fitToPage = True
        s.page_setup.fitToWidth = 1
        s.page_setup.fitToHeight = 0
        s.page_setup.orientation = "landscape" if sum(t["widths"]) > 500 else "portrait"
        if len(preview) < 8:
            preview.append(
                {
                    "sheet": s.title,
                    "page": t["page"],
                    "rows": rows,
                    "columns": cols,
                    "values": [r[:12] for r in values],
                }
            )
        offset += rows + 2
    book.save(output)
    # Independent ZIP / XML checks prevent formulas and external relationships.
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(output) as z:
        for name in z.namelist():
            if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                tree = ET.fromstring(z.read(name))
                if any(x.tag.rsplit("}", 1)[-1] == "f" for x in tree.iter()):
                    raise ConversionError("Unsafe spreadsheet output.")
    return preview


def convert(source, output, options):
    source = Path(source)
    output = Path(output)
    if not 0 < source.stat().st_size <= MAX_BYTES:
        raise ConversionError("Choose a PDF between 1 byte and 30 MiB.")
    with source.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise ConversionError("This file is not a PDF.")
    try:
        reader = PdfReader(source)
    except Exception:
        raise ConversionError("The PDF is damaged or cannot be opened.")
    if reader.is_encrypted:
        raise ConversionError("Unlock this PDF before converting it.")
    try:
        count = len(reader.pages)
    except Exception:
        raise ConversionError("The PDF page structure is damaged.")
    if not 0 < count <= 200:
        raise ConversionError("Choose a PDF with 1–200 pages.")
    if not isinstance(options, dict) or set(options) - {"pages", "layout", "ocr"}:
        raise ConversionError("Invalid conversion options.")
    layout = options.get("layout", "tables")
    ocr = options.get("ocr", True)
    if layout not in ("tables", "single") or not isinstance(ocr, bool):
        raise ConversionError("Invalid conversion options.")
    selected = pages_for(options.get("pages", "all"), count)
    tables = []
    warnings = []
    missing = []
    ocr_pages = []
    aligned_pages = []
    with pdfplumber.open(source) as doc:
        if len(doc.pages) != count:
            raise ConversionError("The PDF has an inconsistent page structure.")
        models = os.environ.get("PDF_EXCEL_MODELS")
        model_tables = None
        if models:
            native_indices = []
            for index in selected:
                page = doc.pages[index]
                if (
                    page.width <= 0
                    or page.height <= 0
                    or page.width * page.height > 10_000_000
                ):
                    raise ConversionError("A page has unsupported dimensions.")
                if not page.rotation and not (page.images and len(page.chars) < 10):
                    native_indices.append(index)
            try:
                model_tables = extract_layout_tables(
                    source, native_indices, models, doc.pages, ruled_tables
                )
            except LayoutError as error:
                raise ConversionError(str(error))
        for index in selected:
            page = doc.pages[index]
            if (
                page.width <= 0
                or page.height <= 0
                or page.width * page.height > 10_000_000
            ):
                raise ConversionError("A page has unsupported dimensions.")
            # Reject an image region with no corresponding text, including mixed pages.
            image_only = bool(page.images) and len(page.chars) < 10
            if image_only:
                if not ocr:
                    raise ConversionError(
                        f"Page {index+1} needs OCR. Enable scanned-page recognition."
                    )
                found = scan_tables(page)
                ocr_pages.append(index + 1)
                if not found:
                    raise ConversionError(
                        f"No reliable table was recognized on scanned page {index+1}. Try a clearer scan with visible table lines."
                    )
            elif page.rotation:
                if not os.environ.get("STIRLING_URL"):
                    raise ConversionError(
                        "Rotated tables need the conversion server. Rotate the page upright and try again."
                    )
                found = stirling_tables(source, index)
                warnings.append(
                    f"Page {index+1}: rotated table was reconstructed; check number formatting."
                )
            else:
                found = (
                    model_tables.get(index, [])
                    if model_tables is not None
                    else native_tables(page)
                )
                if model_tables is not None and not found:
                    # Small, clearly aligned numeric tables can be below the
                    # layout model's detection threshold. Never recover prose.
                    found = conservative_aligned_tables(page)
            if not found:
                missing.append(index + 1)
            if any(t["method"] == "aligned" for t in found):
                aligned_pages.append(index + 1)
            for j, t in enumerate(found):
                if t.get("bbox"):
                    b = t["bbox"]
                    sizes = [
                        c["size"]
                        for c in page.chars
                        if b[0] <= c["x0"] <= b[2]
                        and b[1] <= c["top"] <= b[3]
                        and c["size"] > 0
                    ]
                    if sizes:
                        t["fontSize"] = max(6, min(14, median(sizes)))
                t.update(page=index + 1, index=j + 1)
                tables.append(t)
            if sum(len(e["text"]) for t in tables for e in t["cells"]) > 5_000_000:
                raise ConversionError("The extracted text exceeds the workbook budget.")
            if sum(len(t["heights"]) * len(t["widths"]) for t in tables) > MAX_CELLS:
                raise ConversionError("The extracted tables exceed the cell budget.")
            page.close()
    if not tables:
        raise ConversionError(
            "No tables were found. Choose a PDF containing a table with aligned rows and columns."
        )
    if missing:
        warnings.append(
            "No table extracted from pages: "
            + ", ".join(map(str, missing))
            + ". Non-table text and images are not included."
        )
    if ocr_pages:
        warnings.append(
            "OCR used on pages: "
            + ", ".join(map(str, ocr_pages))
            + ". Check every number and merged cell against the original."
        )
    if aligned_pages:
        warnings.append(
            "Column boundaries inferred from text spacing on pages: "
            + ", ".join(map(str, aligned_pages))
            + ". Check the row and column alignment."
        )
    if any(t["method"] == "layout" for t in tables):
        warnings.append(
            "Table structure was reconstructed. Check merged cells and column alignment against the original PDF."
        )
    warnings.append(
        "Only detected tables are included. Text and numbers are stored as text to preserve spelling, leading zeros and precision."
    )
    preview = write_workbook(tables, output, layout)
    if output.stat().st_size > MAX_BYTES:
        output.unlink()
        raise ConversionError("The workbook exceeds the download size limit.")
    return {
        "pages": len(selected),
        "tables": len(tables),
        "sheets": 1 if layout == "single" else len(tables),
        "warnings": warnings,
        "missingPages": missing,
        "ocrPages": ocr_pages,
        "preview": preview,
    }


if __name__ == "__main__":
    try:
        result = convert(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
        print(json.dumps(result, ensure_ascii=False))
    except ConversionError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)
    except Exception:
        print(
            json.dumps(
                {"error": "The PDF could not be converted safely. Try another file."}
            )
        )
        sys.exit(2)
