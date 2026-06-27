"""Assess the TRUE accuracy of the full-res refinement, independent of the
human-clicked anchors (which carry their own few-px uncertainty). Use the
internal FIT RESIDUAL of the many auto-detected intersections, and test whether
a richer grid model fits them better (which would mean the fixed pitch ratios /
4-DOF similarity / lack of a distortion term is the limiter, not the refinement).

Models (image x,y as a function of ideal grid coords U=cum(d_col,cl),
V=cum(d_row,rl)):
  sim4   : current af model (theta, x0, y0, single scale)
  aniso5 : similarity but independent x/y scale (tests global d_col:d_row ratio)
  affine6: full 2x3 (adds shear)
  homog8 : homography (perspective / keystone)
Also report the residual's correlation with radius (radial-distortion signature).
"""
import importlib.util, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent; A = HERE.parent
def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
af = _load("af", "anchor_fit_sweep.py"); ra = _load("ra", "reg_auto.py")
ATLAS = json.load(open(A / "atlas.json"))
DC = ATLAS["die_pitch_px_in_0129"]["d_col"]; DR = ATLAS["die_pitch_px_in_0129"]["d_row"]
IMG_CX, IMG_CY = 8256 / 2, 5504 / 2


def rmse(res):
    return float(np.sqrt(np.mean(np.sum(res ** 2, axis=1))))


def fit_linear(M, XY):
    """Least-squares M @ coef = XY (per column). Returns residual Nx2."""
    coef, *_ = np.linalg.lstsq(M, XY, rcond=None)
    return XY - M @ coef


def fit_homography(UV, XY):
    n = len(UV)
    Arows = []
    for (u, v), (x, y) in zip(UV, XY):
        Arows.append([u, v, 1, 0, 0, 0, -x * u, -x * v, -x])
        Arows.append([0, 0, 0, u, v, 1, -y * u, -y * v, -y])
    Amat = np.array(Arows)
    _, _, Vt = np.linalg.svd(Amat)
    h = Vt[-1].reshape(3, 3)
    UV1 = np.column_stack([UV, np.ones(n)])
    proj = (h @ UV1.T).T
    proj = proj[:, :2] / proj[:, 2:3]
    return XY - proj


def sim4_predict(pairs_fit, cl, rl):
    p = af.fit_sweep_affine(pairs_fit, ATLAS, theta_init_deg=4.5, scale_init=1.0)
    return np.array(af.grid_xy(cl, rl, p, ATLAS))


def loo_rmse(pairs, model):
    """Leave-one-out CV RMSE for 'sim4' or 'affine6'."""
    errs = []
    for i in range(len(pairs)):
        tr = pairs[:i] + pairs[i + 1:]
        cl, rl, x, y = pairs[i]
        if model == "sim4":
            pred = sim4_predict(tr, cl, rl)
        else:
            UVt = np.column_stack([[[af._cum(DC, c), af._cum(DR, rr)] for (c, rr, _, _) in tr],
                                   np.ones(len(tr))])
            XYt = np.array([[xx, yy] for (_, _, xx, yy) in tr])
            coef, *_ = np.linalg.lstsq(UVt, XYt, rcond=None)
            pred = np.array([af._cum(DC, cl), af._cum(DR, rl), 1.0]) @ coef
        errs.append((pred[0] - x) ** 2 + (pred[1] - y) ** 2)
    return float(np.sqrt(np.mean(errs)))


for name, (path, anchors) in ra.SWEEPS.items():
    det = ra.detect(path); r = ra.register(name, det, anchors=anchors)
    if not r.get("success"):
        print(f"{name}: FAIL"); continue
    pr, n_int, pairs = ra.refine_full_res(path, r["affine"])
    UV = np.array([[af._cum(DC, cl), af._cum(DR, rl)] for (cl, rl, x, y) in pairs])
    XY = np.array([[x, y] for (cl, rl, x, y) in pairs])

    res4 = np.array([[af.grid_xy(cl, rl, pr, ATLAS)[0] - x, af.grid_xy(cl, rl, pr, ATLAS)[1] - y]
                     for (cl, rl, x, y) in pairs])
    M_aff = np.column_stack([UV, np.ones(len(UV))])
    coef, *_ = np.linalg.lstsq(M_aff, XY, rcond=None)
    res6 = XY - M_aff @ coef
    resH = fit_homography(UV, XY)

    # decompose the 2x2 of affine6: coef rows are [a b c] for x and y => A=[[a_x,b_x],[a_y,b_y]]
    Amat = np.array([[coef[0, 0], coef[1, 0]], [coef[0, 1], coef[1, 1]]])
    sx = np.hypot(Amat[0, 0], Amat[1, 0]); sy = np.hypot(Amat[0, 1], Amat[1, 1])
    shear = np.degrees(np.arccos(np.clip(
        (Amat[0, 0] * Amat[0, 1] + Amat[1, 0] * Amat[1, 1]) / (sx * sy), -1, 1))) - 90

    print(f"\n{name}: {n_int} intersections")
    print(f"  sim4 (current)  in-sample {rmse(res4):5.2f}px   LOO {loo_rmse(pairs,'sim4'):5.2f}px"
          f"   (low-res anchor-RMSE was {r.get('anchor_rmse_px',0):.0f})")
    print(f"  affine6         in-sample {rmse(res6):5.2f}px   LOO {loo_rmse(pairs,'affine6'):5.2f}px")
    print(f"  homography8     in-sample {rmse(resH):5.2f}px")
    print(f"  affine6 scales: sx/sy ratio = {sx/sy:.4f}  shear = {shear:+.3f} deg")
