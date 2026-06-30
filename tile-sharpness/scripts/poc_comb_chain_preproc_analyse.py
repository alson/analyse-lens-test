"""Stage Preproc — cause isolation: the ABLATION analysis. For each pre-processing arm
(baseline -> +flat -> +specmask -> +phasewin -> +fixed-focus, plus the clip negative
control) run the Stage-T_n self-calibration collapse and report the collapse RESIDUAL and
the residual/within-config-FLOOR RATIO, so we see WHICH linear step (if any) drives the
cross-M instability down toward the floor.

DECISION RULE (set in advance):
  * residual -> 0.38-0.49 floor, ratio -> ~1.0-1.3  => instability was MEASUREMENT-INDUCED,
    cross-M REVIVES; report which step did it + re-check gates.
  * residual barely moves through all linear steps  => GENUINE TARGET VARIATION; cross-M
    dead for these targets, now PROVEN.
  * watch the FLOOR: if a step drops residual AND floor in lockstep (ratio flat) that is
    NOT progress -> report the RATIO, not just the residual.
  * the clip arm is a NEGATIVE CONTROL: if it 'collapses' that is INVALID (nonlinear
    destroys the MTF signal) and is flagged, not counted as a revival.

UNTRACKED / exploratory. Reuses the Stage-T_n self-cal machinery (self_calibrate,
isotonic_decreasing) and the Relock structure typing — imported read-only.

Usage (nufan or local; pure-CSV):
  PYTHONPATH=<src> python scripts/poc_comb_chain_preproc_analyse.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_tn_analyse as T  # noqa: E402  (self_calibrate)

OUT = HERE / "poc_comb_chain_out" / "preproc"

SNR_MIN = 3.0
MAX_OVER = 0.05
MIN_C = 1e-3

# anchor-pitch clusters by SUBJECT lp/mm of the fundamental (matches relock_b_analyse).
FUND_CLUSTERS = [("C8", 4.0, 11.0), ("C14", 11.0, 22.0), ("C28", 22.0, 40.0)]

# the ablation ladder (tag -> human label). Order is the cumulative ablation order.
ARMS = [
    ("baseline", "baseline (sat + per-axis anchor)"),
    ("flat", "+ flat-fielding"),
    ("flat_spec", "+ specular masking / robust FFT"),
    ("flat_spec_win", "+ phase-aligned windowing"),
    ("flat_spec_win_foc", "+ fixed cross-config focus"),
    ("clip_NEGCTRL", "+ clip [NEGATIVE CONTROL — INVALID]"),
]


def load(path):
    rows = []
    if not path.exists():
        return rows
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
        res.append(T.self_calibrate(ts)["residual_rms"])
    return (float(np.median(res)) if res else float("nan")), len(res)


def prep(rows):
    rows = [r for r in rows if valid(r)]
    for r in rows:
        r["stype"] = stype(r)
        r["logA"] = np.log(max(r["C"], MIN_C))
        r["w"] = float(np.log1p(r["snr"]))
    return [r for r in rows if r["stype"] is not None]


def collapse_for_type(typed, st, *, low_order=None):
    teeth = [t for t in typed if t["stype"] == st]
    if low_order is not None:
        teeth = [t for t in teeth if t["order"] <= low_order]
    if len(teeth) < 8 or len(set(t["order"] for t in teeth)) < 2:
        return None
    cal = T.self_calibrate(teeth)
    null = per_order_null(teeth)
    floor, nfl = within_config_floor(teeth)
    ratio = cal["residual_rms"] / floor if floor == floor and floor > 0 else float("nan")
    nconf = len(set(t["config"] for t in teeth))
    return dict(st=st, n=len(teeth), configs=nconf, resid=cal["residual_rms"],
                null=null, floor=floor, ratio=ratio, cal=cal, teeth=teeth)


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


def gate_recheck(typed):
    """Empty-magnification float + bare105/bare150 + corr(M, MTF) at f_px 0.10/0.15/0.20,
    using the structure-corrected MTF from each type's self-cal (same as relock_b_analyse)."""
    by_type = defaultdict(list)
    for r in typed:
        by_type[r["stype"]].append(r)
    cals = {}
    for st, teeth in by_type.items():
        if len(teeth) >= 8 and len(set(t["order"] for t in teeth)) >= 2:
            cals[st] = T.self_calibrate(teeth)
    cfg_mtf = defaultdict(list)
    M_of = {}
    for r in typed:
        st = r["stype"]
        if st not in cals:
            continue
        logT = cals[st]["Tn"].get(r["order"])
        if logT is None:
            continue
        cfg_mtf[r["config"]].append((r["f_px"], float(np.exp(r["logA"] - logT))))
        M_of[r["config"]] = r["M"]

    def interp_cfg(cfg, fpx):
        samps = [(f, m) for (f, m) in cfg_mtf[cfg] if m > 0]
        if len(samps) < 2:
            return None
        xs = np.array([s[0] for s in samps]); ys = np.array([s[1] for s in samps])
        o = np.argsort(xs); xs, ys = xs[o], ys[o]
        ux = np.unique(xs)
        uy = np.array([np.exp(np.mean(np.log(ys[xs == v]))) for v in ux])
        if len(ux) < 2 or fpx < ux.min() or fpx > ux.max():
            return None
        return float(np.exp(np.interp(fpx, ux, np.log(np.maximum(uy, 1e-9)))))

    def find(subs, exc=()):
        for cfg in cfg_mtf:
            if all(s in cfg for s in subs) and not any(e in cfg for e in exc):
                return cfg
        return None

    bare = {"Sigma Macro 105": find(["Sigma Macro 105", "1_1", "F8"], ["+"]),
            "Sigma APO Macro 150": find(["Sigma APO Macro 150", "1_1", "F8"], ["+"]),
            "NIKKOR Z MC 105": find(["NIKKOR Z MC 105", "1_1", "F8"], ["+"])}
    res = {}
    for fpx in (0.10, 0.15, 0.20):
        Ms, Vs = [], []
        for cfg in cfg_mtf:
            v = interp_cfg(cfg, fpx)
            if v is not None:
                Ms.append(M_of[cfg]); Vs.append(v)
        flo = []
        for cfg in cfg_mtf:
            if not any(t in cfg for t in ("TC-", "5T", "6T", "MCON", "500D")):
                continue
            donor = next((d for fam, d in bare.items() if fam in cfg and d), None)
            if not donor:
                continue
            vc, vd = interp_cfg(cfg, fpx), interp_cfg(donor, fpx)
            if vc and vd and vc > vd:
                flo.append(f"{short(cfg)}>{short(donor)}")
        b105, b150 = bare["Sigma Macro 105"], bare["Sigma APO Macro 150"]
        ratio = None
        if b105 and b150:
            v105, v150 = interp_cfg(b105, fpx), interp_cfg(b150, fpx)
            if v105 and v150:
                ratio = v105 / v150
        res[fpx] = dict(corrM=pear(Ms, Vs), nfloat=len(flo), floats=flo[:4],
                        ratio105_150=ratio)
    return res


