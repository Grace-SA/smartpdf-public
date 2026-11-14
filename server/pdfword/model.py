"""Bounded, engine-independent document structure. Coordinates are page points."""

import math
import re
from lxml import etree

MAX_CELLS = 10000
MAX_TEXT = 1000000


class Rejected(ValueError):
    pass


def box(value, width, height):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise Rejected("Invalid content region.")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise Rejected("Invalid content position.")
    x0, y0, x1, y1 = value
    if x1 <= x0 or y1 <= y0 or x0 < -1 or y0 < -1 or x1 > width + 1 or y1 > height + 1:
        raise Rejected("Content falls outside the page.")
    return [max(0, x0), max(0, y0), min(width, x1), min(height, y1)]


def plain(value):
    if not isinstance(value, str) or len(value) > 100000 or "\ufffd" in value:
        raise Rejected("Text requires review.")
    # Preserve meaningful whitespace, numbers and punctuation; do not rewrite OCR.
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise Rejected("Invalid text characters.")
    return value


def table_text(value):
    # A common OCR representation of physical units; preserve their actual value.
    powers = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")
    return re.sub(
        r"\$([A-Za-z]+)\^\{([0-9+-]+)\}\$",
        lambda m: m[1] + m[2].translate(powers),
        value,
    )


def cell_text(node):
    """Retain block/line boundaries without inserting spaces into inline runs."""
    pieces = []

    def boundary():
        if pieces and not pieces[-1].endswith("\n"):
            pieces.append("\n")

    def visit(element):
        if element.tag == "br":
            pieces.append("\n")
            return
        if element.tag == "p":
            boundary()
        value = element.text_content()
        if (
            element.tag in {"sup", "sub"}
            and re.fullmatch("[0-9+-]+", value)
            and not element.xpath(".//p|.//br")
        ):
            pieces.append(value.translate(str.maketrans(
                "0123456789+-",
                "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻" if element.tag == "sup" else "₀₁₂₃₄₅₆₇₈₉₊₋",
            )))
        else:
            if element.text:
                pieces.append(element.text)
            for child in element:
                visit(child)
                if child.tail and not (child.tag == "p" and not child.tail.strip()):
                    pieces.append(child.tail)
        if element.tag == "p":
            boundary()

    visit(node)
    return plain(table_text("".join(pieces).strip()))


def validate_table_structure(root):
    """Do not quietly drop model text placed outside the reconstructed cells."""
    structure = {
        "table": {"tr", "thead", "tbody", "tfoot"},
        "thead": {"tr"}, "tbody": {"tr"}, "tfoot": {"tr"},
        "tr": {"td", "th"},
    }
    for element in root.iter():
        if element.tag in structure:
            if (element.text or "").strip():
                raise Rejected("Table contains text outside cells; review the source.")
            for child in element:
                if child.tag not in structure[element.tag] or (child.tail or "").strip():
                    raise Rejected("Table contains unassigned content; review the source.")
        elif any(child.tag in structure or child.tag in {"td", "th"} for child in element):
            raise Rejected("Unsupported nested table structure.")


def table_from_html(markup):
    """Accept only a complete bounded table; never interpret arbitrary model HTML."""
    if (
        not isinstance(markup, str)
        or len(markup) > 500000
        or re.search(r"<!|<\?", markup)
    ):
        raise Rejected("Table markup requires review.")
    # HTML numeric references are ordinary OCR text, not entity declarations.
    # Validate their code points before parsing, without pre-decoding markup.
    for match in re.finditer(r"&#(x[\da-f]+|\d+);", markup, re.I):
        value = match[1]
        code = int(value[1:], 16) if value.lower().startswith("x") else int(value)
        if code not in (9, 10, 13) and not (
            32 <= code <= 0xD7FF
            or 0xE000 <= code <= 0xFFFD
            or 0x10000 <= code <= 0x10FFFF
        ):
            raise Rejected("Invalid table text reference.")
    from lxml import html

    try:
        root = html.fromstring(
            markup, parser=html.HTMLParser(no_network=True, recover=False)
        )
    except (ValueError, etree.ParserError, etree.XMLSyntaxError) as error:
        raise Rejected("Table could not be read.") from error
    if root.tag != "table" or not markup.rstrip().lower().endswith("</table>"):
        raise Rejected("Incomplete table.")
    allowed = {
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "br",
        "b",
        "strong",
        "i",
        "em",
        "span",
        "p",
        "sup",
        "sub",
    }
    if any(n.tag not in allowed for n in root.iter()) or root.xpath(".//table"):
        raise Rejected("Unsupported nested table content.")
    validate_table_structure(root)
    rows = root.xpath("./tr|./thead/tr|./tbody/tr|./tfoot/tr")
    if not 1 <= len(rows) <= 500:
        raise Rejected("Table exceeds row limit.")
    occupied = set()
    cells = []
    for r, row in enumerate(rows):
        c = 0
        for node in row.xpath("./td|./th"):
            while (r, c) in occupied:
                c += 1
            try:
                rs, cs = int(node.get("rowspan", "1")), int(node.get("colspan", "1"))
            except ValueError as error:
                raise Rejected("Invalid table span.") from error
            if not 1 <= rs <= len(rows) - r or not 1 <= cs <= 64 or c + cs > 64:
                raise Rejected("Table span exceeds limits.")
            slots = {(rr, cc) for rr in range(r, r + rs) for cc in range(c, c + cs)}
            if occupied & slots or len(occupied | slots) > MAX_CELLS:
                raise Rejected("Overlapping or oversized table.")
            occupied.update(slots)
            cells.append(
                dict(
                    row=r,
                    col=c,
                    rowspan=rs,
                    colspan=cs,
                    text=cell_text(node),
                    header=node.tag == "th" or bool(node.xpath("ancestor::thead")),
                )
            )
            c += cs
    if not cells:
        raise Rejected("Empty table.")
    cols = max(c for r, c in occupied) + 1
    if len(occupied) != len(rows) * cols:
        raise Rejected("Incomplete table grid; review the source.")
    return dict(rows=len(rows), cols=cols, cells=cells)


