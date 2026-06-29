"""Stage Relock — Phase B step 2: cross-M self-calibration collapse on the RE-ANCHORED
comb (relock_all.csv). The decisive question: with the comb anchored on each region's
TRUE per-axis coarse grid (so the harmonics are a genuine harmonic series of the real
fundamental), does the Stage-T_n collapse residual DROP toward the within-config noise
floor (reviving cross-M ranking), or does it stay unstable?

UNTRACKED / exploratory. Reuses the Stage-T_n self-cal machinery (self_calibrate,
isotonic_decreasing) imported from poc_comb_chain_tn_analyse — read-only.

STRUCTURE TYPING. The relock reads u and v as SEPARATE axis-locked combs (Phase A: u and v
are genuinely different gratings, often anisotropic). So a structure type here is
(cls, axis, anchor-pitch cluster). We never pool u with v or different pitch clusters.

Compared head-to-head against the PRIOR (production-anchored) Stage-T_n / Stage-Targets
numbers: magenta.P11 collapse 0.790 (floor 0.392); maze 0.842 (floor 0.490); cleanest die
0.624 (floor 0.19).

Usage (nufan):
  PYTHONPATH=<src> ~/.cache/uv-venvs/tile-sharpness/bin/python \
      scripts/poc_comb_chain_relock_b_analyse.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_tn_analyse as T  # noqa: E402  (self_calibrate, isotonic_decreasing)

OUT = HERE / "poc_comb_chain_out" / "relock"
OUT.mkdir(parents=True, exist_ok=True)

SNR_MIN = 3.0
MAX_OVER = 0.05
MIN_C = 1e-3

# anchor-pitch clusters (PIXEL pitch of the relocked coarse fundamental, M-dependent so
# we cluster in SUBJECT lp/mm of the fundamental instead — robust across M).
# fundamental subj lp/mm ~ f0_px * 229.9 * M. Observed clusters ~6-10 (coarse ~30px) and
# a finer tail. We bucket the fundamental subject freq.
FUND_CLUSTERS = [("C8", 4.0, 11.0), ("C14", 11.0, 22.0), ("C28", 22.0, 40.0)]


def load(path):
    rows = []
    for r in csv.DictReader(open(path)):
        try:
            rows.append(dict(
                config=r["config"], M=float(r["M"]), region=r["region"],
                cls=r["cls"], axis=r["axis"], feature=r["feature"],
                anchor_pitch=(float(r["anchor_pitch_px"]) if r["anchor_pitch_px"] else float("nan")),
                order=int(r["harmonic_order"]),
                f_subj=float(r["f_subj_lpmm"]), f_px=float(r["f_px"]),
                C=float(r["contrast"]), snr=float(r["snr"]),
                over=float(r["over_ceiling"])))
        except (ValueError, KeyError):
            continue
    return rows


def valid(r):
    return r["snr"] >= SNR_MIN and r["over"] <= MAX_OVER and r["C"] > MIN_C


def fund_subj(r):
    return r["f_subj"] / max(1, r["order"])


def stype(r):
    if r["feature"] == "maze":
        return "maze"
    f1 = fund_subj(r)
    for name, lo, hi in FUND_CLUSTERS:
        if lo <= f1 < hi:
            return f"{r['cls']}.{r['axis']}.{name}"
    return None


def per_order_null(teeth):
    null_res = []
    for o in set(t["order"] for t in teeth):
        vals = np.array([t["logA"] for t in teeth if t["order"] == o])
        ww = np.array([t["w"] for t in teeth if t["order"] == o])
        if len(vals) < 2:
            continue
        null_res.append(np.sum(ww * (vals - np.average(vals, weights=ww)) ** 2))
    null_n = sum(t["w"] for t in teeth)
    return float(np.sqrt(sum(null_res) / null_n)) if null_n else float("nan")


def within_config_floor(teeth):
    byc = defaultdict(list)
    for t in teeth:
        byc[t["config"]].append(t)
    res = []
    for cfg, ts in byc.items():
        if len(ts) < 6 or len(set(t["order"] for t in ts)) < 2:
            continue
        cal = T.self_calibrate(ts)
        res.append(cal["residual_rms"])
    return (float(np.median(res)) if res else float("nan")), len(res)


def main():
    rows = load(HERE / "poc_comb_chain_out" / "relock" / "relock_all.csv")
    rows = [r for r in rows if valid(r)]
    for r in rows:
        r["stype"] = stype(r)
        r["logA"] = np.log(max(r["C"], MIN_C))
        r["w"] = float(np.log1p(r["snr"]))
    typed = [r for r in rows if r["stype"] is not None]
    print(f"valid relocked teeth: {len(rows)}  (typed: {len(typed)})")

    by_type = defaultdict(list)
    for r in typed:
        by_type[r["stype"]].append(r)

    print("\nstructure-type tooth counts (RELOCKED, per-axis):")
    for st in sorted(by_type):
        ts = by_type[st]
        nconf = len(set(t["config"] for t in ts))
        ords = sorted(set(t["order"] for t in ts))
        fr = [t["f_px"] for t in ts]
        ap = [t["anchor_pitch"] for t in ts if t["anchor_pitch"] == t["anchor_pitch"]]
        print(f"  {st:18s} n={len(ts):4d} configs={nconf:2d} orders={ords} "
              f"f_px[{min(fr):.3f},{max(fr):.3f}] "
              f"anchorPx~{np.median(ap):.0f}" if ap else f"  {st:18s} n={len(ts)}")

    print("\n" + "=" * 92)
    print("PHASE B — cross-M self-calibration collapse on the RE-ANCHORED comb")
    print("  resid = cross-M collapse (want -> within-config floor). PRIOR(prod-anchor):")
    print("    magenta.P11 0.790 (floor 0.392); maze 0.842 (floor 0.490); cleanest die 0.624 (floor 0.19)")
    print("=" * 92)
    print(f"{'target':<20}{'nteeth':<8}{'configs':<9}{'collapse':<10}"
          f"{'perOrdNull':<12}{'withinFloor':<12}{'ratio':<8}{'verdict'}")

    results = []
    for st in sorted(by_type):
        teeth = by_type[st]
        nconf = len(set(t["config"] for t in teeth))
        if len(teeth) < 8 or len(set(t["order"] for t in teeth)) < 2:
            print(f"{st:<20}{len(teeth):<8}{nconf:<9}{'--too few':<10}")
            continue
        cal = T.self_calibrate(teeth)
        null = per_order_null(teeth)
        floor, nfloor = within_config_floor(teeth)
        ratio = cal["residual_rms"] / floor if floor == floor and floor > 0 else float("nan")
        margin_null = (null - cal["residual_rms"]) / null if null else 0
        if ratio == ratio and ratio < 1.3 and margin_null > 0.2:
            verdict = "STABLE*"
        elif margin_null > 0.15:
            verdict = "marginal"
        else:
            verdict = "UNSTABLE"
        print(f"{st:<20}{len(teeth):<8}{nconf:<9}{cal['residual_rms']:<10.3f}"
              f"{null:<12.3f}{floor:<12.3f}{ratio:<8.2f}{verdict}")
        results.append((st, len(teeth), nconf, cal["residual_rms"], null, floor, ratio, verdict))

    # low-order-only (orders<=3) for the data-rich pad clusters
    print("\n--- low-order-only (orders<=3) ---")
    for st in sorted(by_type):
        if st == "maze":
            continue
        teeth = [t for t in by_type[st] if t["order"] <= 3]
        if len(teeth) < 8 or len(set(t["order"] for t in teeth)) < 2:
            continue
        cal = T.self_calibrate(teeth)
        null = per_order_null(teeth)
        floor, _ = within_config_floor(teeth)
        ratio = cal["residual_rms"] / floor if floor == floor and floor > 0 else float("nan")
        print(f"  {st:<18} orders<=3: collapse={cal['residual_rms']:.3f} "
              f"null={null:.3f} floor={floor:.3f} ratio={ratio:.2f}")

    # ===== single cleanest region class (the Phase-A v-axis winner: 5C/5D/9C type) =====
    # die type (1,2) / (1,3), v-axis, ~30px coarse grid. Pool by (region-pattern, v-axis).
    print("\n" + "=" * 92)
    print("Cleanest v-axis coarse grid (the ~30px dominant feature Phase A found, SNR 120-254)")
    print("=" * 92)
    vrich = [t for t in typed if t["axis"] == "v" and t["cls"] == "magenta"
             and 22 <= (t["anchor_pitch"] if t["anchor_pitch"] == t["anchor_pitch"] else 0) <= 40]
    if len(vrich) >= 8:
        cal = T.self_calibrate(vrich)
        null = per_order_null(vrich)
        floor, nfl = within_config_floor(vrich)
        ratio = cal["residual_rms"] / floor if floor == floor and floor > 0 else float("nan")
        nconf = len(set(t["config"] for t in vrich))
        print(f"  magenta v-axis ~30px: n={len(vrich)} configs={nconf} "
              f"collapse={cal['residual_rms']:.3f} null={null:.3f} floor={floor:.3f} "
              f"ratio={ratio:.2f}")
        results.append(("magenta.v.30px_clean", len(vrich), nconf,
                        cal["residual_rms"], null, floor, ratio,
                        "STABLE*" if ratio < 1.3 else "UNSTABLE"))

    # ===== cross-structure: pad(u) vs pad(v) vs maze MTF agreement at shared f_px =====
    print("\n" + "=" * 92)
    print("Cross-structure agreement at shared f_px (RE-ANCHORED) — want ~1x")
    print("=" * 92)
    # build per-(stype) self-cal, then per-config MTF samples = A_n / T_n
    cals = {}
    for st, teeth in by_type.items():
        if len(teeth) >= 8 and len(set(t["order"] for t in teeth)) >= 2:
            cals[st] = T.self_calibrate(teeth)
    cfg_mtf = defaultdict(list)
    for r in typed:
        st = r["stype"]
        if st not in cals:
            continue
        logT = cals[st]["Tn"].get(r["order"])
        if logT is None:
            continue
        cfg_mtf[r["config"]].append((r["f_px"], np.exp(r["logA"] - logT), st))
    # physicality
    allm = np.array([m for v in cfg_mtf.values() for (_, m, _) in v])
    if len(allm):
        print(f"  physicality: n={len(allm)} >1.0={100*np.mean(allm>1.0):.1f}% "
              f"median={np.median(allm):.3f} p95={np.percentile(allm,95):.3f}")
    # pad-v vs maze ratio at shared f_px
    for padkind in ("v", "u"):
        ratios = []
        for cfg, samps in cfg_mtf.items():
            pads = [(f, m) for (f, m, st) in samps if st.startswith(f"magenta.{padkind}")]
            mazes = [(f, m) for (f, m, st) in samps if st == "maze"]
            for fm, mm in mazes:
                cand = [(abs(fp - fm), mp) for fp, mp in pads if abs(fp - fm) < 0.02 and mp > 0 and mm > 0]
                if cand:
                    cand.sort(); ratios.append(cand[0][1] / mm)
        if ratios:
            ratios = np.array(ratios)
            print(f"  pad_{padkind} vs maze: n={len(ratios)} median={np.median(ratios):.2f}x "
                  f"geomean={np.exp(np.mean(np.log(ratios))):.2f}x log-spread={np.std(np.log(ratios)):.2f}")

    # ===== ranking sanity + empty-magnification (the decision-relevant gate) =====
    print("\n" + "=" * 92)
    print("RANKING SANITY (re-anchored, structure-corrected MTF) — the empty-magnification test")
    print("=" * 92)
    M_of = {r["config"]: r["M"] for r in typed}

    def interp_cfg(cfg, fpx, stype_pref=None):
        samps = [(f, m) for (f, m, st) in cfg_mtf[cfg]
                 if (stype_pref is None or st == stype_pref) and m > 0]
        if len(samps) < 2:
            return None
        xs = np.array([s[0] for s in samps]); ys = np.array([s[1] for s in samps])
        o = np.argsort(xs); xs, ys = xs[o], ys[o]
        ux = np.unique(xs)
        uy = np.array([np.exp(np.mean(np.log(ys[xs == v]))) for v in ux])
        if len(ux) < 2 or fpx < ux.min() or fpx > ux.max():
            return None
        return float(np.exp(np.interp(fpx, ux, np.log(np.maximum(uy, 1e-9)))))

    def short(c):
        lens, mag = c.split(" | ")[0], c.split(" | ")[1]
        lens = (lens.replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "Sig105")
                .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "Sig150")
                .replace("NIKKOR Z MC 105mm f_2.8 VR S", "ZMC105")
                .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100-400")
                .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
                .replace("Olympus MCON-35", "MCON35").replace("Canon 500D", "500D")
                .replace(" + ", "+"))
        return f"{lens} {mag}"

    for fpx in (0.10, 0.15, 0.20):
        ranked = []
        for cfg in cfg_mtf:
            v = interp_cfg(cfg, fpx)
            if v is not None:
                ranked.append((cfg, M_of[cfg], v))
        ranked.sort(key=lambda x: -x[2])
        print(f"\n  --- f_px={fpx:.2f} ---  top 6:")
        for i, (cfg, m, v) in enumerate(ranked[:6], 1):
            print(f"    {i:>2}. mtf={v:.4f} M={m:.2f}  {short(cfg)}")

        def find(subs, exc=()):
            for cfg in cfg_mtf:
                if all(s in cfg for s in subs) and not any(e in cfg for e in exc):
                    return cfg
            return None
        bare = {"Sigma Macro 105": find(["Sigma Macro 105", "1_1", "F8"], ["+"]),
                "Sigma APO Macro 150": find(["Sigma APO Macro 150", "1_1", "F8"], ["+"]),
                "NIKKOR Z MC 105": find(["NIKKOR Z MC 105", "1_1", "F8"], ["+"])}
        flo = []
        for cfg in cfg_mtf:
            if not any(t in cfg for t in ("TC-", "5T", "6T", "MCON", "500D")):
                continue
            donor = next((d for fam, d in bare.items() if fam in cfg and d), None)
            if not donor:
                continue
            vc, vd = interp_cfg(cfg, fpx), interp_cfg(donor, fpx)
            if vc and vd and vc > vd:
                flo.append(f"{short(cfg)}({vc:.3f})>{short(donor)}({vd:.3f})")
        print("    empty-mag float: " + ("NONE (good)" if not flo else "; ".join(flo[:4])))
        b105, b150 = bare["Sigma Macro 105"], bare["Sigma APO Macro 150"]
        if b105 and b150:
            v105, v150 = interp_cfg(b105, fpx), interp_cfg(b150, fpx)
            if v105 and v150:
                print(f"    bare105={v105:.4f} bare150={v150:.4f} ratio={v105/v150:.2f} (want ~1.0)")

    # write CSV
    csvp = OUT / "phaseB_collapse.csv"
    with csvp.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["target", "n_teeth", "n_configs", "collapse_resid",
                    "per_order_null", "within_config_floor", "ratio", "verdict"])
        for r in results:
            w.writerow([r[0], r[1], r[2], round(r[3], 4),
                        round(r[4], 4) if r[4] == r[4] else "",
                        round(r[5], 4) if r[5] == r[5] else "",
                        round(r[6], 4) if r[6] == r[6] else "", r[7]])
    print(f"\nWROTE {csvp}")

    # verdict
    print("\n" + "=" * 92)
    print("PHASE B VERDICT")
    print("=" * 92)
    pad_results = [r for r in results if r[0] != "maze" and r[3] == r[3]]
    if pad_results:
        best = min(pad_results, key=lambda r: r[6] if r[6] == r[6] else 9)
        print(f"  best re-anchored target: {best[0]} collapse={best[3]:.3f} "
              f"floor={best[5]:.3f} ratio={best[6]:.2f}")
        print(f"  PRIOR best (prod-anchor): cleanest die 0.624 / floor 0.19 (ratio 3.4); "
              f"magenta.P11 0.790 / floor 0.392 (ratio 2.0)")
        print(f"  A target is STABLE only if ratio resid/floor approaches ~1.0-1.3.")


if __name__ == "__main__":
    main()
