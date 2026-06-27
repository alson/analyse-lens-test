"""Two questions:
 (1) Does LENS DISTORTION explain residuals? Expect ~0 for true macros (AF200,
     Sigma150) but more for the 100-400 / 24-120 pressed into macro service.
     Test: affine6 baseline vs affine6 + radial (k1,k2) about image centre, with
     affine refit (distortion & affine are coupled). Report residual reduction
     + the distortion magnitude at the field edge.
 (2) Is the ATLAS GRID GEOMETRY (d_col/d_row ratios from the 0129 photo) slightly
     off vs the full-res algorithm? The wafer is rigid, so a one-time tweak could
     help. Test: fit FREE pitch ratios to the best-sampled low-distortion sweep
     and compare to the atlas; check residual improvement + cross-sweep
     consistency of the implied pitches.

Uses an inline refinement at R=160 (the better ROI margin found by the param sweep).
"""
import importlib.util, json
from pathlib import Path
import numpy as np, cv2
from PIL import Image
from scipy.optimize import least_squares

HERE = Path(__file__).parent; A = HERE.parent
def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
af = _load("af", "anchor_fit_sweep.py"); ra = _load("ra", "reg_auto.py")
ATLAS = json.load(open(A / "atlas.json"))
DC = ATLAS["die_pitch_px_in_0129"]["d_col"]; DR = ATLAS["die_pitch_px_in_0129"]["d_row"]
CX, CY, NORM = 8256 / 2, 5504 / 2, 4000.0


