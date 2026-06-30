"""Stage AltEst-2 — the consolidated approaches x gates summary table (small CSV for the
report). Hand-curated from the analysis runs (poc_altest2_*_analyse.py outputs)."""
import sys
from pathlib import Path
import pandas as pd

OUT = Path(__file__).resolve().parent / "poc_comb_chain_out" / "altest2"

rows = [
    dict(approach="P1 same-patch PSD-ratio relMTF (SENSOR f_px=0.10)",
         coverage="38/38 (1 component, 29679 edges)", m_deconf="corr(M)=-0.68",
         empty_mag="NO float", known_orders="YES (macro<vintage<diopter; med 7/11/31)",
         repeatable="YES (Spearman 0.99)", gates="4/4",
         verdict="HARDENED WINNER — bridge ROBUST (M~2 jackknife <=0.07)"),
    dict(approach="P1 same-patch PSD-ratio relMTF (SENSOR f_px=0.12)",
         coverage="38/38", m_deconf="corr(M)=-0.58", empty_mag="NO float",
         known_orders="YES (med 8/11/30)", repeatable="YES (0.98)", gates="4/4",
         verdict="HARDENED WINNER (window centre)"),
    dict(approach="P1 same-patch PSD-ratio relMTF (SENSOR f_px=0.15)",
         coverage="35/38 (M~2 drop)", m_deconf="corr(M)=-0.37", empty_mag="NO float",
         known_orders="YES (med 7.5/13/30)", repeatable="YES (1.00)", gates="4/4",
         verdict="VIABLE; window edge (loses M~2 coverage)"),
    dict(approach="P1 SENSOR f_px>=0.18", coverage="<=32/38", m_deconf="corr(M) flips +",
         empty_mag="float appears", known_orders="degrades", repeatable="-", gates="<4/4",
         verdict="WINDOW BREAKS — M~2/diopter coverage loss + rising noise"),
    dict(approach="P1 SUBJECT-freq (control)", coverage="38/38", m_deconf="corr(M)=+0.17",
         empty_mag="YES (diopters float)", known_orders="partial", repeatable="-",
         gates="1/4", verdict="M-confound RETURNS — confirms sensor-freq does the work"),
    dict(approach="P2 through-focus Gaussian sub-frame FWHM",
         coverage="38/38", m_deconf="corr(M)=-0.22, corr(N_eff)=-0.10",
         empty_mag="~NO (1 borderline)", known_orders="YES (med 8/23/31)",
         repeatable="finer (sub-frame; ties BROKEN)", gates="3.5/4",
         verdict="REFINED A4 — de-confounded, ties broken; agrees P1 (rho 0.40-0.58)"),
    dict(approach="P2 log-parabola curvature", coverage="38/38", m_deconf="corr(M)=+0.13..+0.40",
         empty_mag="YES (accessories float)", known_orders="NO", repeatable="noisy",
         gates="1/4", verdict="FAIL — 2nd-deriv noise-dominated"),
    dict(approach="P3.1 pad-edge averaged-ESF MTF @ f_px=0.10",
         coverage="38/38 (vs 4/16 for SE-edge!)", m_deconf="corr(M)=+0.01",
         empty_mag="NO float (f_px=0.10)", known_orders="YES (med 8/26)",
         repeatable="100k+ edges/config", gates="4/4 (relative only)",
         verdict="COVERAGE SOLVED; ranking de-confounded & agrees P1 (rho 0.52-0.79). "
                 "CAVEAT: absolute MTF over-reads (>1) -> relative/ranking read only"),
    dict(approach="P3.1 pad-edge ERF sigma", coverage="38/38", m_deconf="corr(M)=-0.18",
         empty_mag="NO float", known_orders="YES (med 8.5/24)",
         repeatable="floors at sharp end", gates="3/4",
         verdict="Discriminates the soft tail; saturates (0.2px floor) at the sharp end"),
    dict(approach="P3.2 relative deconvolution (whole-spectrum kernel)",
         coverage="27/38 (high-M drop)", m_deconf="corr(M)=+0.40",
         empty_mag="1 float (S105+5T)", known_orders="YES direction (macros top, tail OK)",
         repeatable="resid 0.21 px^2", gates="2.5/4",
         verdict="Independent (different math); agrees P1 (rho 0.73-0.85). Mild M-confound "
                 "from whole-spectrum fit; high-M coverage thin"),
    dict(approach="P3.3 edge-mask x same-patch ratio",
         coverage="38/38", m_deconf="corr(M)=-0.61", empty_mag="NO float",
         known_orders="YES", repeatable="resid 0.29", gates="4/4",
         verdict="PASS — 'reproducible-distortion' idea works; ~=P1 (rho 0.96-0.97)"),
    dict(approach="P3.4 matched-filter (synthetic lattice template)",
         coverage="38/38", m_deconf="corr(M)=+0.13", empty_mag="NO float",
         known_orders="partial (TC configs float mid)", repeatable="resid 1.60 (noisy)",
         gates="2/4", verdict="WEAK — single-freq template partly credits M; noisy"),
    dict(approach="P3.5 full-amp ratio (P1 sibling)", coverage="38/38",
         m_deconf="corr(M)=-0.62", empty_mag="NO float", known_orders="YES",
         repeatable="resid 0.26", gates="4/4", verdict="~=P1 (rho 0.97-0.98); sanity sibling"),
    dict(approach="P3.5 gradient-energy ratio", coverage="38/38", m_deconf="corr(M)=+0.08",
         empty_mag="NO float", known_orders="partial (tail OK, mid scrambled)",
         repeatable="resid 0.43", gates="2/4",
         verdict="system-MTF (credits M like Approach 2); cross-check only"),
]
df = pd.DataFrame(rows)
df.to_csv(OUT / "altest2_gate_summary.csv", index=False)
print(df.to_string(index=False))
print("\nwrote altest2_gate_summary.csv")
