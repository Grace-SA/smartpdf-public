"""Conservative native reconstruction of headed numeric/text registers."""
import re
from statistics import median


def headed_registers(words):
    """Require repeated columns AND a complete, unambiguous header.

    This deliberately excludes sparse cells, spans and parallel numbered lists.
    All text comes from native words; no values or missing cells are inferred.
    """
    if not words or len(words) > 60000:
        return []
    numeric = re.compile(r"[-+($€£¥]?\d[\d,.%()−-]*")
    height = median(w["bottom"] - w["top"] for w in words)
    if height <= 0:
        return []
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > min(3, height * .35):
            lines.append([])
        lines[-1].append(word)

    def groups(line):
        result = []
        for word in sorted(line, key=lambda w: w["x0"]):
            if not result or word["x0"] - result[-1][-1]["x1"] > max(6, height * 1.2):
                result.append([])
            result[-1].append(word)
        return result

    def text(cell):
        return " ".join(w["text"] for w in cell)

    def bounds(cell):
        return [min(w["x0"] for w in cell), min(w["top"] for w in cell),
                max(w["x1"] for w in cell), max(w["bottom"] for w in cell)]

    rows = [groups(line) for line in lines]
    result = []
    cursor = 0
    while cursor < len(rows):
        start = cursor
        row = rows[start]
        columns = len(row)
        numeric_columns = {i for i, cell in enumerate(row) if numeric.fullmatch(text(cell))}
        if not 4 <= columns <= 32 or not 2 <= len(numeric_columns) < columns:
            cursor += 1
            continue
        first_boxes = [bounds(cell) for cell in row]
        end = start + 1
        while end < len(rows) and end - start < 500:
            candidate = rows[end]
            if len(candidate) != columns:
                break
            if lines[end][0]["top"] - lines[end-1][0]["top"] > height * 2.5:
                break
            if {i for i, cell in enumerate(candidate) if numeric.fullmatch(text(cell))} != numeric_columns:
                break
            boxes = [bounds(cell) for cell in candidate]
            if any(abs(b[2 if i in numeric_columns else 0] - first_boxes[i][2 if i in numeric_columns else 0]) > 2
                   for i, b in enumerate(boxes)):
                break
            end += 1
        cursor = max(start + 1, end)
        if end - start < 4:
            continue
        # A near adjacent partial data row is ambiguity, not a second table.
        if end < len(rows) and lines[end][0]["top"] - lines[end-1][0]["top"] <= height * 2.5:
            if len(rows[end]) >= 2 and any(numeric.fullmatch(text(c)) for c in rows[end]):
                continue
        boxes = [[bounds(cell) for cell in row] for row in rows[start:end]]
        lefts = [min(row[c][0] for row in boxes) for c in range(columns)]
        rights = [max(row[c][2] for row in boxes) for c in range(columns)]
        if any(rights[c] + 3 >= lefts[c+1] for c in range(columns-1)):
            continue
        edges = [lefts[0]] + [(rights[c] + lefts[c+1])/2 for c in range(columns-1)] + [rights[-1]]
        header = [[] for _ in range(columns)]
        header_start = start
        for index in range(start-1, max(-1, start-5), -1):
            if lines[start][0]["top"] - lines[index][0]["top"] > height * 4:
                break
            if any(numeric.fullmatch(text(cell)) for cell in rows[index]):
                break
            assigned = []
            for cell in rows[index]:
                b = bounds(cell)
                centre = (b[0] + b[2])/2
                matches = [c for c in range(columns) if edges[c] <= centre <= edges[c+1]]
                if len(matches) != 1:
                    break
                assigned.append((matches[0], cell))
            else:
                for c, cell in assigned:
                    header[c] = cell + header[c]
                header_start = index
                continue
            break
        if not all(header):
            continue
        # Headers may be wider than narrow numeric columns, but must still fit
        # without crossing the neighbouring column's actual text.
        lefts = [min(lefts[c], bounds(header[c])[0]) for c in range(columns)]
        rights = [max(rights[c], bounds(header[c])[2]) for c in range(columns)]
        if any(rights[c] + 2 >= lefts[c+1] for c in range(columns-1)):
            continue
        edges = [lefts[0]] + [(rights[c] + lefts[c+1])/2 for c in range(columns-1)] + [rights[-1]]
        header_lines = []
        for cell in header:
            parts = []
            for word in sorted(cell, key=lambda w: (w["top"], w["x0"])):
                if not parts or abs(word["top"] - parts[-1][0]["top"]) > min(3, height * .35):
                    parts.append([])
                parts[-1].append(word)
            header_lines.append(parts)
        header_rows = max(map(len, header_lines))
        if header_rows > 2:
            continue
        if header_rows == 2:
            split = [parts for parts in header_lines if len(parts) == 2]
            # Two levels need repeated baselines, not one accidentally wrapped
            # label. Single-line headings must be centred across those levels.
            tops = [median(parts[k][0]["top"] for parts in split) for k in (0, 1)]
            if (len(split) < 2 or tops[1] - tops[0] < height
                    or any(abs(parts[k][0]["top"] - tops[k]) > 2 for parts in split for k in (0, 1))
                    or any(abs(parts[0][0]["top"] - sum(tops)/2) > 2 for parts in header_lines if len(parts) == 1)):
                continue
        cells = []
        for col, parts in enumerate(header_lines):
            for row_index, cell in enumerate(parts):
                sizes = [c["size"] for w in cell for c in w.get("chars", [])]
                cells.append(dict(row=row_index, col=col,
                                  rowspan=header_rows if len(parts) == 1 else 1, colspan=1,
                                  text=text(cell), size=median(sizes) if sizes else height, header=True))
        for row_index, row in enumerate(rows[start:end], header_rows):
            for col, cell in enumerate(row):
                sizes = [c["size"] for w in cell for c in w.get("chars", [])]
                cells.append(dict(row=row_index, col=col, rowspan=1, colspan=1,
                                  text=text(cell), size=median(sizes) if sizes else height,
                                  header=False))
        result.append(dict(kind="table", rows=end-start+header_rows, cols=columns, cells=cells,
                           header_rows=header_rows,
                           bbox=[edges[0], min(w["top"] for w in lines[header_start]),
                                 edges[-1], max(w["bottom"] for w in lines[end-1])],
                           widths=[b-a for a, b in zip(edges, edges[1:])], source="native"))
    return result
