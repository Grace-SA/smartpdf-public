import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook, load_workbook

spec = importlib.util.spec_from_file_location(
    "acceptance", Path(__file__).with_name("evaluate-acceptance.py")
)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ["outputs", "references", "corpus"]:
            (self.root / name).mkdir()
        source = self.root / "corpus/source.pdf"
        source.write_bytes(b"synthetic source identity for evaluator tests")
        self.sha = scorer.digest(source)
        self.reference = {
            "id": "SYN-001",
            "sourceReviewed": True,
            "sourceSha256": self.sha,
            "evidence": {"review": "Synthetic explicit expectations"},
            "tables": [
                {
                    "page": 1,
                    "index": 1,
                    "rows": 2,
                    "columns": 2,
                    "cells": [
                        {"r": 0, "c": 0, "rs": 1, "cs": 2, "text": "Region name"},
                        {"r": 1, "c": 0, "rs": 1, "cs": 1, "text": "L Ribs"},
                        {"r": 1, "c": 1, "rs": 1, "cs": 1, "text": "00123"},
                    ],
                }
            ],
        }
        self.output = self.root / "outputs/SYN-001.xlsx"
        book = Workbook()
        book.active.title = "Page 1 Table 1"
        book.active.append(["Region\nname"])
        book.active.append(["L Ribs", "00123"])
        book.active.merge_cells("A1:B1")
        book.save(self.output)
        (self.root / "corpus/manifest.json").write_text(
            json.dumps([{"id": "SYN-001", "sha256": self.sha, "file": "source.pdf"}])
        )
        (self.root / "benchmark.json").write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "id": "SYN-001",
                            "sha256": self.sha,
                            "status": "converted",
                            "outputSha256": scorer.digest(self.output),
                        }
                    ]
                }
            )
        )
        self.ledger = self.root / "ledger.json"
        self.ledger.write_text(json.dumps({"results": []}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_literal_text_merges_and_line_wrap(self):
        self.assertEqual(scorer.check_workbook(self.output, self.reference), [])
        for changed in ["LRibs", "123", "=1+1"]:
            with self.subTest(changed=changed):
                book = load_workbook(self.output)
                book.active["A2" if changed == "LRibs" else "B2"] = changed
                path = self.root / "changed.xlsx"
                book.save(path)
                failures = scorer.check_workbook(path, self.reference)
                self.assertIn("text", {x["kind"] for x in failures})
                if changed == "=1+1":
                    self.assertIn("formula", {x["kind"] for x in failures})

    def test_extra_sheet_cell_or_missing_merge_cannot_pass(self):
        book = load_workbook(self.output)
        book.active.unmerge_cells("A1:B1")
        book.active["C2"] = "extra"
        book.create_sheet("Unexpected")
        book.save(self.output)
        kinds = {x["kind"] for x in scorer.check_workbook(self.output, self.reference)}
        self.assertTrue({"worksheets", "dimensions", "merges", "text"} <= kinds)

    def test_unreviewed_is_pending_and_stale_output_is_rejected(self):
        refs = self.root / "references"
        report = scorer.evaluate(self.root, refs, self.ledger)
        self.assertEqual(report["summary"], {"pending-source-review": 1})
        (refs / "SYN-001.json").write_text(json.dumps(self.reference))
        self.assertEqual(
            scorer.evaluate(self.root, refs, self.ledger)["summary"], {"table-pass": 1}
        )
        self.output.write_bytes(b"stale workbook")
        with self.assertRaisesRegex(ValueError, "stale workbook"):
            scorer.evaluate(self.root, refs, self.ledger)

    def test_changed_source_is_rejected(self):
        (self.root / "corpus/source.pdf").write_bytes(b"replacement")
        with self.assertRaisesRegex(ValueError, "source identity"):
            scorer.evaluate(self.root, self.root / "references", self.ledger)

    def test_numeric_zero_is_not_an_empty_cell(self):
        self.assertEqual(scorer.normalized(0), "0")
        book = load_workbook(self.output)
        book.active["C2"] = 0
        book.save(self.output)
        failures = scorer.check_workbook(self.output, self.reference)
        self.assertTrue(
            any(x["kind"] == "text" and x.get("cell") == "C2" for x in failures)
        )

    def test_negative_handling_is_separate_from_table_success(self):
        self.ledger.write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "id": "SYN-001",
                            "sha256": self.sha,
                            "acceptanceStatus": "accepted-negative",
                            "verification": "Synthetic negative expectation",
                        }
                    ]
                }
            )
        )
        self.assertEqual(
            scorer.evaluate(self.root, self.root / "references", self.ledger)[
                "summary"
            ],
            {"negative-fail": 1},
        )
        path = self.root / "benchmark.json"
        run = json.loads(path.read_text())
        run["results"][0]["status"] = "refused"
        path.write_text(json.dumps(run))
        self.assertEqual(
            scorer.evaluate(self.root, self.root / "references", self.ledger)[
                "summary"
            ],
            {"negative-pass": 1},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
