"""(b) One-time wafer-grid recalibration. Jointly fit SHARED pitch ratios
(d_col/d_row) + per-sweep (affine + radial distortion) to the full-res refined
intersections of the ISOTROPIC, low-distortion reference sweeps (sweep1 100-400
gives wide col 0..10 coverage and is distortion-corrected; sweep2 AF200 macro is
distortion-free). Then VALIDATE on the held-out sweeps: does the recalibrated
geometry reduce their residual vs the atlas geometry? Only then is a tweak real.
"""
import importlib.util, json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).parent; A = HERE.parent
def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
af = _load("af", "anchor_fit_sweep.py"); ra = _load("ra", "reg_auto.py")
ATLAS = json.load(open(A / "atlas.json"))
DC0 = np.array(ATLAS["die_pitch_px_in_0129"]["d_col"], float)
DR0 = np.array(ATLAS["die_pitch_px_in_0129"]["d_row"], float)
CX, CY, NORM = ra.DIST_CENTER[0], ra.DIST_CENTER[1], ra.DIST_NORM
REF = ["sweep1_M0.385", "sweep2_M1.0"]            # isotropic, low-distortion
ALL = list(ra.SWEEPS)


def cum(d4, k):
    k = float(k)
    if k <= 0: return 0.0
    ki = int(np.floor(k)); frac = k - ki
    return (ki // 4) * sum(d4) + sum(d4[:ki % 4]) + (frac * d4[ki % 4] if frac else 0.0)


def fwd(sp, dc, dr, cl, rl):
    th, x0, y0, s, k1, k2 = sp
    U = cum(dc, cl); V = cum(dr, rl)
    xu = x0 + s * (np.cos(th) * U + np.sin(th) * V)
    yu = y0 + s * (np.sin(th) * U - np.cos(th) * V)
    dx, dy = xu - CX, yu - CY; r2 = (dx * dx + dy * dy) / NORM ** 2
    f = 1 + k1 * r2 + k2 * r2 * r2
    return CX + dx * f, CY + dy * f


def fit_one(pairs, dc, dr, seed_scale):
    """Per-sweep affine+distortion with FIXED pitches; return RMSE."""
    def res(p):
        o = []
        for cl, rl, x, y in pairs:
            xp, yp = fwd(p, dc, dr, cl, rl); o += [xp - x, yp - y]
        return np.array(o)
    XY = np.array([[x, y] for _, _, x, y in pairs])
    s0 = [np.radians(4.7), XY[:, 0].mean(), XY[:, 1].mean(), seed_scale, 0, 0]
    sol = least_squares(res, s0, method="lm")
    return float(np.sqrt((sol.fun ** 2).mean() * 2))


# collect refined intersections per sweep
PAIRS, SCALE = {}, {}
for name in ALL:
    path, anchors = ra.SWEEPS[name]
    det = ra.detect(path); r = ra.register(name, det, anchors=anchors)
    pr, n, pairs = ra.refine_full_res(path, r["affine"])
    PAIRS[name] = pairs; SCALE[name] = r["affine"]["scale"]

# joint fit: 7 global pitch params [dc1,dc2,dc3, dr0,dr1,dr2,dr3] (dc[0]=1) + 6/sweep
nref = len(REF)
def unpack(p):
    dc = np.r_[1.0, p[0:3]]; dr = p[3:7]
    sw = [p[7 + 6 * i: 7 + 6 * (i + 1)] for i in range(nref)]
    return dc, dr, sw

def joint_res(p):
    dc, dr, sw = unpack(p)
    o = []
    for i, name in enumerate(REF):
        for cl, rl, x, y in PAIRS[name]:
            xp, yp = fwd(sw[i], dc, dr, cl, rl); o += [xp - x, yp - y]
    return np.array(o)

p0 = [DC0[1] / DC0[0], DC0[2] / DC0[0], DC0[3] / DC0[0],
      DR0[0] / DC0[0], DR0[1] / DC0[0], DR0[2] / DC0[0], DR0[3] / DC0[0]]
for name in REF:
    XY = np.array([[x, y] for _, _, x, y in PAIRS[name]])
    p0 += [np.radians(4.7), XY[:, 0].mean(), XY[:, 1].mean(), SCALE[name] * DC0[0], 0, 0]
sol = least_squares(joint_res, p0, method="lm")
dc_f, dr_f, _ = unpack(sol.x)
# normalize recal pitches to same overall scale convention as atlas (scale by DC0[0])
dc_recal = dc_f * DC0[0]; dr_recal = dr_f * DC0[0]

print("=== recalibrated wafer grid (refs: sweep1+sweep2, distortion-corrected) ===")
print(f"  d_col atlas = {np.round(DC0,1)}")
print(f"  d_col recal = {np.round(dc_recal,1)}   ratio Δ% = {np.round((dc_recal/dc_recal[0])/(DC0/DC0[0])*100-100,2)}")
print(f"  d_row atlas = {np.round(DR0,1)}")
print(f"  d_row recal = {np.round(dr_recal,1)}   ratio Δ% = {np.round((dr_recal/dc_recal[0])/(DR0/DC0[0])*100-100,2)}")
print(f"  col:row aspect atlas={DR0[0]/DC0[0]:.4f} recal={dr_recal[0]/dc_recal[0]:.4f}")

print("\n=== validation: per-sweep RMSE with ATLAS vs RECAL pitches ===")
print(f"  {'sweep':<18}{'role':>6}{'atlas':>9}{'recal':>9}")
held_improved = True
for name in ALL:
    role = "REF" if name in REF else "held"
    ra_ = fit_one(PAIRS[name], DC0, DR0, SCALE[name] * DC0[0])
    rr_ = fit_one(PAIRS[name], dc_recal, dr_recal, SCALE[name] * dc_recal[0])
    if role == "held" and rr_ > ra_:
        held_improved = False
    print(f"  {name:<18}{role:>6}{ra_:>8.2f}p{rr_:>8.2f}p")

out = {"d_col": [float(v) for v in dc_recal], "d_row": [float(v) for v in dr_recal],
       "refs": REF, "held_out_improved": bool(held_improved),
       "note": "recalibrated wafer pitches in 0129-px (d_col[0] anchored to atlas); "
               "joint fit over reference sweeps with per-sweep affine+radial distortion."}
json.dump(out, open(A / "out" / "grid_recal.json", "w"), indent=1)
print(f"\nwrote out/grid_recal.json  held_out_improved={held_improved}")
