"""Stage AltEst analysis — approaches 1 (spectral-ratio relative MTF + chain) and
2 (same-patch direct detail), with the validation gates.

Reads the per-config-per-patch PSD + detail CSVs and the saved patch .npy files from
poc_altest_patch_driver.py. For approach 1 it builds, for each shared patch and each
config PAIR, the PSD-RATIO relative MTF and reads it at:
  (i)  a fixed SUBJECT frequency  f_grid   (the end-to-end system comparison — CREDITS
       magnification, expected to float empty-mag);
  (ii) a fixed SENSOR frequency   f_sensor = f_grid*SPU/px_per_unit  (the M-de-confound
       attempt — read each config at the same cy/sensor-px).
It then solves a transitive least-squares chain (like comb B1) on the pairwise
log-ratios -> a global cross-config score, separately for (i) and (ii), and runs the
gates: M de-confounding (corr score vs M), empty-magnification float, known orderings,
repeatability across patches.

For approach 2 it directly compares per-patch detail metrics across configs on the
SAME patch (sharper config resolves more), aggregates over shared patches, and runs the
same gates.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_altest_lib as L

OUT = HERE / "poc_comb_chain_out" / "altest"
PATCH_DIR = OUT / "patches"
SPU = 700.0
GRID_UNIT_UM = 1965.7   # one atlas grid unit on the wafer (subject space)

# ---- known config groupings for the gates ---------------------------------- #
def lens_key(sid):
    return sid.split("_")[0]

def is_bare(config):
    return "+" not in config and " + " not in config

# donor map: +TC/diopter config -> its bare donor lens substring
DONOR = {
    "TC-1401": None, "TC-2001": None, "5T": None, "6T": None,
    "MCON-35": "100-400", "Canon 500D": "100-400",
}


def load():
    psd = pd.concat([pd.read_csv(f) for f in OUT.glob("psd_shard_*.csv")], ignore_index=True)
    det = pd.concat([pd.read_csv(f) for f in OUT.glob("det_shard_*.csv")], ignore_index=True)
    meta = pd.concat([pd.read_csv(f) for f in OUT.glob("meta_shard_*.csv")], ignore_index=True)
    meta = meta.drop_duplicates("config")
    return psd, det, meta


def chain_solve(edges, nodes):
    """Weighted LS transitive chain: edges = list of (i, j, delta, w) meaning
    score_i - score_j = delta. Gauge: zero mean. Returns dict node->score."""
    idx = {n: k for k, n in enumerate(nodes)}
    n = len(nodes)
    rows, rhs, ws = [], [], []
    for i, j, d, w in edges:
        r = np.zeros(n); r[idx[i]] = 1; r[idx[j]] = -1
        rows.append(r); rhs.append(d); ws.append(w)
    # gauge
    r = np.ones(n); rows.append(r); rhs.append(0.0); ws.append(len(edges) or 1.0)
    A = np.array(rows); b = np.array(rhs); W = np.sqrt(np.array(ws))
    sol, *_ = np.linalg.lstsq(A * W[:, None], b * W, rcond=None)
    return {nd: float(sol[k]) for nd, k in idx.items()}


def relative_mtf_chain(psd, meta, mode, f_target):
    """mode='subject' reads ratio at fixed f_grid=f_target; mode='sensor' reads at
    fixed sensor cy/px=f_target (per-config f_grid = f_target*px_per_unit/SPU)."""
    px_per_unit = dict(zip(meta.sid, meta.px_per_unit))
    Mmap = dict(zip(meta.sid, meta.M))
    # per (sid, patch): interpolate sqrt(psd) at the needed f_grid
    edges = []
    sids = sorted(psd.sid.unique())
    # group by patch; within a patch, every pair of configs that both have it -> edge
    for patch, g in psd.groupby("patch"):
        curves = {}
        for sid, gg in g.groupby("sid"):
            gg = gg.sort_values("f_grid")
            curves[sid] = (gg.f_grid.values, np.sqrt(np.clip(gg.psd.values, 1e-30, None)))
        present = list(curves)
        for a in range(len(present)):
            for b in range(a + 1, len(present)):
                sa, sb = present[a], present[b]
                fa, va = curves[sa]; fb, vb = curves[sb]
                if mode == "subject":
                    fga = fgb = f_target
                else:  # sensor: same cy/sensor-px -> different f_grid per config
                    fga = f_target * px_per_unit[sa] / SPU
                    fgb = f_target * px_per_unit[sb] / SPU
                if not (fa.min() <= fga <= fa.max() and fb.min() <= fgb <= fb.max()):
                    continue
                ma = np.interp(fga, fa, va); mb = np.interp(fgb, fb, vb)
                if ma <= 0 or mb <= 0:
                    continue
                # amplitude ratio = relative MTF (target spectrum cancels: same patch)
                edges.append((sa, sb, float(np.log(ma / mb)), 1.0))
    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
    if len(nodes) < 2:
        return None, None
    scores = chain_solve(edges, nodes)
    # connectivity (union-find) + residual consistency
    parent = {n: n for n in nodes}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, j, d, w in edges:
        parent[find(i)] = find(j)
    ncomp = len({find(n) for n in nodes})
    resid = np.sqrt(np.mean([(scores[i] - scores[j] - d) ** 2 for i, j, d, w in edges])) if edges else np.nan
    info = dict(nodes=nodes, edges=edges, Mmap=Mmap, ncomp=ncomp,
                resid=resid, n_edges=len(edges))
    return scores, info


def gate_report(scores, meta, label):
    Mmap = dict(zip(meta.sid, meta.M))
    rows = []
    for sid, sc in scores.items():
        rows.append((sid, sc, Mmap.get(sid, np.nan)))
    df = pd.DataFrame(rows, columns=["sid", "score", "M"]).sort_values("score", ascending=False)
    corr = np.corrcoef(df.M, df.score)[0, 1] if len(df) > 2 else np.nan
    print(f"\n--- {label} ---")
    print(f"corr(M, score) = {corr:+.3f}   (want ~0; +ve = floats high-M/empty-mag)")
    print(df.to_string(index=False))
    # empty-mag check: does any +TC config outrank ALL bare lenses?
    bare = df[~df.sid.str.contains(r"\+", regex=True)]
    acc = df[df.sid.str.contains(r"\+", regex=True)]
    if len(bare) and len(acc):
        top_acc = acc.score.max(); top_bare = bare.score.max()
        floats = acc[acc.score > top_bare]
        print(f"empty-mag: best accessory score {top_acc:.3f} vs best bare {top_bare:.3f}"
              f"  -> {'FLOATS ABOVE bare ('+','.join(floats.sid)+')' if len(floats) else 'OK (no float)'}")
    return df, corr


def main():
    psd, det, meta = load()
    print(f"loaded {psd.sid.nunique()} configs, {psd.patch.nunique()} patches, "
          f"{len(det)} detail rows")
    print("configs:", sorted(psd.sid.unique()))

    # ---- Approach 1: spectral-ratio relative MTF chain --------------------- #
    print("\n" + "=" * 70 + "\nAPPROACH 1 — same-patch PSD-ratio relative MTF chain\n" + "=" * 70)
    for f_grid in (0.06, 0.10, 0.15):
        sc, info = relative_mtf_chain(psd, meta, "subject", f_grid)
        if sc:
            subj_lpmm = f_grid * SPU / GRID_UNIT_UM * 1000
            print(f"\n[chain: {len(info['nodes'])} nodes, {info['n_edges']} edges, "
                  f"{info['ncomp']} component(s), resid={info['resid']:.3f}]")
            gate_report(sc, meta, f"A1 SUBJECT-freq f_grid={f_grid} (~{subj_lpmm:.0f} lp/mm subj)")
    sensor_scores = {}
    for f_px in (0.10, 0.15, 0.20):
        sc, info = relative_mtf_chain(psd, meta, "sensor", f_px)
        if sc:
            print(f"\n[chain: {len(info['nodes'])} nodes, {info['n_edges']} edges, "
                  f"{info['ncomp']} component(s), resid={info['resid']:.3f}]")
            gate_report(sc, meta, f"A1 SENSOR-freq f_px={f_px} cy/px")
            sensor_scores[f_px] = sc
    # persist the headline A1 sensor-freq scores (small committed artifact)
    Mmap = dict(zip(meta.sid, meta.M))
    allsids = sorted({s for sc in sensor_scores.values() for s in sc})
    srows = [dict(sid=s, M=Mmap.get(s),
                  **{f"score_fpx{f}": sensor_scores[f].get(s) for f in sensor_scores})
             for s in allsids]
    pd.DataFrame(srows).to_csv(OUT / "a1_sensor_scores.csv", index=False)
    print("\nwrote a1_sensor_scores.csv")

    # ---- Gate (c): repeatability of the A1 SENSOR-freq ranking across patches ---- #
    print("\n--- A1 repeatability: split patches in two halves, re-rank, Spearman ---")
    from scipy.stats import spearmanr
    pats = sorted(psd.patch.unique())
    h1 = set(pats[::2]); h2 = set(pats[1::2])
    for f_px in (0.10, 0.15):
        s1, _ = relative_mtf_chain(psd[psd.patch.isin(h1)], meta, "sensor", f_px)
        s2, _ = relative_mtf_chain(psd[psd.patch.isin(h2)], meta, "sensor", f_px)
        if s1 and s2:
            common = sorted(set(s1) & set(s2))
            rho, _ = spearmanr([s1[k] for k in common], [s2[k] for k in common])
            print(f"  f_px={f_px}: {len(common)} configs in both halves, "
                  f"Spearman rho = {rho:+.3f}  ({'repeatable' if rho > 0.7 else 'NOT repeatable'})")

    # ---- Approach 2: same-patch direct detail ------------------------------ #
    print("\n" + "=" * 70 + "\nAPPROACH 2 — same-patch direct detail metrics\n" + "=" * 70)
    for metric in ("tenengrad", "lap_energy", "hf_energy", "variance"):
        # per patch, log-ratio edges between configs (sharper = more detail)
        edges = []
        for patch, g in det.groupby("patch"):
            sub = g[["sid", metric]].dropna()
            present = sub.sid.tolist(); vals = dict(zip(sub.sid, sub[metric]))
            for a in range(len(present)):
                for b in range(a + 1, len(present)):
                    sa, sb = present[a], present[b]
                    if vals[sa] > 0 and vals[sb] > 0:
                        edges.append((sa, sb, float(np.log(vals[sa] / vals[sb])), 1.0))
        nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
        if len(nodes) > 2:
            sc = chain_solve(edges, nodes)
            gate_report(sc, meta, f"A2 detail={metric}")


if __name__ == "__main__":
    main()
