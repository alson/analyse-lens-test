"""Bond-pad-edge target selection for the true-reflectance-edge resolution metric.

REPORT_taskAD §E.4 established that the groove scribe specular-over-reads (a
groove is a lit/shadow emboss) while a TRUE reflectance edge reads <= the
diffraction ceiling. The single designed slanted-edge atlas feature reads a
non-discriminating ~0.10 cy/px and is sparse (1 of 16 die types). Bond-pad edges
(metal->substrate) are true reflectance edges catalogued in 14/16 die types, so
they give broad field coverage.

This module locates, for a registered sweep, the bond-pad region nearest each
field target and the longest straight CONTRAST edge inside it that is slanted
~2-15 deg off axis (good for slanted-edge super-resolution). The caller measures
MTF50 on the returned full-image ``Segment`` with
``slanted_edge.mtf50_step_erf`` at that position's best-focus shot.

Pure geometry + OpenCV; no MTF here so it stays test-light and reusable.
"""
from __future__ import annotations

import cv2
import numpy as np

from .lsf import Segment

IMAGE_W, IMAGE_H = 8256, 5504
SLANT_LO_DEG, SLANT_HI_DEG = 2.0, 15.0
MAX_TARGET_DIST_PX = 1700.0   # how far a pad region may be from a field target


def enumerate_bondpad_regions(p, atlas, grid_xy):
    """All in-FOV bond-pad regions for affine ``p``.

    ``grid_xy(col, row, u, v, p)`` -> (x, y) projector (handles radial term).
    Returns list of dicts: col,row,type,comp,bbox(x0,y0,x1,y1),cx,cy."""
    regions = []
    for col in range(0, 11):
        for row in range(0, 6):
            typ = f"({col % 4}, {row % 4})"
            dt = atlas["die_types"].get(typ, {})
            for ci, bp in enumerate(dt.get("feature_inventory", {}).get("bond_pads", [])):
                u0, v0, u1, v1 = bp["bbox_uv"]
                corners = [grid_xy(col, row, u, v, p)
                           for (u, v) in [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
                xs = [c[0] for c in corners]
                ys = [c[1] for c in corners]
                cx, cy = float(np.mean(xs)), float(np.mean(ys))
                m = 70
                if not (m < cx < IMAGE_W - m and m < cy < IMAGE_H - m):
                    continue
                if min(xs) < 0 or max(xs) >= IMAGE_W or min(ys) < 0 or max(ys) >= IMAGE_H:
                    continue
                regions.append(dict(col=col, row=row, type=typ, comp=ci,
                                    bbox=(float(min(xs)), float(min(ys)),
                                          float(max(xs)), float(max(ys))),
                                    cx=cx, cy=cy))
    return regions


def slanted_edge_candidates(patch, ox, oy, *, slant_lo=SLANT_LO_DEG, slant_hi=SLANT_HI_DEG,
                            min_len_frac=0.30, max_candidates=12):
    """All straight CONTRAST edges in ``patch`` slanted ``slant_lo..slant_hi`` deg off
    the NEAREST axis, longest first. Returns ``[(Segment, off_axis_deg, length_px)]``
    in FULL-image coords (offset by ``ox,oy``).

    A bond-pad region is a periodic grid; the single longest Hough line is often
    internal structure (a bright trace ridge / a pad-row edge), NOT a clean
    metal->substrate step. So we return MULTIPLE candidates and let the caller pick
    the longest one whose ESF passes the single-step quality gate."""
    patch = np.ascontiguousarray(patch, dtype=np.uint8)
    if min(patch.shape) < 16:
        return []
    p = cv2.GaussianBlur(patch, (3, 3), 0)
    edges = cv2.Canny(p, 40, 120)
    minlen = max(20, int(min_len_frac * min(patch.shape)))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180.0, threshold=40,
                            minLineLength=minlen, maxLineGap=8)
    if lines is None:
        return []
    cands = []
    for ln in lines:
        x0, y0, x1, y1 = (float(v) for v in ln[0])
        L = float(np.hypot(x1 - x0, y1 - y0))
        ang = np.degrees(np.arctan2(y1 - y0, x1 - x0)) % 180.0
        off = min(ang, abs(ang - 90.0), abs(ang - 180.0))   # off nearest axis
        if not (slant_lo <= off <= slant_hi):
            continue
        cands.append((Segment(x0=x0 + ox, y0=y0 + oy, x1=x1 + ox, y1=y1 + oy), off, L))
    cands.sort(key=lambda c: -c[2])
    return cands[:max_candidates]


def longest_slanted_edge(patch, ox, oy, **kw):
    """Back-compat: the single longest slanted contrast edge, or ``None``."""
    cands = slanted_edge_candidates(patch, ox, oy, **kw)
    return cands[0] if cands else None


def pick_padedge_targets(p, atlas, grid_xy, field_targets, detect_image,
                         *, pad_px=25, max_dist_px=MAX_TARGET_DIST_PX,
                         max_regions_per_target=8, accept=None):
    """For each field target (name -> (fx,fy) image fractions), find the best
    bond-pad-edge target: the longest slanted CONTRAST edge, near that target, that
    is a GENUINE single reflectance step (not the periodic pad-array structure /
    a bright-trace ridge / noise).

    ``detect_image`` is a single grayscale frame used to detect edge geometry AND
    to gate candidates (a reasonably-focused mid-stack shot; the affine fixes
    location, focus is refined later by the caller).

    ``accept(image, seg) -> bool`` validates a candidate as a clean step (e.g.
    ``lambda im, s: mtf50_step_erf(im, s) is not None`` — the quality gate). If
    ``None``, the first geometric candidate is taken (legacy behaviour). Scanning
    candidates with the gate is what makes pad edges usable: it skips the array's
    internal structure and locks onto the pad-field / die boundary.

    Returns ``{name: (region, Segment, off_deg, length_px)}`` for targets that
    found an accepted edge."""
    regions = enumerate_bondpad_regions(p, atlas, grid_xy)
    out = {}
    H, W = detect_image.shape
    detf = detect_image.astype(np.float32)
    for name, (fx, fy) in field_targets.items():
        tx, ty = fx * IMAGE_W, fy * IMAGE_H
        near = sorted(regions, key=lambda r: np.hypot(r["cx"] - tx, r["cy"] - ty))
        picked = None
        for r in near[:max_regions_per_target]:
            if np.hypot(r["cx"] - tx, r["cy"] - ty) > max_dist_px:
                break
            x0, y0, x1, y1 = (int(v) for v in r["bbox"])
            gx0, gy0 = max(0, x0 - pad_px), max(0, y0 - pad_px)
            gx1, gy1 = min(W, x1 + pad_px), min(H, y1 + pad_px)
            patch = detect_image[gy0:gy1, gx0:gx1]
            if patch.size == 0 or min(patch.shape) < 16:
                continue
            cands = slanted_edge_candidates(patch, gx0, gy0)
            for seg, off, L in cands:
                if accept is None or accept(detf, seg):
                    picked = (r, seg, off, L)
                    break
            if picked is not None:
                break
        if picked is not None:
            out[name] = picked
    return out
