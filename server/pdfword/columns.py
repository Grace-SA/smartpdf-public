"""Conservative geometric column bands; unsupported layouts keep editable flow."""


from bisect import bisect_left


def independent_baselines(groups):
    """Require independently wrapping text, not uniform paired table rows."""
    tops = [sorted(set(round(y, 1) for y in group)) for group in groups]
    if len(tops) != 2:
        return False
    for own, other in (tops, tops[::-1]):
        independent = 0
        for value in own:
            index = bisect_left(other, value)
            if all(abs(value - neighbour) > 3 for neighbour in other[max(0,index-1):index+1]):
                independent += 1
        if independent < max(3, len(own) * 0.25):
            return False
    return True


def column_flow(blocks, width):
    body = [b for b in blocks if b["kind"] not in ("header", "footer")]
    if len(body) < 4:
        return blocks
    for count in (3, 2):
        cuts = [width * i / count for i in range(1, count)]

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
            if any(
                b is not block
                and column(b) is not None
                and b["bbox"][1] < block["bbox"][3]
                and b["bbox"][3] > block["bbox"][1]
                for b in pending
            ):
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
                # A narrow but persistent gutter is safe only for substantial prose
                # columns; compact grids retain the conservative 18pt threshold.
                prose = all(sum(len(b.get("text", "")) for b in col
                                if b["kind"] in ("paragraph", "list")) >= 160
                            and len(col) >= 4 for col in columns)
                prose = prose and independent_baselines(
                    [[b["bbox"][1] for b in col] for col in columns])
                gap = 2 if prose and count == 2 else 18
                valid = all(a[1] + gap <= b[0] for a, b in zip(ranges, ranges[1:]))
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