def table_header_rows(table):
    """Only complete leading semantic header rows may be repeated or removed."""
    header = [True] * table["rows"]
    covered = [False] * table["rows"]
    for cell in table["cells"]:
        for row in range(cell["row"], cell["row"] + cell["rowspan"]):
            covered[row] = True
            header[row] = header[row] and cell.get("header") is True
    count = 0
    for row in range(table["rows"]):
        if not covered[row] or not header[row]:
            break
        count += 1
    # A merged header extending into a data row cannot be split safely.
    if any(c["row"] < count < c["row"] + c["rowspan"] for c in table["cells"]):
        return 0
    return count


def content_text(block):
    if block["kind"] == "table":
        return "\n".join(c["text"] for c in block["cells"])
    return block.get("text", "")


def validate(model):
    if model.get("schema") != 2 or not 1 <= len(model.get("pages", [])) <= 200:
        raise Rejected("Invalid document structure.")
    total = 0
    seen = set()
    for i, page in enumerate(model["pages"]):
        if page["index"] != i or any(
            not math.isfinite(page[k]) or not 72 <= page[k] <= 1584
            for k in ("width", "height")
        ):
            raise Rejected("Invalid page geometry.")
        if len(page["blocks"]) > 5000:
            raise Rejected("Page has too many regions.")
        for b in page["blocks"]:
            if b["id"] in seen:
                raise Rejected("Duplicate content block.")
            seen.add(b["id"])
            box(b["bbox"], page["width"], page["height"])
            if b["kind"] not in {
                "paragraph",
                "heading",
                "list",
                "table",
                "image",
                "header",
                "footer",
                "formula",
            }:
                raise Rejected("Unsupported content type.")
            total += len(plain(content_text(b)))
            if b["kind"] == "table":
                nr, nc = b["rows"], b["cols"]
                occupied = set()
                if type(nr) != int or type(nc) != int:
                    raise Rejected("Invalid table dimensions.")
                if "widths" in b and (
                    len(b["widths"]) != nc
                    or any(
                        type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                        for v in b["widths"]
                    )
                ):
                    raise Rejected("Invalid table column widths.")
                if not 1 <= nr <= 500 or not 1 <= nc <= 64 or nr * nc > MAX_CELLS:
                    raise Rejected("Table too large.")
                for c in b["cells"]:
                    if any(flag in c and type(c[flag]) is not bool for flag in ("bold", "italic")):
                        raise Rejected("Invalid table cell emphasis.")
                    r, col, rs, cs = (
                        c[k] for k in ("row", "col", "rowspan", "colspan")
                    )
                    if (
                        any(type(v) != int for v in (r, col, rs, cs))
                        or min(r, col) < 0
                        or min(rs, cs) < 1
                        or r + rs > nr
                        or col + cs > nc
                    ):
                        raise Rejected("Invalid table cell.")
                    slots = {
                        (rr, cc)
                        for rr in range(r, r + rs)
                        for cc in range(col, col + cs)
                    }
                    if slots & occupied:
                        raise Rejected("Overlapping table cells.")
                    occupied |= slots
                if len(occupied) != nr * nc:
                    raise Rejected("Missing table cells.")
    if total > MAX_TEXT:
        raise Rejected("Document exceeds text limit.")
    return model

