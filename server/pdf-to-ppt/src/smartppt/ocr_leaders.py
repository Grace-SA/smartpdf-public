"""Keep proven trailing dot leaders out of upright CJK text fitting/erasure."""
from copy import deepcopy
import numpy as np
from .consensus import erase_bounds
from .partial_consensus import cjk


def trim_dot_leaders(image, lines):
    """Shrink at an empty stripe, only after a repeated external guide proves it.

    Text and source records are never changed. One recognized terminal period
    is retained. Numeric/other punctuation endings, skew, short sequences and
    unproven geometry cannot authorize trimming.
    A proven guide inside the erase box with no safe divider stays raster.
    """
    refined = deepcopy(lines); changed = []; ambiguous = []; verified = []
    pixels = np.asarray(image)
    for index, line in enumerate(refined):
        text = line['text'].rstrip(); p = line['polygon']
        # An explicitly recognized final period is text, even when it belongs
        # to a guide visually. Preserve that dot; never strip punctuation.
        keep = int(text.endswith('.'))
        stem = text[:-1].rstrip() if keep else text
        if len(stem) < 4 or not cjk(stem[-1]):
            continue
        if not (p[0][1] == p[1][1] and p[2][1] == p[3][1] and
                p[0][0] == p[3][0] and p[1][0] == p[2][0] and
                p[0][0] < p[1][0] and p[0][1] < p[3][1]):
            continue
        l, t, r, b = erase_bounds(line); height = b-t
        if l < 0 or t < 0 or r > pixels.shape[1] or b > pixels.shape[0] or height < 8 or r-l < height:
            continue
        start = max(l, r-2*height); end = min(pixels.shape[1], r+10*height)
        strip = pixels[t:b, start:end].astype(float)
        paper = np.median(strip.reshape(-1, 3), axis=0)
        if paper.min() < 180:
            continue
        mask = np.max(np.abs(strip-paper), axis=2) > 30
        padded = np.pad(mask.astype(np.uint8), 1)
        neighbors = sum(padded[y:y+mask.shape[0], x:x+mask.shape[1]] for y in range(3) for x in range(3))
        mask &= neighbors >= 3
        columns = np.flatnonzero(mask.any(axis=0))
        if not len(columns):
            continue
        segments = []
        for group in np.split(columns, np.flatnonzero(np.diff(columns) > 1)+1):
            left, right = int(group[0]), int(group[-1])+1
            ink = np.argwhere(mask[:, left:right])
            top, bottom = int(ink[:, 0].min()), int(ink[:, 0].max())+1
            segments.append((start+left, start+right, top, bottom))

        def dot(s):
            return s[1]-s[0] <= height*.25 and s[3]-s[2] <= height*.25

        seed = None
        for n in range(len(segments)-5):
            group = segments[n:n+6]
            if group[0][0] < r or not all(dot(s) for s in group):
                continue
            centers = [(s[0]+s[1])/2 for s in group]
            pitch = float(np.median(np.diff(centers)))
            cy = float(np.median([(s[2]+s[3])/2 for s in group]))
            if (not max(s[1]-s[0] for s in group)+1 <= pitch <= height*.65 or
                    any(abs(d-pitch) > max(1, pitch*.15) for d in np.diff(centers)) or
                    any(abs((s[2]+s[3])/2-cy) > max(1, height*.06) for s in group)):
                continue
            seed = n, pitch, cy
            break
        if seed is None:
            continue
        first, pitch, cy = seed
        while first:
            previous, current = segments[first-1], segments[first]
            gap = (current[0]+current[1]-previous[0]-previous[1])/2
            if (not dot(previous) or abs(gap-pitch) > max(1, pitch*.15) or
                    abs((previous[2]+previous[3])/2-cy) > max(1, height*.06)):
                break
            first -= 1
        if not first or segments[first-1][3]-segments[first-1][2] < height*.45:
            if segments[first][0] < r:ambiguous.append(index)
            continue
        # A faint leading dot can fall below the segmentation threshold. Do
        # not count the next strong dot as the recognized terminal period.
        first_dot = segments[first]
        ghost_left = int(np.floor(first_dot[0]-pitch))-1
        ghost_right = int(np.ceil(first_dot[1]-pitch))+1
        if ghost_left > segments[first-1][1]:
            ghost = pixels[t+max(0,first_dot[2]-1):t+min(height,first_dot[3]+1),ghost_left:ghost_right].astype(float)
            faint = np.max(np.abs(ghost-paper),axis=2)>12
            coherent = (any(faint[y:y+2,x:x+2].sum() >= 3 for y in range(faint.shape[0]-1) for x in range(faint.shape[1]-1)) or
                        np.any(faint[:,:-2] & faint[:,1:-1] & faint[:,2:]) or
                        np.any(faint[:-2,:] & faint[1:-1,:] & faint[2:,:]))
            if coherent:
                ambiguous.append(index)
                continue
        left, right = segments[first+keep-1][1], segments[first+keep][0]
        cuts = [cut for cut in range(left, right)
                if 0 <= r-cut <= height and cut-l >= height and
                np.max(np.abs(pixels[t:b, cut:cut+1].astype(float)-paper)) <= 12]
        if not cuts:
            if segments[first][0] < r:ambiguous.append(index)
            continue
        cut = min(cuts, key=lambda x: abs(x-(left+right)/2))
        verified.append(index)
        if cut == r:
            continue
        # erase_bounds adds a pixel: keep its exclusive right edge in the gap.
        p[1][0] = p[2][0] = cut-1
        changed.append(index)
    return refined, changed, ambiguous, verified
