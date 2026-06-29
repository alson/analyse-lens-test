"""Stage T_n — steps 2-5: empirical per-structure harmonic content + the gates.

UNTRACKED / exploratory. Pure-CSV analysis of poc_comb_chain_out/tn_all.csv (the
saturation-channel comb amplitudes extracted by poc_comb_chain_tn_extract.py).

The model for a comb tooth measured on a flat periodic structure:

    A_n(M) = MTF(n*f0_px(M)) * T_n        (T_n = intrinsic harmonic content)

The prior POC assumed T_n = |sinc(nD)| (odd-only square wave) -> invalid MTF (>1) and
pad-vs-maze MTF disagreeing ~5x. Here we measure T_n EMPIRICALLY:

  STEP 2  group teeth by STRUCTURE TYPE = (cls, pad-pitch cluster) and the maze, so we
          never pool different gratings (the report flags >=2 pad pitches ~16 & ~35).
  STEP 3  two T_n estimators per structure type:
            (direct)  at the highest-M configs, low-order teeth sit at low cy/px where
                      MTF~=1, so A_n/A_1 ~= T_n/T_1 directly.
            (self-cal, PRIMARY)  the same structure type across M puts its teeth at
                      different f_px. Jointly solve {log T_n} and a single smooth
                      MTF(f_px) so all teeth collapse onto one curve:
                          log A_n(M) = log MTF(f_px) + log T_n
                      by alternating least squares (MTF = monotone PCHIP-ish isotonic
                      fit on a log-f_px grid; T_n = per-order offset).
  STEP 4  DECISIVE STABILITY TEST: report the collapse residual. If a consistent
          {T_n}+MTF exists (low residual) the content is stable; if the teeth refuse to
          collapse for ANY {T_n}, the content is specular/texture-unstable -> dead.
  STEP 5  gates, re-run with empirical T_n:
            - cross-structure agreement (pad vs maze MTF ratio at shared f_px -> ~1x?)
            - physicality (MTF <= 1, monotone non-increasing)
            - M de-confounding (corr(M, MTF) ~ 0)
            - ranking sanity (bare 105~150; 105 more TC-tolerant; macros>primes>diopter;
              no empty-magnification +TC float)

Outputs printed + poc_comb_chain_out/tn/.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

OUT = HERE / "poc_comb_chain_out" / "tn"
OUT.mkdir(parents=True, exist_ok=True)
LPMM_PER_CYPX = L.LPMM_PER_CYPX

SNR_MIN = 3.0
MAX_OVER = 0.05            # ceiling-valid gate (same as B1)
MIN_C = 1e-3

# pad pitch clusters in SUBJECT lp/mm (from a1_all fundamental histogram):
#   ~11-12  (call P11), ~14-18 (P16), ~32-36 (P35). cyan handled the same way.
PAD_CLUSTERS = [("P11", 9.0, 13.0), ("P16", 13.0, 26.0), ("P35", 26.0, 42.0)]


def load(path):
    rows = []
    for r in csv.DictReader(open(path)):
        rows.append(dict(
            config=r["config"], M=float(r["M"]), region=r["region"],
            cls=r["cls"], feature=r["feature"],
            order=int(r["harmonic_order"]),
            f_subj=float(r["f_subj_lpmm"]), f_px=float(r["f_px"]),
            C=float(r["contrast"]), snr=float(r["snr"]),
            ceiling=float(r["ceiling"]), over=float(r["over_ceiling"])))
    return rows


def fund_subj(r):
    """Subject fundamental frequency implied by this tooth (f_subj / order)."""
    return r["f_subj"] / max(1, r["order"])


def structure_type(r):
    """Group teeth by structure TYPE: maze is its own type; pads are grouped by their
    fundamental pitch cluster + cls so we never pool different gratings."""
    if r["feature"] == "maze":
        return "maze"
    f1 = fund_subj(r)
    for name, lo, hi in PAD_CLUSTERS:
        if lo <= f1 < hi:
            return f"{r['cls']}.{name}"
    return None  # outside known clusters -> drop


def valid(r):
    return (r["snr"] >= SNR_MIN and r["over"] <= MAX_OVER and r["C"] > MIN_C)


# --------------------------------------------------------------------------- #
# Self-calibration collapse: log A_n(M) = log MTF(f_px) + log T_n
# --------------------------------------------------------------------------- #

def isotonic_decreasing(x, y, w):
    """Weighted isotonic (non-increasing in x) regression via PAVA on x-sorted data."""
    order = np.argsort(x)
    xs, ys, ws = x[order], y[order], w[order]
    # PAVA for non-increasing: negate y, fit non-decreasing, negate back
    yy = -ys
    vals = list(yy)
    wts = list(ws)
    idx = [[i] for i in range(len(yy))]
    i = 0
    while i < len(vals) - 1:
        if vals[i] > vals[i + 1]:  # violation of non-decreasing
            nv = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / (wts[i] + wts[i + 1])
            vals[i] = nv
            wts[i] = wts[i] + wts[i + 1]
            idx[i] = idx[i] + idx[i + 1]
            del vals[i + 1]; del wts[i + 1]; del idx[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    fit = np.zeros_like(ys)
    for v, ii in zip(vals, idx):
        for k in ii:
            fit[k] = -v
    out = np.zeros_like(y)
    out[order] = fit
    return out


def self_calibrate(teeth, n_iter=60):
    """teeth: list of dicts with f_px, order, logA, w (per measurement of ONE structure
    type, possibly many configs/regions). Jointly solve log MTF(f_px) (monotone
    non-increasing) and log T_n (per harmonic order) so logA ~= logMTF(f_px)+logT_n.

    Returns dict(Tn={order:logT}, residual_rms, n, curve=(fpx_grid, logmtf), per-point
    residuals). Gauge: log T_1 = 0 (normalise to fundamental).
    """
    fpx = np.array([t["f_px"] for t in teeth])
    ords = np.array([t["order"] for t in teeth])
    logA = np.array([t["logA"] for t in teeth])
    w = np.array([t["w"] for t in teeth])
    uord = sorted(set(ords.tolist()))
    logT = {o: 0.0 for o in uord}
    logmtf_pt = np.zeros_like(logA)
    for _ in range(n_iter):
        # 1. given T_n, MTF samples = logA - logT(order); isotonic fit vs f_px
        resid = logA - np.array([logT[o] for o in ords])
        logmtf_pt = isotonic_decreasing(fpx, resid, w)
        # 2. given MTF, logT(order) = weighted mean of (logA - logMTF) within each order
        r2 = logA - logmtf_pt
        for o in uord:
            m = ords == o
            logT[o] = float(np.sum(r2[m] * w[m]) / np.sum(w[m]))
        # gauge: anchor fundamental T_1 = 0 (shift the whole MTF curve to compensate)
        if 1 in logT:
            shift = logT[1]
            for o in uord:
                logT[o] -= shift
            logmtf_pt = logmtf_pt + shift
    pred = logmtf_pt + np.array([logT[o] for o in ords])
    res = logA - pred
    rms = float(np.sqrt(np.sum(w * res ** 2) / np.sum(w)))
    return dict(Tn={o: logT[o] for o in uord}, residual_rms=rms, n=len(teeth),
                fpx=fpx, logmtf_pt=logmtf_pt, ords=ords, res=res, w=w, M=None)


def mtf_at(cal, fpx_query):
    """Interpolate the collapsed MTF curve (in log space) at a query f_px."""
    xs = cal["fpx"]; ys = cal["logmtf_pt"]
    o = np.argsort(xs); xs, ys = xs[o], ys[o]
    if fpx_query < xs.min() or fpx_query > xs.max():
        return None
    return float(np.exp(np.interp(fpx_query, xs, ys)))


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


def pear(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def main():
    rows = load(HERE / "poc_comb_chain_out" / "tn_all.csv")
    rows = [r for r in rows if valid(r)]
    for r in rows:
        r["stype"] = structure_type(r)
    rows = [r for r in rows if r["stype"] is not None]
    print(f"valid teeth (saturation): {len(rows)}")

    # weight per tooth = log(snr) (robust to huge SNRs)
    for r in rows:
        r["logA"] = np.log(max(r["C"], MIN_C))
        r["w"] = float(np.log1p(r["snr"]))

    # group teeth by structure type
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["stype"]].append(r)
    print("\nstructure-type tooth counts:")
    for st in sorted(by_type):
        nconf = len(set(t["config"] for t in by_type[st]))
        ords = sorted(set(t["order"] for t in by_type[st]))
        fr = [t["f_px"] for t in by_type[st]]
        print(f"  {st:16s} n={len(by_type[st]):4d}  configs={nconf:2d}  orders={ords}  "
              f"f_px [{min(fr):.3f},{max(fr):.3f}]")

    # =================================================================== #
    # STEP 3+4 : self-calibrate each structure type, report collapse residual
    # =================================================================== #
    print("\n" + "=" * 74)
    print("STEP 3/4 — self-calibration collapse per structure type")
    print("=" * 74)
    cals = {}
    for st in sorted(by_type):
        teeth = by_type[st]
        if len(teeth) < 8 or len(set(t["order"] for t in teeth)) < 2:
            print(f"  {st}: too few teeth/orders -> skip")
            continue
        cal = self_calibrate(teeth)
        cals[st] = cal
        # head-to-head: collapse residual with the FIXED square-wave T_n (D=0.5, the prior
        # assumption) instead of free T_n. Same isotonic MTF machinery, T_n frozen.
        sq = {o: np.log(max(abs(np.sinc(o * 0.5)) / abs(np.sinc(0.5)), 1e-3))
              for o in set(t["order"] for t in teeth)}
        fpx = np.array([t["f_px"] for t in teeth])
        ords = np.array([t["order"] for t in teeth])
        logA = np.array([t["logA"] for t in teeth])
        w = np.array([t["w"] for t in teeth])
        resid_sq = logA - np.array([sq[o] for o in ords])
        logmtf_sq = isotonic_decreasing(fpx, resid_sq, w)
        pred_sq = logmtf_sq + np.array([sq[o] for o in ords])
        rms_sq = float(np.sqrt(np.sum(w * (logA - pred_sq) ** 2) / np.sum(w)))
        cal["resid_squarewave"] = rms_sq
        # baseline residual: same MTF fit but with the OLD square-wave T_n (D=0.5 -> odd
        # only). compute residual if we FORCE T_n = |sinc(nD)| / |sinc(D)| instead of free.
        Tn_str = " ".join(f"T{o}={np.exp(v):.3f}" for o, v in sorted(cal["Tn"].items()))
        # null model: each tooth independently = its own value (residual 0) is overfit;
        # the meaningful baseline = scatter of logA within each (order) bucket after only
        # removing a per-order mean (i.e. ignore MTF rolloff). If MTF matters, the
        # collapse residual should be << this.
        null_res = []
        for o in set(t["order"] for t in teeth):
            vals = np.array([t["logA"] for t in teeth if t["order"] == o])
            ww = np.array([t["w"] for t in teeth if t["order"] == o])
            null_res.append(np.sum(ww * (vals - np.average(vals, weights=ww)) ** 2))
        null_n = sum(t["w"] for t in teeth)
        null_rms = float(np.sqrt(sum(null_res) / null_n))
        print(f"  {st:16s} collapse_resid={cal['residual_rms']:.3f}  "
              f"(squarewave-Tn={cal['resid_squarewave']:.3f}, per-order-only={null_rms:.3f})  {Tn_str}")

    # =================================================================== #
    # empirical T_n vs square-wave assumption + maze EVEN(N=2) content
    # =================================================================== #
    print("\n" + "=" * 74)
    print("EMPIRICAL T_n  vs  square-wave |sinc(nD)| (D=0.5, odd-only)")
    print("=" * 74)
    for st in sorted(cals):
        cal = cals[st]
        ords = sorted(cal["Tn"])
        print(f"\n  {st}:")
        print(f"    order:        " + " ".join(f"n={o}" for o in ords))
        emp = [np.exp(cal["Tn"][o]) for o in ords]
        print(f"    empirical T_n: " + " ".join(f"{v:5.3f}" for v in emp))
        sq = [abs(np.sinc(o * 0.5)) for o in ords]  # |sinc(n/2)|: n=1 ->0.637, even->0
        sq = [s / sq[0] if sq[0] > 0 else 0 for s in sq]
        print(f"    square (D0.5): " + " ".join(f"{v:5.3f}" for v in sq))
        if "maze" in st or st == "maze":
            t2 = np.exp(cal["Tn"].get(2, -99))
            print(f"    >>> maze N=2 (even) empirical content: T2/T1 = {t2:.3f} "
                  f"(square-wave predicts 0.000)")

    # =================================================================== #
    # STEP 5 — gates
    # =================================================================== #
    print("\n" + "=" * 74)
    print("STEP 5 — VALIDATION GATES")
    print("=" * 74)

    # ----- per-config absolute MTF samples using empirical T_n -----
    # For each config and structure type: MTF_sample(f_px) = A_n / T_n  (empirical T_n
    # from that structure's self-cal). One sample per tooth; aggregate per (config, f_px).
    cfg_mtf = defaultdict(list)   # config -> list of (f_px, MTF, stype, M)
    M_of = {}
    for r in rows:
        st = r["stype"]
        if st not in cals:
            continue
        logT = cals[st]["Tn"].get(r["order"])
        if logT is None:
            continue
        mtf = np.exp(r["logA"] - logT)
        cfg_mtf[r["config"]].append((r["f_px"], mtf, st, r["M"], r["order"]))
        M_of[r["config"]] = r["M"]

    # --- GATE: physicality (MTF <= 1, monotone) ---
    print("\n[GATE physicality] fraction of MTF samples > 1.0 (should be ~0):")
    allmtf = [m for v in cfg_mtf.values() for (_, m, _, _, _) in v]
    allmtf = np.array(allmtf)
    print(f"   all structure-corrected MTF samples: n={len(allmtf)}  "
          f">1.0: {100*np.mean(allmtf > 1.0):.1f}%  "
          f">1.2: {100*np.mean(allmtf > 1.2):.1f}%  "
          f"median={np.median(allmtf):.3f} p95={np.percentile(allmtf,95):.3f}")

    # --- GATE: cross-structure agreement (pad vs maze at shared f_px within a config) ---
    print("\n[GATE cross-structure] pad-vs-maze MTF ratio at shared f_px (want ~1x):")
    ratios = []
    for cfg, samps in cfg_mtf.items():
        pads = [(f, m) for (f, m, st, _, _) in samps if not st.startswith("maze") and st != "maze"]
        mazes = [(f, m) for (f, m, st, _, _) in samps if st == "maze" or st.startswith("maze")]
        if not pads or not mazes:
            continue
        # match each maze tooth to nearest pad tooth in f_px (within 0.02 cy/px)
        for fm, mm in mazes:
            cand = [(abs(fp - fm), mp) for fp, mp in pads if abs(fp - fm) < 0.02 and mp > 0 and mm > 0]
            if cand:
                cand.sort()
                ratios.append(cand[0][1] / mm)
    if ratios:
        ratios = np.array(ratios)
        print(f"   n={len(ratios)}  median={np.median(ratios):.2f}x  "
              f"geomean={np.exp(np.mean(np.log(ratios))):.2f}x  "
              f"log-spread={np.std(np.log(ratios)):.2f}")
        print(f"   (prior square-wave model: ~5.15x median. want ->1x)")
    else:
        print("   no shared-f_px pad/maze pairs found")

    # --- GATE: M de-confounding (corr(M, MTF) at fixed f_px) ---
    print("\n[GATE M de-confounding] corr(M, structure-corrected MTF @ common f_px):")
    def interp_cfg(cfg, fpx, stype_pref=None):
        samps = [(f, m) for (f, m, st, _, _) in cfg_mtf[cfg]
                 if (stype_pref is None or st == stype_pref) and m > 0]
        if len(samps) < 2:
            return None
        xs = np.array([s[0] for s in samps]); ys = np.array([s[1] for s in samps])
        o = np.argsort(xs); xs, ys = xs[o], ys[o]
        # collapse duplicate f_px by geomean
        ux = np.unique(xs)
        uy = np.array([np.exp(np.mean(np.log(ys[xs == v]))) for v in ux])
        if len(ux) < 2 or fpx < ux.min() or fpx > ux.max():
            return None
        return float(np.exp(np.interp(fpx, ux, np.log(np.maximum(uy, 1e-9)))))
    for fpx in (0.10, 0.15, 0.20):
        Ms, Vs = [], []
        for cfg in cfg_mtf:
            v = interp_cfg(cfg, fpx)
            if v is not None:
                Ms.append(M_of[cfg]); Vs.append(v)
        print(f"   f_px={fpx:.2f}: corr={pear(Ms, Vs):+.3f}  (n={len(Ms)} configs)  "
              f"[baseline raw was +0.33/+0.78]")

    # --- GATE: ranking sanity + empty-magnification ---
    print("\n[GATE ranking] fixed-f_px ranking (structure-corrected MTF):")
    for fpx in (0.10, 0.15, 0.20):
        ranked = []
        for cfg in cfg_mtf:
            v = interp_cfg(cfg, fpx)
            if v is not None:
                ranked.append((cfg, M_of[cfg], v))
        ranked.sort(key=lambda x: -x[2])
        print(f"\n   --- f_px={fpx:.2f} ---")
        for i, (cfg, m, v) in enumerate(ranked[:8], 1):
            print(f"     {i:>2}. mtf={v:.4f} M={m:.2f}  {short(cfg)}")
        # empty-mag check
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
        print(f"     empty-mag float: " + ("NONE (good)" if not flo else "; ".join(flo)))
        # bare 105 vs 150
        b105, b150 = bare["Sigma Macro 105"], bare["Sigma APO Macro 150"]
        if b105 and b150:
            v105, v150 = interp_cfg(b105, fpx), interp_cfg(b150, fpx)
            if v105 and v150:
                print(f"     bare105={v105:.4f} bare150={v150:.4f} "
                      f"ratio={v105/v150:.2f} (want ~1.0)")

    # write per-tooth MTF csv
    csvp = OUT / "tn_mtf_samples.csv"
    with csvp.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["config", "M", "stype", "order", "f_px", "C", "Tn", "MTF"])
        for r in rows:
            st = r["stype"]
            if st not in cals:
                continue
            logT = cals[st]["Tn"].get(r["order"])
            if logT is None:
                continue
            w.writerow([short(r["config"]), round(r["M"], 3), st, r["order"],
                        round(r["f_px"], 4), round(r["C"], 4),
                        round(float(np.exp(logT)), 4),
                        round(float(np.exp(r["logA"] - logT)), 4)])
    print(f"\nWROTE {csvp}")

    # write T_n table
    tnp = OUT / "tn_empirical.csv"
    with tnp.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["stype", "order", "Tn_empirical", "Tn_squarewave_D0.5", "collapse_resid"])
        for st in sorted(cals):
            cal = cals[st]
            ords = sorted(cal["Tn"])
            sq0 = abs(np.sinc(0.5))
            for o in ords:
                w.writerow([st, o, round(float(np.exp(cal["Tn"][o])), 4),
                            round(float(abs(np.sinc(o * 0.5)) / sq0), 4),
                            round(cal["residual_rms"], 4)])
    print(f"WROTE {tnp}")


if __name__ == "__main__":
    main()
