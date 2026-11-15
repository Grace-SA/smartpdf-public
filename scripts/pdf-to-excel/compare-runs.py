"""Compare identical public samples and the same independent evaluator version.

Usage: compare-runs.py BASELINE CANDIDATE OUTPUT.json
Baseline may retain original cell-evaluation.json plus corrected cell-evaluation-v2.json.
No references are supplied to the converter. The comparison never rewrites values.
"""

from collections import Counter
import hashlib
import json
import re
from pathlib import Path
import statistics
import sys


def read(root, name):
    return json.loads((root / name).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(baseline, candidate):
    old, new = (read(root, "benchmark.json") for root in (baseline, candidate))
    before, after = ({r["id"]: r for r in run["results"]} for run in (old, new))
    if len(before) != len(old["results"]) or len(after) != len(new["results"]):
        raise ValueError("Duplicate sample identities")
    if not before or set(before) != set(after):
        raise ValueError("A complete comparison requires the same nonempty sample IDs")
    if any(before[k]["sha256"] != after[k]["sha256"] for k in before):
        raise ValueError("Source hashes changed")
    for field in (
        "python",
        "timeoutSeconds",
        "workers",
        "modelsEnabled",
        "stirlingEnabled",
    ):
        if old["runtime"][field] != new["runtime"][field]:
            raise ValueError("Benchmark runtime differs: " + field)
    old_eval_name = (
        "cell-evaluation-v2.json"
        if read(baseline, "cell-evaluation.json").get("evaluationVersion") != 3
        and (baseline / "cell-evaluation-v2.json").exists()
        else "cell-evaluation.json"
    )
    evaluations = [
        read(baseline, old_eval_name),
        read(candidate, "cell-evaluation.json"),
    ]
    if evaluations[0].get("evaluationVersion") != evaluations[1].get(
        "evaluationVersion"
    ):
        raise ValueError("Evaluate both runs using the same scoring version")
    if evaluations[0].get("evaluationVersion") != 3 and len(before) != 200:
        raise ValueError("Legacy comparison requires the same 200 samples")
    annotated = [{r["id"]: r for r in run["results"]} for run in evaluations]
    if set(annotated[0]) != set(annotated[1]):
        raise ValueError("Annotation identities differ")
    if evaluations[0].get("evaluationVersion") == 3:
        for evaluation, cells, root in zip(
            evaluations, annotated, (baseline, candidate)
        ):
            for field, relative in (
                ("benchmarkSha256", "benchmark.json"),
                ("manifestSha256", "corpus/manifest.json"),
            ):
                path = root / relative
                if not path.is_file() or evaluation.get(field) != digest(path):
                    raise ValueError(
                        f"Scoring report {field} binding changed or missing"
                    )
            hashes = evaluation.get("referenceSha256")
            if evaluation.get("integrityMode") != "verified-manifest":
                raise ValueError(
                    "Scoring version 3 requires verified-manifest integrity mode"
                )
            if (
                len(cells) != len(evaluation["results"])
                or not set(cells).issubset(before)
                or not isinstance(hashes, dict)
                or not hashes
                or set(hashes) != set(cells)
                or any(
                    not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h)
                    for h in hashes.values()
                )
            ):
                raise ValueError(
                    "Verified reference hashes must cover every annotated sample"
                )
        if evaluations[0]["referenceSha256"] != evaluations[1]["referenceSha256"]:
            raise ValueError("Reference hashes changed")
    metrics = (
        "exactTextAtPosition",
        "whitespaceNormalizedTextAtPosition",
        "textAndSpanAtPosition",
        "alignedNormalizedText",
        "alignedTextAndSpan",
        "textMultisetIntersection",
        "annotatedMergedCells",
        "mergedTextAndSpanAtPosition",
        "alignedMergedTextAndSpan",
    )
    rows = []
    for key in sorted(before):
        a, b = before[key], after[key]
        row = dict(
            id=key,
            beforeStatus=a["status"],
            afterStatus=b["status"],
            beforeTables=a.get("tables", 0),
            afterTables=b.get("tables", 0),
            beforeSeconds=a["seconds"],
            afterSeconds=b["seconds"],
        )
        if key in annotated[0]:
            row["cellDeltas"] = {
                metric: annotated[1][key].get(metric, 0)
                - annotated[0][key].get(metric, 0)
                for metric in metrics
            }
        rows.append(row)
    totals = [run["totals"] for run in evaluations]
    if totals[0]["annotatedNonemptyCells"] != totals[1]["annotatedNonemptyCells"]:
        raise ValueError("Annotation denominator changed")
    summary = {
        "samples": len(before),
        "statusBefore": dict(Counter(r["status"] for r in before.values())),
        "statusAfter": dict(Counter(r["status"] for r in after.values())),
        "recovered": [
            r["id"]
            for r in rows
            if r["beforeStatus"] != "converted" and r["afterStatus"] == "converted"
        ],
        "newRefusals": [
            r["id"]
            for r in rows
            if r["beforeStatus"] == "converted" and r["afterStatus"] != "converted"
        ],
        "annotatedFiles": len(annotated[0]),
        "annotatedNonemptyCells": totals[0]["annotatedNonemptyCells"],
        "metrics": {
            metric: {
                "before": totals[0].get(metric, 0),
                "after": totals[1].get(metric, 0),
                "delta": totals[1].get(metric, 0) - totals[0].get(metric, 0),
            }
            for metric in metrics
        },
        "strictRegressions": [
            r["id"]
            for r in rows
            if r.get("cellDeltas", {}).get("textAndSpanAtPosition", 0) < 0
        ],
        "alignedRegressions": [
            r["id"]
            for r in rows
            if r.get("cellDeltas", {}).get("alignedTextAndSpan", 0) < 0
        ],
        "medianSeconds": [
            statistics.median(r["seconds"] for r in run["results"])
            for run in (old, new)
        ],
        "maxSeconds": [max(r["seconds"] for r in run["results"]) for run in (old, new)],
    }
    for label, root in (("before", baseline), ("after", candidate)):
        counts = (
            read(root, "reference-comparison.json")
            if (root / "reference-comparison.json").is_file()
            else None
        )
        summary[label + "TableCountMatches"] = (
            counts["summary"]["tableCountMatches"] if counts else None
        )
        summary[label + "TableCountVerification"] = (
            "legacy-report-present" if counts else "not-verified"
        )
    return {
        "scope": f"Same {len(before)} public PDFs, identical runtime budget and evaluator; recall is not overall accuracy. Unannotated outputs require separate review.",
        "evaluationVersion": evaluations[0].get("evaluationVersion"),
        "baselineBenchmarkSha256": digest(baseline / "benchmark.json"),
        "candidateBenchmarkSha256": digest(candidate / "benchmark.json"),
        "baselineCellEvaluationSha256": digest(baseline / old_eval_name),
        "candidateCellEvaluationSha256": digest(candidate / "cell-evaluation.json"),
        "summary": summary,
        "results": rows,
    }


if __name__ == "__main__":
    baseline, candidate, output = map(Path, sys.argv[1:4])
    report = compare(baseline, candidate)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["summary"], indent=2))
