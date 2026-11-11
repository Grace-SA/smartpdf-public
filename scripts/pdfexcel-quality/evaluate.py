"""Run the frozen synthetic benchmark without retaining document outputs."""

from __future__ import annotations
import argparse
import json
import tempfile
from pathlib import Path

from baseline import evaluate_pdf
from corpus import cases, generate
from validate import QualityError, verify_result
from pdfminer.pdfparser import PDFSyntaxError
from pdfminer.psparser import PSEOF


FROZEN_CASE_IDS = (
    "ruled-basic",
    "empty-cells",
    "multiline-cells",
    "merged-header",
    "literal-values",
    "unicode-chinese",
    "unicode-japanese",
    "two-tables",
    "multipage",
    "landscape",
    "blank-page",
    "narrative-page",
    "borderless",
    "scanned-table",
    "mixed-native-scan",
    "rotated-page",
    "password-protected",
    "corrupted",
    "empty-input",
)


def run():
    inventory = cases()
    if tuple(case.get("id") for case in inventory) != FROZEN_CASE_IDS:
        raise QualityError("corpus_inventory")
    results = []
    with tempfile.TemporaryDirectory(prefix="pdfexcel-synthetic-") as directory:
        for case in inventory:
            path = Path(directory) / (case["id"] + ".pdf")
            generate(case, path)
            try:
                report, output = evaluate_pdf(path)
            except (PDFSyntaxError, PSEOF):
                report, output = {"refusal": "invalid_pdf"}, None
            try:
                if "refusal" in case:
                    if report != {"refusal": case["refusal"]} or output is not None:
                        raise QualityError("wrong_refusal")
                else:
                    verify_result(case, report, output)
                results.append({"id": case["id"], "passed": True})
            except QualityError as error:
                results.append(
                    {"id": case["id"], "passed": False, "reason": str(error)}
                )
    conversions = [r for r, c in zip(results, inventory) if "refusal" not in c]
    refusals = [r for r, c in zip(results, inventory) if "refusal" in c]
    return {
        "status": "evaluation_only",
        "production_ready": False,
        "synthetic_corpus_gate": "pass"
        if all(r["passed"] for r in results)
        else "fail",
        "conversion_passed": sum(r["passed"] for r in conversions),
        "conversion_total": len(conversions),
        "refusal_passed": sum(r["passed"] for r in refusals),
        "refusal_total": len(refusals),
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Measure known gaps without enforcing the synthetic-corpus gate",
    )
    args = parser.parse_args()
    result = run()
    print(json.dumps(result, indent=2))
    raise SystemExit(
        0 if args.report_only or result["synthetic_corpus_gate"] == "pass" else 1
    )
