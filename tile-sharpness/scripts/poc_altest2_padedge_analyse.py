"""Stage AltEst-2 — P3.1 pad-edge MTF gates. Per-config averaged-ESF MTF read at fixed
sensor frequency + ERF sigma. Reads padedge_shard_*.csv; runs the four gates."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "poc_comb_chain_out" / "altest2"
ACC = r"\+"
MODERN = ["Z105_1_1_F8", "AF200_1_1_F8", "S105_1_1_F8", "S150_1_1_F8"]
VINTAGE = ["V55f28287318_1_1_F8", "V55f28537016_1_1_F8", "V55f35209088_1_1_F8",
           "V55f35258263_1_1_F8", "AF60_1_1_F8"]


def gate(df, col, label, higher_is_sharper):
    d = df.dropna(subset=[col]).copy()
    if len(d) < 4:
        print(f"\n--- {label}: only {len(d)} configs (COVERAGE fail) ---")
        print(d[["sid", "M", col]].to_string(index=False))
        return
    d = d.sort_values(col, ascending=not higher_is_sharper).reset_index(drop=True)
    d["rank"] = range(1, len(d) + 1)
    sgn = 1.0 if higher_is_sharper else -1.0
    corr = np.corrcoef(d.M, sgn * d[col])[0, 1]
    print(f"\n--- {label} ({len(d)} configs) ---")
    print(f"corr(M, sharpness) = {corr:+.3f}")
    print(d[["rank", "sid", "M", "n_edge_samples", col]].round(3).to_string(index=False))
    bare = d[~d.sid.str.contains(ACC, regex=True)]
    acc = d[d.sid.str.contains(ACC, regex=True)]
    if len(bare) and len(acc):
        bbr = bare["rank"].min()
        floats = acc[acc["rank"] < bbr]
        print(f"empty-mag: best bare rank={bbr} ({bare.iloc[0].sid}); "
              f"accessory above it: {'NONE (OK)' if not len(floats) else ', '.join(floats.sid)}")
    rk = {s: i for i, s in enumerate(d.sid)}
    mm = np.median([rk[s] for s in MODERN if s in rk]) if any(s in rk for s in MODERN) else np.nan
    vv = np.median([rk[s] for s in VINTAGE if s in rk]) if any(s in rk for s in VINTAGE) else np.nan
    print(f"§L: median rank modern-bare={mm}, vintage55/60={vv} (want modern<vintage)")


def main():
    files = list(OUT.glob("padedge_shard_*.csv"))
    if not files:
        print("no padedge shards"); return
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates("config")
    print(f"loaded {len(df)} configs with a valid averaged-ESF read "
          f"(of 38 attempted -> coverage {len(df)}/38)")
    gate(df, "mtf_fpx0.15", "P3.1 pad-edge MTF @ f_px=0.15 (cy/px)", higher_is_sharper=True)
    gate(df, "mtf_fpx0.1", "P3.1 pad-edge MTF @ f_px=0.10 (cy/px)", higher_is_sharper=True)
    gate(df, "sigma_px", "P3.1 pad-edge ERF sigma (px; smaller=sharper)", higher_is_sharper=False)
    gate(df, "mtf50_cypx", "P3.1 pad-edge MTF50 (cy/px)", higher_is_sharper=True)
    df.to_csv(OUT / "p31_padedge_summary.csv", index=False)
    print("\nwrote p31_padedge_summary.csv")


if __name__ == "__main__":
    main()
