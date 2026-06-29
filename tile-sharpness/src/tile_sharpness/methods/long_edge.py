"""Long-isolated-edge target geometry for the absolute-MTF50 metric.

REPORT_taskAD §E.4/§F established: the groove scribe specular-over-reads (it is a
lit/shadow emboss), and bond-pad "regions" are dense PERIODIC arrays whose longest
internal contrast edge is an aliased pad-row edge that also over-reads. The single
*designed* slanted-edge atlas feature (die (0,3), the dark vertical bar) reads
<= ceiling but was reported as a non-discriminating ~0.10 cy/px floor — measured
through a SMALL bbox.

This module tests the height/length hypothesis: that the floor is a SHORT-edge
artefact (too few rows starve the super-resolved ESF), not an intrinsic limit. It
locates the dark bar's actual long vertical edges to sub-pixel and returns a
``Segment`` along the full edge (or a centred sub-segment of a requested length, to
sweep MTF50 vs edge-length). Pure geometry + OpenCV; no MTF here.

The edge is a SINGLE monotone reflectance step (background -> dark metal bar), so it
is measured with ``slanted_edge.mtf50_step_erf`` (single erf), NOT the two-wall
groove path.
"""
from __future__ import annotations

import numpy as np

from .lsf import Segment


def _subpixel_peak(mag: np.ndarray, k: int) -> float:
    """Parabolic sub-pixel offset of a peak at index ``k`` in ``mag``."""
    if k <= 0 or k >= len(mag) - 1:
        return 0.0
    denom = mag[k - 1] - 2 * mag[k] + mag[k + 1]
    if denom == 0:
        return 0.0
    return 0.5 * (mag[k - 1] - mag[k + 1]) / denom


def refine_bar_edge(image_2d: np.ndarray, bbox: tuple[float, float, float, float],
                    side: str = "left", *, pad: int = 35, search: int = 8,
                    min_rows: int = 20, max_off_axis_deg: float = 6.0
                    ) -> tuple[Segment, float] | None:
    """Locate one vertical edge of the dark bar inside ``bbox`` (image coords) to
    sub-pixel and fit a straight line through the per-row edge points.

    ``bbox`` = (x0,y0,x1,y1) approximate bar location (from atlas registration).
    ``side`` = 'left' (bg->dark, falling) or 'right' (dark->bg, rising).
    Returns ``(Segment, off_axis_deg)`` spanning the full detected edge, or ``None``
    if the edge is too short, too tilted (likely a misdetection), or low-contrast.
    """
    H, W = image_2d.shape
    x0, y0, x1, y1 = bbox
    gx0, gy0 = max(0, int(x0 - pad)), max(0, int(y0 - pad))
    gx1, gy1 = min(W, int(x1 + pad)), min(H, int(y1 + pad))
    patch = image_2d[gy0:gy1, gx0:gx1].astype(np.float32)
    ph, pw = patch.shape
    if ph < min_rows or pw < 8:
        return None
    colmean = patch.mean(axis=0)
    thr = (colmean.max() + colmean.min()) / 2.0
    dark = np.where(colmean < thr)[0]
    if dark.size < 4:
        return None
    bxl, bxr = int(dark.min()), int(dark.max())
    pts = []
    for ry in range(ph):
        row = patch[ry]
        if side == "left":
            lo, hi = max(0, bxl - search), min(pw - 1, bxl + search)
            seg = row[lo:hi + 1]
            gr = np.gradient(seg)
            k = int(np.argmin(gr))          # falling
        else:
            lo, hi = max(0, bxr - search), min(pw - 1, bxr + search)
            seg = row[lo:hi + 1]
            gr = np.gradient(seg)
            k = int(np.argmax(gr))          # rising
        if 1 <= k <= len(seg) - 2:
            off = _subpixel_peak(np.abs(gr), k)
            pts.append((lo + k + off + gx0, ry + gy0))
    if len(pts) < min_rows:
        return None
    pts = np.array(pts)
    ys, xs = pts[:, 1], pts[:, 0]
    A = np.polyfit(ys, xs, 1)
    resid = xs - np.polyval(A, ys)
    keep = np.abs(resid) < 2.5 * (np.std(resid) + 1e-6)
    ys, xs = ys[keep], xs[keep]
    if ys.size < min_rows:
        return None
    A = np.polyfit(ys, xs, 1)
    off_axis = abs(np.degrees(np.arctan(A[0])))
    if off_axis > max_off_axis_deg:
        return None
    y_a, y_b = float(ys.min()), float(ys.max())
    seg = Segment(x0=float(np.polyval(A, y_a)), y0=y_a,
                  x1=float(np.polyval(A, y_b)), y1=y_b)
    return seg, off_axis


def subsegment(seg: Segment, length_px: float) -> Segment:
    """Centred sub-segment of ``seg`` with the requested length (clamped to the
    full length). Used to sweep MTF50 vs edge-length (the height hypothesis)."""
    L = seg.length_px
    length_px = min(length_px, L)
    if L <= 0:
        return seg
    ux, uy = (seg.x1 - seg.x0) / L, (seg.y1 - seg.y0) / L
    cx, cy = 0.5 * (seg.x0 + seg.x1), 0.5 * (seg.y0 + seg.y1)
    h = length_px / 2.0
    return Segment(x0=cx - ux * h, y0=cy - uy * h, x1=cx + ux * h, y1=cy + uy * h)
