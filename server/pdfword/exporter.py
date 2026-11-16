"""Editable Word export with source-page bookmarks and bounded embedded assets."""

import os
import re
import tempfile
import math
import unicodedata
from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from model import Rejected, validate, content_text
from math_export import segments
from columns import column_flow


def set_columns(section, count=1, widths=None):
    props = section._sectPr
    old = props.find(qn("w:cols"))
    if old is not None:
        props.remove(old)
    cols = OxmlElement("w:cols")
    cols.set(qn("w:num"), str(count))
    cols.set(qn("w:space"), "360")
    if widths:
        cols.set(qn("w:equalWidth"), "0")
        available = (
            section.page_width.pt
            - section.left_margin.pt
            - section.right_margin.pt
            - 18 * (count - 1)
        ) * 20
        for width in widths:
            col = OxmlElement("w:col")
            col.set(qn("w:w"), str(round(available * width / sum(widths))))
            col.set(qn("w:space"), "360")
            cols.append(col)
    props.append(cols)


def mark(paragraph, index):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(index))
    start.set(qn("w:name"), f"smartpdf_page_{index+1}")
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(index))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def run_text(paragraph, text, block):
    last = None
    for value, formula, _ in segments(text):
        if formula is not None:
            paragraph._p.append(formula)
        else:
            last = plain_run(paragraph, value, block)
    return last


def plain_run(paragraph, text, block):
    run = paragraph.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(max(6, min(36, block.get("size", 11))))
    run.bold = block.get("bold", False)
    run.italic = block.get("italic", False)
    run.font.color.rgb = RGBColor(0, 0, 0)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Noto Sans SC")
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.widow_control = True
    return run


def content_column_weights(block):
    """Balance unmeasured OCR grids by text density rather than equal widths.

    A square-root demand balances long prose against short dates and IDs.
    Merged cells contribute across their full span; a merged title must not
    make its first column wider than the rest of the table.
    """
    weights = [6.0] * block["cols"]
    for cell in block["cells"]:
        units = sum(
            2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
            for char in cell["text"]
        )
        demand = max(6, min(36, cell.get("size", 10))) * math.sqrt(
            max(1, units) / cell["rowspan"]
        )
        share = demand / cell["colspan"]
        for column in range(cell["col"], cell["col"] + cell["colspan"]):
            weights[column] = max(weights[column], share)
    return weights


def add_table(document, block, width, existing=None):
    # Word merges adjacent w:tbl elements when opening/saving a document.
    # Separate independent tables, while explicit continuations reuse one table.
    body = document.element.body
    previous = body[-2] if len(body) > 1 else None
    if existing is None and previous is not None and previous.tag == qn("w:tbl"):
        separator = document.add_paragraph()
        separator.paragraph_format.space_before = Pt(0)
        separator.paragraph_format.space_after = Pt(0)
        separator.paragraph_format.line_spacing = Pt(1)
        separator.paragraph_format.keep_with_next = True
    table = (
        existing
        if existing is not None
        else document.add_table(rows=0, cols=block["cols"])
    )
    table.style = "Table Grid"
    # Word does not reliably rebalance an equal OCR grid on open. Supply
    # content-weighted preferred widths when source geometry is unavailable.
    table.autofit = "widths" not in block
    widths = block.get("widths")
    if widths is None:
        widths = (
            [column.width.pt for column in existing.columns]
            if existing is not None
            else content_column_weights(block)
        )
    total = sum(widths)
    column_widths = [width * w / total for w in widths]
    if min(column_widths) < 2:
        if width < 2 * len(widths):
            raise Rejected("Table columns cannot fit the available page width.")
        flexible = sum(max(0, w - 2) for w in column_widths)
        column_widths = [
            2 + (width - 2 * len(widths)) * max(0, w - 2) / flexible
            for w in column_widths
        ]
    for c, w in zip(table.columns, column_widths):
        c.width = Pt(w)
    # Word expands even a fixed grid to fit its default 5.4pt cell margins.
    # Fine subdivisions of merged cells can therefore push a table off-page.
    # Reserve 2pt for minimum content and borders and bound horizontal padding.
    padding = max(0, min(20, int((min(column_widths) * 20 - 40) / 2)))
    props = table._tbl.tblPr
    margins = props.find(qn("w:tblCellMar"))
    if margins is not None:
        props.remove(margins)
    margins = OxmlElement("w:tblCellMar")
    for side in ("left", "right"):
        edge = OxmlElement("w:" + side)
        edge.set(qn("w:w"), str(padding))
        edge.set(qn("w:type"), "dxa")
        margins.append(edge)
    props.insert_element_before(margins, "w:tblLook")
    skip = 1 if existing is not None and block.get("repeat_header") else 0
    offset = len(table.rows) - skip
    for _ in range(block["rows"] - skip):
        table.add_row()
    # python-docx rebuilds its complete cell map for every table.cell() call.
    # Finish merges first, then reuse one map for the many text assignments.
    for c in block["cells"]:
        if c["row"] < skip:
            continue
        r = c["row"] + offset
        col = c["col"]
        if c["rowspan"] > 1 or c["colspan"] > 1:
            table.cell(r, col).merge(
                table.cell(r + c["rowspan"] - 1, col + c["colspan"] - 1)
            )
    grid = table._cells
    for c in block["cells"]:
        if c["row"] < skip:
            continue
        cell = grid[(c["row"] + offset) * block["cols"] + c["col"]]
        cell.text = ""
        cell.paragraphs[0].clear()
        run_text(
            cell.paragraphs[0],
            c["text"],
            {"size": c.get("size", 10), "bold": c.get("header", False)},
        )
        cell.paragraphs[0].paragraph_format.space_after = Pt(0)
        cell.paragraphs[0].paragraph_format.space_before = Pt(0)
    for row in table.rows:
        props = row._tr.get_or_add_trPr()
        if props.find(qn("w:cantSplit")) is None:
            props.append(OxmlElement("w:cantSplit"))
    if table.rows and (
        block.get("header_rows")
        or any(c.get("header") for c in block["cells"] if c["row"] == 0)
    ):
        props = table.rows[0]._tr.get_or_add_trPr()
        if props.find(qn("w:tblHeader")) is None:
            props.append(OxmlElement("w:tblHeader"))
    return table


