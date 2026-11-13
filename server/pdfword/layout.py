"""Native geometric reconstruction. PDFium renders; pdfplumber supplies glyphs/grids."""

import math
import re
from statistics import median
from model import Rejected, table_header_rows


def contains(a, b, pad=0):
    x, y = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return a[0] - pad <= x <= a[2] + pad and a[1] - pad <= y <= a[3] + pad


def union(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def order_blocks(blocks):
    """Recursive whitespace cuts separate columns before ordering within each column."""
    if len(blocks) < 2:
        return blocks
    for axis, min_gap in ((0, 18), (1, 5)):
        intervals = sorted((b["bbox"][axis], b["bbox"][axis + 2]) for b in blocks)
        end = intervals[0][1]
        gaps = []
        for lo, hi in intervals[1:]:
            if lo - end >= min_gap:
                gaps.append((lo - end, (lo + end) / 2))
            end = max(end, hi)
        if gaps:
            _, cut = max(gaps)
            left = [b for b in blocks if b["bbox"][axis + 2] <= cut]
            right = [b for b in blocks if b["bbox"][axis] >= cut]
            if left and right and len(left) + len(right) == len(blocks):
                return order_blocks(left) + order_blocks(right)
    return sorted(blocks, key=lambda b: (round(b["bbox"][1] / 3), b["bbox"][0]))


def join_words(words):
    text = ""
    previous = None
    for w in sorted(words, key=lambda w: w["x0"]):
        value = w["text"]
        cjk = (
            previous
            and re.search(r"[\u2e80-\u9fff]$", text)
            and re.match(r"[\u2e80-\u9fff，。！？；：]", value)
        )
        text += (" " if text and not cjk else "") + value
        previous = w
    return text


def words_to_blocks(words, width, height):
    if not words:
        return []
    sizes = [c.get("size", 11) for w in words for c in w.get("chars", [])]
    normal = median(sizes) if sizes else 11
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        line = next(
            (
                l
                for l in reversed(lines[-8:])
                if abs(median(t["top"] for t in l) - w["top"]) <= max(2, normal * 0.25)
            ),
            None,
        )
        if line is None:
            lines.append([w])
        else:
            line.append(w)
    blocks = []
    for line in lines:
        groups = []
        for w in sorted(line, key=lambda w: w["x0"]):
            if not groups or w["x0"] - groups[-1][-1]["x1"] > max(26, normal * 2.5):
                groups.append([])
            groups[-1].append(w)
        for group in groups:
            chars = [c for w in group for c in w.get("chars", [])]
            fonts = [c.get("fontname", "").lower() for c in chars]
            size = median(c.get("size", normal) for c in chars) if chars else normal
            bounds = union([[w["x0"], w["top"], w["x1"], w["bottom"]] for w in group])
            text = join_words(group)
            runs = []
            consumed = ""
            for w in sorted(group, key=lambda w: w["x0"]):
                prefix = (
                    ""
                    if not consumed
                    or (
                        re.search(r"[\u2e80-\u9fff]$", consumed)
                        and re.match(r"[\u2e80-\u9fff，。！？；：]", w["text"])
                    )
                    else " "
                )
                letters = w.get("chars", [])
                names = [c.get("fontname", "").lower() for c in letters]
                runs.append(
                    dict(
                        text=prefix + w["text"],
                        size=(
                            median(c.get("size", size) for c in letters)
                            if letters
                            else size
                        ),
                        bold=bool(
                            names and sum("bold" in f for f in names) > len(names) / 2
                        ),
                        italic=bool(
                            names
                            and sum("italic" in f or "oblique" in f for f in names)
                            > len(names) / 2
                        ),
                    )
                )
                consumed += prefix + w["text"]
            kind = "heading" if size >= normal * 1.23 else "paragraph"
            if re.match(r"^\s*(?:[•●▪]|[-–]\s|\d+[.)]\s|[a-zA-Z][.)]\s)", text):
                kind = "list"
            blocks.append(
                dict(
                    kind=kind,
                    bbox=bounds,
                    text=text,
                    runs=runs,
                    size=size,
                    bold=bool(
                        fonts and sum("bold" in f for f in fonts) > len(fonts) / 2
                    ),
                    italic=bool(
                        fonts
                        and sum("italic" in f or "oblique" in f for f in fonts)
                        > len(fonts) / 2
                    ),
                    source="native",
                )
            )
    ordered = order_blocks(blocks)
    result = []
    for block in ordered:
        prev = result[-1] if result else None
        if (
            prev
            and prev["kind"] == block["kind"] == "paragraph"
            and abs(prev["bbox"][0] - block["bbox"][0]) < max(4, normal * 0.5)
            and abs(prev["size"] - block["size"]) < 1
            and prev["bold"] == block["bold"]
            and 0 <= block["bbox"][1] - prev["bbox"][3] <= normal * 0.75
            and abs(prev["bbox"][2] - block["bbox"][2]) < width * 0.25
        ):
            separator = (
                ""
                if re.search(r"[\u2e80-\u9fff]$", prev["text"])
                and re.match(r"[\u2e80-\u9fff]", block["text"])
                else " "
            )
            if block.get("runs"):
                block["runs"][0]["text"] = separator + block["runs"][0]["text"]
                prev["runs"].extend(block["runs"])
            prev["text"] += separator + block["text"]
            prev["bbox"] = union([prev["bbox"], block["bbox"]])
        else:
            result.append(block)
    return result


def native_tables(page, words):
    result = []
    for table in page.find_tables():
        if len(table.rows) < 2 or len(table.columns) < 2:
            continue
        boxes = [list(c) for c in table.cells if c]
        xs = sorted(set(round(v, 1) for c in boxes for v in (c[0], c[2])))
        ys = sorted(set(round(v, 1) for c in boxes for v in (c[1], c[3])))
        if (len(xs) - 1) * (len(ys) - 1) > 10000:
            raise Rejected("Table exceeds cell budget.")
        cells = []
        for b in boxes:
            c0, c1 = (
                min(range(len(xs)), key=lambda j: abs(xs[j] - b[k])) for k in (0, 2)
            )
            r0, r1 = (
                min(range(len(ys)), key=lambda j: abs(ys[j] - b[k])) for k in (1, 3)
            )
            # Word extraction can join glyphs across a ruling. Assign glyphs to
            # cells first so an entire joined word cannot land in one neighbour.
            from pdfplumber.utils import extract_words

            chars = [
                char
                for w in words
                for char in w.get("chars", [])
                if b[0] <= (char["x0"] + char["x1"]) / 2 < b[2]
                and b[1] <= (char["top"] + char["bottom"]) / 2 < b[3]
            ]
            inside = extract_words(
                chars, return_chars=True, x_tolerance=2, y_tolerance=3
            )
            paras = words_to_blocks(inside, page.width, page.height)
            cells.append(
                dict(
                    row=r0,
                    col=c0,
                    rowspan=r1 - r0,
                    colspan=c1 - c0,
                    text="\n".join(p["text"] for p in paras),
                    size=median(p["size"] for p in paras) if paras else 10,
                    header=False,
                )
            )
        if sum(bool(c["text"]) for c in cells) < 2:
            continue
        slots = set()
        for c in cells:
            covered = {
                (r, col)
                for r in range(c["row"], c["row"] + c["rowspan"])
                for col in range(c["col"], c["col"] + c["colspan"])
            }
            if slots & covered:
                raise Rejected("Incomplete native table grid.")
            slots |= covered
        if len(slots) != (len(xs) - 1) * (len(ys) - 1):
            raise Rejected("Incomplete native table grid.")
        result.append(
            dict(
                kind="table",
                bbox=list(table.bbox),
                rows=len(ys) - 1,
                cols=len(xs) - 1,
                cells=cells,
                widths=[b - a for a, b in zip(xs, xs[1:])],
                source="native",
            )
        )
    return result


def borderless_tables(words, page):
    """Recover regular numeric grids only; ambiguous/multiline grids still use OCR."""
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 3:
            lines.append([])
        lines[-1].append(word)
    rows = []
    for line in lines:
        groups = []
        for word in sorted(line, key=lambda w: w["x0"]):
            if not groups or word["x0"] - groups[-1][-1]["x1"] > 18:
                groups.append([])
            groups[-1].append(word)
        rows.append(groups)
    result = []
    pending = []

    def finish():
        if len(pending) < 3:
            return
        cols = len(pending[0])
        numeric = sum(
            all(
                re.fullmatch(r"[-+($€£¥]?\d[\d,.%()−-]*", join_words(cell))
                for cell in row[1:]
            )
            for row in pending
        )
        if numeric < max(2, len(pending) - 1):
            return
        boxes = [
            [
                union([[w["x0"], w["top"], w["x1"], w["bottom"]] for w in cell])
                for cell in row
            ]
            for row in pending
        ]
        lefts = [min(row[c][0] for row in boxes) for c in range(cols)]
        rights = [max(row[c][2] for row in boxes) for c in range(cols)]
        if any(rights[c] + 12 > lefts[c + 1] for c in range(cols - 1)):
            return
        edges = (
            [lefts[0]]
            + [(rights[c] + lefts[c + 1]) / 2 for c in range(cols - 1)]
            + [rights[-1]]
        )
        cells = []
        for r, row in enumerate(pending):
            for c, cell in enumerate(row):
                sizes = [char["size"] for w in cell for char in w.get("chars", [])]
                cells.append(
                    dict(
                        row=r,
                        col=c,
                        rowspan=1,
                        colspan=1,
                        text=join_words(cell),
                        size=median(sizes) if sizes else 10,
                        header=False,
                    )
                )
        result.append(
            dict(
                kind="table",
                rows=len(pending),
                cols=cols,
                cells=cells,
                bbox=union([b for row in boxes for b in row]),
                widths=[b - a for a, b in zip(edges, edges[1:])],
                source="native",
            )
        )

    for row in rows:
        if pending:
            previous = pending[-1]
            height = max(w["bottom"] - w["top"] for cell in previous for w in cell)
            gap = row[0][0]["top"] - previous[0][0]["top"]
            if len(row) != len(previous) or gap > max(18, height * 2.5):
                finish()
                pending = []
        if 2 <= len(row) <= 32:
            pending.append(row)
    finish()
    return result


def graphics(page, tables):
    boxes = []
    for image in page.images:
        b = [image["x0"], image["top"], image["x1"], image["bottom"]]
        if b[2] - b[0] > 3 and b[3] - b[1] > 3:
            boxes.append(b)
    # Connected vector regions preserve charts; table borders are already reconstructed.
    for obj in page.curves + page.rects + page.lines:
        b = [obj["x0"], obj["top"], obj["x1"], obj["bottom"]]
        if any(contains(t["bbox"], b, 2) for t in tables):
            continue
        if (b[2] - b[0]) * (b[3] - b[1]) > page.width * page.height * 0.8:
            continue
        if b[2] - b[0] < 2 and b[3] - b[1] < 2:
            continue
        boxes.append([b[0] - 1, b[1] - 1, b[2] + 1, b[3] + 1])
    merged = []
    for b in boxes:
        pending = True
        while pending:
            pending = False
            for other in list(merged):
                if not (
                    b[2] + 4 < other[0]
                    or other[2] + 4 < b[0]
                    or b[3] + 4 < other[1]
                    or other[3] + 4 < b[1]
                ):
                    b = union([b, other])
                    merged.remove(other)
                    pending = True
        merged.append(b)
    return [
        [max(0, b[0]), max(0, b[1]), min(page.width, b[2]), min(page.height, b[3])]
        for b in merged
        if b[2] - b[0] > 12 and b[3] - b[1] > 12
    ]


def native_page(page):
    if len(page.chars) > 60000:
        raise Rejected("Page exceeds text budget.")
    clean = page.dedupe_chars(tolerance=0.5)
    words = clean.extract_words(
        return_chars=True, x_tolerance=2, y_tolerance=3, keep_blank_chars=False
    )
    words = [w for w in words if w["text"].strip()]
    tables = native_tables(clean, words)
    remaining_words = [
        w
        for w in words
        if not any(
            contains(t["bbox"], [w["x0"], w["top"], w["x1"], w["bottom"]])
            for t in tables
        )
    ]
    tables.extend(borderless_tables(remaining_words, clean))
    images = graphics(clean, tables)
    excluded = [t["bbox"] for t in tables] + images
    remaining = [
        w
        for w in words
        if not any(
            contains(b, [w["x0"], w["top"], w["x1"], w["bottom"]]) for b in excluded
        )
    ]
    # Sparse text-only grids also occur without any numeric cells or rules.
    # Three separated short cells on repeated baselines require layout recognition.
    baselines = []
    for word in sorted(remaining, key=lambda w: (w["top"], w["x0"])):
        if not baselines or abs(word["top"] - baselines[-1][0]["top"]) > 3:
            baselines.append([])
        baselines[-1].append(word)
    sparse_rows = 0
    for row in baselines:
        groups = []
        for word in sorted(row, key=lambda w: w["x0"]):
            if not groups or word["x0"] - groups[-1][-1]["x1"] > 18:
                groups.append([])
            groups[-1].append(word)
        if len(groups) >= 3 and all(
            sum(len(w["text"]) for w in group) <= 32 for group in groups
        ):
            sparse_rows += 1
    if sparse_rows >= 2:
        raise Rejected("Layout needs OCR.")
    # Aligned numeric rows without ruling are ambiguous in native extraction.
    # Ask the layout model instead of quietly exporting a table as prose.
    aligned = {}
    # Require an indented continuation line, not just a nearby word: a compact
    # row-number / label / status grid is otherwise indistinguishable from lists.
    baseline_for = {id(word): i for i, row in enumerate(baselines) for word in row}

    def continued_list_marker(word):
        if not re.fullmatch(r"\d+[.)]", word["text"]):
            return False
        index = baseline_for[id(word)]
        row = baselines[index]
        following = [v for v in row if 0 <= v["x0"] - word["x1"] <= 12]
        if not following:
            return False
        first = min(following, key=lambda v: v["x0"])
        if not first["text"][:1].isalpha():
            return False
        height = max(1, word["bottom"] - word["top"])
        for continuation in baselines[index + 1:index + 9]:
            gap = continuation[0]["top"] - word["top"]
            if gap > height * 1.8:
                break
            if gap < height * 0.8:
                continue
            # No new marker or text may occupy the marker's hanging indent.
            if any(word["x0"] - 2 <= v["x0"] < first["x0"] - 3 for v in continuation):
                continue
            if any(abs(v["x0"] - first["x0"]) <= 3 and v["text"][:1].isalpha()
                   for v in continuation):
                return True
        return False

    for w in remaining:
        if not continued_list_marker(w) and re.fullmatch(r"[-+($€£¥]?\d[\d,.%()−-]*", w["text"]):
            key = round(w["x1"] / 8)
            aligned.setdefault(key, set()).add(round(w["top"] / 5))
    if any(len(rows) >= 3 for rows in aligned.values()):
        candidates = words_to_blocks(remaining, page.width, page.height)
        if any(
            abs(a["bbox"][1] - b["bbox"][1]) < 4 and a["bbox"][2] + 18 < b["bbox"][0]
            for a in candidates
            for b in candidates
        ):
            raise Rejected("Layout needs OCR.")
    blocks = words_to_blocks(remaining, page.width, page.height) + tables
    blocks.extend(dict(kind="image", bbox=b, source="native") for b in images)
    return order_blocks(blocks)


def repeated_margins(pages):
    """Only repeated margin text is promoted; single-page headings stay in the body."""
    if len(pages) < 2:
        return
    keys = {}
    for p in pages:
        if len(p["blocks"]) < 2:
            continue
        for b in p["blocks"]:
            if b["kind"] not in ("paragraph", "heading"):
                continue
            edge = (
                "header"
                if b["bbox"][3] < p["height"] * 0.08
                else "footer" if b["bbox"][1] > p["height"] * 0.92 else None
            )
            if edge:
                title = re.sub(
                    r"\s*(?:\(?continued\)?|续表|（续）)\s*$",
                    "",
                    b["text"].strip(),
                    flags=re.I,
                )
                key = (edge, re.sub(r"\d+", "#", title))
                keys.setdefault(key, []).append((p["index"], b))
    for (edge, _), items in keys.items():
        if len({i for i, b in items}) >= max(2, math.ceil(len(pages) * 0.6)):
            for _, b in items:
                b["kind"] = edge


def link_tables(pages):
    """Merge only repeated-header continuations reaching adjacent page edges."""
    for previous, current in zip(pages, pages[1:]):
        a = next(
            (b for b in reversed(previous["blocks"]) if b["kind"] == "table"), None
        )
        b = next((b for b in current["blocks"] if b["kind"] == "table"), None)
        if not a or not b or a["cols"] != b["cols"]:
            continue
        header_count_a = table_header_rows(a)
        header_count_b = table_header_rows(b)

        def header(t, count):
            return sorted(
                (c["row"], c["col"], c["rowspan"], c["colspan"], c["text"].strip())
                for c in t["cells"] if c["row"] < count
            )
        titles = lambda p: [
            re.sub(
                r"\s*(?:\(?continued\)?|续表|（续）)\s*$",
                "",
                v["text"].strip(),
                flags=re.I,
            ).casefold()
            for v in p["blocks"]
            if v["kind"] in ("header", "heading") and v["bbox"][1] < p["height"] * 0.15
        ]
        explicit = any(
            re.search(r"(?:\bcontinued\)?|续表|（续）)\s*$", v.get("text", ""), re.I)
            for v in current["blocks"]
            if v["bbox"][1] < current["height"] * 0.15
        )
        continuation = b.get("continuation", False) or (
            explicit and bool(set(titles(previous)) & set(titles(current)))
        )
        repeats = (
            0 < header_count_a == header_count_b < b["rows"]
            and header(a, header_count_a) == header(b, header_count_b)
            and any(c["text"].strip() for c in b["cells"] if c["row"] < header_count_b)
        )
        if not (
            (repeats or continuation)
            and a["bbox"][3] > previous["height"] * 0.75
            and b["bbox"][1] < current["height"] * 0.25
        ):
            continue
        # Require compatible column proportions as independent geometry evidence.
        wa = a.get("widths")
        wb = b.get("widths")
        if (
            wa
            and wb
            and max(abs(x / sum(wa) - y / sum(wb)) for x, y in zip(wa, wb)) > 0.06
        ):
            continue
        b["continues"] = a.get("continues", a["id"])
        b["repeat_header"] = repeats
        b["repeat_header_rows"] = header_count_b if repeats else 0
        if repeats:
            a["header_rows"] = header_count_a

