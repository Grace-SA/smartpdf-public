"""Experimental source-backed OCR for numeric reports with dotted row leaders.

No document IDs, labels, expected values or sample-specific crop coordinates.
Returns no table when geometry, row coverage or independent recognition disagree.
"""

import math, re
from collections import Counter, defaultdict
from statistics import median
import cv2, numpy as np
from pdfplumber.utils import cluster_objects
from ocr_monospace import from_pixels

NUMERIC = re.compile(r"(?:\d+(?:\.\d+)?|\.\d+)")


def flat(text):
    return "".join(text.split())


def normalized(text):
    return " ".join(text.split())


def box_of(points):
    return [
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    ]


def crop(image, box, pad=0):
    x0, y0, x1, y1 = box
    return image[
        max(0, math.floor(y0) - pad) : min(image.shape[0], math.ceil(y1) + pad),
        max(0, math.floor(x0) - pad) : min(image.shape[1], math.ceil(x1) + pad),
    ]


def leaders(image, box, right, height):
    x0, y0, x1, y1 = box
    im = crop(image, [x0, y0, right, y1])
    gray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    n, _, stats, centers = cv2.connectedComponentsWithStats(bw)
    dots = [
        (centers[i][0] + math.floor(x0), centers[i][1] + math.floor(y0))
        for i in range(1, n)
        if 1 <= stats[i, cv2.CC_STAT_HEIGHT] <= height * 0.22
        and 1 <= stats[i, cv2.CC_STAT_WIDTH] <= height * 0.22
        and centers[i][0] > height * 2
    ]
    chains = []
    for start in dots:
        chain = sorted(
            p
            for p in dots
            if p[0] >= start[0] and abs(p[1] - start[1]) <= max(2, height * 0.1)
        )
        if len(chain) < 3:
            continue
        gaps = [b[0] - a[0] for a, b in zip(chain, chain[1:])]
        pitch = median(gaps)
        if pitch < height * 0.5:
            continue
        if all(abs(g - pitch) <= pitch * 0.25 for g in gaps) and not any(
            centers[i][0] + math.floor(x0) >= chain[0][0]
            and stats[i, cv2.CC_STAT_HEIGHT] > height * 0.3
            for i in range(1, n)
        ):
            chains.append(chain)
    if not chains:
        return None
    return max(chains, key=len)[0][0] - max(3, height * 0.16)


def grid(result):
    words = []
    for points, text, score in result:
        if (
            len(points) != 4
            or not text
            or not all(math.isfinite(v) for p in points for v in p)
        ):
            continue
        b = box_of(points)
        if b[0] >= b[2] or b[1] >= b[3]:
            continue
        words.append(dict(box=b, text=text, score=float(score)))
    numeric = [w for w in words if NUMERIC.fullmatch(w["text"]) and w["score"] >= 0.9]
    if len(numeric) < 30:
        return None
    h = median(w["box"][3] - w["box"][1] for w in numeric)
    if h < 8:
        return None
    columns = [
        g
        for g in cluster_objects(numeric, lambda w: w["box"][2], h * 0.4)
        if len(g) >= 5
    ]
    if not 3 <= len(columns) <= 16:
        return None
    columns.sort(key=lambda g: median(w["box"][2] for w in g))
    slopes = []
    for a, b in zip(columns, columns[1:]):
        for w in a:
            y = (w["box"][1] + w["box"][3]) / 2
            close = [v for v in b if abs((v["box"][1] + v["box"][3]) / 2 - y) < h * 0.5]
            if len(close) != 1:
                continue
            v = close[0]
            dx = v["box"][2] - w["box"][2]
            if dx > h * 2:
                slopes.append(((v["box"][1] + v["box"][3]) / 2 - y) / dx)
    if len(slopes) < 20:
        return None
    slope = median(slopes)
    if abs(slope) > 0.03:
        return None
    cy = (
        lambda w: (w["box"][1] + w["box"][3]) / 2
        - slope * (w["box"][0] + w["box"][2]) / 2
    )
    groups = cluster_objects(words, cy, h * 0.32)
    xs = [median(w["box"][2] for w in g) for g in columns]
    data = []
    for group in groups:
        values = [None] * (len(xs) + 1)
        valid = True
        for w in sorted(group, key=lambda w: w["box"][0]):
            if w["box"][2] < xs[0] - h * 2:
                col = 0
            else:
                col = 1 + min(range(len(xs)), key=lambda i: abs(xs[i] - w["box"][2]))
                if abs(xs[col - 1] - w["box"][2]) > h * 0.6 or not NUMERIC.fullmatch(
                    w["text"]
                ):
                    valid = False
                    break
            if values[col] is not None:
                valid = False
                break
            values[col] = w
        if (
            valid
            and values[0]
            and sum(c.isalpha() for c in values[0]["text"]) >= 3
            and any(values[1:])
        ):
            data.append(
                dict(values=values, y=median(cy(w) for w in group), group=group)
            )
    if (
        len(data) < 5
        or sum(sum(v is not None for v in r["values"][1:]) >= len(xs) - 1 for r in data)
        < len(data) * 0.7
    ):
        return None
    return dict(
        data=data,
        words=words,
        groups=groups,
        columns=xs,
        height=h,
        slope=slope,
        columnWords=columns,
    )


