"""Verify the independent scorer with hand-authored reference cells."""

import contextlib
import importlib.util
import io
import hashlib
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


def seal_fixture(root):
    """Declare synthetic fixture bytes independently of the scorer."""

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    (root / "corpus").mkdir(exist_ok=True)
    source = root / "corpus/WEB-001.pdf"
    source.write_bytes(b"%PDF- synthetic scorer-only fixture")
    manifest = [
        dict(
            id="WEB-001",
            file=source.name,
            sha256=digest(source),
            referenceSha256=digest(root / "references/WEB-001-str.xml"),
        )
    ]
    (root / "corpus/manifest.json").write_text(json.dumps(manifest))
    benchmark = json.loads((root / "benchmark.json").read_text())
    for row in benchmark["results"]:
        row["sha256"] = digest(source)
        if row["status"] == "converted":
            row["outputSha256"] = digest(root / "outputs/WEB-001.xlsx")
    (root / "benchmark.json").write_text(json.dumps(benchmark))


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

    def test_twelve_sample_verified_comparison_binds_reports_references_and_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots = [Path(temporary) / name for name in ("before", "after")]
            run = dict(
                runtime=dict(
                    python="3.12",
                    timeoutSeconds=180,
                    workers=2,
                    modelsEnabled=True,
                    stirlingEnabled=False,
                ),
                results=[
                    dict(id=str(i), sha256=f"fixture-{i}", status="refused", seconds=1)
                    for i in range(12)
                ],
            )
            evaluation = dict(
                evaluationVersion=3,
                integrityMode="verified-manifest",
                referenceSha256={"0": "a" * 64},
                totals=dict(annotatedNonemptyCells=1),
                results=[dict(id="0")],
            )
            for root in roots:
                root.mkdir()
                (root / "benchmark.json").write_text(json.dumps(run))
                (root / "corpus").mkdir()
                (root / "corpus/manifest.json").write_text("[]")
                evaluation["benchmarkSha256"] = comparison.digest(
                    root / "benchmark.json"
                )
                evaluation["manifestSha256"] = comparison.digest(
                    root / "corpus/manifest.json"
                )
                (root / "cell-evaluation.json").write_text(json.dumps(evaluation))

            # A stale legacy score must not override the current verified report.
            (roots[0] / "cell-evaluation-v2.json").write_text(
                json.dumps(dict(evaluationVersion=2))
            )
            report = comparison.compare(*roots)
            self.assertEqual(report["summary"]["strictRegressions"], [])
            self.assertEqual(report["summary"]["samples"], 12)
            self.assertIn("Same 12", report["scope"])
            self.assertIsNone(report["summary"]["beforeTableCountMatches"])
            self.assertEqual(
                report["summary"]["afterTableCountVerification"], "not-verified"
            )
            for updates, message in [
                ({"referenceSha256": {"0": "b" * 64}}, "Reference hashes changed"),
                ({"referenceSha256": {}}, "cover every annotated"),
                ({"results": [dict(id="0"), dict(id="0")]}, "cover every annotated"),
                ({"referenceSha256": {"other": "a" * 64}}, "cover every annotated"),
                ({"referenceSha256": {"0": "bad"}}, "cover every annotated"),
                ({"integrityMode": "unverified-legacy"}, "integrity mode"),
                ({"integrityMode": None}, "integrity mode"),
            ]:
                with self.subTest(updates=updates):
                    (roots[1] / "cell-evaluation.json").write_text(
                        json.dumps(evaluation | updates)
                    )
                    with self.assertRaisesRegex(ValueError, message):
                        comparison.compare(*roots)

            (roots[1] / "cell-evaluation.json").write_text(json.dumps(evaluation))
            for relative, binding in (
                ("benchmark.json", "benchmarkSha256"),
                ("corpus/manifest.json", "manifestSha256"),
            ):
                with self.subTest(relative=relative):
                    path = roots[1] / relative
                    original = path.read_bytes()
                    path.write_bytes(original + b" ")
                    with self.assertRaisesRegex(ValueError, binding):
                        comparison.compare(*roots)
                    path.write_bytes(original)
            # Legacy scoring is intentionally still limited to the historical corpus.
            legacy = evaluation | {"evaluationVersion": 2}
            (roots[0] / "cell-evaluation-v2.json").unlink()
            for root in roots:
                (root / "cell-evaluation.json").write_text(json.dumps(legacy))
            with self.assertRaisesRegex(ValueError, "200 samples"):
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
            seal_fixture(root)
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
                    f'<cell start-row="{r}" start-col="0"><bounding-box x1="{10 + col * 100}" x2="{70 + col * 100}" y2="{100 - r * 20}"/><content>{v}</content></cell>'
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
            seal_fixture(root)
            with contextlib.redirect_stdout(io.StringIO()):
                scorer.evaluate(root)
            result = json.loads((root / "cell-evaluation.json").read_text())["totals"]
            self.assertEqual(result["annotatedTables"], 1)
            self.assertEqual(result["annotatedNonemptyCells"], 4)
            self.assertEqual(result["textAndSpanAtPosition"], 4)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "references").mkdir()
        (self.root / "outputs").mkdir()
        (self.root / "references/WEB-001-str.xml").write_text("<document/>")
        book = Workbook()
        book.active.title = "Page 1 Table 1"
        book.active["A1"] = "Example"
        book.save(self.root / "outputs/WEB-001.xlsx")
        book.close()
        (self.root / "benchmark.json").write_text(
            json.dumps({"results": [dict(id="WEB-001", status="converted")]})
        )
        seal_fixture(self.root)

    def edit(self, relative, change):
        path = self.root / relative
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def evaluate(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            scorer.evaluate(self.root, **kwargs)
        return json.loads((self.root / "cell-evaluation.json").read_text())

    def test_verified_mode_and_explicit_legacy_are_distinct(self):
        result = self.evaluate()
        self.assertEqual(result["evaluationVersion"], 3)
        self.assertEqual(result["integrityMode"], "verified-manifest")
        self.assertEqual(set(result["referenceSha256"]), {"WEB-001"})
        self.assertEqual(
            result["benchmarkSha256"], comparison.digest(self.root / "benchmark.json")
        )
        self.assertEqual(
            result["manifestSha256"],
            comparison.digest(self.root / "corpus/manifest.json"),
        )
        (self.root / "corpus/manifest.json").unlink()
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.evaluate()
        legacy = self.evaluate(allow_unverified=True)
        self.assertEqual(legacy["evaluationVersion"], 2)
        self.assertEqual(legacy["integrityMode"], "unverified-legacy")

    def test_rogue_and_missing_references_rejected(self):
        rogue = self.root / "references/rogue-999-str.xml"
        rogue.write_text("<document/>")
        with self.assertRaisesRegex(ValueError, "Reference file IDs"):
            self.evaluate()
        rogue.unlink()
        (self.root / "references/WEB-001-str.xml").unlink()
        with self.assertRaisesRegex(ValueError, "Reference file IDs"):
            self.evaluate()

    def test_tampered_reference_and_output_rejected(self):
        ref = self.root / "references/WEB-001-str.xml"
        original = ref.read_bytes()
        ref.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "Reference hash"):
            self.evaluate()
        ref.write_bytes(original)
        with (self.root / "outputs/WEB-001.xlsx").open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "Output hash"):
            self.evaluate()

    def test_duplicate_and_missing_benchmark_rows_rejected(self):
        self.edit(
            "benchmark.json", lambda d: d["results"].append(d["results"][0].copy())
        )
        with self.assertRaisesRegex(ValueError, "Duplicate benchmark"):
            self.evaluate()
        self.edit("benchmark.json", lambda d: d.update(results=[]))
        with self.assertRaisesRegex(ValueError, "Benchmark IDs"):
            self.evaluate()

    def test_missing_status_and_changed_source_binding_rejected(self):
        self.edit("benchmark.json", lambda d: d["results"][0].pop("status"))
        with self.assertRaisesRegex(ValueError, "benchmark status"):
            self.evaluate()
        self.edit(
            "benchmark.json",
            lambda d: d["results"][0].update(status="converted", sha256="0" * 64),
        )
        with self.assertRaisesRegex(ValueError, "Benchmark source hash"):
            self.evaluate()

    def test_no_declared_labels_and_duplicate_manifest_rejected(self):
        self.edit("corpus/manifest.json", lambda d: d.append(d[0].copy()))
        with self.assertRaisesRegex(ValueError, "Duplicate manifest"):
            self.evaluate()
        self.edit("corpus/manifest.json", lambda d: d.pop())
        self.edit("corpus/manifest.json", lambda d: d[0].pop("referenceSha256"))
        with self.assertRaisesRegex(ValueError, "declared referenceSha256"):
            self.evaluate()

    def test_source_file_tamper_rejected(self):
        (self.root / "corpus/WEB-001.pdf").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Source hash"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
