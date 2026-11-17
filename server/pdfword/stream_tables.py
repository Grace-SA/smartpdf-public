"""Independent numeric-table proposals, accepted only with cell-level agreement."""
import collections
import json
import math
import os
import re
import subprocess
import tempfile
import unicodedata
from bisect import bisect_right
from pathlib import Path


def characters(value):
    return collections.Counter(c for c in unicodedata.normalize("NFKC", value)
                               if not c.isspace())


def ordered_text(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value) if not c.isspace())


class StreamTables:
    """One bounded extraction per document; an unavailable helper keeps OCR fallback."""
    def __init__(self, source):
        self.source = source
        self.pages = None

    def proposals(self, index):
        if self.pages is None:
            self.pages = {}
            python = os.environ.get("PDFWORD_TABLE_PYTHON")
            if not python:
                return []
            try:
                with tempfile.TemporaryDirectory(prefix="pdfword-tables-") as directory:
                    output = Path(directory) / "tables.json"
                    subprocess.run([python, "-B", str(Path(__file__).with_name("stream_tables_process.py")),
                                    str(self.source), str(output)], check=True, timeout=30,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if output.stat().st_size > 8 * 1024**2:
                        return []
                    proposals = json.loads(output.read_text())
                    if not isinstance(proposals, list) or len(proposals) > 1000:
                        return []
                    for proposal in proposals:
                        page = proposal.get("page") if isinstance(proposal, dict) else None
                        if type(page) is int and 1 <= page <= 200:
                            self.pages.setdefault(page-1, []).append(proposal)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        return self.pages.get(index, [])


def qualified_tables(page, words, proposals):
    """Reject rotated, malformed, sparse and differently assigned candidate cells.

    Camelot confidence scores are deliberately not used as accuracy evidence.
    Trailing footnotes remain outside the grid, in the native paragraph flow.
    """
    from layout import contains, words_to_blocks, native_font
    numeric = re.compile(r"[−+($€£¥-]?\d[\d,.%()−–-]*")
    result = []
    for proposal in proposals[:32]:
        try:
            if proposal.get("rotation") or proposal.get("pdf_size") != [page.width, page.height]:
                continue
            grid, cols, rows = (proposal[key] for key in ("grid", "cols", "rows"))
            if not (3 <= len(cols) <= 32 and 4 <= len(rows) <= 500
                    and len(grid) == len(rows) and len(rows)*len(cols) <= 10000
                    and all(len(row) == len(cols) and all(isinstance(c, str) and len(c) <= 10000 for c in row)
                            for row in grid)):
                continue
            if any(len(pair) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in pair)
                   for pair in cols + rows):
                continue
            if (any(not 0 <= a < b <= page.width for a, b in cols)
                    or any(not 0 <= b < a <= page.height for a, b in rows)
                    or any(abs(a[1]-b[0]) > .01 for a, b in zip(cols, cols[1:]))
                    or any(abs(a[1]-b[0]) > .01 for a, b in zip(rows, rows[1:]))):
                continue
            data_rows = [i for i, row in enumerate(grid)
                         if sum(bool(numeric.fullmatch(c.strip())) for c in row) >= 2]
            if len(data_rows) < 4:
                continue
            start, end = max(0, data_rows[0]-8), data_rows[-1]+1
            if len(data_rows)/(end-data_rows[0]) < .6:
                continue
            bounds = [cols[0][0], page.height-rows[start][0], cols[-1][1], page.height-rows[end-1][1]]
            if any(contains(t["bbox"], bounds) or contains(bounds, t["bbox"]) for t in result):
                continue
            cells = []
            valid = True
            # Assign each word once; scanning every word for every cell makes
            # dense multi-page reports needlessly quadratic in table size.
            x_edges = [cols[0][0]] + [b for _, b in cols]
            y_edges = [page.height-rows[0][0]] + [page.height-b for _, b in rows]
            buckets = collections.defaultdict(list)
            for word in words:
                col = bisect_right(x_edges, (word['x0']+word['x1'])/2)-1
                row = bisect_right(y_edges, (word['top']+word['bottom'])/2)-1
                if 0 <= col < len(cols) and start <= row < end:
                    buckets[row, col].append(word)
            for i in range(start, end):
                row_cells = []
                row_words = [w for j in range(len(cols)) for w in buckets[i, j]]
                for j in range(len(cols)):
                    inside = buckets[i, j]
                    paragraphs = words_to_blocks(inside, page.width, page.height)
                    value = "\n".join(p["text"] for p in paragraphs)
                    if ordered_text(value) != ordered_text(grid[i][j]):
                        valid = False
                        break
                    row_cells.append(dict(row=i-start, col=j, rowspan=1, colspan=1,
                                      text=value, font=native_font(paragraphs),
                                      bold=bool(paragraphs) and all(p.get("bold") for p in paragraphs),
                                      size=min((p["size"] for p in paragraphs), default=10),
                                      header=i < data_rows[0]))
                if not valid and i < data_rows[0]:
                    # A header may genuinely span columns. Require a unique full
                    # phrase match and its proposed owner inside the physical span.
                    row_cells = header_spans(row_words, grid[i], cols, i-start, page)
                    valid = row_cells is not None
                if not valid:
                    break
                cells.extend(row_cells)
            if not valid:
                continue
            # Every native word inside this rectangle belongs to exactly one cell.
            inside = [w for w in words if contains(bounds, [w[k] for k in ("x0", "top", "x1", "bottom")])]
            if characters("".join(w["text"] for w in inside)) != characters("".join(c["text"] for c in cells)):
                continue
            result.append(dict(kind="table", bbox=bounds, rows=end-start, cols=len(cols),
                               cells=cells, widths=[b-a for a, b in cols], source="native",
                               header_rows=data_rows[0]-start))
        except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
            continue
    return result