def source_line(source_words, y, slope, height, left, right):
    return sorted(
        [
            w
            for w in source_words
            if abs(
                (w["box"][1] + w["box"][3]) / 2
                - slope * (w["box"][0] + w["box"][2]) / 2
                - y
            )
            <= height * 0.5
            and left - height * 0.3 <= w["box"][0]
            and w["box"][2] <= right + height * 0.3
        ],
        key=lambda w: w["box"][0],
    )


def partition(words, columns):
    if not words or len(words) > 80:
        return None
    dp = {(0, 0): (0, [])}
    for col, x in enumerate(columns):
        for start in range(len(words)):
            if (col, start) not in dp:
                continue
            cost, groups = dp[col, start]
            for end in range(start + 1, min(len(words) + 1, start + 10)):
                group = words[start:end]
                if len(group) > 1 and any(w["text"] in ("%", "$", "#") for w in group):
                    continue
                score = cost + (max(w["box"][2] for w in group) - x) ** 2
                if (col + 1, end) not in dp or score < dp[col + 1, end][0]:
                    dp[col + 1, end] = (score, groups + [group])
    return dp.get((len(columns), len(words)), (None, None))[1]


def read_crops(reader, crops):
    if (
        len(crops) > 1024
        or any(not im.size or im.shape[0] * im.shape[1] > 2_000_000 for im in crops)
        or sum(im.shape[0] * im.shape[1] for im in crops) > 40_000_000
    ):
        return None
    if not crops:
        return []
    response = reader.text_rec(crops)
    if not isinstance(response, (list, tuple)) or len(response) != 2:
        return None
    rec = response[0]
    if not isinstance(rec, (list, tuple)) or len(rec) != len(crops):
        return None
    if any(
        not isinstance(v, (list, tuple))
        or len(v) < 2
        or not isinstance(v[0], str)
        or len(v[0]) > 1000
        or not isinstance(v[1], (int, float))
        or not math.isfinite(v[1])
        or not 0 <= v[1] <= 1
        for v in rec
    ):
        return None
    return rec


def recognize_fields(image, fields, reader):
    if len(fields) > 128:
        return False
    crops = []
    pads = [0, 1, 2, 3, 4, 6, 8, 10]
    for f in fields:
        for pad in pads:
            b = list(f["box"])
            if f["kind"] == "label":
                b[2] -= pad
            crops.append(crop(image, b, pad))
    if len(crops) > 1024 or any(not im.size for im in crops):
        return False
    rec = read_crops(reader, crops)
    if rec is None:
        return False
    for i, f in enumerate(fields):
        alternatives = rec[i * len(pads) : (i + 1) * len(pads)]
        votes = defaultdict(list)
        for j, (text, score, *_) in enumerate(alternatives):
            if score < 0.95 or not text.strip():
                continue
            corrected, _ = from_pixels(text, crops[i * len(pads) + j])
            value = normalized(corrected or text)
            votes[value].append(float(score))
        candidates = [(len(v), min(v), t) for t, v in votes.items() if len(v) >= 2]
        if candidates:
            candidates.sort(reverse=True)
            if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
                f["failure"] = "ambiguous-consensus"
                f["ambiguousValues"] = [
                    item[2] for item in candidates if item[0] == candidates[0][0]
                ]
                f["alternatives"] = alternatives
                continue
            _, score, value = candidates[0]
            if f.get("kind") == "number" and value != f["original"]:
                f["failure"] = "numeric-disagreement"
                continue
            f.update(text=value, confidence=score)
            continue
        f["failure"] = "no-two-high-confidence-matches"
        f["alternatives"] = alternatives
    return True


