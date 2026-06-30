"""Stage AltEst-2 — P2 REFINED through-focus analysis + cross-validation vs P1.

Aggregates the finer focus-response descriptors (Gaussian sub-frame FWHM, log-parabola
curvature, peak/area, and their fixed-sensor-band variants) per config, runs the four
gates (incl. the A4 de-confound checks corr(.,N_eff) and corr(.,M)), and — the key new
test — Spearman-correlates each P2 descriptor's ranking against the hardened P1 sensor-freq
ranking. Agreement of an independent, de-confounded estimator with P1 is the strongest
corroboration of a real cross-M signal, especially at low M where P1 coverage is densest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
OUT = HERE / "poc_comb_chain_out" / "altest2"
ACC = r"\+"
MODERN = ["Z105_1_1_F8", "AF200_1_1_F8", "S105_1_1_F8", "S150_1_1_F8"]
VINTAGE = ["V55f28287318_1_1_F8", "V55f28537016_1_1_F8", "V55f35209088_1_1_F8",
           "V55f35258263_1_1_F8", "AF60_1_1_F8"]
DIOPTER = ["Z100400+MCON-35_1_1.16_F8", "Z100400+C500D_1.07_1_F8", "AF200+5T+6T_2_1_F8",
           "S150+5T+6T_1.8_1_F8", "AF200+6T_1.7_1_F8"]


def gate(agg, col, label, higher_is_sharper):
    d = agg.dropna(subset=[col]).copy()
    if len(d) < 4:
        print(f"\n--- {label}: too few ---"); return None
    d = d.sort_values(col, ascending=not higher_is_sharper).reset_index(drop=True)
    d["rank"] = range(1, len(d) + 1)
    sgn = 1.0 if higher_is_sharper else -1.0
    cM = np.corrcoef(d.M, sgn * d[col])[0, 1]
    cN = np.corrcoef(d.n_eff, sgn * d[col])[0, 1]
    print(f"\n--- {label} ({len(d)} configs) ---")
    print(f"corr(M, sharp)={cM:+.3f}  corr(N_eff, sharp)={cN:+.3f}  (both want ~0)")
    print(d[["rank", "sid", "M", "n_eff", col]].round(3).to_string(index=False))
    bare = d[~d.sid.str.contains(ACC, regex=True)]; acc = d[d.sid.str.contains(ACC, regex=True)]
    if len(bare) and len(acc):
        bbr = bare["rank"].min(); fl = acc[acc["rank"] < bbr]
        print(f"empty-mag: best bare rank={bbr} ({bare.iloc[0].sid}); "
              f"accessory above: {'NONE (OK)' if not len(fl) else ', '.join(fl.sid)}")
    rk = {s: i for i, s in enumerate(d.sid)}
    def mr(grp):
        v = [rk[s] for s in grp if s in rk]; return round(float(np.median(v)), 1) if v else np.nan
    print(f"§L: median rank modern={mr(MODERN)}, vintage={mr(VINTAGE)}, diopter={mr(DIOPTER)} "
          f"(want modern<vintage<diopter)")
    return d


def main():
    files = list(OUT.glob("psffoc2_shard_*.csv"))
    if not files:
        print("no psffoc2 shards"); return
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    print(f"loaded {df.sid.nunique()} configs, {df.patch.nunique()} patches, {len(df)} rows")
    agg = df.groupby("sid").agg(
        M=("M", "first"), n_eff=("n_eff", "first"), nstack=("nstack", "first"),
        g_fwhm=("g_fwhm", "median"),
        g_fwhm_iqr=("g_fwhm", lambda s: np.subtract(*np.nanpercentile(s, [75, 25]))),
        lp_curv=("lp_curv", "median"),
        g_fwhm_bp=("g_fwhm_bp", "median"),
        lp_curv_bp=("lp_curv_bp", "median"),
        peak_over_area=("peak_over_area", "median"),
        npatch=("patch", "nunique"),
    ).reset_index()

    print("\n" + "=" * 72 + "\nP2 refined through-focus descriptors\n" + "=" * 72)
    d_fwhm = gate(agg, "g_fwhm", "P2 Gaussian sub-frame FWHM (frames; narrower=sharper)", False)
    print("\nrepeatability (g_fwhm IQR across patches):")
    print(agg[["sid", "M", "g_fwhm", "g_fwhm_iqr", "npatch"]].sort_values("g_fwhm").round(2).to_string(index=False))
    d_curv = gate(agg, "lp_curv", "P2 log-parabola curvature (sharper=larger)", True)
    d_fwbp = gate(agg, "g_fwhm_bp", "P2 fixed-band FWHM (frames; narrower=sharper)", False)
    d_cvbp = gate(agg, "lp_curv_bp", "P2 fixed-band curvature (sharper=larger)", True)
    d_poa = gate(agg, "peak_over_area", "P2 peak/area acutance (sharper=larger)", True)

    # ---- cross-validation vs hardened P1 ------------------------------------- #
    print("\n" + "=" * 72 + "\nP2 <-> P1 cross-agreement (Spearman over shared configs)\n" + "=" * 72)
    for fpx in (0.1, 0.12, 0.15):
        p1f = OUT / f"p1_ranking_fpx{fpx}.csv"
        if not p1f.exists():
            continue
        p1 = pd.read_csv(p1f)
        p1map = dict(zip(p1.sid, p1.score))   # higher = sharper
        for col, higher in (("g_fwhm", False), ("lp_curv", True), ("g_fwhm_bp", False),
                            ("lp_curv_bp", True), ("peak_over_area", True)):
            sub = agg.dropna(subset=[col])
            common = [s for s in sub.sid if s in p1map]
            if len(common) < 6:
                continue
            sgn = 1.0 if higher else -1.0
            x = [p1map[s] for s in common]
            y = [sgn * float(sub[sub.sid == s][col].iloc[0]) for s in common]
            rho, _ = spearmanr(x, y)
            # also restrict to LOW-M (M<1.2) where P1 coverage is densest
            lowm = [s for s in common if agg[agg.sid == s].M.iloc[0] < 1.2]
            rho_lo = np.nan
            if len(lowm) >= 6:
                xl = [p1map[s] for s in lowm]
                yl = [sgn * float(sub[sub.sid == s][col].iloc[0]) for s in lowm]
                rho_lo, _ = spearmanr(xl, yl)
            print(f"  P1@f_px={fpx} vs P2:{col:16s} Spearman={rho:+.3f} (n={len(common)})  "
                  f"low-M(M<1.2)={rho_lo:+.3f} (n={len(lowm)})")
        print()
    agg.to_csv(OUT / "p2_psffoc2_summary.csv", index=False)
    print("wrote p2_psffoc2_summary.csv")


if __name__ == "__main__":
    main()
