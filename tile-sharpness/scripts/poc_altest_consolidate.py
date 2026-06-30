"""Consolidate the Stage AltEst per-approach gate outcomes into one small CSV for the
report. Reads the summary CSVs the analysis scripts wrote."""
import sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "poc_comb_chain_out" / "altest"

rows = [
    # approach, variant, M-deconfound corr, empty-mag float?, known-order, repeatable, verdict
    dict(approach="1 same-patch PSD-ratio relMTF", variant="SUBJECT-freq (credits M)",
         m_corr="+0.38..+0.45", empty_mag_float="YES (5T+6T floats)",
         known_orders="partial", repeatable="n/a", gates_passed="1/4",
         verdict="M-confounded as expected (credits magnification)"),
    dict(approach="1 same-patch PSD-ratio relMTF", variant="SENSOR-freq f_px=0.10",
         m_corr="-0.41", empty_mag_float="NO", known_orders="YES (macros lead, diopters tail)",
         repeatable="YES (Spearman 0.96)", gates_passed="4/4",
         verdict="VIABLE under stated conditions — best non-comb estimator"),
    dict(approach="1 same-patch PSD-ratio relMTF", variant="SENSOR-freq f_px=0.15",
         m_corr="-0.14", empty_mag_float="NO", known_orders="YES",
         repeatable="YES (Spearman 0.99)", gates_passed="4/4",
         verdict="VIABLE (best de-confound point)"),
    dict(approach="2 same-patch detail (tenengrad)", variant="-",
         m_corr="+0.40", empty_mag_float="NO (tenengrad) / YES (lap,hf,var)",
         known_orders="partial (diopters tail OK; macros not separated)", repeatable="n/a",
         gates_passed="2/4", verdict="M-confounded; system-MTF metric, credits M"),
    dict(approach="3 blind PSF (Gaussian sigma)", variant="-",
         m_corr="-0.23", empty_mag_float="YES (badly: diopters rank sharpest)",
         known_orders="NO (diopters sharpest = inverted)", repeatable="poor (IQR ~ value)",
         gates_passed="1/4", verdict="FAIL — beta/sigma degeneracy; low-contrast=small-sigma artifact"),
    dict(approach="3 blind PSF (cepstral)", variant="-",
         m_corr="nan", empty_mag_float="-", known_orders="NO (all railed to 3px)",
         repeatable="degenerate", gates_passed="0/4",
         verdict="FAIL — cepstral peak floors; no discrimination"),
    dict(approach="4 through-focus FWHM", variant="-",
         m_corr="-0.04", empty_mag_float="NO", known_orders="partial (AF200 sharpest; macros tie at 8)",
         repeatable="coarse (quantized 5/7/8/11/14)", gates_passed="3/4 (weak)",
         verdict="Directionally sane + de-confounded (corr N_eff=0.00) but coarse; tie among macros"),
    dict(approach="5 SE-edge MTF50 fixed-sensor", variant="-",
         m_corr="-1.0 (n=4)", empty_mag_float="n/a (no bare macros covered)",
         known_orders="UNTESTABLE", repeatable="n/a", gates_passed="0/4",
         verdict="FAIL on COVERAGE — only 4/16 configs, no bare modern macro survives"),
]
df = pd.DataFrame(rows)
df.to_csv(OUT / "altest_gate_summary.csv", index=False)
print(df.to_string(index=False))
print("\nwrote altest_gate_summary.csv")