def recover_validated(image, result, reader, source_words, scale=3):
    info = grid(result)
    if info is None:
        return None, dict(reason="no-repeated-numeric-grid")
    h = info["height"]
    xs = info["columns"]
    slope = info["slope"]
    data = info["data"]
    fields = []
    rows = []
    label_right = min(w["box"][0] for w in info["columnWords"][0]) - h * 0.5
    for row in data:
        values = row["values"]
        label = values[0]
        end = leaders(image, label["box"], label_right, h)
        if end is None:
            return None, dict(reason="missing-dotted-leader", text=label["text"])
        f = dict(
            kind="label",
            box=[label["box"][0], label["box"][1], end, label["box"][3]],
            original=label["text"],
        )
        fields.append(f)
        entries = [f]
        for v in values[1:]:
            if v is None:
                entries.append(None)
                continue
            f = dict(kind="number", box=v["box"], original=v["text"])
            fields.append(f)
            entries.append(f)
        rows.append(dict(y=row["y"], entries=entries))
    # Every intermediate row must be accounted for, including section titles.
    cy = (
        lambda w: (w["box"][1] + w["box"][3]) / 2
        - slope * (w["box"][0] + w["box"][2]) / 2
    )
    used = {id(w) for r in data for w in r["group"]}
    for group in info["groups"]:
        y = median(cy(w) for w in group)
        if not data[0]["y"] < y < data[-1]["y"] or all(id(w) in used for w in group):
            continue
        if any(id(w) in used for w in group) or any(
            w["box"][2] >= label_right for w in group
        ):
            return None, dict(reason="unassigned-row", words=[w["text"] for w in group])
        b = [
            min(w["box"][0] for w in group),
            min(w["box"][1] for w in group),
            max(w["box"][2] for w in group),
            max(w["box"][3] for w in group),
        ]
        native = source_line(
            source_words, y, slope, h, b[0], min(label_right, b[2] + h * 2)
        )
        if native:
            b[2] = max(b[2], max(w["box"][2] for w in native))
        f = dict(
            kind="title",
            box=b,
            original=" ".join(w["text"] for w in group),
            native=native,
        )
        fields.append(f)
        rows.append(dict(y=y, entries=[f], merged=True))
    header_groups = [
        g
        for g in info["groups"]
        if data[0]["y"] - h * 2.5 < median(cy(w) for w in g) < data[0]["y"] - h * 0.6
        and any(w["box"][0] > label_right for w in g)
    ]
    if len(header_groups) != 1:
        return None, dict(reason="ambiguous-header", count=len(header_groups))
    header = header_groups[0]
    y = median(cy(w) for w in header)
    native = source_line(
        source_words, y, slope, h, min(w["box"][0] for w in header), xs[-1] + h
    )
    parts = partition(native, xs)
    if not parts:
        return None, dict(reason="header-segmentation")
    # Every OCR header box must overlap a source word assigned to a header cell.
    # This prevents accepting a table after a leading label such as TOTAL is lost.
    for word in header:
        a = word["box"]
        area = (a[2] - a[0]) * (a[3] - a[1])
        covered = sum(
            max(0, min(a[2], w["box"][2]) - max(a[0], w["box"][0]))
            * max(0, min(a[3], w["box"][3]) - max(a[1], w["box"][1]))
            for w in native
        )
        if covered < area * 0.2:
            return None, dict(reason="uncovered-header")
    # An OCR detector may miss a complete row. Source text geometry, when
    # available, independently requires every numeric-area line to be present.
    native_body = [
        w
        for w in source_words
        if w["box"][0] >= label_right
        and cy(w) > y + h * 0.6
        and w["box"][2] <= xs[-1] + h
    ]
    for group in cluster_objects(native_body, cy, h * 0.32):
        gy = median(cy(w) for w in group)
        matched = [r for r in data if abs(gy - r["y"]) <= h * 0.6]
        if len(matched) != 1:
            return None, dict(reason="uncovered-source-row")
        for w in group:
            a = w["box"]
            area = (a[2] - a[0]) * (a[3] - a[1])
            coverage = sum(
                max(
                    0,
                    min(a[2], v["box"][2] + h * 0.5) - max(a[0], v["box"][0] - h * 0.5),
                )
                * max(
                    0,
                    min(a[3], v["box"][3] + h * 0.2) - max(a[1], v["box"][1] - h * 0.2),
                )
                for v in matched[0]["values"][1:]
                if v
            )
            if coverage < area * 0.1:
                return None, dict(
                    reason="uncovered-source-cell",
                    sourceWord=w,
                    coverage=coverage / area,
                    ocrWords=matched[0]["values"][1:],
                )
    entries = [None]
    for part in parts:
        b = [
            min(w["box"][0] for w in part),
            min(w["box"][1] for w in part),
            max(w["box"][2] for w in part),
            max(w["box"][3] for w in part),
        ]
        f = dict(
            kind="header",
            box=b,
            native=part,
            original=" ".join(w["text"] for w in part),
        )
        fields.append(f)
        entries.append(f)
    rows.append(dict(y=y, entries=entries))
    # Numeric cells already above the confidence gate need no extra recognizer run.
    selected = []
    for f in fields:
        if f["kind"] == "number":
            original = next(
                w
                for w in info["words"]
                if w["box"] == f["box"] and w["text"] == f["original"]
            )
            if original["score"] >= 0.95:
                f.update(text=original["text"], confidence=original["score"])
                continue
        selected.append(f)
    if not recognize_fields(image, selected, reader):
        return None, dict(reason="recognition-budget")
    from ocr_punctuation import resolve as resolve_punctuation

    resolve_punctuation(image, fields)
    refine_uncertain(image, fields, reader)
    verify_source_word_spacing(image, fields, reader)
    failures = [f for f in fields if "text" not in f]
    if failures:
        return None, dict(
            reason="uncertain-fields",
            failures=failures,
            fields=fields,
            rows=rows,
            geometry={k: info[k] for k in ["columns", "height", "slope"]},
        )
    rows.sort(key=lambda r: r["y"])
    left = min(r["entries"][0]["box"][0] for r in rows if r["entries"][0])
    boundaries = (
        [
            left - h * 0.2,
            (label_right + min(w["box"][0] for w in info["columnWords"][0])) / 2,
        ]
        + [(a + b) / 2 for a, b in zip(xs, xs[1:])]
        + [xs[-1] + h * 0.3]
    )
    cells = []
    for r, row in enumerate(rows):
        for col, f in enumerate(row["entries"]):
            if f is None:
                continue
            cells.append(
                dict(
                    r=r,
                    c=col,
                    rs=1,
                    cs=len(xs) + 1 if row.get("merged") else 1,
                    text=f["text"],
                    confidence=f["confidence"],
                )
            )
    ys = (
        [rows[0]["y"] - h * 0.65]
        + [(a["y"] + b["y"]) / 2 for a, b in zip(rows, rows[1:])]
        + [rows[-1]["y"] + h * 0.65]
    )
    return dict(
        widths=[(b - a) / scale for a, b in zip(boundaries, boundaries[1:])],
        heights=[(b - a) / scale for a, b in zip(ys, ys[1:])],
        cells=cells,
        method="ocr-leaders",
    ), dict(fields=fields, rows=rows)


