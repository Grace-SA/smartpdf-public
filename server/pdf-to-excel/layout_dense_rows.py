"""Experimental recovery of dense numeric rows inside coarsely ruled grids."""

from collections import Counter
from statistics import median
import math, re
from pdfplumber.utils import cluster_objects, extract_text


def recover(page):
    from layout_tables import physical_page

    # Default line-based table finding cannot create eight columns without
    # at least nine vertical source edge positions. Count the unfiltered edges
    # as an upper bound, before expensive glyph filtering; no snapping or
    # minimum-length test here can accidentally reduce that bound.
    vertical_positions = {e["x0"] for e in page.edges if e["orientation"] == "v"}
    if len(vertical_positions) < 9:
        return []
    page = physical_page(page)
    outputs = []
    for grid in page.find_tables():
        xs = [
            median(v)
            for v in cluster_objects(
                [x for cell in grid.cells for x in (cell[0], cell[2])], lambda x: x, 1
            )
        ]
        if (
            not 8 <= len(xs) - 1 <= 40
            or any(not math.isfinite(x) for x in xs)
            or any(b - a < 1 for a, b in zip(xs, xs[1:]))
        ):
            continue
        chars = [
            c
            for c in page.chars
            if grid.bbox[0] <= c["x0"] <= c["x1"] <= grid.bbox[2]
            and grid.bbox[1] <= c["top"] <= c["bottom"] <= grid.bbox[3]
            and c["text"].strip()
        ]
        if (
            not chars
            or len(chars) > 50000
            or any(
                not c.get("upright", True)
                or any(
                    not isinstance(c.get(k), (int, float)) or not math.isfinite(c[k])
                    for k in ["x0", "x1", "top", "bottom"]
                )
                for c in chars
            )
        ):
            continue
        h = median(c["bottom"] - c["top"] for c in chars)
        if not 2 <= h <= 50:
            continue
        groups = cluster_objects(chars, lambda c: c["bottom"], min(1, h * 0.2))
        lines = []

        def text(cc):
            return extract_text(cc, x_tolerance=1, y_tolerance=1) if cc else ""

        for group in groups:
            parts = [
                [c for c in group if a <= (c["x0"] + c["x1"]) / 2 < b]
                for a, b in zip(xs, xs[1:])
            ]
            values = [text(cc) for cc in parts]
            compact = all(
                all(
                    b["x0"] - a["x1"] <= h * 0.65
                    for a, b in zip(
                        sorted(cc, key=lambda c: c["x0"]),
                        sorted(cc, key=lambda c: c["x0"])[1:],
                    )
                )
                for cc in parts[1:]
            )
            dense = (
                compact
                and bool(values[0] and any(c.isalpha() for c in values[0]))
                and sum(
                    bool(re.fullmatch(r"[0-9]+(?:[,. ][0-9]+)*", v)) for v in values[1:]
                )
                >= len(values[1:]) * 0.65
                and all(
                    not v or re.fullmatch(r"[0-9]+(?:[,. ][0-9]+)*", v)
                    for v in values[1:]
                )
            )
            lines.append(
                dict(
                    chars=group,
                    parts=parts,
                    values=values,
                    dense=dense,
                    y=median(c["top"] for c in group),
                    bottom=median(c["bottom"] for c in group),
                )
            )
        dense = [i for i, l in enumerate(lines) if l["dense"]]
        if (
            len(dense) < 15
            or dense != list(range(dense[0], dense[-1] + 1))
            or dense[-1] != len(lines) - 1
        ):
            continue
        first, last = dense[0], dense[-1]
        body = lines[first : last + 1]
        gaps = [b["y"] - a["y"] for a, b in zip(body, body[1:])]
        pitch = median(gaps)
        if any(abs(g - pitch) > pitch * 0.15 for g in gaps) or pitch < h * 0.8:
            continue
        # Two complete header text rows immediately precede the repeated body.
        if first < 2:
            continue
        heads = lines[first - 2 : first]
        if (
            body[0]["y"] - heads[1]["y"] > pitch * 2
            or heads[1]["y"] - heads[0]["y"] > pitch * 2
        ):
            continue
        if (
            any(not v for v in heads[1]["values"])
            or sum(
                any(c.isdigit() for c in v) and not any(c.isalpha() for c in v)
                for v in heads[1]["values"]
            )
            > len(xs) * 0.2
        ):
            continue
        y = median((c["top"] + c["bottom"]) / 2 for c in heads[0]["chars"])
        vertical = [
            e
            for e in page.edges
            if e["orientation"] == "v" and e["top"] <= y <= e["bottom"]
        ]
        stops = [
            i for i, x in enumerate(xs) if any(abs(e["x0"] - x) < 1 for e in vertical)
        ]
        if not stops or stops[0] != 0 or stops[-1] != len(xs) - 1:
            continue
        cells = []
        occupied = set()
        valid = True
        for a, b in zip(stops, stops[1:]):
            cc = [
                c for c in heads[0]["chars"] if xs[a] <= (c["x0"] + c["x1"]) / 2 < xs[b]
            ]
            value = text(cc)
            if not value and b - a == 1:
                cells.append(dict(r=0, c=a, rs=2, cs=1, text=heads[1]["values"][a]))
                occupied.add(a)
            else:
                cells.append(dict(r=0, c=a, rs=1, cs=b - a, text=value))
        for col, value in enumerate(heads[1]["values"]):
            if col not in occupied:
                cells.append(dict(r=1, c=col, rs=1, cs=1, text=value))
        for r, row in enumerate(body, 2):
            for c, value in enumerate(row["values"]):
                cells.append(dict(r=r, c=c, rs=1, cs=1, text=value))
        original = Counter(
            "".join(
                c["text"]
                for l in heads + body
                for c in l["chars"]
                if not c["text"].isspace()
            )
        )
        recovered = Counter(
            "".join(c["text"] for c in cells).replace(" ", "").replace("\n", "")
        )
        if original != recovered:
            continue
        top = heads[0]["y"] - h * 0.5
        bottom = body[-1]["bottom"] + h * 0.25
        # Any additional text inside the recovered rectangle invalidates coverage.
        inside = [c for c in chars if top <= (c["top"] + c["bottom"]) / 2 <= bottom]
        if (
            Counter("".join(c["text"] for c in inside if not c["text"].isspace()))
            != original
        ):
            continue
        ys = (
            [
                top,
                (heads[0]["bottom"] + heads[1]["y"]) / 2,
                (heads[1]["bottom"] + body[0]["y"]) / 2,
            ]
            + [(a["bottom"] + b["y"]) / 2 for a, b in zip(body, body[1:])]
            + [bottom]
        )
        # Empty physical blocks retain their visible spans even though populated
        # coarse blocks above were split into individual repeated text records.
        for box in grid.cells:
            if box[1] < ys[2] - pitch * 0.3:
                continue
            if any(
                box[0] < (c["x0"] + c["x1"]) / 2 < box[2]
                and box[1] < (c["top"] + c["bottom"]) / 2 < box[3]
                for c in chars
            ):
                continue
            c0 = min(range(len(xs)), key=lambda i: abs(xs[i] - box[0]))
            c1 = min(range(len(xs)), key=lambda i: abs(xs[i] - box[2]))
            r0 = min(range(len(ys)), key=lambda i: abs(ys[i] - box[1]))
            r1 = min(range(len(ys)), key=lambda i: abs(ys[i] - box[3]))
            if (
                r0 < 2
                or r0 >= r1
                or c0 >= c1
                or max(abs(xs[c0] - box[0]), abs(xs[c1] - box[2])) > 1
                or max(abs(ys[r0] - box[1]), abs(ys[r1] - box[3])) > pitch * 0.3
            ):
                continue
            if (r1 - r0) * (c1 - c0) < 2:
                continue
            members = [c for c in cells if r0 <= c["r"] < r1 and c0 <= c["c"] < c1]
            if len(members) != (r1 - r0) * (c1 - c0) or any(
                c["text"] or c["rs"] != 1 or c["cs"] != 1 for c in members
            ):
                continue
            cells = [c for c in cells if c not in members] + [
                dict(r=r0, c=c0, rs=r1 - r0, cs=c1 - c0, text="")
            ]
        if (
            any(b <= a for a, b in zip(ys, ys[1:]))
            or (len(xs) - 1) * (len(ys) - 1) > 250000
        ):
            continue
        outputs.append(
            dict(
                widths=[b - a for a, b in zip(xs, xs[1:])],
                heights=[b - a for a, b in zip(ys, ys[1:])],
                cells=cells,
                bbox=[xs[0], top, xs[-1], bottom],
                headerRows=2,
                method="native-dense-rows",
                sourceGeometry=True,
            )
        )
    return outputs


def replace_fragments(existing, recovered):
    """Replace only fully contained fragments whose literal cells are preserved."""
    result = list(existing)
    for candidate in recovered:
        box = candidate["bbox"]
        overlapping = []
        valid = True
        normalized = lambda value: "".join(value.split())
        values = Counter(
            normalized(c["text"]) for c in candidate["cells"] if c["text"].strip()
        )
        for old in result:
            other = old.get("bbox")
            if other is None:
                valid = False
                break
            if min(box[2], other[2]) <= max(box[0], other[0]) or min(
                box[3], other[3]
            ) <= max(box[1], other[1]):
                continue
            if not (
                box[0] - 3 <= other[0] < other[2] <= box[2] + 3
                and box[1] - 3 <= other[1] < other[3] <= box[3] + 3
            ):
                valid = False
                break
            previous = Counter(
                normalized(c["text"]) for c in old["cells"] if c["text"].strip()
            )
            if previous - values:
                valid = False
                break
            overlapping.append(old)
        if valid:
            result = [
                t for t in result if not any(t is prior for prior in overlapping)
            ] + [candidate]
    return sorted(
        result, key=lambda t: (t.get("bbox", [0, 0])[1], t.get("bbox", [0, 0])[0])
    )
