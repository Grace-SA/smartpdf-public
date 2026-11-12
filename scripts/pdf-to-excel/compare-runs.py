"""Compare identical public samples and the same independent evaluator version.

Usage: compare-runs.py BASELINE CANDIDATE OUTPUT.json
Baseline may retain original cell-evaluation.json plus corrected cell-evaluation-v2.json.
No references are supplied to the converter. The comparison never rewrites values.
"""

from collections import Counter
import hashlib
import json
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
    if set(before) != set(after) or len(before) != 200:
        raise ValueError("A complete comparison requires the same 200 samples")
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
        if (baseline / "cell-evaluation-v2.json").exists()
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
    annotated = [{r["id"]: r for r in run["results"]} for run in evaluations]
    if set(annotated[0]) != set(annotated[1]):
        raise ValueError("Annotation identities differ")
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
        "samples": 200,
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
        counts = read(root, "reference-comparison.json")
        summary[label + "TableCountMatches"] = counts["summary"]["tableCountMatches"]
    return {
        "scope": "Same 200 public PDFs, identical runtime budget and evaluator; recall is not overall accuracy. Unannotated outputs require separate review.",
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
