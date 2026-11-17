"""Independent local ICDAR annotation/XLSX comparison (not the official scorer).

Compare page-ordered tables and normalized top-left row/column origins. Whitespace
normalization is reported separately from exact text. Missing/refused output is
counted as a miss. No reference data is used by the conversion engine.
"""

import collections
import hashlib
import json
import re
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
                if cell["rs"] > 1 or cell["cs"] > 1:
                    result["alignedMergedTextAndSpan"] += matched and (
                        got["rs"],
                        got["cs"],
                    ) == (cell["rs"], cell["cs"])
    return result


def verified_inputs(root, benchmark):
    """Bind every scored reference and successful output to declared bytes."""
    manifest_path = root / "corpus/manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Verified evaluation requires corpus/manifest.json")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)

    def keyed(rows, label):
        result = {}
        for row in rows:
            identity = row.get("id")
            if not isinstance(identity, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]+", identity
            ):
                raise ValueError(f"Invalid {label} ID")
            if identity in result:
                raise ValueError(f"Duplicate {label} ID: {identity}")
            result[identity] = row
        return result

    declared = keyed(manifest, "manifest")
    runs = keyed(benchmark["results"], "benchmark")
    if set(runs) != set(declared):
        raise ValueError("Benchmark IDs must exactly match the complete manifest")
    references = {k: v for k, v in declared.items() if "referenceSha256" in v}
    if not references:
        raise ValueError("Verified evaluation requires declared referenceSha256 labels")
    files = {
        f.name.removesuffix("-str.xml"): f
        for f in (root / "references").glob("*-str.xml")
    }
    if set(files) != set(references):
        raise ValueError("Reference file IDs must exactly match declared labels")

    def verify(path, expected, label):
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Missing or invalid {label} SHA256")
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError(f"{label} hash mismatch: {path.name}")

    for identity, item in declared.items():
        source_name = item.get("file")
        if not isinstance(source_name, str) or Path(source_name).name != source_name:
            raise ValueError("Invalid source filename")
        verify(root / "corpus" / source_name, item.get("sha256"), "Source")
        run = runs[identity]
        if run.get("sha256") != item["sha256"]:
            raise ValueError(f"Benchmark source hash mismatch: {identity}")
        if run.get("status") not in {"converted", "refused", "timeout", "error"}:
            raise ValueError(f"Missing or invalid benchmark status: {identity}")
        if run["status"] == "converted":
            verify(
                root / "outputs" / (identity + ".xlsx"),
                run.get("outputSha256"),
                "Output",
            )
    for identity, item in references.items():
        verify(files[identity], item["referenceSha256"], "Reference")
    return (
        [files[k] for k in sorted(files)],
        {k: references[k]["referenceSha256"] for k in sorted(references)},
        hashlib.sha256(manifest_bytes).hexdigest(),
    )


def evaluate(root, *, allow_unverified=False):
    root = Path(root)
    benchmark_bytes = (root / "benchmark.json").read_bytes()
    benchmark = json.loads(benchmark_bytes)
    if allow_unverified:
        files = sorted((root / "references").glob("*-str.xml"))
        reference_hashes = {}
        manifest_hash = None
    else:
        files, reference_hashes, manifest_hash = verified_inputs(root, benchmark)
    statuses = {r["id"]: r["status"] for r in benchmark["results"]}
    rows = []
    totals = collections.Counter()
    invalid_boxes = 0
    for file in files:
        sample = file.name.removesuffix("-str.xml")
        expected = collections.defaultdict(list)
        for table in ET.parse(file).findall(".//table"):
            by_page = collections.defaultdict(list)
            for region in table.findall("region"):
                by_page[int(region.get("page"))].append(region)
            for page, regions in by_page.items():
                boxes, cells = [], []
                for region in regions:
                    raw = region.findall("cell")
                    if not raw:
                        continue
                    min_row = min(int(c.get("start-row")) for c in raw)
                    min_col = min(int(c.get("start-col")) for c in raw)
                    for cell in raw:
                        box = cell.find("bounding-box")
                        try:
                            boxes.append(
                                {key: float(box.get(key)) for key in ("x1", "x2", "y2")}
                            )
                        except (ValueError, TypeError, AttributeError):
                            invalid_boxes += 1
                        cells.append(
                            {
                                "r": int(cell.get("start-row"))
                                - min_row
                                + int(region.get("row-increment", "0")),
                                "c": int(cell.get("start-col"))
                                - min_col
                                + int(region.get("col-increment", "0")),
                                "rs": int(cell.get("end-row", cell.get("start-row")))
                                - int(cell.get("start-row"))
                                + 1,
                                "cs": int(cell.get("end-col", cell.get("start-col")))
                                - int(cell.get("start-col"))
                                + 1,
                                "text": cell.findtext("content", ""),
                            }
                        )
                if not boxes or not cells:
                    raise ValueError(
                        "No valid coordinates for reference table ordering"
                    )
                first_row = min(c["r"] for c in cells)
                first_col = min(c["c"] for c in cells)
                for cell in cells:
                    cell["r"] -= first_row
                    cell["c"] -= first_col
                expected[page].append(
                    {
                        "top": -max(b["y2"] for b in boxes),
                        "left": min(b["x1"] for b in boxes),
                        "right": max(b["x2"] for b in boxes),
                        "cells": cells,
                    }
                )
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
                    merged = cell["rs"] > 1 or cell["cs"] > 1
                    scores["annotatedMergedCells"] += merged
                    got = prediction.get((cell["r"], cell["c"]))
                    if not got:
                        continue
                    exact = got["text"] == cell["text"]
                    text_match = normalized(got["text"]) == normalized(cell["text"])
                    span_match = (got["rs"], got["cs"]) == (cell["rs"], cell["cs"])
                    scores["exactTextAtPosition"] += exact
                    scores["whitespaceNormalizedTextAtPosition"] += text_match
                    scores["textAndSpanAtPosition"] += text_match and span_match
                    scores["mergedTextAndSpanAtPosition"] += (
                        merged and text_match and span_match
                    )
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
        scores["outputMergedNonemptyCells"] = sum(
            bool(c["text"].strip()) and (c["rs"] > 1 or c["cs"] > 1)
            for ts in actual.values()
            for _, cells in ts
            for c in cells.values()
        )
        totals.update(scores)
        rows.append({"id": sample, "status": statuses.get(sample), **scores})
    report = {
        "evaluationVersion": 2 if allow_unverified else 3,
        "integrityMode": "unverified-legacy"
        if allow_unverified
        else "verified-manifest",
        "referenceSha256": reference_hashes,
        "benchmarkSha256": None
        if allow_unverified
        else hashlib.sha256(benchmark_bytes).hexdigest(),
        "manifestSha256": manifest_hash,
        "scope": "Table/page regions combined using annotation increments; annotated cells: raw position plus order-preserving row alignment for blank rows/captions; no column reordering; not official ICDAR score or population accuracy",
        "files": len(rows),
        "invalidReferenceBoxesIgnoredForOrdering": invalid_boxes,
        "totals": dict(totals),
        "results": rows,
    }
    (root / "cell-evaluation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"files": len(rows), "totals": dict(totals)}))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Explicit legacy mode: no corpus/reference/output integrity checks",
    )
    args = parser.parse_args()
    evaluate(args.root, allow_unverified=args.allow_unverified)
