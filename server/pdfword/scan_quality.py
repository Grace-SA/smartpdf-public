"""Conservative illumination correction for monochrome document scans."""


def enhance(image):
    import cv2
    import numpy as np

    if image.ndim != 3 or image.shape[2] != 3:
        return image, {"enhanced": False}
    # Preserve photographs, coloured diagrams and clean pages unchanged.
    spread = image.max(axis=2) - image.min(axis=2)
    if np.mean(spread > 25) > 0.02:
        return image, {"enhanced": False}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Binary/high-contrast scans contain no recoverable illumination gradient.
    # Their black borders and halftone photos must not become a paper estimate.
    if np.mean((gray > 24) & (gray < 232)) < 0.05:
        return image, {"enhanced": False}
    factor = min(1, 1000 / max(gray.shape))
    small = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    background = cv2.morphologyEx(small, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    variation = float(np.percentile(background, 90) - np.percentile(background, 10))
    ink = float(np.mean(small.astype(float) < background.astype(float) - 25))
    if np.percentile(background, 10) < 96 or variation < 20 or not 0.005 < ink < 0.25:
        return image, {"enhanced": False}
    background = cv2.GaussianBlur(background, (25, 25), 0)
    background = cv2.resize(
        background, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR
    )
    # Division preserves gray stroke edges; do not binarise faint characters.
    corrected = np.clip(
        gray.astype(np.float32) * 245 / np.maximum(background, 32), 0, 255
    ).astype(np.uint8)
    return cv2.cvtColor(corrected, cv2.COLOR_GRAY2BGR), {
        "enhanced": True,
        "background_variation": round(variation, 2),
        "ink_fraction": round(ink, 4),
    }
