"""B1 analysis + the four gate metrics.

Reads the A1 long table (concatenated shards), builds the transitive least-squares
chain (poc_comb_chain_lib.build_chain), and reports:
  1. Connectivity   — connected components over shared-frequency edges.
  2. Consistency    — least-squares residual RMS + sign-inconsistent triangles.
  3. Cross-M transitivity — find >=1 ranking link between configs sharing NO direct
     frequency, established via an intermediary.
  4. Sanity vs known — bare 105 ~ 150; 105+TC20 >= 150+TC20; modern macros > stacks.

Usage: python scripts/poc_comb_chain_b1_analyse.py out/a1_all.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402


def load_rows(path):
    out = []
    for r in csv.DictReader(open(path)):
        out.append(dict(config=r["config"], M=float(r["M"]), feature=r["feature"],
                        harmonic_order=int(r["harmonic_order"]),
                        f_subj_lpmm=float(r["f_subj_lpmm"]),
                        contrast=float(r["contrast"]), snr=float(r["snr"]),
                        ceiling=float(r["ceiling"]),
                        over_ceiling=float(r["over_ceiling"])))
    return out


def direct_shared(res, ca, cb):
    """Do configs ca, cb share a direct frequency node (both valid)?"""
    na = set(res["cfg_node"].get(ca, {})); nb = set(res["cfg_node"].get(cb, {}))
    return na & nb


def main():
    path = sys.argv[1]
    agg = sys.argv[2] if len(sys.argv) > 2 else "median"
    rows = load_rows(path)
    # carry M per config for reporting
    M_by_cfg = {}
    for r in csv.DictReader(open(path)):
        M_by_cfg[r["config"]] = float(r["M"])
    print(f"(aggregation = {agg})")
    res = L.build_chain(rows, freq_tol_lpmm=4.0, snr_min=3.0, max_over=0.05, agg=agg)

    print("=" * 80)
    print("B1 CHAIN — least-squares cross-config sharpness ranking")
    print("=" * 80)
    print(f"configs in graph: {len(res['configs'])}")
    print(f"shared-frequency nodes (>=2 configs): {res['n_nodes']}")
    print(f"edges (config pairs sharing >=1 node): {res['n_edges']}")

    print("\n--- GATE 1: CONNECTIVITY ---")
    comps = res["components"]
    print(f"connected components: {len(comps)}")
    for i, comp in enumerate(comps):
        print(f"  component {i}: {len(comp)} configs"
              + ("" if len(comp) > 1 else f"  ISOLATED -> {comp[0]}"))
    isolated = [c for comp in comps if len(comp) == 1 for c in comp]
    all_cfgs = set(res["configs"])
    # configs that produced rows but no valid edges at all
    print(f"isolated nodes: {len(isolated)}")
    for c in isolated:
        print(f"    ISOLATED: {c}")

    print("\n--- GATE 2: CONSISTENCY ---")
    print(f"least-squares residual RMS (log-contrast): {res['residual_rms']:.4f} "
          f"(= {100*(2.718**res['residual_rms']-1):.1f}% typical edge mismatch)")
    print(f"triangles examined: {res['n_triangles']}, "
          f"sign/magnitude-inconsistent (>0.20 log): {res['n_triangles_inconsistent']}")
    if res["n_triangles"]:
        print(f"  inconsistent fraction: {res['n_triangles_inconsistent']/res['n_triangles']*100:.1f}%")

    print("\n--- RANKING ---")
    for rank, (cfg, s) in enumerate(res["ranking"], 1):
        print(f"  {rank:>2}. s={s:+.3f}  M={M_by_cfg.get(cfg,float('nan')):.2f}  {cfg}")

    print("\n--- GATE 3: CROSS-M TRANSITIVITY ---")
    # The maze rung (M-invariant 76.9 lp/mm) is shared by nearly every config, so with
    # it included almost all pairs are DIRECTLY connected — transitivity is then trivial
    # and uninformative. The real test of the core claim: DROP the maze and ask whether a
    # low-M-only and a high-M-only config — which then share NO direct pad rung — are
    # still linked through a mid-M intermediary's overlapping pad harmonics.
    import collections
    res_nomaze = L.build_chain(rows, freq_tol_lpmm=4.0, snr_min=3.0, max_over=0.05,
                               agg=agg, drop_features=("maze",))
    adj = collections.defaultdict(set)
    for ii, jj, *_ in res_nomaze["edges"]:
        adj[res_nomaze["configs"][ii]].add(res_nomaze["configs"][jj])
        adj[res_nomaze["configs"][jj]].add(res_nomaze["configs"][ii])

    def nm_shared(ca, cb):
        na = set(res_nomaze["cfg_node"].get(ca, {})); nb = set(res_nomaze["cfg_node"].get(cb, {}))
        return na & nb

    def bfs_path(src, dst):
        from collections import deque
        q = deque([[src]]); seen = {src}
        while q:
            p = q.popleft()
            if p[-1] == dst:
                return p
            for nb in adj[p[-1]]:
                if nb not in seen:
                    seen.add(nb); q.append(p + [nb])
        return None

    print(f"  (maze-removed graph: {res_nomaze['n_edges']} pad-only edges, "
          f"{len(res_nomaze['components'])} component(s))")
    found = 0
    cfgs = res_nomaze["configs"]
    # prioritise the largest-ΔM pairs (most convincing cross-M links)
    pairs = [(cfgs[a], cfgs[b]) for a in range(len(cfgs)) for b in range(a + 1, len(cfgs))]
    pairs.sort(key=lambda p: -abs(M_by_cfg.get(p[0], 0) - M_by_cfg.get(p[1], 0)))
    for ca, cb in pairs:
        dM = abs(M_by_cfg.get(ca, 0) - M_by_cfg.get(cb, 0))
        if dM < 0.7:
            continue
        if nm_shared(ca, cb):
            continue
        path = bfs_path(ca, cb)
        if path and len(path) >= 3:
            sa = res["scores"].get(ca, 0.0); sb = res["scores"].get(cb, 0.0)
            rel = "≈" if abs(sa - sb) < 0.10 else (">" if sa > sb else "<")
            print(f"  LINK (NO direct pad rung shared, ΔM={dM:.2f}):"
                  f"\n    {ca} (M={M_by_cfg[ca]:.2f}, s={sa:+.3f})"
                  f"\n    {rel} {cb} (M={M_by_cfg[cb]:.2f}, s={sb:+.3f})"
                  f"\n    via pad-rung path: "
                  + " -> ".join(f"{p.split(' | ')[0][:16]}(M{M_by_cfg[p]:.1f})" for p in path))
            found += 1
            if found >= 2:
                break
    if not found:
        print("  NO pad-only cross-M indirect link found — the cross-M claim rests on the"
              " maze rung alone (which DOES link all M, but is a single shared frequency).")

    print("\n--- GATE 4: SANITY vs KNOWN ---")
    sc = res["scores"]
    def get(substr_list, exclude=()):
        for c, s in sc.items():
            if all(x in c for x in substr_list) and not any(x in c for x in exclude):
                return c, s
        return None, None

    checks = []
    # bare = no accessory: exclude any config with a '+' in the lens segment
    c105, s105 = get(["Sigma Macro 105", "1_1", "F8"], exclude=["+"])
    c150, s150 = get(["Sigma APO Macro 150", "1_1", "F8"], exclude=["+"])
    if s105 is not None and s150 is not None:
        checks.append(("bare Sigma 105 ≈ bare 150 (within ~0.15 log)",
                       abs(s105 - s150) < 0.15, f"105 s={s105:+.3f} vs 150 s={s150:+.3f}"))
    c105t2, s105t2 = get(["Sigma Macro 105", "TC-2001", "2_1"])
    c150t2, s150t2 = get(["Sigma APO Macro 150", "TC-2001", "2_1"])
    if s105t2 is not None and s150t2 is not None:
        checks.append(("105+TC20 @2:1 ≥ 150+TC20 @2:1 (105 tolerates TCs better)",
                       s105t2 >= s150t2 - 0.05, f"105+TC20 s={s105t2:+.3f} vs 150+TC20 s={s150t2:+.3f}"))
    # modern macro > heavy stack
    cstack, sstack = get(["Sigma Macro 105", "5T + 6T"])
    if s105 is not None and sstack is not None:
        checks.append(("bare modern macro > 105+5T+6T stack",
                       s105 > sstack, f"bare105 s={s105:+.3f} vs 105+5T+6T s={sstack:+.3f}"))
    # diopter should be lower-ish
    cdio, sdio = get(["Canon 500D"])
    if s105 is not None and sdio is not None:
        checks.append(("bare modern macro > 100-400+Canon 500D diopter",
                       s105 > sdio, f"bare105 s={s105:+.3f} vs 100-400+500D s={sdio:+.3f}"))
    for desc, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {desc}\n          {detail}")

    print("\n--- VERDICT ---")
    one_component = len([c for c in comps if len(c) > 1]) <= 1 and len(isolated) == 0
    consistent = res["residual_rms"] < 0.35 and (
        res["n_triangles"] == 0 or res["n_triangles_inconsistent"] / max(1, res["n_triangles"]) < 0.25)
    sanity_ok = sum(1 for _, ok, _ in checks if ok) >= max(1, len(checks) - 1)
    # The CORE claim is a cross-M ranking via a COMB of shared rungs. A pass therefore
    # requires (a) a pad-only indirect cross-M link (the comb, not just the single maze
    # frequency) AND (b) the sanity checks — including bare~bare and NO empty-mag config
    # ranking above the bare lens it is built from. Maze-only connectivity is NOT enough.
    pad_crossM = found > 0
    # empty-magnification check: does any +accessory config outrank its bare donor?
    empty_mag_violation = False
    rk = res["ranking"]
    pos = {c: i for i, (c, _) in enumerate(rk)}
    for c in res["configs"]:
        if "TC-" in c or "5T" in c or "6T" in c:
            # find a plausible bare donor by lens family
            fam = "Sigma Macro 105" if "Sigma Macro 105" in c else (
                  "Sigma APO Macro 150" if "Sigma APO Macro 150" in c else (
                  "NIKKOR Z MC 105" if "NIKKOR Z MC 105" in c else None))
            if fam:
                bc, _ = get([fam, "1_1", "F8"], exclude=["+"])
                if bc and pos.get(c, 99) < pos.get(bc, 99):
                    empty_mag_violation = True
    print(f"  connectivity (single component, no isolates): {one_component}")
    print(f"  consistency (resid<0.35, <25% bad triangles): {consistent}")
    print(f"  cross-M via PAD COMB (maze removed): {pad_crossM}  "
          f"(maze-only connects all M but is one frequency, not a comb)")
    print(f"  sanity vs known ({sum(1 for _,ok,_ in checks if ok)}/{len(checks)} pass): {sanity_ok}")
    print(f"  empty-magnification violation (TC/ext outranks its bare donor): {empty_mag_violation}")
    hold = one_component and consistent and pad_crossM and sanity_ok and not empty_mag_violation
    print(f"\n  >>> CHAIN HOLDS: {hold} <<<")


if __name__ == "__main__":
    main()
