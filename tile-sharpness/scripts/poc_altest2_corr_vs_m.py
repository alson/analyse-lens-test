"""M-resolved cross-estimator agreement for the AltEst-2 cross-M relative-MTF estimators.

Reads the committed per-config per-estimator scores (P1 same-patch PSD-ratio @ f_px0.10,
pad-edge averaged-ESF, same-patch relative deconvolution, through-focus Gaussian-of-defocus),
sign-aligned so higher == sharper, and computes the pairwise Spearman rank correlation
WITHIN M bands using PER-PAIR coverage (each pair uses the configs it both covers).

Caveats: 3 coarse bands; n≈10 (low/high) / ~17 (mid) so Spearman SE ~0.2-0.3 (only large
swings are real); configs cluster near M≈1; the relative-deconvolution estimator has NO
M>=1.4 coverage. Output: per-band table (stdout) + corr_vs_m.png.
"""
import pandas as pd, numpy as np
from scipy.stats import spearmanr
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

B = ("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/"
     "tile-sharpness/scripts/poc_comb_chain_out/altest2/")

est = {}
d = pd.read_csv(B+"p1_ranking_fpx0.1.csv");  est["P1"]      = d[["sid","M"]].assign(v=d["score"])
d = pd.read_csv(B+"p31_padedge_summary.csv");est["padedge"] = d[["sid","M"]].assign(v=d["mtf_fpx0.1"])
d = pd.read_csv(B+"p32_decon_scores.csv");   est["decon"]   = d[["sid","M"]].assign(v=-d["blur_var_px2"])
d = pd.read_csv(B+"p2_psffoc2_summary.csv"); est["P2"]      = d[["sid","M"]].assign(v=-d["g_fwhm"])

print("=== per-estimator M coverage ===")
for k,v in est.items():
    print(f"  {k:8s} n={len(v):3d}  M {v.M.min():.2f}-{v.M.max():.2f}  (#M>=1.4: {(v.M>=1.4).sum()})")

bands = [(0.0,1.00,"<1.0"),(1.00,1.40,"1.0-1.4"),(1.40,2.20,">=1.4")]
names = list(est)
pairs = [(a,b) for i,a in enumerate(names) for b in names[i+1:]]

print("\n=== per-pair Spearman by M band (n in parens) ===")
res = {p:{} for p in pairs}
for a,b in pairs:
    m = est[a].merge(est[b], on="sid", suffixes=("_a","_b"))
    line=[f"{a:8s}~{b:8s}"]
    for lo,hi,lbl in bands:
        s = m[(m.M_a>=lo)&(m.M_a<hi)]
        if len(s)>=4:
            r = spearmanr(s.v_a, s.v_b).correlation
            res[(a,b)][lbl]=(r,len(s)); line.append(f"{lbl}:{r:+.2f}(n{len(s)})")
        else:
            line.append(f"{lbl}: -- (n{len(s)})")
    print("  "+"  ".join(line))

plt.figure(figsize=(8.8,5.4))
xc = {"<1.0":0.9,"1.0-1.4":1.2,">=1.4":1.7}
for a,b in pairs:
    pts = sorted((xc[lbl],r) for lbl,(r,n) in res[(a,b)].items())
    if pts:
        xs,ys=zip(*pts); plt.plot(xs,ys,marker="o",label=f"{a}↔{b}")
plt.axhline(0,color="k",lw=.6); plt.ylim(-0.7,1.05)
plt.xticks([0.9,1.2,1.7],["<1.0","1.0-1.4",">=1.4"])
plt.xlabel("M band"); plt.ylabel("Spearman ρ within band (per-pair coverage)")
plt.title("Inter-estimator agreement vs magnification\n(per-pair config coverage)",fontsize=9)
plt.legend(fontsize=8,ncol=3,loc="lower center"); plt.grid(alpha=.3); plt.tight_layout()
plt.savefig(B+"corr_vs_m.png",dpi=115); print("\nsaved",B+"corr_vs_m.png")
