"""Editable Word export with source-page bookmarks and bounded embedded assets."""

import os
import re
import tempfile
from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from model import Rejected, validate, content_text


def mark(paragraph, index):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(index))
    start.set(qn("w:name"), f"smartpdf_page_{index+1}")
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(index))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def run_text(paragraph, text, block):
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


def add_table(document, block, width, existing=None):
    table = (
        existing
        if existing is not None
        else document.add_table(rows=0, cols=block["cols"])
    )
    table.style = "Table Grid"
    table.autofit = False
    widths = block.get("widths", [1] * block["cols"])
    total = sum(widths)
    for c, w in zip(table.columns, widths):
        c.width = Pt(width * w / total)
    skip = 1 if existing is not None and block.get("repeat_header") else 0
    offset = len(table.rows) - skip
    for _ in range(block["rows"] - skip):
        table.add_row()
    for c in block["cells"]:
        if c["row"] < skip:
            continue
        r = c["row"] + offset
        col = c["col"]
        cell = table.cell(r, col)
        if c["rowspan"] > 1 or c["colspan"] > 1:
            cell = cell.merge(table.cell(r + c["rowspan"] - 1, col + c["colspan"] - 1))
        cell.text = ""
        run_text(
            cell.paragraphs[0], c["text"], {"size": 10, "bold": c.get("header", False)}
        )
    if table.rows and (
        block.get("header_rows")
        or any(c.get("header") for c in block["cells"] if c["row"] == 0)
    ):
        props = table.rows[0]._tr.get_or_add_trPr()
        if props.find(qn("w:tblHeader")) is None:
            props.append(OxmlElement("w:tblHeader"))
    return table


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
        width = page["width"] - 2 * margin
        height = page["height"] - 2 * margin
        marked = False
        for block in page["blocks"]:
            kind = block["kind"]
            if kind in ("header", "footer"):
                if continuing:
                    continue
                owner = getattr(section, kind)
                owner.is_linked_to_previous = False
                paragraph = (
                    owner.paragraphs[0]
                    if not owner.paragraphs[0].text
                    else owner.add_paragraph()
                )
                run_text(
                    paragraph,
                    block["text"],
                    {**block, "size": min(block.get("size", 9), 9)},
                )
                text.append(block["text"])
                continue
            if kind == "table":
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
            if not marked:
                mark(paragraph, i)
                marked = True
            if kind in ("image", "formula"):
                path = (assets / block["asset"]).resolve()
                if path.parent != assets or path.suffix.lower() != ".png":
                    raise Rejected("Invalid embedded image.")
                from PIL import Image

                with Image.open(path) as image:
                    w, h = image.size
                bw = block["bbox"][2] - block["bbox"][0]
                bh = block["bbox"][3] - block["bbox"][1]
                draw_width = bw * min(1, width / bw, height / bh)
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
