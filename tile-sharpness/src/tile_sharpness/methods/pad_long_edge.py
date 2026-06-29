"""Isolated bright-pad long-edge geometry for the ABSOLUTE-MTF50 metric.

REPORT_taskAD established the failure modes of every wafer MTF target tried so
far: the groove scribe is a lit/shadow EMBOSS (specular over-read), bond-pad
"regions" are dense PERIODIC arrays (aliased over-read), the designed 4D bar is a
short lit/shadow emboss (over-reads sharp / floors shadow). The one thing not yet
properly tried is a clean ISOLATED LONG REFLECTANCE STEP.

Die 2B (atlas die type ``(2, 1)`` "horizontal_lines_plus_serpent") has TWO LARGE
BRIGHT rectangular metal pads in its centre. Their long top/bottom edges are
clean isolated reflectance steps (dark surround -> bright metal pad) — NOT a
groove (no second wall to glint), NOT periodic (unlike the flanking comb
gratings). The catch that defeated the prior slant-edge agent: a blind
Canny+Hough edge picker locks onto the dense comb gratings flanking the pads, not
the pad edge. FIX (this module): use the ATLAS to put a window on the die, find
the pad as the largest BRIGHT connected component, take ONE of its long
horizontal edges, and MASK the measurement window to a thin strip straddling only
that edge — so no grating competes.

The pad edge has the same ~5 deg grid tilt as everything else -> good slanted-edge
super-resolution. It is a SINGLE monotone step, so it is measured with
``slanted_edge.mtf50_long_edge`` (re-centred ISO-12233 long-edge estimator) and
cross-checked with ``mtf50_step_erf``.

ISOLATION GATE (the make-or-break for a clean ABSOLUTE read): a valid slanted
edge needs BOTH sides to asymptote to a constant within the window, i.e. clean
background on each side >= a few x the edge blur (PSF), with NO competing parallel
structure inside the half-window. This module measures, per chosen edge, the
clean-background distance to the nearest parallel structure on each side and
reports it so the caller can gate / pick an asymmetric window.

Pure geometry + OpenCV + numpy; no MTF here.
"""
from __future__ import annotations

import numpy as np

from .lsf import Segment


def _subpixel_peak(mag: np.ndarray, k: int) -> float:
    if k <= 0 or k >= len(mag) - 1:
        return 0.0
    denom = mag[k - 1] - 2 * mag[k] + mag[k + 1]
    if denom == 0:
        return 0.0
    return 0.5 * (mag[k - 1] - mag[k + 1]) / denom


