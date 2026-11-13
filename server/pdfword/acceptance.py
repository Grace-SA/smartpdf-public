"""Offline release gate. Generating DOCX alone never establishes acceptance.

Input is an independently reviewed evaluation JSON, not a worker manifest.
Downloaded documents and evaluation inventories stay outside Git.
"""

import argparse
import json
import math
from collections import defaultdict

CATEGORIES = {
    "paragraphs",
    "scans",
    "tables",
    "merged_tables",
    "borderless_tables",
    "multipage_tables",
    "mixed",
    "columns",
    "cjk",
    "japanese",
    "low_quality",
    "long_documents",
}


def evaluate(report):
    failures = []
    families = set()
    pages = 0
    passed = 0
    heldout = 0
    groups = defaultdict(list)
    rows = report.get("documents", [])
    for row in rows:
        family = row.get("family")
        if not family or family in families:
            failures.append("Duplicate or missing source family")
            continue
        families.add(family)
        count = row.get("pages", 0)
        if type(count) != int or count < 1:
            failures.append("Missing valid page count")
            count = 0
        pages += count
        heldout += (
            row.get("partition") == "held_out"
            and row.get("frozen_before_development") is True
        )
        categories = set(row.get("categories", []))
        valid = (
            row.get("status") == "accepted"
            and row.get("independent_opc") is True
            and row.get("visual_review") is True
            and row.get("edit_reopen") is True
            and row.get("ground_truth_verified") is True
            and type(row.get("native")) is bool
        )
        metrics = row.get("metrics", {})

        def threshold(name, bound, minimum=False):
            value = metrics.get(name)
            return (
                type(value) in (int, float)
                and math.isfinite(value)
                and 0 <= value <= 1
                and (value >= bound if minimum else value <= bound)
            )

        valid = valid and threshold("reading_order", 0.99, True)
        if row.get("native"):
            valid = valid and threshold("text_accuracy", 0.999, True)
        else:
            valid = valid and threshold(
                "cer", 0.01 if categories & {"cjk", "japanese"} else 0.005
            )
        if categories & {
            "tables",
            "merged_tables",
            "borderless_tables",
            "multipage_tables",
        }:
            valid = (
                valid
                and threshold("cell_accuracy", 0.99, True)
                and threshold("teds", 0.98, True)
            )
        valid = bool(
            valid
            and type(metrics.get("critical_errors")) is int
            and metrics["critical_errors"] == 0
        )
        passed += valid
        for c in categories:
            groups[c].append(valid)
    if len(families) < 120 or pages < 600:
        failures.append("Need 120 independent source documents and 600 pages")
    if heldout * 3 < len(families):
        failures.append("Need at least one third genuinely frozen held-out sources")
    if not rows or passed / len(rows) < 0.95:
        failures.append(
            "End-to-end acceptance is below 95%; refusals and review cases count as failures"
        )
    for name in sorted(CATEGORIES):
        values = groups[name]
        if len(values) < 10:
            failures.append(f"{name}: need 10 independently reviewed sources")
        elif sum(values) / len(values) < 0.9:
            failures.append(f"{name}: acceptance below 90%")
    for name, limit in [
        ("native_10page_warm_p95_seconds", 10),
        ("ocr_10page_warm_p95_seconds", 90),
    ]:
        value = report.get("performance", {}).get(name)
        if type(value) not in (int, float) or not 0 < value <= limit:
            failures.append(f"Unmet performance gate: {name}")
    for name in [
        "microsoft_word",
        "linux_gpu_isolation",
        "concurrent_load",
        "cancellation_cleanup",
        "browser_regression",
    ]:
        if report.get("platform_checks", {}).get(name) is not True:
            failures.append(f"Unverified platform gate: {name}")
    return dict(
        ready=not failures,
        documents=len(families),
        pages=pages,
        accepted=passed,
        failures=failures,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    args = parser.parse_args()
    result = evaluate(json.loads(open(args.report).read()))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ready"] else 2)

