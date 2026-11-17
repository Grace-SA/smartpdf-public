"""Compare public corpus output with pinned upstream table-count annotations.

This measures detection counts, never cell/text accuracy. Files remain outside Git.
Usage: python scripts/pdf-to-excel/compare-references.py <corpus-parent>
"""

import concurrent.futures
import json
import sys
import urllib.request
from pathlib import Path


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def main(root, offline=False):
    manifest = json.loads((root / "corpus/manifest.json").read_text())
    results = {
        r["id"]: r for r in json.loads((root / "benchmark.json").read_text())["results"]
    }
    candidates = [r for r in manifest if r["repository"] == "camelot-dev/camelot"]
    references = root / "references"
    references.mkdir(exist_ok=True)
    paths = set()
    if offline:
        candidates = [
            r for r in candidates if (references / (r["id"] + ".json")).exists()
        ]
    else:
        for commit in {r["commit"] for r in candidates}:
            tree = fetch_json(
                f"https://api.github.com/repos/camelot-dev/camelot/git/trees/{commit}?recursive=1"
            )
            paths.update((commit, r["path"]) for r in tree["tree"])
        candidates = [
            r for r in candidates if (r["commit"], r["path"][:-4] + ".json") in paths
        ]

    def compare(item):
        path = item["path"][:-4] + ".json"
        url = f"https://raw.githubusercontent.com/{item['repository']}/{item['commit']}/{path}"
        if offline:
            data = json.loads((references / (item["id"] + ".json")).read_text())
        else:
            data = fetch_json(url)
            (references / (item["id"] + ".json")).write_text(json.dumps(data, indent=2))
            for kind in ("str", "reg"):
                xml_url = url.removesuffix(".json") + "-" + kind + ".xml"
                with urllib.request.urlopen(xml_url, timeout=30) as response:
                    (references / (item["id"] + "-" + kind + ".xml")).write_bytes(
                        response.read()
                    )
        actual = results[item["id"]]
        expected = data["numExpectedTables"]
        return {
            "id": item["id"],
            "referenceUrl": url,
            "expectedTables": expected,
            "actualTables": actual.get("tables", 0),
            "conversionStatus": actual["status"],
            "tableCountMatches": actual.get("tables", 0) == expected,
            "upstreamExpectedFailure": data.get("expectedFailure"),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(compare, candidates))
    summary = {
        "files": len(rows),
        "tableCountMatches": sum(r["tableCountMatches"] for r in rows),
        "converted": sum(r["conversionStatus"] == "converted" for r in rows),
        "refused": sum(r["conversionStatus"] == "refused" for r in rows),
        "convertedCountMatches": sum(
            r["tableCountMatches"] and r["conversionStatus"] == "converted"
            for r in rows
        ),
    }
    (root / "reference-comparison.json").write_text(
        json.dumps(
            {
                "scope": "Upstream expected table counts only, not cell/text accuracy",
                "summary": summary,
                "results": rows,
            },
            indent=2,
        )
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main(Path(sys.argv[1]), offline="--offline" in sys.argv[2:])
