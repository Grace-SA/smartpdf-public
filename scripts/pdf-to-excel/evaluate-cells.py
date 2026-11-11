"""Independent local ICDAR annotation/XLSX comparison (not the official scorer).

Compare page-ordered tables and normalized top-left row/column origins. Whitespace
normalization is reported separately from exact text. Missing/refused output is
counted as a miss. No reference data is used by the conversion engine.
"""

import collections
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from openpyxl import load_workbook


def normalized(value):
    return "".join((value or "").split())


def aligned_cell_scores(reference, prediction):
    """Order-preserving row alignment; never move a value to a different column.

    Blank spacer rows and extra captions should not shift every later cell.
    Unmatched rows remain misses/extras in recall/precision denominators.
    """

    def compact(cells):
        row_ids = sorted(
            {
                r
                for (start, _), c in cells.items()
                for r in range(start, start + c["rs"])
            }
        )
        rows = collections.defaultdict(dict)
        positions = {r: i for i, r in enumerate(row_ids)}
        for (r, c), value in cells.items():
            if value["text"].strip():
                rows[positions[r]][c] = dict(
                    value, rs=positions[r + value["rs"] - 1] - positions[r] + 1
                )
        return [row for _, row in sorted(rows.items())]

    left, right = compact(reference), compact(prediction)
    if len(left) * len(right) > 4_000_000:
        raise ValueError("Row alignment exceeds evaluation budget")
    scores = [
        [
            sum(
                normalized(c["text"]) == normalized(b[col]["text"])
                for col, c in a.items()
                if col in b
            )
            for b in right
        ]
        for a in left
    ]
    dp = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i in range(1, len(left) + 1):
        for j in range(1, len(right) + 1):
            dp[i][j] = max(
                dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1] + scores[i - 1][j - 1]
            )
    pairs = []
    i, j = len(left), len(right)
    while i and j:
        if scores[i - 1][j - 1] and dp[i][j] == dp[i - 1][j - 1] + scores[i - 1][j - 1]:
            pairs.append((left[i - 1], right[j - 1]))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    result = collections.Counter()
    for a, b in pairs:
        for col, cell in a.items():
            got = b.get(col)
            if got:
                matched = normalized(got["text"]) == normalized(cell["text"])
                result["alignedExactText"] += got["text"] == cell["text"]
                result["alignedNormalizedText"] += matched
                result["alignedTextAndSpan"] += matched and (got["rs"], got["cs"]) == (
                    cell["rs"],
                    cell["cs"],
                )
    return result


def evaluate(root):
    statuses = {
        r["id"]: r["status"]
        for r in json.loads((root / "benchmark.json").read_text())["results"]
    }
    rows = []
    totals = collections.Counter()
    invalid_boxes = 0
    for file in sorted((root / "references").glob("*-str.xml")):
        sample = file.name.removesuffix("-str.xml")
        expected = collections.defaultdict(list)
        for region in ET.parse(file).findall(".//region"):
            cells = region.findall("cell")
            if not cells:
                continue
            boxes = []
            for cell in cells:
                box = cell.find("bounding-box")
                try:
                    boxes.append({key: float(box.get(key)) for key in ("x1", "y2")})
                except (ValueError, TypeError, AttributeError):
                    # Known upstream coordinate typos must not become guessed data.
                    invalid_boxes += 1
            if not boxes:
                raise ValueError("No valid coordinates for reference table ordering")
            min_row = min(int(c.get("start-row")) for c in cells)
            min_col = min(int(c.get("start-col")) for c in cells)
            table = {
                "top": -max(b["y2"] for b in boxes),
                "left": min(b["x1"] for b in boxes),
                "cells": [
                    {
                        "r": int(c.get("start-row")) - min_row,
                        "c": int(c.get("start-col")) - min_col,
                        "rs": int(c.get("end-row", c.get("start-row")))
                        - int(c.get("start-row"))
                        + 1,
                        "cs": int(c.get("end-col", c.get("start-col")))
                        - int(c.get("start-col"))
                        + 1,
                        "text": c.findtext("content", ""),
                    }
                    for c in cells
                ],
            }
            expected[int(region.get("page"))].append(table)
        actual = collections.defaultdict(list)
        if statuses.get(sample) == "converted":
            book = load_workbook(root / "outputs" / (sample + ".xlsx"))
            for sheet in book:
                match = re.fullmatch(r"Page (\d+) Table (\d+)", sheet.title)
                if not match:
                    raise ValueError("Evaluation requires one worksheet per table")
                nonempty = [c for row in sheet for c in row if c.value is not None]
                if not nonempty:
                    continue
                min_row = min(c.row for c in nonempty)
                min_col = min(c.column for c in nonempty)
                merges = {(m.min_row, m.min_col): m for m in sheet.merged_cells}
                cells = {}
                for cell in nonempty:
                    merge = merges.get((cell.row, cell.column))
                    cells[cell.row - min_row, cell.column - min_col] = {
                        "text": str(cell.value),
                        "rs": merge.max_row - merge.min_row + 1 if merge else 1,
                        "cs": merge.max_col - merge.min_col + 1 if merge else 1,
                    }
                actual[int(match[1])].append((int(match[2]), cells))
            book.close()
        scores = collections.Counter()
        for page, tables in expected.items():
            tables.sort(key=lambda t: (t["top"], t["left"]))
            predictions = [cells for _, cells in sorted(actual.get(page, []))]
            for index, table in enumerate(tables):
                prediction = predictions[index] if index < len(predictions) else {}
                scores.update(
                    aligned_cell_scores(
                        {(c["r"], c["c"]): c for c in table["cells"]}, prediction
                    )
                )
                scores["annotatedTables"] += 1
                for cell in table["cells"]:
                    if not cell["text"].strip():
                        continue
                    scores["annotatedNonemptyCells"] += 1
                    got = prediction.get((cell["r"], cell["c"]))
                    if not got:
                        continue
                    exact = got["text"] == cell["text"]
                    text_match = normalized(got["text"]) == normalized(cell["text"])
                    span_match = (got["rs"], got["cs"]) == (cell["rs"], cell["cs"])
                    scores["exactTextAtPosition"] += exact
                    scores["whitespaceNormalizedTextAtPosition"] += text_match
                    scores["textAndSpanAtPosition"] += text_match and span_match
        # Text recall independent of positions helps separate content from layout loss.
        expected_text = collections.Counter(
            normalized(c["text"])
            for ts in expected.values()
            for t in ts
            for c in t["cells"]
            if c["text"].strip()
        )
        actual_text = collections.Counter(
            normalized(c["text"])
            for ts in actual.values()
            for _, cells in ts
            for c in cells.values()
            if c["text"].strip()
        )
        scores["textMultisetIntersection"] = sum((expected_text & actual_text).values())
        scores["outputNonemptyCells"] = sum(actual_text.values())
        totals.update(scores)
        rows.append({"id": sample, "status": statuses.get(sample), **scores})
    report = {
        "scope": "Page-ordered annotated cells: raw position plus order-preserving row alignment for blank rows/captions; no column reordering; not official ICDAR score or population accuracy",
        "files": len(rows),
        "invalidReferenceBoxesIgnoredForOrdering": invalid_boxes,
        "totals": dict(totals),
        "results": rows,
    }
    (root / "cell-evaluation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"files": len(rows), "totals": dict(totals)}))


if __name__ == "__main__":
    evaluate(Path(sys.argv[1]))
