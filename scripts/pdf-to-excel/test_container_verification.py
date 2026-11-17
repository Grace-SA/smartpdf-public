"""Regression tests for the three-fixture Linux container output verifier."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from openpyxl import Workbook

VERIFIER = Path(__file__).with_name("verify-container.py")


class ContainerVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixtures = self.root / "fixtures"
        self.outputs = self.root / "outputs"
        self.fixtures.mkdir()
        self.outputs.mkdir()
        self.manifest = [
            {"id": "ruled", "cells": [["Code", "Amount"], ["00123", "12.00"]]},
            {"id": "scan-chinese", "cells": [["编号", "名称"], ["00123", "合成测试"]]},
            {"id": "native-form", "expect": "form", "checked": 6, "unchecked": 6},
        ]
        for reference in self.manifest[:2]:
            book = Workbook()
            for row in reference["cells"]:
                book.active.append(row)
            book.save(self.outputs / (reference["id"] + ".xlsx"))
        self.merged = Workbook()
        self.merged.active.merge_cells("A1:C1")
        self.merged.active["A1"] = "Quarterly report"
        self.merged.active["A3"] = "00123"
        self.merged.save(self.outputs / "merged.xlsx")

    def run_verifier(self):
        (self.fixtures / "expected.json").write_text(json.dumps(self.manifest))
        return subprocess.run(
            [sys.executable, str(VERIFIER), str(self.fixtures), str(self.outputs)],
            capture_output=True, text=True,
        )

    def test_unrelated_form_manifest_does_not_break_table_verification(self):
        result = self.run_verifier()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("values and merged cells verified", result.stdout)

    def test_required_reference_cells_cannot_be_missing(self):
        del self.manifest[0]["cells"]
        self.assertNotEqual(self.run_verifier().returncode, 0)

    def test_required_reference_cannot_be_missing(self):
        self.manifest.pop(1)
        self.assertNotEqual(self.run_verifier().returncode, 0)

    def test_changed_table_values_fail(self):
        self.manifest[1]["cells"][1][1] = "different"
        self.assertNotEqual(self.run_verifier().returncode, 0)

    def test_missing_output_fails(self):
        (self.outputs / "ruled.xlsx").unlink()
        self.assertNotEqual(self.run_verifier().returncode, 0)

    def test_wrong_merged_range_fails(self):
        self.merged.active.unmerge_cells("A1:C1")
        self.merged.save(self.outputs / "merged.xlsx")
        self.assertNotEqual(self.run_verifier().returncode, 0)

    def test_wrong_merged_literal_fails(self):
        self.merged.active["A3"] = 123
        self.merged.save(self.outputs / "merged.xlsx")
        self.assertNotEqual(self.run_verifier().returncode, 0)


if __name__ == "__main__":
    unittest.main()
