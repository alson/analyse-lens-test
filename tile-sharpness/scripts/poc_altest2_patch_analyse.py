"""Stage AltEst-2 — P1 HARDENED analysis of the same-patch PSD-ratio relative MTF.

Extends poc_altest_patch_analyse.py on the WIDENED 38-config set, adding the hardening
asked for:
  * f_px window sweep (0.08..0.30) with corr(M,score), empty-mag float, node coverage at
    each f_px -> characterises exactly where/why the trustworthy window breaks;
  * transitive-BRIDGE robustness for the M~2 configs: report each config's edge count and
    which OTHER configs it shares cells with (its "anchors"); jackknife the M~2 scores by
    dropping each anchor config and measuring score shift -> bridge sensitivity;
  * split-half repeatability (Spearman) on the wider set, at several f_px;
  * a clean per-config relative-MTF ranking with bootstrap uncertainty (resample shared
    cells) -> +-1 sigma on each score.

Reads altest2/{psd,det,meta}_shard_*.csv. Writes altest2/p1_*.csv. Read-only on libs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "poc_comb_chain_out" / "altest2"
SPU = 700.0
GRID_UNIT_UM = 1965.7

# §L known orderings to check (modern macros lead; diopter/100-400 tail; TC degrades).
MODERN_MACRO_BARE = ["Z105_1_1_F8", "AF200_1_1_F8", "S105_1_1_F8", "S150_1_1_F8"]
VINTAGE = ["V55f28287318_1_1_F8", "V55f28537016_1_1_F8", "V55f35209088_1_1_F8",
           "V55f35258263_1_1_F8", "AF60_1_1_F8"]
DIOPTER_TAIL = ["Z100400+MCON-35_1_1.16_F8", "Z100400+C500D_1.07_1_F8"]


def load():
    psd = pd.concat([pd.read_csv(f) for f in OUT.glob("psd_shard_*.csv")], ignore_index=True)
    meta = pd.concat([pd.read_csv(f) for f in OUT.glob("meta_shard_*.csv")], ignore_index=True)
    meta = meta.drop_duplicates("config")
    return psd, meta


def chain_solve(edges, nodes):
    idx = {n: k for k, n in enumerate(nodes)}; n = len(nodes)
    rows, rhs, ws = [], [], []
    for i, j, d, w in edges:
        r = np.zeros(n); r[idx[i]] = 1; r[idx[j]] = -1
        rows.append(r); rhs.append(d); ws.append(w)
    rows.append(np.ones(n)); rhs.append(0.0); ws.append(len(edges) or 1.0)
    A = np.array(rows); b = np.array(rhs); W = np.sqrt(np.array(ws))
    sol, *_ = np.linalg.lstsq(A * W[:, None], b * W, rcond=None)
    return {nd: float(sol[k]) for nd, k in idx.items()}


def build_edges(psd, meta, mode, f_target, patches=None):
    ppu = dict(zip(meta.sid, meta.px_per_unit))
    if patches is not None:
        psd = psd[psd.patch.isin(patches)]
    edges = []
    pair_cells = {}  # (sa,sb) -> set of cells
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
                else:
                    if sa not in ppu or sb not in ppu:
                        continue
                    fga = f_target * ppu[sa] / SPU
                    fgb = f_target * ppu[sb] / SPU
                if not (fa.min() <= fga <= fa.max() and fb.min() <= fgb <= fb.max()):
                    continue
                ma = np.interp(fga, fa, va); mb = np.interp(fgb, fb, vb)
                if ma <= 0 or mb <= 0:
                    continue
                edges.append((sa, sb, float(np.log(ma / mb)), 1.0))
                pair_cells.setdefault((sa, sb), set()).add(patch)
    return edges, pair_cells


def solve(edges):
    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
    if len(nodes) < 2:
        return None, None, None
    scores = chain_solve(edges, nodes)
    parent = {n: n for n in nodes}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, j, d, w in edges:
        parent[find(i)] = find(j)
    ncomp = len({find(n) for n in nodes})
    resid = np.sqrt(np.mean([(scores[i] - scores[j] - d) ** 2 for i, j, d, w in edges]))
    return scores, ncomp, resid


def gate_summary(scores, Mmap, label):
    df = pd.DataFrame([(s, sc, Mmap.get(s)) for s, sc in scores.items()],
                      columns=["sid", "score", "M"]).sort_values("score", ascending=False)
    corr = np.corrcoef(df.M, df.score)[0, 1] if len(df) > 2 else np.nan
    bare = df[~df.sid.str.contains(r"\+", regex=True)]
    acc = df[df.sid.str.contains(r"\+", regex=True)]
    floats = []
    if len(bare) and len(acc):
        top_bare = bare.score.max()
        floats = acc[acc.score > top_bare].sid.tolist()
    return df, corr, floats


def main():
    from scipy.stats import spearmanr
    psd, meta = load()
    Mmap = dict(zip(meta.sid, meta.M))
    print(f"loaded {psd.sid.nunique()} configs, {psd.patch.nunique()} patches")

    # ---- f_px window sweep (sensor mode) -------------------------------------- #
    print("\n" + "=" * 72 + "\nP1 — f_px window sweep (SENSOR mode)\n" + "=" * 72)
    sweep_rows = []
    scores_by_fpx = {}
    for f_px in (0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30):
        edges, pc = build_edges(psd, meta, "sensor", f_px)
        sc, ncomp, resid = solve(edges)
        if sc is None:
            continue
        scores_by_fpx[f_px] = (sc, pc)
        df, corr, floats = gate_summary(sc, Mmap, f"f_px={f_px}")
        sweep_rows.append(dict(f_px=f_px, n_nodes=len(sc), n_edges=len(edges),
                               ncomp=ncomp, resid=round(resid, 3), corr_M=round(corr, 3),
                               empty_mag_floats=";".join(floats) or "none"))
        print(f"f_px={f_px:.2f}: nodes={len(sc):2d} edges={len(edges):5d} comp={ncomp} "
              f"resid={resid:.3f} corr(M,score)={corr:+.3f} floats={floats or 'none'}")
    pd.DataFrame(sweep_rows).to_csv(OUT / "p1_fpx_sweep.csv", index=False)

    # ---- detailed ranking + bootstrap uncertainty at the trustworthy points --- #
    for f_px in (0.10, 0.12, 0.15):
        if f_px not in scores_by_fpx:
            continue
        sc, pc = scores_by_fpx[f_px]
        df, corr, floats = gate_summary(sc, Mmap, "")
        # bootstrap: resample patches with replacement, re-solve, collect score spread
        pats = sorted(psd.patch.unique())
        boots = {s: [] for s in sc}
        rng = np.random.default_rng(0)
        for _ in range(120):
            bp = rng.choice(pats, size=len(pats), replace=True)
            edges, _ = build_edges(psd[psd.patch.isin(set(bp))], meta, "sensor", f_px)
            bs, _, _ = solve(edges)
            if bs:
                for s in bs:
                    boots[s].append(bs[s])
        df["sigma"] = df.sid.map(lambda s: float(np.std(boots[s])) if boots[s] else np.nan)
        df["n_edges"] = df.sid.map(lambda s: sum(len(v) for k, v in pc.items() if s in k))
        print(f"\n--- P1 SENSOR-freq f_px={f_px} ranking (corr(M)={corr:+.3f}; "
              f"floats={floats or 'none'}) ---")
        print(df.round(3).to_string(index=False))
        df.round(4).to_csv(OUT / f"p1_ranking_fpx{f_px}.csv", index=False)

        # §L gate checks
        present = set(df.sid)
        def med_rank(group):
            rk = {s: i for i, s in enumerate(df.sid)}
            vals = [rk[s] for s in group if s in rk]
            return np.median(vals) if vals else np.nan
        print(f"  §L: median rank modern-macro-bare={med_rank(MODERN_MACRO_BARE):.1f}, "
              f"vintage55/60={med_rank(VINTAGE):.1f}, diopter-tail={med_rank(DIOPTER_TAIL):.1f} "
              f"(lower=sharper; want macro<vintage<diopter)")

    # ---- transitive-bridge robustness for the M~2 configs --------------------- #
    print("\n" + "=" * 72 + "\nP1 — M~2 transitive-bridge robustness (jackknife anchors)\n" + "=" * 72)
    f_px = 0.10
    sc, pc = scores_by_fpx[f_px]
    m2 = [s for s in sc if Mmap.get(s, 0) > 1.9]
    for target in m2:
        anchors = sorted({(b if a == target else a) for (a, b) in pc if target in (a, b)},
                         key=lambda s: -sum(1 for k in pc if target in k and s in k))
        ncells = {anc: sum(1 for k in pc if target in k and anc in k) for anc in anchors}
        base = sc[target]
        shifts = []
        for drop in anchors:
            keep_sids = set(sc) - {drop}
            sub = psd[psd.sid.isin(keep_sids)]
            edges, _ = build_edges(sub, meta, "sensor", f_px)
            s2, _, _ = solve(edges)
            if s2 and target in s2:
                shifts.append((drop, ncells[drop], s2[target] - base))
        print(f"\n{target} (M={Mmap[target]:.2f}) base score={base:+.3f}, "
              f"{len(anchors)} anchors, total shared cells={sum(ncells.values())}")
        for drop, nc, sh in sorted(shifts, key=lambda r: -abs(r[2]))[:6]:
            print(f"   drop {drop:28s} (-{nc:2d} cells): score shift {sh:+.3f}")
        worst = max((abs(s[2]) for s in shifts), default=0)
        print(f"   worst single-anchor shift: {worst:.3f}  "
              f"({'ROBUST' if worst < 0.15 else 'SENSITIVE'})")

    # ---- split-half repeatability --------------------------------------------- #
    print("\n" + "=" * 72 + "\nP1 — split-half repeatability (Spearman)\n" + "=" * 72)
    pats = sorted(psd.patch.unique())
    h1 = set(pats[::2]); h2 = set(pats[1::2])
    for f_px in (0.10, 0.12, 0.15):
        e1, _ = build_edges(psd[psd.patch.isin(h1)], meta, "sensor", f_px)
        e2, _ = build_edges(psd[psd.patch.isin(h2)], meta, "sensor", f_px)
        s1, _, _ = solve(e1); s2, _, _ = solve(e2)
        if s1 and s2:
            common = sorted(set(s1) & set(s2))
            rho, _ = spearmanr([s1[k] for k in common], [s2[k] for k in common])
            print(f"f_px={f_px}: {len(common)} configs both halves, Spearman={rho:+.3f} "
                  f"({'repeatable' if rho > 0.7 else 'NOT repeatable'})")

    # ---- subject-freq control (should re-introduce the M-confound) ------------ #
    print("\n" + "=" * 72 + "\nP1 — SUBJECT-freq control (expect M-confound returns)\n" + "=" * 72)
    for f_grid in (0.06, 0.10):
        edges, _ = build_edges(psd, meta, "subject", f_grid)
        sc, _, _ = solve(edges)
        if sc:
            df, corr, floats = gate_summary(sc, Mmap, "")
            print(f"f_grid={f_grid}: corr(M,score)={corr:+.3f} floats={floats[:4] or 'none'}")


if __name__ == "__main__":
    main()