def image_rows(blocks):
    """Keep adjacent non-overlapping figures on their original horizontal band."""
    result = []
    index = 0
    while index < len(blocks):
        first = blocks[index]
        group = [first]
        if first["kind"] == "image":
            while index + len(group) < len(blocks):
                other = blocks[index + len(group)]
                if other["kind"] != "image":
                    break
                a, b = group[-1]["bbox"], other["bbox"]
                overlap = min(first["bbox"][3], b[3]) - max(first["bbox"][1], b[1])
                if b[0] < a[2] or overlap < 0.5 * max(first["bbox"][3] - first["bbox"][1], b[3] - b[1]):
                    break
                group.append(other)
        result.append(first if len(group) == 1 else dict(kind="image_row", images=group))
        index += len(group)
    return result


def export_word(model, destination, assets):
    validate(model)
    destination = Path(destination)
    assets = Path(assets).resolve()
    if destination.suffix.lower() != ".docx" or destination.exists():
        raise Rejected("Choose a new Word output file.")
    doc = Document()
    for k, r in list(doc.part.package.rels.items()):
        if r.reltype.endswith("/thumbnail"):
            del doc.part.package.rels[k]
    doc.core_properties.author = "Smart PDF"
    doc.core_properties.last_modified_by = "Smart PDF"
    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(4)
    tables = {}
    text = []
    image_count = 0
    active_margins = {"header": False, "footer": False}
    for i, page in enumerate(model["pages"]):
        body = [b for b in page["blocks"] if b["kind"] not in ("header", "footer")]
        continuing = bool(
            i
            and len(body) == 1
            and body[0].get("continues") in tables
            and page["width"] == model["pages"][i - 1]["width"]
            and page["height"] == model["pages"][i - 1]["height"]
        )
        section = (
            doc.sections[-1]
            if continuing or not i
            else doc.add_section(WD_SECTION_START.NEW_PAGE)
        )
        section.page_width = Pt(page["width"])
        section.page_height = Pt(page["height"])
        section.orientation = (
            WD_ORIENT.LANDSCAPE
            if page["width"] > page["height"]
            else WD_ORIENT.PORTRAIT
        )
        margin = min(36, page["width"] / 10, page["height"] / 10)
        section.left_margin = section.right_margin = section.top_margin = (
            section.bottom_margin
        ) = Pt(margin)
        section.header_distance = section.footer_distance = Pt(min(16, margin / 2))
        set_columns(section)
        if not continuing:
            # Each source page owns its margins, including an explicitly empty
            # margin. Later continuous column sections inherit this page only.
            for edge in ("header", "footer"):
                edge_blocks = [b for b in page["blocks"] if b["kind"] == edge]
                owner = getattr(section, edge)
                if edge_blocks or active_margins[edge]:
                    owner.is_linked_to_previous = False
                active_margins[edge] = bool(edge_blocks)
                for block in edge_blocks:
                    paragraph = (owner.paragraphs[0] if not owner.paragraphs[0].text
                                 else owner.add_paragraph())
                    run_text(paragraph, block["text"],
                             {**block, "size": min(block.get("size", 9), 9)})
                    text.append(block["text"])
        width = page["width"] - 2 * margin
        height = page["height"] - 2 * margin
        marked = False
        column_break = False
        for block in image_rows(column_flow(page["blocks"], page["width"])):
            kind = block["kind"]
            if kind == "columns_start":
                section = doc.add_section(WD_SECTION_START.CONTINUOUS)
                set_columns(section, block["count"], block["widths"])
                available = page["width"] - 2 * margin - 18 * (block["count"] - 1)
                column_widths = [
                    available * w / sum(block["widths"]) for w in block["widths"]
                ]
                column_index = 0
                width = column_widths[column_index]
                continue
            if kind == "column_break":
                column_index += 1
                width = column_widths[column_index]
                column_break = True
                continue
            if kind == "columns_end":
                section = doc.add_section(WD_SECTION_START.CONTINUOUS)
                set_columns(section)
                width = page["width"] - 2 * margin
                continue
            if kind in ("header", "footer"):
                continue
            if kind == "table":
                if column_break:
                    paragraph = doc.add_paragraph()
                    paragraph.paragraph_format.space_after = Pt(0)
                    paragraph.paragraph_format.line_spacing = Pt(1)
                    paragraph.add_run().add_break(WD_BREAK.COLUMN)
                    column_break = False
                old = tables.get(block.get("continues")) if continuing else None
                table = add_table(doc, block, width, old)
                tables[block["id"]] = table
                if not marked:
                    target = (
                        table.rows[
                            -(
                                block["rows"]
                                - (
                                    1
                                    if old is not None and block.get("repeat_header")
                                    else 0
                                )
                            )
                        ]
                        .cells[0]
                        .paragraphs[0]
                    )
                    mark(target, i)
                    marked = True
                text.append(content_text(block))
                continue
            paragraph = doc.add_paragraph()
            if column_break:
                paragraph.add_run().add_break(WD_BREAK.COLUMN)
                column_break = False
            if not marked:
                mark(paragraph, i)
                marked = True
            if kind in ("image", "formula", "image_row"):
                group = block["images"] if kind == "image_row" else [block]
                left = min(item["bbox"][0] for item in group)
                span = max(item["bbox"][2] for item in group) - left
                tallest = max(item["bbox"][3] - item["bbox"][1] for item in group)
                scale = min(1, width / span, height / tallest)
                for index, item in enumerate(group):
                    path = (assets / item["asset"]).resolve()
                    if path.parent != assets or path.suffix.lower() != ".png":
                        raise Rejected("Invalid embedded image.")
                    if index:
                        paragraph.paragraph_format.tab_stops.add_tab_stop(Pt((item["bbox"][0] - left) * scale))
                        paragraph.add_run().add_tab()
                    draw_width = (item["bbox"][2] - item["bbox"][0]) * scale
                    paragraph.add_run().add_picture(str(path), width=Pt(draw_width))
                    image_count += 1
                continue
            if kind == "heading":
                paragraph.style = (
                    "Heading 1" if block.get("size", 14) > 18 else "Heading 2"
                )
                paragraph.paragraph_format.keep_with_next = True
            elif kind == "list":
                # Retain the original ordinal, punctuation and restart. Word's default
                # List Number silently renumbers non-contiguous source lists.
                paragraph.style = "List Paragraph"
                paragraph.paragraph_format.left_indent = Pt(14)
                paragraph.paragraph_format.first_line_indent = Pt(-14)
            value = block.get("text", "")
            if block.get("runs"):
                if "".join(r["text"] for r in block["runs"]) != value:
                    raise Rejected("Text runs do not match source content.")
                for run in block["runs"]:
                    run_text(paragraph, run["text"], run)
            else:
                run_text(paragraph, value, block)
            text.append(value)
        if not marked:
            mark(doc.add_paragraph(), i)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        staged = Path(temp) / "output.docx"
        doc.save(staged)
        if staged.stat().st_size > 30 * 1024**2:
            raise Rejected("Word output exceeds the size limit.")
        if os.name == "nt":
            os.rename(staged, destination)
        else:
            os.link(staged, destination)
    return dict(
        schema=2,
        pages=len(model["pages"]),
        images=image_count,
        tables=len({id(t) for t in tables.values()}),
        textCharacters=sum(len(t) for t in text),
        warnings=model.get("warnings", []),
    )
