"""Stage AltEst approach 5 analysis — direction-aware SE-edge MTF50 at fixed sensor
frequency, with gates. Reads edge_shard_*.csv."""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "poc_comb_chain_out" / "altest"


def main():
    files = list(OUT.glob("edge_shard_*.csv"))
    if not files:
        print("no edge shards"); return
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.dropna(subset=["mtf50_cypx"])
    for col in ("M", "mtf50_cypx", "mtf50_subj", "over", "n_eff", "ceil_cypx"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    print(f"coverage: {df.sid.nunique()} configs with a valid SE-edge MTF50 "
          f"(of 16 — sparse feature)")
    df = df.sort_values("mtf50_subj", ascending=False)
    print("\n=== SE-edge MTF50 (sensor cy/px and subject lp-cy/px x M) vs ceiling ===")
    print(df[["sid", "M", "n_eff", "ceil_cypx", "mtf50_cypx", "over", "mtf50_subj",
              "n_edges"]].to_string(index=False))
    # gates
    if len(df) > 3 and df.M.nunique() > 1 and df.mtf50_cypx.nunique() > 1:
        # sensor-space: corr(M, mtf50_cypx) — high-M reads lower sensor cy/px? (DOF/diffraction)
        print(f"\ncorr(M, mtf50_cypx sensor) = {np.corrcoef(df.M, df.mtf50_cypx)[0,1]:+.3f}")
        print(f"corr(M, mtf50_subj)        = {np.corrcoef(df.M, df.mtf50_subj)[0,1]:+.3f}"
              " (want ~0; +ve = subject MTF50 credits magnification)")
        bare = df[~df.sid.str.contains(r"\+", regex=True)]
        acc = df[df.sid.str.contains(r"\+", regex=True)]
        if len(bare) and len(acc):
            tb = bare.mtf50_subj.max()
            fl = acc[acc.mtf50_subj > tb]
            print(f"empty-mag (subject MTF50): best bare {bare.iloc[0].sid} {tb:.3f}; "
                  f"accessory above it: {'NONE (OK)' if not len(fl) else ', '.join(fl.sid)}")
        over = (df.over > 1.1).sum()
        print(f"reads over diffraction ceiling (>1.1x): {over}/{len(df)} "
              "(SE edge should read <= ceiling if trustworthy)")
    df.to_csv(OUT / "edge_summary.csv", index=False)
    print("\nwrote edge_summary.csv")


if __name__ == "__main__":
    main()
