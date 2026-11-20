"""Conservative geometric column bands; unsupported layouts keep editable flow."""


def gutter_cuts(body, width, count):
    """Infer clear gutters when unequal outer margins shift the column bands."""
    candidates = [b for b in body if b["kind"] in {"paragraph", "list"}
                  and 0 < b["bbox"][2] - b["bbox"][0] < width / count * 1.35]
    groups = []
    for block in sorted(candidates, key=lambda b: b["bbox"][0]):
        left, _, right, _ = block["bbox"]
        if groups and left - groups[-1][1] < 18:
            groups[-1][1] = max(groups[-1][1], right)
            groups[-1][2] += 1
        else:
            groups.append([left, right, 1])
    if len(groups) != count or any(n < 2 for _, _, n in groups):
        return None
    # Short labels and dates form aligned records, not independent prose columns.
    if any(sum(len(b.get("text", "").strip()) for b in candidates
               if left <= b["bbox"][0] and b["bbox"][2] <= right) < 80
           for left, right, _ in groups):
        return None
    return [(a[1] + b[0]) / 2 for a, b in zip(groups, groups[1:])]


def column_flow(blocks, width):
    if any(b.get("static_form") for b in blocks):
        return blocks
    body = [b for b in blocks if b["kind"] not in ("header", "footer")]
    if len(body) < 4:
        return blocks
    candidates = []
    proven = next((b["native_columns"] for b in body if b.get("native_columns")), None)
    if proven and len(proven) == 2 and 0 < proven[0] < proven[1] < width:
        candidates.append((3, proven, 6))
    for count in (3, 2):
        candidates.append((count, [width * i / count for i in range(1, count)], 18))
        inferred = gutter_cuts(body, width, count)
        if inferred:
            candidates.append((count, inferred, 18))
    for count, cuts, minimum_gap in candidates:

        def column(block):
            left, _, right, _ = block["bbox"]
            if any(left < c < right for c in cuts):
                return None
            return sum(left >= c for c in cuts)

        wide = sorted(
            [b for b in body if column(b) is None], key=lambda b: b["bbox"][1]
        )
        bands = []
        pending = list(body)
        for block in wide:
            # A full-width element overlapping column text is not a safe section cut.
            overlaps = [b for b in pending if b is not block
                        and column(b) is not None
                        and b["bbox"][1] < block["bbox"][3]
                        and b["bbox"][3] > block["bbox"][1]]
            if overlaps:
                header = [block] + overlaps
                if (proven and all(b["kind"] in ("paragraph", "heading")
                        and b["bbox"][3] <= width*.12
                        and b["bbox"][3]-b["bbox"][1] <= 24
                        and len(b.get("text", "")) <= 160 for b in header)):
                    header.sort(key=lambda b:b["bbox"][0])
                    if any(a["bbox"][2] > b["bbox"][0] for a,b in zip(header,header[1:])):
                        bands=[]
                        break
                    before=[b for b in pending if b["bbox"][3] <= block["bbox"][1]]
                    if before:bands.append(before)
                    bands.append([dict(kind="form_row",items=header,bbox=[
                        min(b["bbox"][0] for b in header),min(b["bbox"][1] for b in header),
                        max(b["bbox"][2] for b in header),max(b["bbox"][3] for b in header)])])
                    pending=[b for b in pending if b not in header and b not in before]
                    continue
                bands = []
                break
            before = [b for b in pending if b["bbox"][3] <= block["bbox"][1]]
            if before:
                bands.append(before)
            bands.append([block])
            pending = [b for b in pending if b is not block and b not in before]
        else:
            if pending:
                bands.append(pending)
        if not bands:
            continue
        planned = []
        changed = False
        for band in bands:
            columns = [[b for b in band if column(b) == i] for i in range(count)]
            valid = all(len(col) >= 2 for col in columns) and sum(
                map(len, columns)
            ) == len(band)
            if valid:
                ranges = [
                    (min(b["bbox"][0] for b in col), max(b["bbox"][2] for b in col))
                    for col in columns
                ]
                valid = all(a[1] + minimum_gap <= b[0] for a, b in zip(ranges, ranges[1:]))
                valid = (
                    valid
                    and min(max(b["bbox"][3] for b in col) for col in columns)
                    - max(min(b["bbox"][1] for b in col) for col in columns)
                    > 10
                )
            if valid:
                changed = True
                planned.append(
                    dict(
                        kind="columns_start",
                        count=count,
                        widths=[b - a for a, b in ranges],
                    )
                )
                for index, col in enumerate(columns):
                    if index:
                        planned.append(dict(kind="column_break"))
                    planned.extend(
                        sorted(col, key=lambda b: (b["bbox"][1], b["bbox"][0]))
                    )
                planned.append(dict(kind="columns_end"))
            else:
                planned.extend(band)
        if changed:
            return [b for b in blocks if b["kind"] in ("header", "footer")] + planned
    return blocks
