"""Strict checks against source-reviewed local references, never engine output.

Unreviewed files stay pending. Correct negative handling is counted separately
from table fidelity. Whitespace wrapping is normalized; letters, internal word
boundaries, numbers, sheet dimensions and merged ranges must all agree.
"""

import hashlib
import json
from pathlib import Path
import re
import sys
from collections import Counter

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text):
    return re.sub(r"\s+", " ", "" if text is None else str(text)).strip()


def check_workbook(path, reference):
    failures = []
    book = load_workbook(path, data_only=False)
    try:
        expected_names = {
            f"Page {table['page']} Table {table['index']}"
            for table in reference["tables"]
        }
        if set(book.sheetnames) != expected_names:
            failures.append({"kind": "worksheets"})
        for table in reference["tables"]:
            name = f"Page {table['page']} Table {table['index']}"
            if name not in book:
                continue
            sheet = book[name]
            if (sheet.max_row, sheet.max_column) != (table["rows"], table["columns"]):
                failures.append({"kind": "dimensions", "sheet": name})
            expected, merges = {}, set()
            covered = set()
            for cell in table["cells"]:
                r, c, rs, cs = (cell[k] for k in ("r", "c", "rs", "cs"))
                if not (
                    0 <= r < r + rs <= table["rows"]
                    and 0 <= c < c + cs <= table["columns"]
                ):
                    raise ValueError("Reference cell outside table")
                region = {(y, x) for y in range(r, r + rs) for x in range(c, c + cs)}
                if covered & region:
                    raise ValueError("Reference cells overlap")
                covered.update(region)
                expected[(r + 1, c + 1)] = normalized(cell["text"])
                if rs > 1 or cs > 1:
                    merges.add(
                        f"{get_column_letter(c+1)}{r+1}:{get_column_letter(c+cs)}{r+rs}"
                    )
            if set(map(str, sheet.merged_cells.ranges)) != merges:
                failures.append({"kind": "merges", "sheet": name})
            for row in sheet:
                for cell in row:
                    if cell.data_type == "f":
                        failures.append(
                            {"kind": "formula", "sheet": name, "cell": cell.coordinate}
                        )
                    if normalized(cell.value) != expected.pop(
                        (cell.row, cell.column), ""
                    ):
                        failures.append(
                            {"kind": "text", "sheet": name, "cell": cell.coordinate}
                        )
            if any(expected.values()):
                failures.append({"kind": "missing-cells", "sheet": name})
    finally:
        book.close()
    return failures


def evaluate(root, references, ledger_path):
    benchmark = json.loads((root / "benchmark.json").read_text())
    runs = {row["id"]: row for row in benchmark["results"]}
    manifest = json.loads((root / "corpus/manifest.json").read_text())
    reviews = {row["id"]: row for row in json.loads(ledger_path.read_text())["results"]}
    results = []
    for sample in manifest:
        key = sample["id"]
        run = runs.get(key, {})
        row = {"id": key, "result": "pending-source-review"}
        results.append(row)
        if (
            run.get("sha256") != sample["sha256"]
            or digest(root / "corpus" / sample["file"]) != sample["sha256"]
        ):
            raise ValueError(f"Missing run or source identity mismatch: {key}")
        review = reviews.get(key, {})
        if review.get("acceptanceStatus") == "accepted-negative":
            if review.get("sha256") != sample["sha256"] or not review.get(
                "verification"
            ):
                raise ValueError(f"Unverified negative reference: {key}")
            row["result"] = (
                "negative-pass" if run["status"] == "refused" else "negative-fail"
            )
            continue
        path = references / (key + ".json")
        if not path.exists():
            continue
        reference = json.loads(path.read_text())
        if (
            not reference.get("sourceReviewed")
            or not reference.get("evidence")
            or reference.get("sourceSha256") != sample["sha256"]
        ):
            raise ValueError(f"Unverified table reference: {key}")
        row["referenceSha256"] = digest(path)
        if run["status"] != "converted":
            row.update(result="table-fail", failures=[{"kind": "not-converted"}])
            continue
        output = root / "outputs" / (key + ".xlsx")
        if not output.exists() or digest(output) != run.get("outputSha256"):
            raise ValueError(f"Missing or stale workbook: {key}")
        failures = check_workbook(output, reference)
        row.update(result="table-fail" if failures else "table-pass", failures=failures)
    report = {
        "scope": "Source-reviewed table content/shape/merges only; unreviewed files remain pending. Negative handling is separate. This does not measure pixel-perfect visual fidelity.",
        "benchmarkSha256": digest(root / "benchmark.json"),
        "ledgerSha256": digest(ledger_path),
        "summary": dict(Counter(row["result"] for row in results)),
        "results": results,
    }
    (root / "acceptance-evaluation.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate(*map(Path, sys.argv[1:4]))["summary"]))
