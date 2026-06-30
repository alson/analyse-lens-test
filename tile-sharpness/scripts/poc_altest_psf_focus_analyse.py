"""Stage AltEst analysis — approaches 3 (blind PSF) and 4 (through-focus shape) gates.

Reads psffoc_shard_*.csv. For each estimator builds a per-config aggregate (median over
shared patches), ranks configs, and runs the gates: M de-confounding, empty-mag float,
known orderings, repeatability (per-patch spread).
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

OUT = HERE / "poc_comb_chain_out" / "altest"
ACC = r"\+"


def gate(df, value_col, label, higher_is_sharper):
    """df has columns sid, M, <value_col> per config (already aggregated)."""
    d = df.dropna(subset=[value_col]).copy()
    if len(d) < 3:
        print(f"\n--- {label}: too few configs ---"); return
    # sharper-first ordering
    d = d.sort_values(value_col, ascending=not higher_is_sharper)
    d["rank"] = range(1, len(d) + 1)
    # M de-confound: corr between a sharpness-direction score and M
    sgn = 1.0 if higher_is_sharper else -1.0
    corr = np.corrcoef(d.M, sgn * d[value_col])[0, 1]
    print(f"\n--- {label} ---")
    print(f"corr(M, sharpness) = {corr:+.3f}  (want ~0; +ve = high-M reads sharper = empty-mag bias)")
    print(d[["rank", "sid", "M", value_col]].to_string(index=False))
    bare = d[~d.sid.str.contains(ACC, regex=True)]
    acc = d[d.sid.str.contains(ACC, regex=True)]
    if len(bare) and len(acc):
        # "sharper" = better rank (lower rank number)
        best_bare_rank = bare["rank"].min()
        floats = acc[acc["rank"] < best_bare_rank]
        print(f"empty-mag: best bare rank={best_bare_rank} ({bare.iloc[0].sid}); "
              f"accessory configs ranked above it: "
              f"{'NONE (OK)' if not len(floats) else ', '.join(floats.sid)}")


def main():
    files = list(OUT.glob("psffoc_shard_*.csv"))
    if not files:
        print("no psffoc shards"); return
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    print(f"loaded {df.sid.nunique()} configs, {df.patch.nunique()} patches, {len(df)} rows")

    # repeatability: per-config per-patch spread of sigma_subj_um
    agg = df.groupby(["sid"]).agg(
        M=("M", "first"),
        sigma_subj_um=("sigma_subj_um", "median"),
        sigma_subj_iqr=("sigma_subj_um", lambda s: np.subtract(*np.nanpercentile(s, [75, 25]))),
        beta=("beta", "median"),
        cepstral_px=("cepstral_px", "median"),
        foc_fwhm=("foc_fwhm", "median"),
        foc_fwhm_iqr=("foc_fwhm", lambda s: np.subtract(*np.nanpercentile(s, [75, 25]))),
        foc_curv=("foc_curv", "median"),
        n_eff=("n_eff", "first"),
        npatch=("patch", "nunique"),
    ).reset_index()

    print("\n" + "=" * 70 + "\nAPPROACH 3 — blind PSF (Gaussian sigma in SUBJECT um; smaller = sharper)\n" + "=" * 70)
    gate(agg, "sigma_subj_um", "A3 sigma_subj_um (Gaussian-PSF fit)", higher_is_sharper=False)
    # repeatability note
    print("\nrepeatability (sigma_subj_um IQR across patches, want small vs spread):")
    print(agg[["sid", "M", "sigma_subj_um", "sigma_subj_iqr", "npatch"]].sort_values("sigma_subj_um").to_string(index=False))
    gate(agg, "cepstral_px", "A3 cepstral blur radius (px; smaller=sharper)", higher_is_sharper=False)

    print("\n" + "=" * 70 + "\nAPPROACH 4 — through-focus response (FWHM frames; narrower = sharper)\n" + "=" * 70)
    gate(agg, "foc_fwhm", "A4 through-focus FWHM (frames; narrower=sharper)", higher_is_sharper=False)
    print("\nrepeatability (foc_fwhm IQR across patches):")
    print(agg[["sid", "M", "foc_fwhm", "foc_fwhm_iqr", "n_eff"]].sort_values("foc_fwhm").to_string(index=False))
    # N_eff/M-aware: DOF ~ N_eff*(some)/M^2; correlate fwhm with N_eff to see if it's just DOF
    d = agg.dropna(subset=["foc_fwhm"])
    if len(d) > 3:
        print(f"\ncorr(foc_fwhm, N_eff) = {np.corrcoef(d.foc_fwhm, d.n_eff)[0,1]:+.3f} "
              f"(if ~+1, FWHM is just DOF/aperture, not glass quality)")
        print(f"corr(foc_fwhm, M)     = {np.corrcoef(d.foc_fwhm, d.M)[0,1]:+.3f}")
    agg.to_csv(OUT / "psffoc_summary.csv", index=False)
    print("\nwrote psffoc_summary.csv")


if __name__ == "__main__":
    main()