def refine_uncertain(image, fields, reader):
    # Additional scaled crops only confirm an existing numeric literal; they cannot replace it.
    candidates = []
    crops = []
    pixel_budget = 0
    for f in fields:
        if "text" in f or f.get("failure") in (
            "ambiguous-consensus",
            "numeric-disagreement",
        ):
            continue
        for pad in [0, 2, 4]:
            im = crop(image, f["box"], pad)
            for factor in [2, 3]:
                if (
                    not im.size
                    or im.shape[0] * im.shape[1] * factor * factor > 2_000_000
                ):
                    return
                pixels = im.shape[0] * im.shape[1] * factor * factor
                if pixel_budget + pixels > 40_000_000:
                    return
                pixel_budget += pixels
                crops.append(
                    cv2.resize(
                        im, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC
                    )
                )
        candidates.append(f)
    if not candidates:
        return
    rec = read_crops(reader, crops)
    if rec is None:
        return
    for i, f in enumerate(candidates):
        votes = defaultdict(list)
        for text, score, *_ in rec[i * 6 : i * 6 + 6]:
            if score >= 0.95 and text.strip():
                votes[normalized(text)].append(float(score))
        good = [
            (len(v), min(v), t)
            for t, v in votes.items()
            if len(v) >= 2 and (f["kind"] != "number" or t == f["original"])
        ]
        good.sort(reverse=True)
        if good and (len(good) == 1 or good[0][0] > good[1][0]):
            _, score, value = good[0]
            f.update(text=value, confidence=score, refinement="scaled-crop-consensus")
            f.pop("failure", None)
        f["scaledAlternatives"] = rec[i * 6 : i * 6 + 6]


