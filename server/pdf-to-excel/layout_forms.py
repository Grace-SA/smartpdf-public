"""Source-positioned native forms with independently visible checkbox states."""

from collections import Counter, defaultdict
from statistics import median
import math
from pdfplumber.utils import cluster_objects, extract_text


def black(colour):
    if colour is None:
        return True
    if isinstance(colour, (int, float)):
        return math.isfinite(colour) and 0 <= colour <= 0.05
    if not isinstance(colour, (list, tuple)) or not all(
        isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in colour
    ):
        return False
    return (len(colour) == 3 and max(colour) <= 0.05) or (
        len(colour) == 4 and max(colour[:3]) <= 0.05 and colour[3] >= 0.95
    )


def control_rectangles(page):
    from layout_tables import visible_box

    view = visible_box(page)
    boxes = []
    for r in page.rects:
        if not (
            view[0] <= r["x0"] < r["x1"] <= view[2]
            and view[1] <= r["top"] < r["bottom"] <= view[3]
        ):
            continue
        if (
            not r.get("stroke")
            or r.get("fill")
            or not black(r.get("stroking_color"))
            or not 5 <= r["width"] <= 15
            or abs(r["width"] - r["height"]) > 1
        ):
            continue
        boxes.append(r)
    return boxes


def checkboxes(page):
    candidates = control_rectangles(page)
    if len(candidates) > 128 or len(page.lines) + len(page.curves) > 10000:
        return None
    boxes = []
    for r in candidates:
        if any(
            abs(r["x0"] - b["x0"]) < 1 and abs(r["top"] - b["top"]) < 1 for b in boxes
        ):
            continue
        signs = set()
        interior = False
        for line in page.lines:
            if not black(line.get("stroking_color")):
                continue
            pts = line.get("pts", [])
            if len(pts) != 2:
                continue
            (x0, y0), (x1, y1) = pts
            dx = x1 - x0
            dy = y1 - y0
            if (
                r["x0"] + 0.75 < (x0 + x1) / 2 < r["x1"] - 0.75
                and r["top"] + 0.75 < (y0 + y1) / 2 < r["bottom"] - 0.75
                and abs(dx) + abs(dy) > 1
            ):
                interior = True
            if abs(dx) < r["width"] * 0.7 or abs(dy) < r["height"] * 0.7:
                continue
            if all(
                r["x0"] - 0.5 <= x <= r["x1"] + 0.5
                and r["top"] - 0.5 <= y <= r["bottom"] + 0.5
                for x, y in pts
            ):
                signs.add(1 if dx * dy > 0 else -1)
        if (signs or interior) and len(signs) != 2:
            return None
        # Text, filled marks and curved strokes must not silently become an
        # empty checkbox. Only a pair of complete straight diagonals is proven.
        if any(
            c["text"].strip()
            and r["x0"] < (c["x0"] + c["x1"]) / 2 < r["x1"]
            and r["top"] < (c["top"] + c["bottom"]) / 2 < r["bottom"]
            for c in page.chars
        ):
            return None
        if not signs and any(
            r["x0"] <= (v["x0"] + v["x1"]) / 2 <= r["x1"]
            and r["top"] <= (v["top"] + v["bottom"]) / 2 <= r["bottom"]
            and (v.get("fill") or (v in page.curves and v.get("stroke")))
            and v["width"] > 1
            and v["height"] > 1
            for v in page.rects + page.curves
            if v is not r
        ):
            return None
        boxes.append(
            dict(
                x0=r["x0"],
                x1=r["x1"],
                top=r["top"],
                bottom=r["bottom"],
                text="☒" if signs else "☐",
                checkbox=True,
            )
        )
    return boxes


def horizontal_rules(page, view):
    rules = []
    for r in page.rects:
        if (
            not black(r.get("non_stroking_color"))
            or not r.get("fill")
            or r["width"] <= 30
            or not 0 < r["height"] < 4
        ):
            continue
        x0 = max(view[0], r["x0"])
        x1 = min(view[2], r["x1"])
        y = (r["top"] + r["bottom"]) / 2
        if x0 < x1 and view[1] <= y < view[3]:
            rules.append(dict(x0=x0, x1=x1, y=y, weight=r["height"]))
    return rules