def main():
    print("=" * 100)
    print("Stage Preproc — cause isolation ABLATION")
    print("  resid = cross-M self-cal collapse (log-contrast). floor = within-config noise.")
    print("  REVIVE if ratio -> ~1.0-1.3 (toward floor); DEAD/genuine if ratio stays ~1.5-2+.")
    print("  PRIOR (Relock, prod best): dominant grid 0.643/floor 0.423 ratio 1.52; "
          "best ratio 1.46. maze 0.845/floor 0.313 ratio 2.70.")
    print("=" * 100)

    # representative targets to track across arms (the data-rich, comparable types).
    TRACK = ["magenta.v.C8", "magenta.u.C8", "magenta.v.C14", "magenta.u.C14", "maze"]

    loaded = {}
    for tag, _ in ARMS:
        rows = load(OUT / f"{tag}_all.csv")
        loaded[tag] = prep(rows) if rows else []

    # ablation table: per arm, the dominant grid (magenta.v.C8) + maze + a "best pad" ratio
    print(f"\n{'arm':<40}{'target':<16}{'nteeth':<8}{'resid':<9}{'null':<8}{'floor':<8}{'ratio':<8}")
    print("-" * 100)
    summary = []  # (tag, label, target, resid, null, floor, ratio)
    for tag, label in ARMS:
        typed = loaded[tag]
        if not typed:
            print(f"{label:<40}{'(no data)':<16}")
            continue
        # primary tracked target = dominant ~30px v-grid (magenta.v.C8). Fall back if absent.
        printed_any = False
        for st in TRACK:
            r = collapse_for_type(typed, st)
            if r is None:
                continue
            lbl = label if not printed_any else ""
            print(f"{lbl:<40}{st:<16}{r['n']:<8}{r['resid']:<9.3f}{r['null']:<8.3f}"
                  f"{r['floor']:<8.3f}{r['ratio']:<8.2f}")
            summary.append((tag, label, st, r['resid'], r['null'], r['floor'], r['ratio']))
            printed_any = True
        if not printed_any:
            print(f"{label:<40}{'(no typed teeth)':<16}")
        print()

    # low-order-only (orders<=3) on the dominant grid — the cleanest cross-M test
    print("=" * 100)
    print("Low-order (<=3) on the dominant grid magenta.v.C8 (cleanest signal):")
    print(f"  {'arm':<40}{'resid':<9}{'null':<8}{'floor':<8}{'ratio':<8}")
    for tag, label in ARMS:
        typed = loaded[tag]
        if not typed:
            continue
        r = collapse_for_type(typed, "magenta.v.C8", low_order=3)
        if r is None:
            continue
        print(f"  {label:<40}{r['resid']:<9.3f}{r['null']:<8.3f}{r['floor']:<8.3f}{r['ratio']:<8.2f}")

    # gate re-check per arm (decision-relevant): empty-mag float, bare105/150, corr(M,MTF)
    print("\n" + "=" * 100)
    print("GATE RE-CHECK per arm (does the empty-magnification fallacy stop / does bare105~150?)")
    print("=" * 100)
    for tag, label in ARMS:
        typed = loaded[tag]
        if not typed:
            continue
        g = gate_recheck(typed)
        print(f"\n  {label}:")
        for fpx in (0.10, 0.15, 0.20):
            d = g[fpx]
            r = f"{d['ratio105_150']:.2f}" if d['ratio105_150'] else "n/a"
            fl = "NONE" if d['nfloat'] == 0 else f"{d['nfloat']}: " + "; ".join(d['floats'])
            print(f"    f_px={fpx:.2f}: corr(M,MTF)={d['corrM']:+.2f} bare105/150={r} "
                  f"empty-mag-float={fl}")

    # write the ablation summary CSV
    OUT.mkdir(parents=True, exist_ok=True)
    csvp = OUT / "preproc_ablation.csv"
    with csvp.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["arm_tag", "arm_label", "target", "collapse_resid",
                    "per_order_null", "within_config_floor", "ratio"])
        for s in summary:
            w.writerow([s[0], s[1], s[2], round(s[3], 4),
                        round(s[4], 4) if s[4] == s[4] else "",
                        round(s[5], 4) if s[5] == s[5] else "",
                        round(s[6], 4) if s[6] == s[6] else ""])
    print(f"\nWROTE {csvp}")

    # verdict against the decision rule (dominant grid magenta.v.C8 ratio trajectory)
    print("\n" + "=" * 100)
    print("DECISION-RULE READOUT (dominant grid magenta.v.C8 ratio across the LINEAR arms)")
    print("=" * 100)
    traj = [(label, next((s for s in summary if s[0] == tag and s[2] == "magenta.v.C8"), None))
            for tag, label in ARMS if tag != "clip_NEGCTRL"]
    base_ratio = None
    for label, s in traj:
        if s is None:
            continue
        if base_ratio is None:
            base_ratio = s[6]
        arrow = ""
        print(f"  {label:<42} resid={s[3]:.3f} ratio={s[6]:.2f}{arrow}")
    clip = next((s for s in summary if s[0] == "clip_NEGCTRL" and s[2] == "magenta.v.C8"), None)
    if clip:
        print(f"  [NEG CTRL] clip                            resid={clip[3]:.3f} "
              f"ratio={clip[6]:.2f}  <-- INVALID if low (nonlinear destroys MTF)")


if __name__ == "__main__":
    main()
