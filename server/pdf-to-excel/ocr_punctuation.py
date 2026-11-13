"""Resolve only a period/hyphen OCR tie with a separately visible ink component."""

import math
from statistics import median
import cv2


def resolve(image, fields):
    for field in fields:
        options = field.get("ambiguousValues", [])
        if (
            field.get("failure") != "ambiguous-consensus"
            or field.get("kind") != "label"
            or len(options) != 2
        ):
            continue
        compact = ["".join(value.split()) for value in options]
        if (
            len(compact[0]) != len(compact[1])
            or sum(ch.isalpha() for ch in compact[0]) < 5
        ):
            continue
        changed = [i for i, (a, b) in enumerate(zip(*compact)) if a != b]
        if len(changed) != 1 or {compact[0][changed[0]], compact[1][changed[0]]} != {
            ".",
            "-",
        }:
            continue
        x0, y0, x1, y1 = field["box"]
        crop = image[
            max(0, math.floor(y0)) : min(image.shape[0], math.ceil(y1)),
            max(0, math.floor(x0)) : min(image.shape[1], math.ceil(x1)),
        ]
        if not crop.size:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        _, _, stats, _ = cv2.connectedComponentsWithStats(ink)
        parts = sorted(stats[1:].tolist(), key=lambda p: p[0])
        if len(parts) != len(compact[0]):
            continue
        index = changed[0]
        letters = [p for i, p in enumerate(parts) if compact[0][i].isalpha()]
        top = median(p[1] for p in letters)
        height = median(p[3] for p in letters)
        if height < 8 or any(abs(p[3] - height) > height * 0.25 for p in letters):
            continue
        x, y, width, h, _ = parts[index]
        center = (y + h / 2 - top) / height
        mark = None
        if (
            height * 0.2 <= width <= height * 0.8
            and h <= height * 0.25
            and width >= h * 1.5
            and 0.3 <= center <= 0.7
        ):
            mark = "-"
        elif (
            width <= height * 0.25
            and h <= height * 0.25
            and 0.7 <= width / h <= 1.4
            and 0.8 <= center <= 1.1
        ):
            mark = "."
        if mark is None:
            continue
        value = next(
            option
            for option, letters in zip(options, compact)
            if letters[index] == mark
        )
        scores = [
            float(entry[1])
            for entry in field.get("alternatives", [])
            if " ".join(entry[0].split()) == value and entry[1] >= 0.95
        ]
        if len(scores) < 2:
            continue
        field.update(
            text=value,
            confidence=min(scores),
            refinement="isolated-punctuation-geometry",
        )
        field.pop("failure", None)
