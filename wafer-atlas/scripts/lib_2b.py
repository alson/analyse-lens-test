"""Shared helpers for the 2B flat serpent/line MTF routes.

Registration (reg_auto), 2B-die location by appearance, de-rotated experimental
block extraction. Used by both Route-1 (harmonic-decay) and Route-2 (flat-edge)
drivers so geometry is computed once and identically.
"""
from __future__ import annotations
import importlib.util, json
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
WA = HERE.parent
ROOT = WA.parent
import sys
sys.path.insert(0, str(ROOT / "tile-sharpness" / "src"))
from tile_sharpness.methods import periodic_fft as pf  # noqa: E402

RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
M_ANCHOR_SCALE = 1.6549
LPMM_PER_CYPX = 1000.0 / 4.35           # 229.9
EXP_BBOX_UV = (0.0, 0.266, 0.999, 0.881)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


reg_auto = _load("reg_auto")


def central_lapvar(g):
    c = g[IMAGE_H // 2 - 800:IMAGE_H // 2 + 800, IMAGE_W // 2 - 800:IMAGE_W // 2 + 800]
    return cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var()


def register_best(ap_dir, n_sharp=5):
    """Robust registration: register the sharpest few + a spread, keep min residual.
    Returns (rmse, affine, jp_path, all_jpgs) or (None, None, None, jpgs)."""
    jpgs = sorted(Path(ap_dir).glob("*.jpg"))
    if not jpgs:
        return None, None, None, []
    lv = []
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((central_lapvar(g) if g is not None else -1, jp))
    lv.sort(reverse=True)
    cand = [j for _, j in lv[:n_sharp]] + [jpgs[int(len(jpgs) * f)] for f in (0.35, 0.5, 0.65)]
    best = None
    for jp in dict.fromkeys(cand):
        try:
            p = reg_auto.register_and_refine("d", path=str(jp), anchors=None)
        except Exception:
            continue
        if p is None or not p.get("n_refine_intersections"):
            continue
        r = p["reg_fit_rmse_px"]
        # sanity: scale-collapse guard (REPORT §A.2) + residual ceiling
        M = p["scale"] / M_ANCHOR_SCALE
        if not (0.15 < M < 3.5) or r > 8.0:
            continue
        if best is None or r < best[0]:
            best = (r, p, jp)
    if best is None:
        return None, None, None, jpgs
    return best[0], best[1], best[2], jpgs


def block_bbox(col, row, aff):
    u0, v0, u1, v1 = EXP_BBOX_UV
    cor = [reg_auto.grid_xy_distorted(col + u, row + v, aff) for u, v in
           [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
    xs = [c[0] for c in cor]; ys = [c[1] for c in cor]
    return min(xs), min(ys), max(xs), max(ys)


def _pad_score(block):
    h, w = block.shape
    if h < 60 or w < 60:
        return 0.0
    ws = max(5, int(0.05 * min(h, w)) | 1)
    blur = cv2.blur(block, (ws, ws)); sq = cv2.blur(block * block, (ws, ws))
    lstd = np.sqrt(np.maximum(sq - blur * blur, 0))
    uni = ((lstd < np.percentile(lstd, 30)) & (block > np.percentile(block, 45))).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, ws // 2) | 1, max(3, ws // 2) | 1))
    uni = cv2.morphologyEx(uni, cv2.MORPH_OPEN, k, 1)
    uni = cv2.morphologyEx(uni, cv2.MORPH_CLOSE, k, 2)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(uni, connectivity=8)
    areas = [stats[i, cv2.CC_STAT_AREA] for i in range(1, n)]
    return (max(areas) / (h * w)) if areas else 0.0


def find_2b(g, aff, want_type=(2, 1)):
    """Best in-FOV die of the requested (col%4,row%4) type by the 2B pad signature.
    Returns (col,row,block_bbox_int) or None. Falls back to the highest-scoring die
    if no exact-type die is fully in FOV."""
    res = []
    for col in range(11):
        for row in range(6):
            bx0, by0, bx1, by1 = block_bbox(col, row, aff)
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            if not (60 < cx < IMAGE_W - 60 and 60 < cy < IMAGE_H - 60):
                continue
            ix0, iy0 = max(0, int(bx0)), max(0, int(by0))
            ix1, iy1 = min(IMAGE_W, int(bx1)), min(IMAGE_H, int(by1))
            if ix1 - ix0 < 80 or iy1 - iy0 < 80:
                continue
            if ((ix1 - ix0) * (iy1 - iy0)) / max(1, (bx1 - bx0) * (by1 - by0)) < 0.85:
                continue
            res.append((_pad_score(g[iy0:iy1, ix0:ix1]), col, row, (ix0, iy0, ix1, iy1)))
    res.sort(reverse=True)
    for sc, col, row, bb in res:
        if (col % 4, row % 4) == want_type:
            return col, row, bb, sc
    if res:
        sc, col, row, bb = res[0]
        return col, row, bb, sc
    return None


def get_block(jp, aff, want_type=(2, 1), derotate=True):
    """Decode jp, locate the 2B-type die, return (label, block_float, theta_used,
    bbox, M). block is de-rotated so lines are axis-aligned if derotate=True."""
    g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    found = find_2b(g, aff, want_type)
    if not found:
        return None
    col, row, bb, sc = found
    ix0, iy0, ix1, iy1 = bb
    crop = g[iy0:iy1, ix0:ix1]
    theta = aff.get("theta_deg", 0.0)
    block = pf.derotate(crop, theta) if derotate else crop
    M = aff["scale"] / M_ANCHOR_SCALE
    lbl = f"{col}{'ABCDEF'[row]}"
    return dict(label=lbl, block=block, theta=theta, bbox=bb, M=M, score=sc, full=g)
