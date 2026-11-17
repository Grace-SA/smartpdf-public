"""Restore a collapsed header separator above one physically merged text row."""


def recover(model, native):
    from layout_partition import valid_box
    from layout_tables import overlap

    cols = len(model.get("widths", []))
    if (
        len(model.get("heights", [])) != 2
        or not 2 <= cols <= 30
        or not valid_box(model.get("bbox"))
    ):
        return model

    def content(table, count, *, physical):
        cells = table.get("cells", [])
        occupied = set()
        for cell in cells:
            values = [cell.get(k) for k in ("r", "c", "rs", "cs")]
            if any(type(v) is not int for v in values):
                return None
            r, c, rs, cs = values
            if not (r in (0, 1) and rs == 1 and 0 <= c < c + cs <= count):
                return None
            area = {(r, x) for x in range(c, c + cs)}
            if occupied & area or not isinstance(cell.get("text"), str):
                return None
            occupied.update(area)
        headers = sorted((c for c in cells if c["r"] == 0), key=lambda c: c["c"])
        body = [c for c in cells if c["r"] == 1 and c["text"].strip()]
        if (
            len(headers) != count
            or any(c["cs"] != 1 or not c["text"].strip() for c in headers)
            or len(body) != 1
            or body[0]["c"] != 0
            or not any(ch.isalpha() for ch in body[0]["text"])
            or any(ch.isdigit() for ch in body[0]["text"])
        ):
            return None
        if physical and (
            len(cells) != count + 1
            or body[0]["cs"] != count
            or len(occupied) != 2 * count
        ):
            return None
        return (
            [word for c in headers for word in c["text"].split()],
            body[0]["text"].split(),
        )

    before = content(model, cols, physical=False)
    if before is None:
        return model
    matches = [
        t
        for t in native
        if t.get("closedGrid")
        and len(t.get("heights", [])) == 2
        and len(t.get("widths", [])) == cols + 1
        and valid_box(t.get("bbox"))
        and overlap(model["bbox"], t["bbox"]) >= 0.9
        and max(abs(a - b) for a, b in zip(model["bbox"], t["bbox"])) <= 3
        and content(t, cols + 1, physical=True) == before
    ]
    return matches[0] if len(matches) == 1 else model
