"""Stage AltEst-2 — consolidate all estimators: cross-agreement Spearman matrix + a
consensus cross-M relative ranking (rank-average of the estimators that pass the gates),
with per-config agreement spread. Writes the matrix + consensus CSVs for the report.

Estimators included (all read so a HIGHER aligned value = sharper):
  P1   same-patch PSD-ratio relMTF, sensor-freq f_px=0.10 and 0.12 (the hardened winner)
  P2   through-focus Gaussian sub-frame FWHM (de-confounded; sharper = smaller -> negate)
  P3.1 pad-edge averaged-ESF MTF @ f_px=0.10 (full coverage)
  P3.2 relative deconvolution blur-variance (sharper = smaller -> negate)
  P3.3 edge-mask x same-patch ratio
  P3.5 full-amp ratio (P1 sibling, sanity)
Gate-failing estimators (P2 curvature, P3.4 matched-filter, P3.5 gradient-energy) are
reported in the matrix for completeness but excluded from the consensus.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
OUT = HERE / "poc_comb_chain_out" / "altest2"


def load_series():
    s = {}
    # P1 sensor-freq scores (higher = sharper)
    for fpx in (0.1, 0.12, 0.15):
        f = OUT / f"p1_ranking_fpx{fpx}.csv"
        if f.exists():
            d = pd.read_csv(f); s[f"P1_fpx{fpx}"] = dict(zip(d.sid, d.score))
    # P2 g_fwhm (smaller=sharper -> negate)
    f = OUT / "p2_psffoc2_summary.csv"
    if f.exists():
        d = pd.read_csv(f)
        # drop the degenerate g_fwhm outlier (>50 frames = bad fit)
        d = d[d.g_fwhm < 50]
        s["P2_gfwhm"] = dict(zip(d.sid, -d.g_fwhm))
    # P3.1 pad-edge MTF@0.10 (higher=sharper)
    f = OUT / "p31_padedge_summary.csv"
    if f.exists():
        d = pd.read_csv(f); s["P31_padedge"] = dict(zip(d.sid, d["mtf_fpx0.1"]))
        s["P31_sigma"] = dict(zip(d.sid, -d.sigma_px))
    # P3.2 decon blur-var (smaller=sharper -> negate)
    f = OUT / "p32_decon_scores.csv"
    if f.exists():
        d = pd.read_csv(f); s["P32_decon"] = dict(zip(d.sid, -d.blur_var_px2))
    # P3.3 edge-mask (higher=sharper)
    f = OUT / "p33_edgemask_scores.csv"
    if f.exists():
        d = pd.read_csv(f); s["P33_edgemask"] = dict(zip(d.sid, d.score))
    # P3.5 full-amp (higher=sharper)
    f = OUT / "p35_fullamp_scores.csv"
    if f.exists():
        d = pd.read_csv(f); s["P35_fullamp"] = dict(zip(d.sid, d.score))
    # P3.4 matched-filter (higher=sharper) — for matrix only
    f = OUT / "p34_matchfilter_scores.csv"
    if f.exists():
        d = pd.read_csv(f); s["P34_matchfilt"] = dict(zip(d.sid, d.score))
    return s


def main():
    s = load_series()
    names = list(s)
    print("estimators:", names)
    # Spearman matrix over the configs each pair shares
    M = pd.DataFrame(index=names, columns=names, dtype=float)
    for a in names:
        for b in names:
            common = sorted(set(s[a]) & set(s[b]))
            if len(common) >= 6:
                rho, _ = spearmanr([s[a][k] for k in common], [s[b][k] for k in common])
                M.loc[a, b] = round(rho, 3)
    print("\n=== Cross-agreement Spearman matrix (higher-aligned = sharper) ===")
    print(M.to_string())
    M.to_csv(OUT / "p_crossagreement_matrix.csv")

    # consensus: gate-passing estimators only (exclude P34 matched-filter; P31_sigma kept
    # as a soft member, it saturates at the sharp end so down-weight by using rank-average).
    CONSENSUS = ["P1_fpx0.1", "P1_fpx0.12", "P2_gfwhm", "P31_padedge", "P32_decon",
                 "P33_edgemask", "P35_fullamp"]
    CONSENSUS = [c for c in CONSENSUS if c in s]
    # rank each estimator (1=sharpest), average ranks over the estimators that cover a config
    all_sids = sorted({k for c in CONSENSUS for k in s[c]})
    rank_tbl = {}
    for c in CONSENSUS:
        order = sorted(s[c], key=lambda k: -s[c][k])
        rk = {k: i + 1 for i, k in enumerate(order)}
        rank_tbl[c] = rk
    rows = []
    for sid in all_sids:
        rks = [rank_tbl[c][sid] for c in CONSENSUS if sid in rank_tbl[c]]
        if not rks:
            continue
        rows.append(dict(sid=sid, mean_rank=float(np.mean(rks)),
                         rank_std=float(np.std(rks)), n_estimators=len(rks),
                         **{c: rank_tbl[c].get(sid) for c in CONSENSUS}))
    cons = pd.DataFrame(rows).sort_values("mean_rank").reset_index(drop=True)
    cons.insert(0, "consensus_rank", range(1, len(cons) + 1))
    print("\n=== CONSENSUS cross-M relative ranking (mean rank over gate-passing estimators) ===")
    show = ["consensus_rank", "sid", "mean_rank", "rank_std", "n_estimators"]
    print(cons[show].to_string(index=False))
    cons.to_csv(OUT / "p_consensus_ranking.csv", index=False)
    print("\nwrote p_crossagreement_matrix.csv, p_consensus_ranking.csv")


if __name__ == "__main__":
    main()