def verify_source_word_spacing(image, fields, reader):
    candidates = []
    crops = []
    for f in fields:
        native = f.get("native", [])
        if (
            f["kind"] != "title"
            or not native
            or len(native) > 12
            or f.get("failure") == "numeric-disagreement"
        ):
            continue
        expected = " ".join(w["text"] for w in native)
        if f.get("failure") == "ambiguous-consensus" and (
            not f.get("ambiguousValues")
            or any(flat(value) != flat(expected) for value in f["ambiguousValues"])
        ):
            continue
        if expected == f.get("text") or (
            "text" in f and flat(expected) != flat(f["text"])
        ):
            continue
        start = len(crops)
        for word in native:
            for pad in [0, 2, 4]:
                crops.append(crop(image, word["box"], pad))
        candidates.append((f, start, native, expected))
    if not crops:
        return
    rec = read_crops(reader, crops)
    if rec is None:
        return
    for f, start, words, expected in candidates:
        scores = []
        for i, word in enumerate(words):
            matches = [
                float(score)
                for text, score, *_ in rec[start + i * 3 : start + (i + 1) * 3]
                if text == word["text"] and score >= 0.95
            ]
            if len(matches) < 2:
                break
            scores.append(min(matches))
        if len(scores) == len(words):
            f.update(
                text=expected,
                confidence=min(scores),
                refinement="source-word-and-crop-consensus",
            )
            f.pop("failure", None)


def recover(image, result, reader, source_words, scale=3):
    """Bound parser inputs before any image operation or OCR model invocation."""
    if (
        not isinstance(image, np.ndarray)
        or image.ndim != 3
        or image.shape[2] != 3
        or image.dtype != np.uint8
        or not image.size
        or image.shape[0] * image.shape[1] > 20_000_000
    ):
        return None, dict(reason="invalid-image")
    if (
        not isinstance(scale, (int, float))
        or not math.isfinite(scale)
        or not 0.5 <= scale <= 6
    ):
        return None, dict(reason="invalid-scale")
    if (
        not isinstance(result, (list, tuple))
        or not 30 <= len(result) <= 10000
        or not isinstance(source_words, (list, tuple))
        or not 1 <= len(source_words) <= 10000
    ):
        return None, dict(reason="invalid-word-count")

    def valid_box(box):
        return (
            isinstance(box, (list, tuple))
            and len(box) == 4
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
            and 0 <= box[0] < box[2] <= image.shape[1]
            and 0 <= box[1] < box[3] <= image.shape[0]
        )

    for entry in result:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            return None, dict(reason="invalid-ocr-word")
        points, text, score = entry
        if (
            not isinstance(points, (list, tuple))
            or len(points) != 4
            or any(
                not isinstance(p, (list, tuple))
                or len(p) != 2
                or any(
                    not isinstance(v, (int, float)) or not math.isfinite(v) for v in p
                )
                for p in points
            )
        ):
            return None, dict(reason="invalid-ocr-box")
        if (
            not valid_box(box_of(points))
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 1000
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            return None, dict(reason="invalid-ocr-word")
    for word in source_words:
        if (
            not isinstance(word, dict)
            or not valid_box(word.get("box"))
            or not isinstance(word.get("text"), str)
            or not word["text"].strip()
            or len(word["text"]) > 1000
        ):
            return None, dict(reason="invalid-source-word")
    return recover_validated(image, result, reader, source_words, scale)


def extract_from_page(page, reader):
    """Fresh pixel recognition; embedded OCR text supplies geometry, never truth."""
    from layout_tables import visible_box

    view = visible_box(page)
    scale = 3
    if (
        page.rotation
        or (view[2] - view[0]) * (view[3] - view[1]) * scale * scale > 20_000_000
    ):
        return None
    image = np.asarray(
        page.to_image(resolution=72 * scale, antialias=True).original.convert("RGB")
    )
    result, _ = reader(image)
    if not result:
        return None
    words = [
        dict(
            box=[
                (w["x0"] - view[0]) * scale,
                (w["top"] - view[1]) * scale,
                (w["x1"] - view[0]) * scale,
                (w["bottom"] - view[1]) * scale,
            ],
            text=w["text"],
        )
        for w in page.crop(tuple(view)).extract_words(x_tolerance=1, y_tolerance=2)
    ]
    table, diagnostics = recover(image, result, reader, words, scale)
    if table is None:
        return None
    ink = median((f["box"][3] - f["box"][1]) / scale for f in diagnostics["fields"])
    font = max(6, min(14, ink, median(table["heights"]) * 0.75))
    table.update(
        sourceGeometry=True,
        fontSize=font,
        sourcePageOrientation=(
            "portrait" if view[3] - view[1] >= view[2] - view[0] else "landscape"
        ),
    )
    for cell in table["cells"]:
        cell["sourceRasterGeometry"] = True
        if cell["r"] == 0 and cell["cs"] == 1:
            longest = max((len(word) for word in cell["text"].split()), default=0)
            col = cell["c"]
            old = table["widths"][col]
            table["widths"][col] = max(
                old, min(old * 1.8, old + 24, longest * font * 0.72 + 8)
            )
    return table
