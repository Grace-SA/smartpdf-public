"""Download 200 SHA-deduplicated upstream fixtures; keep all binaries local only."""

import concurrent.futures, hashlib, json, pathlib, urllib.request, urllib.parse, sys

root = pathlib.Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
repos = [
    ("camelot-dev/camelot", "master"),
    ("tabulapdf/tabula-java", "master"),
    ("jsvine/pdfplumber", "stable"),
    ("py-pdf/pypdf", "main"),
]


def read(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "SmartPDF-public-corpus-research"}
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read(32 * 1024 * 1024)


candidates = []
for repo, ref in repos:
    try:
        tree = json.loads(
            read(f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1")
        )
        sha = tree["sha"]
        items = [
            x
            for x in tree["tree"]
            if x["path"].lower().endswith(".pdf")
            and x.get("size", 0) < 30 * 1024 * 1024
            and any(t in x["path"] for t in ["test", "example"])
        ]
        print(repo, len(items), flush=True)
        for x in sorted(items, key=lambda x: x["path"]):
            candidates.append(
                {
                    "repository": repo,
                    "commit": sha,
                    "path": x["path"],
                    "url": f"https://raw.githubusercontent.com/{repo}/{sha}/"
                    + urllib.parse.quote(x["path"]),
                    "license_review": "Upstream fixture; research only, redistribution not approved",
                }
            )
    except Exception as e:
        print(repo, type(e).__name__, flush=True)


def download(item):
    try:
        data = read(item["url"])
        if not data.startswith(b"%PDF-"):
            return None
        h = hashlib.sha256(data).hexdigest()
        file = root / (h + ".pdf")
        file.write_bytes(data)
        return dict(item, sha256=h, bytes=len(data), file=file.name)
    except Exception:
        return None


seen = set()
manifest = []
# Iterate in bounded batches so retries do not download an unlimited corpus.
for start in range(0, len(candidates), 16):
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(download, candidates[start : start + 16]))
    for item in results:
        if item and item["sha256"] not in seen and len(manifest) < 200:
            seen.add(item["sha256"])
            item["id"] = f"WEB-{len(manifest)+1:03d}"
            manifest.append(item)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("unique", len(manifest), flush=True)
    if len(manifest) >= 200:
        break
print("Downloaded", len(manifest), "unique PDFs")
if len(manifest) < 200:
    sys.exit(2)
