"""Conservative editable-text coverage, separate from ground-truth accuracy."""
import collections
import re
import unicodedata


def compact(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text) if not c.isspace())


def check_coverage(expected, actual, *, numeric_tokens=True):
    if len(actual) != len(expected):
        raise ValueError("Source page coverage mismatch")
    scores = []
    for source, result in zip(expected, actual):
        left, right = compact(source["text"]), compact(result)
        a, b = collections.Counter(left), collections.Counter(right)
        score = sum((a & b).values()) / max(1, len(left)) if left else 1
        pattern = r"\d+(?:[.,]\d+)*" if numeric_tokens else r"\d"
        numbers = lambda t: collections.Counter(re.findall(pattern, unicodedata.normalize("NFKC", t)))
        if score < 0.995 or numbers(source["text"]) - numbers(result):
            raise ValueError("Native output lost page text or numbers")
        if source.get("excludeClippedNumbers") and numbers(result) != numbers(source["text"]):
            raise ValueError("Native output exposed excluded numeric text")
        scores.append(round(score, 6))
    return scores


def editable_block_text(blocks):
    values = []
    for block in blocks:
        if block["kind"] == "table":
            from model import content_text
            values.append(content_text(block))
        elif block["kind"] not in ("image", "formula"):
            values.append(block.get("text", ""))
    return " ".join(values)


def editable_source_text(page, blocks):
    """Figure labels may remain in retained pictures; prose must stay editable."""
    clean = page.dedupe_chars(tolerance=0.5)
    def inside(char, bounds):
        return (char["x0"] >= bounds[0] - .5 and char["top"] >= bounds[1] - .5
                and char["x1"] <= bounds[2] + .5 and char["bottom"] <= bounds[3] + .5)
    labels = []
    for block in blocks:
        if block["kind"] != "image":
            continue
        value = "".join(c["text"] for c in clean.chars if inside(c, block["bbox"]))
        if len(compact(value)) <= 80:
            labels.append(block["bbox"])
    filtered = clean.filter(lambda obj: obj.get("object_type") != "char" or not any(inside(obj, bounds) for bounds in labels))
    return filtered.extract_text(x_tolerance=2, y_tolerance=3) or ""
