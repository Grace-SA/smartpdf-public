"""Source-backed recovery for conflicting model spans in a physical table.

A model may omit blank columns, reverse vertical headers, or omit the grid's
external stub and detached total. Geometry comes from visible borders. Every
non-whitespace source character must agree with the prediction before use.
"""

from collections import Counter
from statistics import median

from pdfplumber.utils import cluster_list, extract_text


def inside(char, box):
    return (
        box[0] <= (char["x0"] + char["x1"]) / 2 < box[2]
        and box[1] <= (char["top"] + char["bottom"]) / 2 < box[3]
    )


def oriented_text(chars):
    if not chars:
        return ""
    # Rotate glyph coordinates, not their strings. Merely reversing words loses
    # reading order across spaces and multiple vertical lines.
    if all(
        not c["upright"] and abs(c["matrix"][0]) < 0.01 and c["matrix"][1] > 0
        for c in chars
    ):
        chars = [
            dict(
                c,
                x0=-c["bottom"],
                x1=-c["top"],
                top=c["x0"],
                bottom=c["x1"],
                doctop=c["x0"],
                upright=True,
                width=c["height"],
                height=c["width"],
            )
            for c in chars
        ]
    elif all(
        not c["upright"] and abs(c["matrix"][0]) < 0.01 and c["matrix"][1] < 0
        for c in chars
    ):
        chars = [
            dict(
                c,
                x0=c["top"],
                x1=c["bottom"],
                top=-c["x1"],
                bottom=-c["x0"],
                doctop=-c["x1"],
                upright=True,
                width=c["height"],
                height=c["width"],
            )
            for c in chars
        ]
    elif any(not c["upright"] for c in chars):
        # Mixed or oblique writing needs a different reading-order model.
        return None
    return extract_text(chars, x_tolerance=2, y_tolerance=3)


def has_vertical_headers(item, page):
    from layout_tables import model_box

    box = model_box(item["prov"][0]["bbox"], page)
    chars = [c for c in page.chars if not c["upright"] and inside(c, box)]
    return len(chars) >= 20 and len(cluster_list([c["x0"] for c in chars], 3)) >= 2


def boundaries(boxes, positions):
    return [
        median(group)
        for group in cluster_list([box[k] for box in boxes for k in positions], 3)
    ]


def indices(box, xs, ys):
    c, end_c = [
        min(range(len(xs)), key=lambda k: abs(xs[k] - value))
        for value in (box[0], box[2])
    ]
    r, end_r = [
        min(range(len(ys)), key=lambda k: abs(ys[k] - value))
        for value in (box[1], box[3])
    ]
    return r, c, end_r, end_c


def recover_source_grid(item, page):
    from layout_tables import model_box, overlap, physical_page, visible_box

    box = model_box(item["prov"][0]["bbox"], page)
    page = physical_page(page.crop(tuple(visible_box(page))))
    grids = page.find_tables()
    candidates = [t for t in grids if overlap(t.bbox, box) >= 0.65]
    if not candidates:
        return None
    main = max(
        candidates, key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1])
    )
    xs = boundaries(main.cells, (0, 2))
    ys = boundaries(main.cells, (1, 3))
    if len(xs) < 4 or len(ys) < 4 or (len(xs) - 1) * (len(ys) - 1) > 250000:
        return None
    covered = set()
    for cell in main.cells:
        r, c, er, ec = indices(cell, xs, ys)
        region = {(rr, cc) for rr in range(r, er) for cc in range(c, ec)}
        if not region or covered & region:
            return None
        covered.update(region)
    if len(covered) != (len(xs) - 1) * (len(ys) - 1):
        return None
    boxes = list(main.cells)
    pitch = median(b - a for a, b in zip(ys, ys[1:]))
    for other in grids:
        if other is main:
            continue
        b = other.bbox
        if (
            main.bbox[3] <= b[1] <= min(box[3], main.bbox[3] + 3 * pitch)
            and b[3] <= box[3] + 3
            and b[0] >= xs[0] - 3
            and b[2] <= xs[-1] + 3
            and all(
                min(abs(value - x) for x in xs) <= 3
                for cell in other.cells
                for value in (cell[0], cell[2])
            )
        ):
            boxes.extend(other.cells)
    ys = boundaries(boxes, (1, 3))
    source_box = [min(box[0] - 2, xs[0]), ys[0], xs[-1], ys[-1]]
    chars = [c for c in page.chars if inside(c, source_box)]
    stub = [c for c in chars if (c["x0"] + c["x1"]) / 2 < xs[0]]
    if stub:
        left = min(c["x0"] for c in stub) - 2
        if xs[0] - left > (xs[-1] - xs[0]) / 3:
            return None
        stub_rows = {
            r
            for r in range(len(ys) - 1)
            if any(inside(c, [left, ys[r], xs[0], ys[r + 1]]) for c in stub)
        }
        if len(stub_rows) < 3:
            return None
        xs = [left, *xs]
    if (len(xs) - 1) * (len(ys) - 1) > 250000:
        return None
    cells, covered = [], set()
    for cell in boxes:
        r, c, er, ec = indices(cell, xs, ys)
        region = {(rr, cc) for rr in range(r, er) for cc in range(c, ec)}
        if not region or covered & region:
            return None
        covered.update(region)
        cells.append(dict(r=r, c=c, rs=er - r, cs=ec - c))
    # Only external stub/footer cells can be inferred: the main grid was
    # independently required to be closed and complete above.
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            if (r, c) not in covered:
                cells.append(dict(r=r, c=c, rs=1, cs=1))
    for cell in cells:
        r, c, rs, cs = (cell[k] for k in ("r", "c", "rs", "cs"))
        bbox = [xs[c], ys[r], xs[c + cs], ys[r + rs]]
        glyphs = [ch for ch in chars if inside(ch, bbox)]
        cell["text"] = oriented_text(glyphs)
        if cell["text"] is None:
            return None
        if glyphs and all(not ch["upright"] for ch in glyphs):
            cell["rotation"] = 90 if glyphs[0]["matrix"][1] > 0 else 180
        if glyphs and all("bold" in ch.get("fontname", "").lower() for ch in glyphs):
            cell["bold"] = True
    before = Counter(
        ch for c in item["data"]["table_cells"] for ch in c["text"] if not ch.isspace()
    )
    after = Counter(ch for c in cells for ch in c["text"] if not ch.isspace())
    if not before or before != after:
        return None
    return dict(
        widths=[b - a for a, b in zip(xs, xs[1:])],
        heights=[b - a for a, b in zip(ys, ys[1:])],
        bbox=[xs[0], ys[0], xs[-1], ys[-1]],
        cells=cells,
        method="ruled-recovery",
        sourceGeometry=True,
    )
