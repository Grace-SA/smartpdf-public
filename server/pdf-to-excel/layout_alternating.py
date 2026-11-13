"""Recover complete records in fixed-width reports with alternating field rows."""

from collections import Counter
from statistics import median
import re
from pdfplumber.utils import cluster_objects
from layout_tables import visible_box


def recover_alternating_tables(page):
    page = page.crop(tuple(visible_box(page)))
    words = page.extract_words(x_tolerance=2, y_tolerance=2)
    lines = cluster_objects(words, lambda w: (w["top"] + w["bottom"]) / 2, 2)
    lines = [sorted(line, key=lambda w: w["x0"]) for line in lines]
    rules = [
        i
        for i, line in enumerate(lines)
        if len(line) >= 3 and all(re.fullmatch(r"[-_]{3,}", w["text"]) for w in line)
    ]
    if len(rules) != 2:
        return []
    tables = []
    for first, second in zip(rules, rules[1:]):
        if second != first + 2 or first < 1:
            continue
        a, b = lines[first], lines[second]
        if len(a) < 5 or len(b) < 3 or len(a) <= len(b):
            continue
        if sum(any(abs(x["x0"] - y["x0"]) <= 1 for y in b) for x in a) < 3:
            continue
        height = median(w["bottom"] - w["top"] for w in a + b)
        if not height <= b[0]["top"] - a[0]["top"] <= height * 2.5:
            continue
        left, right = a[0]["x0"], a[-1]["x1"]
        if abs(left - b[0]["x0"]) > 1 or b[-1]["x1"] > right:
            continue
        anchors = sorted({round(w["x0"], 1) for w in a + b})
        if len(anchors) > len(a) + 2:
            continue

        def partition(line, pattern):
            starts = [w["x0"] for w in pattern]
            edges = starts + [right + 1]
            fields = []
            for j, start in enumerate(starts):
                part = [
                    w
                    for w in line
                    if start - 1 <= (w["x0"] + w["x1"]) / 2 < edges[j + 1] - 1
                ]
                if (
                    not part
                    or min(w["x0"] for w in part) < start - 1
                    or max(w["x1"] for w in part) > edges[j + 1] + 1
                ):
                    return None
                fields.append(" ".join(w["text"] for w in part))
            if sum(len(v.replace(" ", "")) for v in fields) != sum(
                len(w["text"].replace(" ", "")) for w in line
            ):
                return None
            return fields

        headers = [partition(lines[first - 1], a), partition(lines[second - 1], b)]
        if any(
            v is None or any(not any(ch.isalpha() for ch in field) for field in v)
            for v in headers
        ):
            continue
        body = []
        positions = []
        end = second + 1
        for i in range(second + 1, len(lines) - 1, 2):
            row1, row2 = lines[i], lines[i + 1]
            values1, values2 = partition(row1, a), partition(row2, b)
            gap = row2[0]["top"] - row1[0]["top"]
            if (
                values1 is None
                or values2 is None
                or not height * 0.7 <= gap <= height * 1.3
            ):
                break
            if (
                positions
                and abs((row1[0]["top"] - positions[-1]) - height * 3) > height * 0.25
            ):
                break
            body.extend([values1, values2])
            positions.append(row1[0]["top"])
            end = i + 2
        if len(body) < 6:
            continue
        # Do not silently export a prefix when an incomplete record remains.
        if any(
            partition(line, a) is not None
            or partition(line, b) is not None
            or sum(any(abs(w["x0"] - v["x0"]) <= 1 for v in a + b) for w in line) >= 2
            for line in lines[end:]
        ):
            continue
        end_bottom = max(w["bottom"] for w in lines[end - 1])
        chosen = [w for line in lines[first - 1 : end] for w in line]
        glyphs = [
            c
            for c in page.chars
            if left - 1 <= (c["x0"] + c["x1"]) / 2 <= right + 1
            and lines[first - 1][0]["top"] - 1
            <= (c["top"] + c["bottom"]) / 2
            <= end_bottom + 1
        ]
        if (
            not glyphs
            or sum("courier" in c["fontname"].lower() for c in glyphs)
            < len(glyphs) * 0.95
        ):
            continue
        cells = []
        for r, row in enumerate(headers + body):
            pattern = a if r % 2 == 0 else b
            for j, text in enumerate(row):
                c = min(
                    range(len(anchors)),
                    key=lambda k: abs(anchors[k] - pattern[j]["x0"]),
                )
                ec = (
                    min(
                        range(len(anchors)),
                        key=lambda k: abs(anchors[k] - pattern[j + 1]["x0"]),
                    )
                    if j + 1 < len(pattern)
                    else len(anchors)
                )
                cells.append(dict(r=r, c=c, rs=1, cs=ec - c, text=text))
        source = Counter(
            ch for w in chosen if w not in a + b for ch in w["text"] if not ch.isspace()
        )
        result = Counter(ch for c in cells for ch in c["text"] if not ch.isspace())
        if source != result:
            continue
        ys = (
            [
                min(w["top"] for w in lines[first - 1]),
                min(w["top"] for w in lines[second - 1]),
            ]
            + [min(w["top"] for w in line) for line in lines[second + 1 : end]]
            + [end_bottom + 2]
        )
        xs = anchors + [right]
        tables.append(
            dict(
                cells=cells,
                widths=[b - a for a, b in zip(xs, xs[1:])],
                heights=[b - a for a, b in zip(ys, ys[1:])],
                bbox=[left, ys[0], right, ys[-1]],
                method="alternating-fields",
                headerRows=2,
                sourceGeometry=True,
            )
        )
    return tables
