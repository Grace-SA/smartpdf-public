"""Verify the independent scorer with hand-authored reference cells."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from openpyxl import Workbook

spec = importlib.util.spec_from_file_location(
    "evaluate_cells", Path(__file__).with_name("evaluate-cells.py")
)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)
comparison_spec = importlib.util.spec_from_file_location(
    "compare_runs", Path(__file__).with_name("compare-runs.py")
)
comparison = importlib.util.module_from_spec(comparison_spec)
comparison_spec.loader.exec_module(comparison)


class EvaluationTests(unittest.TestCase):
    def test_comparison_rejects_changed_corpus_and_evaluator(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots = [Path(temporary) / name for name in ("before", "after")]
            run = {
                "runtime": dict(
                    python="3.12",
                    timeoutSeconds=180,
                    workers=2,
                    modelsEnabled=True,
                    stirlingEnabled=True,
                ),
                "results": [
                    dict(
                        id=str(i),
                        sha256=f"fixture-{i}",
                        status="converted",
                        tables=1,
                        seconds=1,
                    )
                    for i in range(200)
                ],
            }
            evaluation = dict(
                evaluationVersion=2,
                totals=dict(annotatedNonemptyCells=1, textAndSpanAtPosition=1),
                results=[dict(id="0", textAndSpanAtPosition=1)],
            )
            for root in roots:
                root.mkdir()
                (root / "benchmark.json").write_text(json.dumps(run))
                (root / "cell-evaluation.json").write_text(json.dumps(evaluation))
                (root / "reference-comparison.json").write_text(
                    json.dumps({"summary": {"tableCountMatches": 1}})
                )
            self.assertEqual(
                comparison.compare(*roots)["summary"]["strictRegressions"], []
            )
            evaluation["results"][0]["textAndSpanAtPosition"] = 0
            evaluation["totals"]["textAndSpanAtPosition"] = 0
            (roots[1] / "cell-evaluation.json").write_text(json.dumps(evaluation))
            self.assertEqual(
                comparison.compare(*roots)["summary"]["strictRegressions"], ["0"]
            )
            evaluation["evaluationVersion"] = 3
            (roots[1] / "cell-evaluation.json").write_text(json.dumps(evaluation))
            with self.assertRaisesRegex(ValueError, "same scoring version"):
                comparison.compare(*roots)
            run["results"][0]["sha256"] = "changed"
            (roots[1] / "benchmark.json").write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError, "Source hashes changed"):
                comparison.compare(*roots)

    def run_case(self, status="converted", merged=True, value="00123"):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "references").mkdir()
            (root / "outputs").mkdir()
            (root / "references/WEB-001-str.xml").write_text(
                """<document><table><region page="1">
              <cell start-row="0" start-col="0" end-col="1"><bounding-box x1="10" x2="40" y2="100"/><content>Heading</content></cell>
              <cell start-row="1" start-col="0"><bounding-box x1="10" x2="40" y2="80"/><content>00123</content></cell>
              <cell start-row="1" start-col="1"><bounding-box x1="60" x2="90" y2="80"/><content>Two words</content></cell>
            </region></table></document>"""
            )
            (root / "benchmark.json").write_text(
                json.dumps({"results": [{"id": "WEB-001", "status": status}]})
            )
            book = Workbook()
            sheet = book.active
            sheet.title = "Page 1 Table 1"
            sheet.append(["Heading", None])
            sheet.append([value, "Two\nwords"])
            if merged:
                sheet.merge_cells("A1:B1")
            book.save(root / "outputs/WEB-001.xlsx")
            with contextlib.redirect_stdout(io.StringIO()):
                scorer.evaluate(root)
            return json.loads((root / "cell-evaluation.json").read_text())["totals"]

    def test_whitespace_is_separate_from_exact_text(self):
        result = self.run_case()
        self.assertEqual(result["exactTextAtPosition"], 2)
        self.assertEqual(result["whitespaceNormalizedTextAtPosition"], 3)
        self.assertEqual(result["textAndSpanAtPosition"], 3)

    def test_lost_leading_zeros_and_merge_are_errors(self):
        result = self.run_case(merged=False, value="123")
        self.assertEqual(result["whitespaceNormalizedTextAtPosition"], 2)
        self.assertEqual(result["textAndSpanAtPosition"], 1)

    def test_refused_output_does_not_reuse_stale_workbook(self):
        result = self.run_case(status="refused")
        self.assertEqual(result["annotatedNonemptyCells"], 3)
        self.assertEqual(result.get("textAndSpanAtPosition", 0), 0)
        self.assertEqual(result["outputNonemptyCells"], 0)

    def test_row_alignment_keeps_column_errors_and_reordered_rows(self):
        def cell(text):
            return {"text": text, "rs": 1, "cs": 1}

        reference = {
            (0, 0): cell("A"),
            (0, 1): cell("1"),
            (2, 0): cell("B"),
            (2, 1): cell("2"),
        }
        with_caption = {
            (0, 0): cell("Caption"),
            (1, 0): cell("A"),
            (1, 1): cell("1"),
            (2, 0): cell("B"),
            (2, 1): cell("2"),
        }
        self.assertEqual(
            scorer.aligned_cell_scores(reference, with_caption)["alignedTextAndSpan"], 4
        )
        wrong_columns = {
            (0, 0): cell("1"),
            (0, 1): cell("A"),
            (1, 0): cell("2"),
            (1, 1): cell("B"),
        }
        self.assertEqual(
            scorer.aligned_cell_scores(reference, wrong_columns)["alignedTextAndSpan"],
            0,
        )
        reversed_rows = {
            (0, 0): cell("B"),
            (0, 1): cell("2"),
            (1, 0): cell("A"),
            (1, 1): cell("1"),
        }
        self.assertEqual(
            scorer.aligned_cell_scores(reference, reversed_rows)["alignedTextAndSpan"],
            2,
        )

    def test_regions_of_one_table_use_declared_offsets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "references").mkdir()
            (root / "outputs").mkdir()
            regions = []
            for col, values in ((0, ("Code", "00123")), (1, ("Amount", "9.50"))):
                cells = "".join(
                    f'<cell start-row="{r}" start-col="0"><bounding-box x1="{10+col*100}" x2="{70+col*100}" y2="{100-r*20}"/><content>{v}</content></cell>'
                    for r, v in enumerate(values)
                )
                regions.append(
                    f'<region page="1" col-increment="{col}" row-increment="7">{cells}</region>'
                )
            (root / "references/WEB-001-str.xml").write_text(
                "<document><table>" + "".join(regions) + "</table></document>"
            )
            (root / "benchmark.json").write_text(
                json.dumps({"results": [{"id": "WEB-001", "status": "converted"}]})
            )
            book = Workbook()
            book.active.title = "Page 1 Table 1"
            book.active.append(["Code", "Amount"])
            book.active.append(["00123", "9.50"])
            book.save(root / "outputs/WEB-001.xlsx")
            with contextlib.redirect_stdout(io.StringIO()):
                scorer.evaluate(root)
            result = json.loads((root / "cell-evaluation.json").read_text())["totals"]
            self.assertEqual(result["annotatedTables"], 1)
            self.assertEqual(result["annotatedNonemptyCells"], 4)
            self.assertEqual(result["textAndSpanAtPosition"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
