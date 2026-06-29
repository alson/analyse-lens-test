"""TASK 1 — Fixed-SENSOR-frequency (cy/px) re-analysis of the comb-chain data.

UNTRACKED / exploratory. Pure-CSV re-analysis of poc_comb_chain_out/a1_all.csv.
NO production module modified.

The B1 chain FAILED because Michelson contrast at a fixed SUBJECT frequency is
M-confounded: corr(M, contrast)=+0.33 raw, +0.70 ceiling-normalized. A high-M config
reads the same subject feature at an EASIER pixel frequency (higher on the sensor MTF),
so empty-magnification +TC configs floated above bare lenses.

This script asks: does comparing on the SENSOR-frequency axis (cy/px) de-confound M?

  1. De-confounding test (headline): corr(M, contrast) and corr(M, ceiling-norm
     contrast) bucketed at fixed f_px, side-by-side with the fixed-f_subj baseline.
  2. Coverage matrix at f_px ~ 0.10/0.15/0.20 cy/px: how many configs have a usable
     (SNR>=3, ceiling-valid) rung, and does coverage span M (incl. low-M)?
  3. Fixed-f_px ranking: interpolate each config's contrast-vs-f_px and compare at a
     common cy/px. Sanity vs known orderings; does it stop floating empty-mag +TC?
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

CSVPATH = sys.argv[1] if len(sys.argv) > 1 else "poc_comb_chain_out/a1_all.csv"

SNR_MIN = 3.0
MAX_OVER = 0.05          # ceiling-valid: over_ceiling <= 0.05
MIN_CONTRAST = 1e-3


def load(path):
    rows = []
    for r in csv.DictReader(open(path)):
        rows.append(dict(
            config=r["config"], M=float(r["M"]), feature=r["feature"],
            harmonic_order=int(r["harmonic_order"]),
            f_subj_lpmm=float(r["f_subj_lpmm"]), f_px=float(r["f_px"]),
            contrast=float(r["contrast"]), snr=float(r["snr"]),
            ceiling=float(r["ceiling"]), over_ceiling=float(r["over_ceiling"]),
        ))
    return rows


def is_valid(r):
    return (r["snr"] >= SNR_MIN and r["over_ceiling"] <= MAX_OVER
            and r["contrast"] > MIN_CONTRAST)


def pearson(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 3:
        return float("nan")
    if np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def short(cfg):
    """short display name."""
    lens, mag, ap = cfg.split(" | ")
    lens = (lens.replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "Sig105")
            .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "Sig150")
            .replace("NIKKOR Z MC 105mm f_2.8 VR S", "ZMC105")
            .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100-400")
            .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
            .replace("Olympus MCON-35", "MCON35").replace("Canon 500D", "500D")
            .replace(" + ", "+"))
    return f"{lens} {mag}"


# --------------------------------------------------------------------------- #
def main():
    rows = load(CSVPATH)
    valid = [r for r in rows if is_valid(r)]
    M_by = {}
    for r in rows:
        M_by[r["config"]] = r["M"]
    configs = sorted(M_by, key=lambda c: M_by[c])
    print(f"loaded {len(rows)} rows, {len(valid)} valid (SNR>=3, ceiling-valid), "
          f"{len(configs)} configs\n")

    # ===================================================================== #
    # PART 1 — DE-CONFOUNDING TEST (headline)
    # ===================================================================== #
    print("=" * 78)
    print("PART 1 — DE-CONFOUNDING: corr(M, contrast) at fixed f_subj vs fixed f_px")
    print("=" * 78)

    # ---- baseline: fixed f_subj. Per-config median contrast within shared subject
    # nodes (same recipe as B1: feature + subj-freq bucket of 4 lp/mm, >=2 cfgs share).
    def buckets(valid, key, width):
        node = defaultdict(lambda: defaultdict(list))  # nodekey -> cfg -> [rows]
        for r in valid:
            b = round(r[key] / width)
            node[(r["feature"], b)][r["config"]].append(r)
        return node

    def per_config_at_shared_nodes(node):
        """For each node shared by >=2 configs, emit (config, M, median C,
        median ceiling-norm C). Returns flat lists for correlation."""
        Ms, Cs, Cn = [], [], []
        rows_out = []
        for nk, members in node.items():
            if len(members) < 2:
                continue
            for cfg, rs in members.items():
                c = float(np.median([x["contrast"] for x in rs]))
                # ceiling-normalized: contrast / ceiling (clip ceiling away from 0)
                cn = float(np.median([x["contrast"] / max(x["ceiling"], 1e-3)
                                      for x in rs]))
                Ms.append(M_by[cfg]); Cs.append(c); Cn.append(cn)
                rows_out.append((nk, cfg, M_by[cfg], c, cn))
        return Ms, Cs, Cn, rows_out

    node_subj = buckets(valid, "f_subj_lpmm", 4.0)
    Ms_s, Cs_s, Cn_s, _ = per_config_at_shared_nodes(node_subj)
    r_subj_raw = pearson(Ms_s, Cs_s)
    r_subj_norm = pearson(Ms_s, Cn_s)

    # ---- new: fixed f_px. Bucket on sensor frequency instead.
    # choose bucket width in cy/px; 0.02 cy/px (~ same fractional resolution).
    FPX_W = 0.02
    node_px = buckets(valid, "f_px", FPX_W)
    Ms_p, Cs_p, Cn_p, _ = per_config_at_shared_nodes(node_px)
    r_px_raw = pearson(Ms_p, Cs_p)
    r_px_norm = pearson(Ms_p, Cn_p)

    print(f"\n  bucket width: f_subj {4.0} lp/mm  |  f_px {FPX_W} cy/px")
    print(f"  shared-node samples: f_subj {len(Ms_s)}  |  f_px {len(Ms_p)}\n")
    print(f"  {'axis':<28}{'corr(M, C_raw)':>16}{'corr(M, C/ceil)':>18}")
    print(f"  {'-'*28}{'-'*16}{'-'*18}")
    print(f"  {'fixed f_subj (BASELINE)':<28}{r_subj_raw:>16.3f}{r_subj_norm:>18.3f}")
    print(f"  {'fixed f_px (NEW)':<28}{r_px_raw:>16.3f}{r_px_norm:>18.3f}")
    print(f"\n  (prior report baseline quoted: +0.33 raw / +0.70 ceiling-norm)")

    # Also: within-bucket correlation, averaged. This is the cleaner statistic:
    # within ONE f_px bucket (so frequency is held fixed), does contrast still
    # correlate with M? If de-confounded, the within-bucket corr should be ~0.
    def within_bucket_corr(node, min_members=4):
        rs = []
        for nk, members in node.items():
            if len(members) < min_members:
                continue
            mm, cc, cn = [], [], []
            for cfg, lst in members.items():
                mm.append(M_by[cfg])
                cc.append(np.median([x["contrast"] for x in lst]))
                cn.append(np.median([x["contrast"] / max(x["ceiling"], 1e-3) for x in lst]))
            r1 = pearson(mm, cc); r2 = pearson(mm, cn)
            if r1 == r1:
                rs.append((len(members), r1, r2))
        if not rs:
            return float("nan"), float("nan"), 0
        w = np.array([x[0] for x in rs], float)
        r_raw = float(np.sum(w * np.array([x[1] for x in rs])) / w.sum())
        r_nrm = float(np.sum(w * np.array([x[2] for x in rs])) / w.sum())
        return r_raw, r_nrm, len(rs)

    wb_subj = within_bucket_corr(node_subj)
    wb_px = within_bucket_corr(node_px)
    print("\n  --- within-bucket corr(M,C), member-count weighted (freq held fixed) ---")
    print(f"  {'axis':<28}{'corr(M,C_raw)':>16}{'corr(M,C/ceil)':>18}{'#buckets':>10}")
    print(f"  {'fixed f_subj':<28}{wb_subj[0]:>16.3f}{wb_subj[1]:>18.3f}{wb_subj[2]:>10d}")
    print(f"  {'fixed f_px':<28}{wb_px[0]:>16.3f}{wb_px[1]:>18.3f}{wb_px[2]:>10d}")

    # ===================================================================== #
    # PART 2 — COVERAGE MATRIX at common sensor frequencies
    # ===================================================================== #
    print("\n" + "=" * 78)
    print("PART 2 — COVERAGE at common f_px (SNR>=3, ceiling-valid rungs)")
    print("=" * 78)
    TARGETS = [0.10, 0.15, 0.20]
    TOL = 0.02
    print(f"\n  tolerance +-{TOL} cy/px; a config 'covers' f_px* if it has >=1 valid "
          f"rung within tol.")
    for ft in TARGETS:
        covered = []
        for c in configs:
            hits = [r for r in valid if r["config"] == c and abs(r["f_px"] - ft) <= TOL]
            if hits:
                covered.append((c, M_by[c], len(hits)))
        Ms_cov = [m for _, m, _ in covered]
        print(f"\n  f_px = {ft:.2f} +- {TOL}:  {len(covered)}/{len(configs)} configs covered"
              + (f"   M range {min(Ms_cov):.2f}-{max(Ms_cov):.2f}" if Ms_cov else ""))
        lowM = [c for c, m, _ in covered if m < 1.15]
        print(f"    low-M configs (M<1.15) covered: {len(lowM)}/"
              f"{sum(1 for c in configs if M_by[c] < 1.15)}")
        for c, m, n in covered:
            tag = "  <-LOW-M" if m < 1.15 else ""
            print(f"      M={m:4.2f}  n={n:2d}  {short(c)}{tag}")

    # ===================================================================== #
    # PART 3 — FIXED-f_px RANKING
    # ===================================================================== #
    print("\n" + "=" * 78)
    print("PART 3 — FIXED-f_px RANKING (interpolate contrast-vs-f_px per config)")
    print("=" * 78)

    # Build, per config, the (f_px, contrast) cloud from valid PAD+maze rungs, take a
    # robust contrast per f_px by binning then interpolate log-contrast vs f_px.
    def config_curve(cfg, feature_filter=None):
        pts = [(r["f_px"], r["contrast"]) for r in valid
               if r["config"] == cfg and (feature_filter is None or r["feature"] in feature_filter)]
        if len(pts) < 3:
            return None
        # bin into 0.01 cy/px bins, median contrast per bin
        binw = 0.01
        b = defaultdict(list)
        for f, c in pts:
            b[round(f / binw)].append(c)
        fs = np.array(sorted(b))
        xs = fs * binw
        ys = np.array([np.median(b[k]) for k in fs])
        return xs, ys

    def interp_at(cfg, fpx, feature_filter=None):
        cur = config_curve(cfg, feature_filter)
        if cur is None:
            return float("nan"), False
        xs, ys = cur
        # only interpolate within the measured span (no extrapolation)
        if fpx < xs.min() or fpx > xs.max():
            return float("nan"), False
        # interpolate in log-contrast
        ly = np.interp(fpx, xs, np.log(np.maximum(ys, 1e-4)))
        return float(np.exp(ly)), True

    for ft in TARGETS:
        print(f"\n  --- ranking at f_px = {ft:.2f} cy/px (subj freq differs per config) ---")
        ranked = []
        for c in configs:
            val, ok = interp_at(c, ft)
            if ok:
                f_subj = ft * 229.885 * M_by[c]
                ranked.append((c, M_by[c], val, f_subj))
        ranked.sort(key=lambda x: -x[2])
        print(f"  {'rank':>4} {'C':>7} {'M':>5} {'subjLpmm':>9}  config")
        for i, (c, m, v, fs) in enumerate(ranked, 1):
            print(f"  {i:>4} {v:7.4f} {m:5.2f} {fs:9.1f}  {short(c)}")

    # ---- Sanity checks at a chosen reference f_px ----
    print("\n  --- SANITY vs known orderings ---")

    def find(substrs, exclude=()):
        for c in configs:
            if all(s in c for s in substrs) and not any(e in c for e in exclude):
                return c
        return None

    bare105 = find(["Sigma Macro 105", "1_1", "F8"], exclude=["+"])
    bare150 = find(["Sigma APO Macro 150", "1_1", "F8"], exclude=["+"])
    bareZMC = find(["NIKKOR Z MC 105", "1_1", "F8"], exclude=["+"])
    bareAF200 = find(["Nikon AF Micro-Nikkor 200", "1_1", "F8"], exclude=["+"])
    t105_14 = find(["Sigma Macro 105", "TC-1401", "1.4_1"])
    t105_20 = find(["Sigma Macro 105", "TC-2001", "2_1"])
    t150_20 = find(["Sigma APO Macro 150", "TC-2001", "2_1"])
    stack105 = find(["Sigma Macro 105", "5T + 6T"])
    dio500 = find(["Canon 500D"])

    for ref in TARGETS:
        print(f"\n  at f_px={ref:.2f}:")
        def g(c):
            v, ok = interp_at(c, ref)
            return v if ok else float("nan")
        def line(desc, a, b, rel):
            va, vb = g(a), g(b)
            if va != va or vb != vb:
                print(f"    [n/a ] {desc}  ({short(a) if a else '?'}={va:.4f} "
                      f"{short(b) if b else '?'}={vb:.4f})")
                return
            if rel == "approx":
                ok = abs(np.log(va) - np.log(vb)) < 0.30
                sym = "≈"
            else:
                ok = va > vb
                sym = ">"
            print(f"    [{'PASS' if ok else 'FAIL'}] {desc}  "
                  f"{short(a)}={va:.4f} {sym}? {short(b)}={vb:.4f}")
        line("bare 105 ≈ bare 150", bare105, bare150, "approx")
        if t105_20 and t150_20:
            line("105+TC20@2:1 ≥ 150+TC20@2:1", t105_20, t150_20, "gt")
        # EMPTY-MAGNIFICATION test: bare 105 vs its own +TC configs
        if t105_14:
            line("bare 105 > 105+TC14@1.4 (no empty-mag float)", bare105, t105_14, "gt")
        if t105_20:
            line("bare 105 > 105+TC20@2:1 (no empty-mag float)", bare105, t105_20, "gt")
        if stack105:
            line("bare 105 > 105+5T+6T stack", bare105, stack105, "gt")
        if dio500:
            line("bare 105 > 100-400+500D diopter", bare105, dio500, "gt")

    # ---- explicit empty-mag verdict across all +accessory configs ----
    print("\n  --- EMPTY-MAGNIFICATION verdict (does any +TC/ext/dio float above its bare donor?) ---")
    donors = {
        "Sigma Macro 105": bare105,
        "Sigma APO Macro 150": bare150,
        "NIKKOR Z MC 105": bareZMC,
    }
    for ref in TARGETS:
        print(f"\n  at f_px={ref:.2f}:")
        any_float = False
        for c in configs:
            if not any(t in c for t in ("TC-", "5T", "6T", "MCON", "500D")):
                continue
            # find donor
            donor = None
            for fam, d in donors.items():
                if fam in c and d:
                    donor = d; break
            if donor is None:
                continue
            vc, okc = interp_at(c, ref)
            vd, okd = interp_at(donor, ref)
            if okc and okd and vc > vd:
                any_float = True
                print(f"    FLOAT: {short(c)} (C={vc:.4f}) > donor {short(donor)} (C={vd:.4f})")
        if not any_float:
            print("    none — no +accessory config outranks its bare donor (GOOD)")


if __name__ == "__main__":
    main()
