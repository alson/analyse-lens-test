"""Does tweaking the refinement PARAMETERS (ROI band size, sub-pixel trough
estimator) tighten the full-res fit? Test on the well-sampled sweeps (sweep1=43,
sweep2=24 intersections) where the fit residual is a trustworthy accuracy metric.
"""
import importlib.util, json
from pathlib import Path
import numpy as np, cv2
from PIL import Image

HERE = Path(__file__).parent; A = HERE.parent
def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
af = _load("af", "anchor_fit_sweep.py"); ra = _load("ra", "reg_auto.py")
ATLAS = json.load(open(A / "atlas.json"))


def trough_parab3(prof):           # current: 3-point parabola at argmin
    return ra._trough(prof)


def trough_parabK(prof, k=4, min_depth_std=1.0):
    if prof.size < 2 * k + 1:
        return None
    s = np.convolve(prof, np.ones(3) / 3.0, mode="same")
    i = int(np.argmin(s))
    if i < k or i > s.size - k - 1 or s[i] > s.mean() - min_depth_std * s.std():
        return None
    xs = np.arange(i - k, i + k + 1); ys = s[i - k:i + k + 1]
    a, b, c = np.polyfit(xs, ys, 2)
    return -b / (2 * a) if abs(a) > 1e-9 else float(i)


def trough_centroid(prof, k=5, min_depth_std=1.0):
    s = np.convolve(prof, np.ones(3) / 3.0, mode="same")
    i = int(np.argmin(s))
    if i < k or i > s.size - k - 1 or s[i] > s.mean() - min_depth_std * s.std():
        return None
    xs = np.arange(i - k, i + k + 1)
    w = (s.max() - s[i - k:i + k + 1]); w = np.clip(w, 0, None)
    return float((xs * w).sum() / w.sum()) if w.sum() > 0 else float(i)


EST = {"parab3": trough_parab3, "parabK": trough_parabK, "centroid": trough_centroid}


def refine(path, p, R, band, est):
    img = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    H, W = img.shape; theta = p["theta_deg"]
    M = cv2.getRotationMatrix2D((R, R), theta, 1.0); Minv = cv2.invertAffineTransform(M)
    pairs = []
    for cl in range(ra.N_COL_LINES):
        for rl in range(ra.N_ROW_LINES):
            xp, yp = af.grid_xy(cl, rl, p, ATLAS); xi, yi = int(round(xp)), int(round(yp))
            if not (R < xi < W - R and R < yi < H - R):
                continue
            der = cv2.warpAffine(img[yi - R:yi + R, xi - R:xi + R], M, (2 * R, 2 * R),
                                 flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            cb = der[R - band:R + band, R - band:R + band]
            xt = est(cb.mean(axis=0)); yt = est(cb.mean(axis=1))
            if xt is None or yt is None:
                continue
            xd, yd = (R - band) + xt, (R - band) + yt
            xr = Minv[0, 0] * xd + Minv[0, 1] * yd + Minv[0, 2]
            yr = Minv[1, 0] * xd + Minv[1, 1] * yd + Minv[1, 2]
            pairs.append((cl, rl, (xi - R) + xr, (yi - R) + yr))
    if len(pairs) < 4:
        return None, 0
    pr = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=theta, scale_init=p["scale"])
    return pr, len(pairs)


for name in ["sweep1_M0.385", "sweep2_M1.0"]:
    path, anchors = ra.SWEEPS[name]
    det = ra.detect(path); r = ra.register(name, det, anchors=anchors)
    print(f"\n{name}:")
    for band in (70, 100, 130):
        row = []
        for ename, est in EST.items():
            pr, n = refine(path, r["affine"], 160, band, est)
            row.append(f"{ename}={pr['rmse_px']:.2f}(n{n})" if pr else f"{ename}=--")
        print(f"  band={band}: " + "  ".join(row))