def recover(page):
    from layout_typography import valid_glyph, family
    from layout_tables import visible_box

    if page.rotation:
        return None
    boxes = checkboxes(page)
    if boxes is None or len(boxes) < 5:
        return None
    view = visible_box(page)
    chars = [
        c
        for c in page.chars
        if c["text"].strip()
        and view[0] <= (c["x0"] + c["x1"]) / 2 <= view[2]
        and view[1] <= (c["top"] + c["bottom"]) / 2 <= view[3]
    ]
    if (
        not chars
        or len(chars) > 15000
        or any(
            not valid_glyph(c)
            or not family(c["fontname"])
            or len(c.get("matrix", ())) != 6
            or not all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in c["matrix"]
            )
            for c in chars
        )
    ):
        return None
    rules = horizontal_rules(page, view)
    decoration_ids = set()
    decorations = []
    h = median(c["size"] for c in chars)
    # Original text baselines keep mixed fonts on the same visual row.
    groups = cluster_objects(chars, lambda c: c["matrix"][5], h * 0.22)
    lines = []
    for group in groups:
        words = []
        for c in sorted(group, key=lambda c: c["x0"]):
            if (
                words
                and c["fontname"] == words[-1][-1]["fontname"]
                and abs(c["size"] - words[-1][-1]["size"]) < 0.1
                and c["x0"] - words[-1][-1]["x1"] < h * 0.9
            ):
                words[-1].append(c)
            else:
                words.append([c])
        runs = []
        for word in words:
            run = dict(
                x0=min(c["x0"] for c in word),
                x1=max(c["x1"] for c in word),
                top=min(c["top"] for c in word),
                bottom=max(c["bottom"] for c in word),
                text=extract_text(word, x_tolerance=1, y_tolerance=1),
                chars=word,
            )
            if (
                len(run["text"]) >= 3
                and set(run["text"]) == {"_"}
                and any(
                    run["top"] <= rule["y"] <= run["bottom"]
                    and min(rule["x1"], run["x1"]) - max(rule["x0"], run["x0"])
                    >= (run["x1"] - run["x0"]) * 0.98
                    for rule in rules
                )
            ):
                decoration_ids.update(id(c) for c in word)
                decorations.append(
                    dict(
                        kind="overprinted-underline",
                        glyphCount=len(run["text"]),
                        bbox=[run[k] for k in ["x0", "top", "x1", "bottom"]],
                    )
                )
            else:
                runs.append(run)
        lines.append(
            dict(
                top=min(c["top"] for c in group),
                bottom=max(c["bottom"] for c in group),
                runs=runs,
            )
        )
    lines.sort(key=lambda l: l["top"])
    for box in boxes:
        candidates = [
            l
            for l in lines
            if min(l["bottom"], box["bottom"]) - max(l["top"], box["top"])
            > min(l["bottom"] - l["top"], box["bottom"] - box["top"]) * 0.4
        ]
        if len(candidates) != 1:
            return None
        candidates[0]["runs"].append(box)
    unit = 1.5
    cols = math.ceil((view[2] - view[0]) / unit)
    ys = [view[1]] + [l["top"] for l in lines] + [view[3]]
    if cols * (len(ys) - 1) > 250000 or any(b - a < 1 for a, b in zip(ys, ys[1:])):
        return None
    cells = []
    for row, line in enumerate(lines, 1):
        runs = sorted(line["runs"], key=lambda r: r["x0"])
        for i, run in enumerate(runs):
            left = max(0, math.floor((run["x0"] - view[0] - 1) / unit))
            end = min(view[2], runs[i + 1]["x0"] - 1 if i + 1 < len(runs) else view[2])
            right = min(cols, max(left + 1, math.floor((end - view[0]) / unit)))
            if i and left < cells[-1]["c"] + cells[-1]["cs"]:
                return None
            if right * unit + view[0] < run["x1"]:
                return None
            cell = dict(r=row, c=left, rs=1, cs=right - left, text=run["text"])
            if run.get("checkbox"):
                cell.update(
                    fontName="DejaVu Sans",
                    fontSize=(run["bottom"] - run["top"]) * 1.2,
                    sourceVector=True,
                    checkbox=True,
                )
            else:
                glyphs = run["chars"]
                widths = defaultdict(list)
                for ch in glyphs:
                    widths[ch["text"]].append(ch["width"])
                cell.update(
                    fontName=family(glyphs[0]["fontname"]),
                    fontSize=median(c["size"] for c in glyphs),
                    bold=all("bold" in c["fontname"].lower() for c in glyphs),
                    sourceFont=True,
                    glyphWidths={k: median(v) for k, v in widths.items()},
                )
            cells.append(cell)
    original = Counter(
        c
        for g in chars
        if id(g) not in decoration_ids
        for c in g["text"]
        if not c.isspace()
    )
    actual = Counter(
        c
        for cell in cells
        if not cell.get("checkbox")
        for c in cell["text"]
        if not c.isspace()
    )
    if original != actual:
        return None
    rules = horizontal_rules(page, view)
    return dict(
        widths=[unit] * cols,
        heights=[b - a for a, b in zip(ys, ys[1:])],
        cells=cells,
        method="native-form",
        coordinateGrid=True,
        decorations=decorations,
        sourceRules=[
            dict(rule, x0=rule["x0"] - view[0], x1=rule["x1"] - view[0])
            for rule in rules
        ],
        sourceRowEdges=ys,
        sourceGeometry=True,
        headerRows=0,
        sourcePageOrientation="landscape" if page.width > page.height else "portrait",
        checkboxCount=len(boxes),
        checkedCount=sum(b["text"] == "☒" for b in boxes),
    )
