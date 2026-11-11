"""Verify Linux-container downloads independently of the HTTP gateway."""

import json
from pathlib import Path
import sys
from openpyxl import load_workbook

fixtures, output = map(Path, sys.argv[1:3])
expected = {
    row["id"]: row["cells"]
    for row in json.loads((fixtures / "expected.json").read_text())
}
for name in ("ruled", "scan-chinese"):
    book = load_workbook(output / (name + ".xlsx"))
    assert [list(row) for row in book.active.values] == expected[name], name
book = load_workbook(output / "merged.xlsx")
assert {str(m) for m in book.active.merged_cells} == {"A1:C1"}
assert book.active["A1"].value == "Quarterly report"
assert book.active["A3"].value == "00123"
print("Linux container XLSX values and merged cells verified.")