def find_bright_pad(image_2d: np.ndarray, bbox: tuple[float, float, float, float],
                    *, min_area_frac: float = 0.012, max_area_frac: float = 0.55,
                    edge_touch_frac: float = 0.02, lstd_pct: float = 30.0,
                    int_pct: float = 45.0,
                    ) -> list[tuple[int, int, int, int]]:
    """The large UNIFORM metal pads inside ``bbox`` (image coords, the die's
    experimental block from the atlas), ranked by area (largest first).

    Returns a list of pixel bboxes ``(x0,y0,x1,y1)`` in image coords (possibly
    empty). The 2B pads are LARGE, LOW-LOCAL-VARIANCE (uniform metal) rectangles —
    distinct from the striped serpent/comb surround (high local variance) and the
    speckly bond-pad borders (very high variance + brightest). We detect them by
    LOCAL STD (uniformity) at a block-relative scale, not raw brightness (the
    brightest pixels are specular border glints, not the pad).

    Rejections: components below ``min_area_frac`` (specks / single comb teeth) or
    above ``max_area_frac`` (off-wafer background / the whole block — not a pad),
    thin shapes (``min(w,h)`` too small), and components hugging the block boundary
    (off-wafer mount or a cut-off pad — its edge is unreliable). Each surviving
    component is a candidate; the caller picks by isolation clearance.
    """
    import cv2
    H, W = image_2d.shape
    bx0, by0, bx1, by1 = (int(max(0, bbox[0])), int(max(0, bbox[1])),
                          int(min(W, bbox[2])), int(min(H, bbox[3])))
    bh, bw = by1 - by0, bx1 - bx0
    if bw < 40 or bh < 40:
        return []
    block = image_2d[by0:by1, bx0:bx1].astype(np.float32)
    # local std over a block-relative window (~5% of min dim) -> uniform = pad
    ws = max(5, (int(0.05 * min(bh, bw)) | 1))
    blur = cv2.blur(block, (ws, ws))
    sq = cv2.blur(block * block, (ws, ws))
    lstd = np.sqrt(np.maximum(sq - blur * blur, 0))
    # pad: low local std AND not the darkest (grooves can be uniformly dark too).
    # Use <= so a perfectly-uniform region (percentile==0) is still selected.
    uni = ((lstd <= np.percentile(lstd, lstd_pct)) & (block > np.percentile(block, int_pct))
           ).astype(np.uint8)
    kk = max(3, (ws // 2) | 1)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kk, kk))
    uni = cv2.morphologyEx(uni, cv2.MORPH_OPEN, k, iterations=1)
    uni = cv2.morphologyEx(uni, cv2.MORPH_CLOSE, k, iterations=2)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(uni, connectivity=8)
    block_area = block.size
    et_x, et_y = max(1, int(edge_touch_frac * bw)), max(1, int(edge_touch_frac * bh))
    out = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if not (min_area_frac * block_area <= area <= max_area_frac * block_area):
            continue
        L = stats[i, cv2.CC_STAT_LEFT]; T = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]; h = stats[i, cv2.CC_STAT_HEIGHT]
        if min(w, h) < max(15, 0.06 * min(bh, bw)):
            continue
        # reject components hugging the block boundary (off-wafer / cut-off)
        if L <= et_x or T <= et_y or (L + w) >= bw - et_x or (T + h) >= bh - et_y:
            continue
        out.append((area, bx0 + int(L), by0 + int(T), bx0 + int(L + w), by0 + int(T + h)))
    out.sort(reverse=True)
    return [(x0, y0, x1, y1) for _, x0, y0, x1, y1 in out]


def refine_pad_hedge(image_2d: np.ndarray, pad_bbox: tuple[int, int, int, int],
                     side: str = "top", *, pad: int = 30, search: int = 10,
                     inset_frac: float = 0.12, min_cols: int = 30,
                     max_off_axis_deg: float = 8.0
                     ) -> tuple[Segment, float] | None:
    """Locate one LONG HORIZONTAL edge of the bright pad to sub-pixel and fit a line.

    ``pad_bbox`` = pad pixel bbox (image coords) from ``find_bright_pad``.
    ``side`` = 'top' (dark surround above -> bright pad, RISING down-the-column) or
    'bottom' (bright pad -> dark surround below, FALLING). Per-column we find the
    sub-pixel vertical position of the steepest |gradient| near the pad edge, then
    fit a straight line and trim outliers. Returns ``(Segment, off_axis_deg)`` along
    the edge (left->right), or ``None`` if too short / too tilted / low-contrast.

    ``inset_frac`` trims the pad's left/right ends (corners are rounded / meet
    perpendicular edges) so we sample only the clean straight central span.
    """
    H, W = image_2d.shape
    px0, py0, px1, py1 = pad_bbox
    inset = int(inset_frac * (px1 - px0))
    cx0, cx1 = px0 + inset, px1 - inset
    if cx1 - cx0 < min_cols:
        return None
    if side == "top":
        ey = py0
        gy0, gy1 = max(0, ey - pad - search), min(H, ey + pad + search)
        want_rising = True          # dark(above)->bright(below): rising in +y
    else:
        ey = py1
        gy0, gy1 = max(0, ey - pad - search), min(H, ey + pad + search)
        want_rising = False         # bright(above)->dark(below): falling in +y
    pts = []
    for cx in range(cx0, cx1):
        col = image_2d[gy0:gy1, cx].astype(np.float32)
        if col.size < 6:
            continue
        gr = np.gradient(col)
        k = int(np.argmax(gr)) if want_rising else int(np.argmin(gr))
        if 1 <= k <= len(col) - 2:
            off = _subpixel_peak(np.abs(gr), k)
            pts.append((cx, gy0 + k + off))
    if len(pts) < min_cols:
        return None
    pts = np.array(pts)
    xs, ys = pts[:, 0], pts[:, 1]
    A = np.polyfit(xs, ys, 1)
    resid = ys - np.polyval(A, xs)
    keep = np.abs(resid) < 2.5 * (np.std(resid) + 1e-6)
    xs, ys = xs[keep], ys[keep]
    if xs.size < min_cols:
        return None
    A = np.polyfit(xs, ys, 1)
    off_axis = abs(np.degrees(np.arctan(A[0])))
    if off_axis > max_off_axis_deg:
        return None
    x_a, x_b = float(xs.min()), float(xs.max())
    seg = Segment(x0=x_a, y0=float(np.polyval(A, x_a)),
                  x1=x_b, y1=float(np.polyval(A, x_b)))
    return seg, off_axis


def perp_profile(image_2d: np.ndarray, seg: Segment, side: str, *,
                 half: float = 80.0, step: float = 0.5, n_along: int = 40,
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Along-edge-AVERAGED intensity vs signed perpendicular distance ``d`` (px):
    ``+d`` = OPEN (dark-surround) side, ``-d`` = INTO the pad. Averaging along the
    edge suppresses pixel noise so the clearance / specular-rim tests are robust."""
    L = seg.length_px
    if L < 8:
        return np.array([]), np.array([])
    ux, uy = (seg.x1 - seg.x0) / L, (seg.y1 - seg.y0) / L
    perpx, perpy = -uy, ux
    pad_sign = +1.0 if side == "top" else -1.0    # +perp points roughly toward the pad
    H, W = image_2d.shape
    ds = np.arange(-half, half + step, step)
    ts = np.linspace(0.2 * L, 0.8 * L, n_along)
    prof = np.full(ds.size, np.nan)
    for i, d in enumerate(ds):
        vals = []
        for t in ts:
            cx = seg.x0 + ux * t - pad_sign * perpx * d   # +d -> open side
            cy = seg.y0 + uy * t - pad_sign * perpy * d
            xi, yi = int(round(cx)), int(round(cy))
            if 0 <= xi < W and 0 <= yi < H:
                vals.append(image_2d[yi, xi])
        if vals:
            prof[i] = float(np.mean(vals))
    return ds, prof


def isolation_clearance(image_2d: np.ndarray, seg: Segment, pad_bbox: tuple[int, int, int, int],
                        side: str, *, probe_px: float = 80.0, n_along: int = 40,
                        ) -> tuple[float, float, bool]:
    """Clean-background clearance (px) on each side of the edge + a specular-rim flag.

    Returns ``(clear_pad_side, clear_open_side, specular_rim)``:
      * ``clear_pad_side`` — px into the bright pad before any interior structure
        (the pad core is uniform, so usually large);
      * ``clear_open_side`` — px into the dark surround before the next competing
        parallel structure (trace/line) brightens it back up — the LOAD-BEARING
        number: a valid slanted edge needs this >= a few x the edge PSF;
      * ``specular_rim`` — True if the open side shows a bright RIM right at the edge
        (a metal-bevel glint, the emboss failure mode) before the dark field.

    Uses the along-edge-averaged ``perp_profile``. The open-side field is "clean"
    while it stays near its near-edge dark level; clearance ends where it rises back
    above the midpoint between that dark level and the pad's bright level.
    """
    ds, prof = perp_profile(image_2d, seg, side, half=probe_px, n_along=n_along)
    if ds.size == 0 or np.all(np.isnan(prof)):
        return 0.0, 0.0, False
    zero = int(np.argmin(np.abs(ds)))
    pad_level = float(np.nanmedian(prof[max(0, zero - int(40 / 0.5)):zero]))   # deep pad side
    # dark level: minimum of the open side just past the edge
    open_idx = np.arange(zero, ds.size)
    open_vals = prof[open_idx]
    finite = open_idx[np.isfinite(open_vals)]
    if finite.size < 5:
        return 0.0, 0.0, False
    step = max(1e-6, float(ds[1] - ds[0]))
    dark_level = float(np.nanmin(prof[zero:zero + int(20 / step)]))
    mid = 0.5 * (dark_level + pad_level)
    # specular rim: a bright BUMP on the open side just past the edge transition —
    # the open-side intensity must first FALL to (near) the dark level, then RISE
    # back up by a clear fraction of the contrast, then fall again (a local peak),
    # all within ~2..12 px of the edge. A clean monotone step has no such bump.
    # Skip the immediate transition zone (>= ~2px past the midpoint).
    i_lo = zero + int(2.0 / step)
    i_hi = min(ds.size, zero + int(14.0 / step))
    specular = False
    if i_hi - i_lo >= 4:
        seg_open = prof[i_lo:i_hi]
        if np.isfinite(seg_open).sum() >= 4:
            local_min = float(np.nanmin(seg_open))
            local_max = float(np.nanmax(seg_open))
            k = int(np.nanargmax(seg_open))
            # a genuine rim: reached near-dark then bumped up, with the peak not at
            # the window's near end (which would just be the tail of the transition)
            rose = (local_max - local_min) > 0.30 * (pad_level - dark_level)
            settled_first = local_min < dark_level + 0.25 * (pad_level - dark_level)
            specular = bool(rose and settled_first and 0 < k < (i_hi - i_lo - 1))
    # open clearance: walk out until intensity exceeds mid (next structure)
    clear_open = probe_px
    for i in range(zero + int(3 / 0.5), ds.size):
        if np.isfinite(prof[i]) and prof[i] > mid:
            clear_open = float(ds[i])
            break
    # pad clearance: walk inward (-d) until intensity drops below mid
    clear_pad = probe_px
    for i in range(zero - int(3 / 0.5), -1, -1):
        if np.isfinite(prof[i]) and prof[i] < mid:
            clear_pad = float(-ds[i])
            break
    return clear_pad, clear_open, specular
