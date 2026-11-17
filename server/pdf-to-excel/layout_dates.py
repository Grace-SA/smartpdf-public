"""Recover aligned year/month tables and geometrically duplicated glyphs."""

import re
from text_tables import aligned_tables
from layout_tables import visible_box

DATE = re.compile(r"(?:19|20)\d{2}年(?:0?[1-9]|1[0-2])月")


def recover_date_tables(page):
    page = page.crop(tuple(visible_box(page))).dedupe_chars(tolerance=0.5)
    result = []
    for t in aligned_tables(page):
        if len(t["widths"]) != 2 or len(t["heights"]) < 3:
            continue
        labels = [c for c in t["cells"] if c["c"] == 0]
        dates = [c for c in t["cells"] if c["c"] == 1]
        if len(labels) != len(t["heights"]) or len(dates) != len(labels):
            continue
        if not all(DATE.fullmatch(c["text"].strip()) for c in dates):
            continue
        if not all(any(ch.isalpha() for ch in c["text"]) for c in labels):
            continue
        t["headerRows"] = 0
        result.append(t)
    return result