def header_spans(words, expected, cols, row, page):
    from layout import words_to_blocks, native_font
    groups = []
    for word in sorted(words, key=lambda w: (round(w['top']/3), w['x0'])):
        if (not groups or abs(word['top']-groups[-1][-1]['top']) > 3
                or word['x0']-groups[-1][-1]['x1'] > max(6, (word['bottom']-word['top'])*1.2)):
            groups.append([])
        groups[-1].append(word)
    used, occupied, cells = set(), set(), []
    for group in groups:
        text = ''.join(w['text'] for w in group)
        if re.fullmatch(r'[−+($€£¥-]?\d[\d,.%()−–-]*', text):
            return None
        matches = [i for i, value in enumerate(expected) if value and ordered_text(value) == ordered_text(text)]
        if len(matches) != 1 or matches[0] in used:
            return None
        centres = [(w['x0']+w['x1'])/2 for w in group]
        covered = [i for i, (left, right) in enumerate(cols) if any(left <= c < right for c in centres)]
        if not covered or not min(covered) <= matches[0] <= max(covered):
            return None
        span = set(range(min(covered), max(covered)+1))
        if len(groups) == 1 and matches[0] == 0 and min(covered) == 0 and len(group) >= 5:
            # A single long table title occupies the otherwise empty header row;
            # stopping at its final glyph would force avoidable Word wrapping.
            span = set(range(len(cols)))
        if occupied & span:
            return None
        occupied |= span
        used.add(matches[0])
        paragraphs = words_to_blocks(group, page.width, page.height)
        cells.append(dict(row=row, col=min(span), rowspan=1, colspan=len(span),
                          text='\n'.join(p['text'] for p in paragraphs), font=native_font(paragraphs),
                          bold=bool(paragraphs) and all(p.get('bold') for p in paragraphs),
                          size=min((p['size'] for p in paragraphs), default=10), header=True))
    if used != {i for i, value in enumerate(expected) if value.strip()}:
        return None
    cells.extend(dict(row=row, col=i, rowspan=1, colspan=1, text='', size=10, header=True)
                 for i in range(len(cols)) if i not in occupied)
    return cells
