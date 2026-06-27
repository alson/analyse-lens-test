"""Why is sweep2's fit RMSE higher? Fit the (gap-aware, correctly-labelled)
auto-detected scribes and report per-scribe-line residuals to localize the error
(spurious scribe? one bad line? uniform detection noise?). Compare across sweeps.
"""
import importlib.util, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent; A = HERE.parent
def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
af = _load("af", "anchor_fit_sweep.py"); ra = _load("ra", "reg_auto.py")
ATLAS = json.load(open(A / "atlas.json"))

# correct offsets found autonomously
OFF = {"sweep2_M1.0": (5, 2), "sweep3_M2.0": (5, 2), "sweep4_newer_rig": (4, 2)}

for name, (cf, rf) in OFF.items():
    det = ra.detect(name and ra.SWEEPS[name][0])
    col_x, row_y = det["col_x"], det["row_y"]
    cl = ra._labels(col_x, cf)
    rrel = ra._rel_indices(row_y); rl = [rf + int(rrel[-1]) - int(r) for r in rrel]
    pairs, idx = [], []
    for ci, xd in enumerate(col_x):
        for ri, yd in enumerate(row_y):
            xo, yo = ra.derot_to_orig(float(xd), float(yd), det)
            pairs.append((cl[ci], rl[ri], xo, yo)); idx.append((ci, ri))
    p = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"], scale_init=0.5)
    resid = []
    for (c, r, x, y) in pairs:
        xp, yp = af.grid_xy(c, r, p, ATLAS); resid.append(np.hypot(xp - x, yp - y))
    resid = np.array(resid)
    print(f"\n{name}: cf={cf} rf={rf}  fit_rmse={p['rmse_px']:.0f}px  scale={p['scale']:.3f}")
    print(f"  col_x(derot)={[int(v) for v in col_x]}  labels={cl}")
    print(f"  row_y(derot)={[int(v) for v in row_y]}  labels={rl}")
    # mean residual grouped by col line and by row line
    for ci in range(len(col_x)):
        m = np.mean([resid[k] for k, (a, b) in enumerate(idx) if a == ci])
        print(f"    col {cl[ci]:>2} (x={int(col_x[ci]):>4}): mean resid {m:6.0f}px")
    for ri in range(len(row_y)):
        m = np.mean([resid[k] for k, (a, b) in enumerate(idx) if b == ri])
        print(f"    row {rl[ri]:>2} (y={int(row_y[ri]):>4}): mean resid {m:6.0f}px")