def refine_pairs(path, p, R=160, band=100):
    img = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    H, W = img.shape; theta = p["theta_deg"]
    M = cv2.getRotationMatrix2D((R, R), theta, 1.0); Minv = cv2.invertAffineTransform(M)
    out = []
    for cl in range(ra.N_COL_LINES):
        for rl in range(ra.N_ROW_LINES):
            xp, yp = af.grid_xy(cl, rl, p, ATLAS); xi, yi = int(round(xp)), int(round(yp))
            if not (R < xi < W - R and R < yi < H - R):
                continue
            der = cv2.warpAffine(img[yi - R:yi + R, xi - R:xi + R], M, (2 * R, 2 * R),
                                 flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            cb = der[R - band:R + band, R - band:R + band]
            xt = ra._trough(cb.mean(axis=0)); yt = ra._trough(cb.mean(axis=1))
            if xt is None or yt is None:
                continue
            xd, yd = (R - band) + xt, (R - band) + yt
            xr = Minv[0, 0] * xd + Minv[0, 1] * yd + Minv[0, 2]
            yr = Minv[1, 0] * xd + Minv[1, 1] * yd + Minv[1, 2]
            out.append((cl, rl, (xi - R) + xr, (yi - R) + yr))
    return out


def affine6(UV, XY):
    M = np.column_stack([UV, np.ones(len(UV))]); coef, *_ = np.linalg.lstsq(M, XY, rcond=None)
    return coef, XY - M @ coef


def rmse(res):
    return float(np.sqrt(np.mean(np.sum(res ** 2, axis=1))))


def fit_distortion(UV, XY, iters=4):
    """affine6 + radial (k1,k2) about image centre, alternating refit."""
    obs = XY.copy(); k = np.zeros(2)
    for _ in range(iters):
        # undistort observed using current k, then fit affine to undistorted
        r = obs - [CX, CY]; s2 = (r[:, 0] ** 2 + r[:, 1] ** 2) / NORM ** 2
        undist = obs - r * (k[0] * s2 + k[1] * s2 ** 2)[:, None]
        coef, _ = affine6(UV, undist)
        pred = np.column_stack([UV, np.ones(len(UV))]) @ coef        # undistorted prediction
        rp = pred - [CX, CY]; sp2 = (rp[:, 0] ** 2 + rp[:, 1] ** 2) / NORM ** 2
        # solve obs - pred = rp*(k1*sp2 + k2*sp2^2)
        Arow = np.vstack([np.column_stack([rp[:, 0] * sp2, rp[:, 0] * sp2 ** 2]),
                          np.column_stack([rp[:, 1] * sp2, rp[:, 1] * sp2 ** 2])])
        b = np.concatenate([obs[:, 0] - pred[:, 0], obs[:, 1] - pred[:, 1]])
        k, *_ = np.linalg.lstsq(Arow, b, rcond=None)
    final = obs - (pred + rp * (k[0] * sp2 + k[1] * sp2 ** 2)[:, None])
    edge_disp = abs(k[0] * (3000 / NORM) ** 2 + k[1] * (3000 / NORM) ** 4) * 3000  # px at r=3000
    return k, rmse(final), edge_disp


print("=== (1) Lens distortion ===")
LENS = {"sweep1_M0.385": "100-400 (tele, non-macro)", "sweep2_M1.0": "AF200 (TRUE macro)",
        "sweep3_M2.0": "Sigma150+TC (macro+TC)", "sweep4_newer_rig": "24-120+ext (non-macro)"}
allpairs = {}
for name, (path, anchors) in ra.SWEEPS.items():
    det = ra.detect(path); r = ra.register(name, det, anchors=anchors)
    if not r.get("success"):
        continue
    pairs = refine_pairs(path, r["affine"]); allpairs[name] = pairs
    UV = np.array([[af._cum(DC, cl), af._cum(DR, rl)] for (cl, rl, x, y) in pairs])
    XY = np.array([[x, y] for (cl, rl, x, y) in pairs])
    _, res6 = affine6(UV, XY)
    k, rmse_d, edge = fit_distortion(UV, XY)
    print(f"  {name:18s} {LENS[name]:24s} n={len(pairs):2d}  affine6={rmse(res6):5.2f}px  "
          f"+radial={rmse_d:5.2f}px  k1={k[0]:+.3f} k2={k[1]:+.3f}  edge_disp@3000px={edge:.1f}px")

print("\n=== (2) Grid geometry: free pitch ratios vs atlas ===")
def free_pitch_resid(pairs, fit_pitch=True):
    cls = np.array([c for c, r, x, y in pairs]); rls = np.array([r for c, r, x, y in pairs])
    XY = np.array([[x, y] for c, r, x, y in pairs])
    def model(prm):
        th, x0, y0, s = prm[:4]
        dc = np.r_[1.0, prm[4:7]] if fit_pitch else np.array(DC) / DC[0]
        dr = np.r_[1.0, prm[7:10]] if fit_pitch else np.array(DR) / DR[0]
        dc = dc * DC[0]; dr = dr * DR[0]
        res = []
        for c, rr, x, y in pairs:
            U = af._cum(list(dc), c); V = af._cum(list(dr), rr)
            xp = x0 + s * (np.cos(th) * U + np.sin(th) * V)
            yp = y0 + s * (np.sin(th) * U - np.cos(th) * V)
            res += [xp - x, yp - y]
        return np.array(res)
    p0 = [np.radians(4.7), XY[:, 0].mean(), XY[:, 1].mean(), 0.6]
    if fit_pitch:
        p0 += [DC[1] / DC[0], DC[2] / DC[0], DC[3] / DC[0], DR[1] / DR[0], DR[2] / DR[0], DR[3] / DR[0]]
    sol = least_squares(model, p0, method="lm")
    return float(np.sqrt((sol.fun ** 2).mean()) * np.sqrt(2)), sol.x

for name in ["sweep1_M0.385"]:
    pairs = allpairs[name]
    rmse_fixed, _ = free_pitch_resid(pairs, fit_pitch=False)
    rmse_free, x = free_pitch_resid(pairs, fit_pitch=True)
    dc_free = np.r_[1.0, x[4:7]]; dr_free = np.r_[1.0, x[7:10]]
    dc_atlas = np.array(DC) / DC[0]; dr_atlas = np.array(DR) / DR[0]
    print(f"  {name}: atlas-pitch RMSE={rmse_fixed:.2f}px  free-pitch RMSE={rmse_free:.2f}px")
    print(f"    d_col ratios atlas={np.round(dc_atlas,4)}  free={np.round(dc_free,4)}  "
          f"Δ%={np.round((dc_free/dc_atlas-1)*100,2)}")
    print(f"    d_row ratios atlas={np.round(dr_atlas,4)}  free={np.round(dr_free,4)}  "
          f"Δ%={np.round((dr_free/dr_atlas-1)*100,2)}")
