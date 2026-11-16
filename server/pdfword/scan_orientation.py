"""Conservative protection against uncertain quarter-turns of horizontal text."""
import math


def line_axis(image):
    import cv2
    import numpy as np

    if image.ndim != 3 or image.shape[2] != 3:
        return None
    scale = min(1, 1400 / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if np.mean(small.max(axis=2) - small.min(axis=2) > 25) > .02:
        return None
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if count > 50000:
        return None
    height, width = gray.shape
    keep = np.zeros(count, dtype=bool)
    for index, (_, _, w, h, area) in enumerate(stats[1:], 1):
        # Exclude rules, borders and large figure components from text evidence.
        keep[index] = (area >= 6 and w >= 2 and h >= 3
                       and w < width * .3 and h < height * .3
                       and max(w / h, h / w) < 12)
    if np.count_nonzero(keep) < 30:
        return None
    mask = keep[labels]
    fraction = float(mask.mean())
    if not .005 < fraction < .35:
        return None
    rows, columns = mask.mean(axis=1), mask.mean(axis=0)
    horizontal = float(np.mean(rows ** 2) / fraction ** 2)
    vertical = float(np.mean(columns ** 2) / fraction ** 2)
    return dict(horizontal_ratio=horizontal / vertical,
                components=int(np.count_nonzero(keep)), ink_fraction=fraction)


def guarded_angle(angle, confidence, evidence):
    if angle not in (0, 90, 180, 270) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("Invalid orientation prediction")
    # Do not infer upside-down direction from line geometry. Strong model
    # predictions and pages without clear text-line evidence retain normal routing.
    rejected = bool(angle in (90, 270) and confidence < .9 and evidence
                    and (evidence["horizontal_ratio"] >= 2
                         or (confidence < .5 and evidence["horizontal_ratio"] >= 1.5)))
    return (0 if rejected else angle), rejected


def rotate_quarter(image, angle):
    import numpy as np

    if angle not in (0, 90, 180, 270):
        raise ValueError("Invalid right-angle rotation")
    # Right-angle rotations need no interpolation, border fill or pixel loss.
    return np.rot90(image, angle // 90).copy() if angle else image
