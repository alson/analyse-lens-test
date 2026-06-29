"""TASK 1 (refined) — intrinsic-corrected MTF samples at fixed sensor frequency.

UNTRACKED / exploratory. Decodes best-focus magenta-pad ROIs (run on nufan), extracts
the pad-comb 1-D profile, and uses production harmonic_mtf to get target-INTRINSIC-
corrected MTF samples (divides each tooth by its |sinc(nD)| content, D estimated from
the profile). This removes the 1/n square-wave falloff that contaminated the raw-contrast
fixed-f_px analysis (the coordinator's methodology fix).

Produces, per config:
  * self-normalized SHAPE  MTF(n*f0)/MTF(f0)  (harmonic_mtf output; M-invariant rolloff)
  * absolute MTF samples   A_n / T_n          (teeth divided by intrinsic content only,
                                               NOT by MTF(f0); keeps absolute scale)
Then interpolates absolute MTF vs f_px to common f_px and computes:
  - corr(M, MTF_abs @ f_px)   [de-confounding headline, intrinsic-corrected variant]
  - fixed-f_px ranking + empty-magnification check
  - sensitivity of the ranking to the duty-cycle estimate D (T_n is uncertain on these
    textured/specular metal cells, not ideal square gratings).

Reuses atlas_periodic_fft registration + the inspect best_pad_region focus/region
selection (same plumbing as A1). Reads SATURATION (diag-2 winner) and luma profiles.
Outputs: poc_comb_chain_out/contrast_inspect/hmtf/
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402
spec2 = importlib.util.spec_from_file_location("ci", HERE / "poc_comb_chain_contrast_inspect.py")
ci = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(ci)  # noqa: E402
from tile_sharpness.methods.periodic_fft import derotate  # noqa: E402
from tile_sharpness.methods import harmonic_mtf as HM  # noqa: E402

OUT = HERE / "poc_comb_chain_out" / "contrast_inspect" / "hmtf"
OUT.mkdir(parents=True, exist_ok=True)
TARGETS = [0.10, 0.15, 0.20]
LPMM_PER_CYPX = L.LPMM_PER_CYPX


def cfg_list():
    out = []
    for r in csv.DictReader(open(HERE / "poc_comb_chain_subset.csv")):
        sample = r["sample"].split("|")[0]
        out.append((f"{r['lens']} | {r['mag_label']} | {r['aperture']}",
                    str(Path(sample).parent)))
    return out


def sat_of(bgr):
    b, g, rr = (bgr[:, :, 0].astype(np.float64), bgr[:, :, 1].astype(np.float64),
                bgr[:, :, 2].astype(np.float64))
    mx = np.maximum(np.maximum(rr, g), b); mn = np.minimum(np.minimum(rr, g), b)
    return np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0) * 255.0


def collapse_profile(der, axis):
    """Collapse a de-rotated 2-D ROI to a 1-D profile across the grating lines.
    axis='x' -> grating varies along x, average over rows -> profile over columns."""
    if axis == "x":
        return der.mean(axis=0)
    return der.mean(axis=1)


def pear(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def main():
    # per config: list of (f_px, mtf_abs) absolute samples for chosen D, plus shape, plus
    # the raw harmonic dict so we can re-derive at other D for the sensitivity sweep.
    per_cfg = {}
    M_by = {}
    rows_out = []
    for name, sweep_dir in cfg_list():
        sd = Path(sweep_dir)
        jpgs = sorted(sd.glob("*.jpg")) + sorted(sd.glob("*.JPG"))
        if not jpgs:
            print(f"=== {name}: NO JPGS"); continue
        print(f"\n=== {name} ({len(jpgs)}) ===", flush=True)
        p = apf.register(jpgs)
        if p is None:
            print("  REG FAILED"); continue
        M = p["scale"] / apf.M_ANCHOR_SCALE
        theta = p["theta_deg"]
        M_by[name] = M
        sel = ci.best_pad_region(jpgs, p, M, theta)
        if sel is None:
            print("  no region"); continue
        _score, region, roi_gray, der_gray, seq, rec = sel
        x0, y0, x1, y1 = [int(v) for v in region["bbox"]]
        f0 = rec["f0_cy_per_px"]; axis = rec.get("axis", "auto")
        bgr = cv2.imread(str(jpgs[seq]), cv2.IMREAD_COLOR)[y0:y1, x0:x1]
        sat = sat_of(bgr)
        der = derotate(sat, theta)
        # decide collapse axis from rec; if 'auto', try both and keep the stronger f0 peak
        cands = ["x", "y"] if axis not in ("x", "y") else [axis]
        best = None
        for ax in cands:
            prof = collapse_profile(der, ax)
            h = HM.harmonic_mtf(prof, f0, n_harmonics=7, snr_min=3.0)
            ha = HM.harmonic_amplitudes(prof, f0, n_harmonics=7)
            if h is None or ha is None:
                continue
            score = ha["amps"][0]
            if best is None or score > best[0]:
                best = (score, ax, prof, h, ha)
        if best is None:
            print(f"  M={M:.3f} f0={f0:.4f} NO harmonic_mtf"); continue
        _s, ax, prof, h, ha = best
        D = h["duty"]
        # absolute MTF samples = A_n / T_n with T_n = |sinc(nD)| (keep absolute scale).
        amps = np.array(ha["amps"]); ns = np.arange(1, len(amps) + 1)
        Tn = np.abs(np.sinc(ns * D))
        mask = Tn > 0.08 * (Tn[0] if Tn[0] > 0 else 1.0)
        f_samp = ns[mask] * f0
        mtf_abs = amps[mask] / Tn[mask]
        # normalize absolute by DC (|F(0)|) so ROI brightness/area cancel -> comparable
        dc = max(ha["dc"], 1e-6)
        mtf_abs = mtf_abs / dc
        per_cfg[name] = dict(M=M, f0=f0, duty=D, axis=ax, ns=ns, amps=amps, dc=dc,
                             f_samp=f_samp, mtf_abs=mtf_abs,
                             shape_f=np.array(h["f_cy_per_px"]),
                             shape=np.array(h["mtf_ratio"]))
        print(f"  M={M:.3f} f0={f0:.4f} axis={ax} duty={D:.2f} "
              f"shape={['%.2f'%v for v in h['mtf_ratio']]}", flush=True)
        for j in range(len(f_samp)):
            rows_out.append(dict(config=name, M=round(M, 3), duty=round(D, 3),
                                 f_px=round(float(f_samp[j]), 4),
                                 mtf_abs=round(float(mtf_abs[j]), 6),
                                 f_subj_lpmm=round(float(f_samp[j]) * LPMM_PER_CYPX * M, 1)))

    configs = sorted(per_cfg, key=lambda c: per_cfg[c]["M"])

    # ---- interpolate absolute MTF vs f_px, correlate with M ----
    def interp_abs(cfg, fpx):
        d = per_cfg[cfg]
        xs = d["f_samp"]; ys = d["mtf_abs"]
        order = np.argsort(xs); xs = xs[order]; ys = ys[order]
        if len(xs) < 2 or fpx < xs.min() or fpx > xs.max():
            return None
        return float(np.exp(np.interp(fpx, xs, np.log(np.maximum(ys, 1e-6)))))

    print("\n" + "=" * 74)
    print("INTRINSIC-CORRECTED (A_n/T_n/DC) absolute MTF at fixed f_px — de-confound test")
    print("=" * 74)
    print("\n  corr(M, intrinsic-corrected absolute MTF @ common f_px):")
    for ft in TARGETS:
        Ms, Vs = [], []
        for c in configs:
            v = interp_abs(c, ft)
            if v is not None:
                Ms.append(per_cfg[c]["M"]); Vs.append(v)
        print(f"    f_px={ft:.2f}: corr={pear(Ms, Vs):+.3f}  (n={len(Ms)} configs)")

    # ---- ranking + empty-mag ----
    def short(c):
        lens, mag, _ = c.split(" | ")
        lens = (lens.replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "Sig105")
                .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "Sig150")
                .replace("NIKKOR Z MC 105mm f_2.8 VR S", "ZMC105")
                .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100-400")
                .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
                .replace("Olympus MCON-35", "MCON35").replace("Canon 500D", "500D")
                .replace(" + ", "+"))
        return f"{lens} {mag}"

    for ft in TARGETS:
        ranked = []
        for c in configs:
            v = interp_abs(c, ft)
            if v is not None:
                ranked.append((c, per_cfg[c]["M"], v))
        ranked.sort(key=lambda x: -x[2])
        print(f"\n  --- ranking @ f_px={ft:.2f} (intrinsic-corrected absolute MTF) ---")
        for i, (c, m, v) in enumerate(ranked, 1):
            print(f"    {i:>2}. mtf={v:.4f} M={m:.2f}  {short(c)}")

    # empty-mag at f_px=0.15
    def find(subs, exc=()):
        for c in configs:
            if all(s in c for s in subs) and not any(e in c for e in exc):
                return c
        return None
    bare = {"Sigma Macro 105": find(["Sigma Macro 105", "1_1", "F8"], ["+"]),
            "Sigma APO Macro 150": find(["Sigma APO Macro 150", "1_1", "F8"], ["+"]),
            "NIKKOR Z MC 105": find(["NIKKOR Z MC 105", "1_1", "F8"], ["+"])}
    print("\n  --- EMPTY-MAGNIFICATION (intrinsic-corrected) ---")
    for ft in TARGETS:
        flo = []
        for c in configs:
            if not any(t in c for t in ("TC-", "5T", "6T", "MCON", "500D")):
                continue
            donor = next((d for fam, d in bare.items() if fam in c and d), None)
            if not donor:
                continue
            vc, vd = interp_abs(c, ft), interp_abs(donor, ft)
            if vc and vd and vc > vd:
                flo.append(f"{short(c)}({vc:.4f})>{short(donor)}({vd:.4f})")
        print(f"    f_px={ft:.2f}: " + ("none float" if not flo else "; ".join(flo)))

    # ---- duty-cycle sensitivity of the ranking ----
    print("\n  --- DUTY-CYCLE SENSITIVITY (Spearman of f_px=0.15 ranking vs D-estimate) ---")
    # recompute abs MTF at fixed D for all configs, re-rank, compare to per-config-D rank
    def rank_at_D(Dfix, ft=0.15):
        order = []
        for c in configs:
            d = per_cfg[c]
            amps = d["amps"]; ns = d["ns"]
            Tn = np.abs(np.sinc(ns * Dfix))
            mask = Tn > 0.08 * (Tn[0] if Tn[0] > 0 else 1.0)
            xs = ns[mask] * d["f0"]; ys = amps[mask] / Tn[mask] / d["dc"]
            o = np.argsort(xs); xs = xs[o]; ys = ys[o]
            if len(xs) < 2 or ft < xs.min() or ft > xs.max():
                continue
            v = float(np.exp(np.interp(ft, xs, np.log(np.maximum(ys, 1e-6)))))
            order.append((c, v))
        order.sort(key=lambda x: -x[1])
        return [c for c, _ in order]
    base = rank_at_D(None) if False else None
    ranks = {D: rank_at_D(D) for D in [0.3, 0.4, 0.5, 0.6]}
    # show top-5 at each D
    for D, rk in ranks.items():
        print(f"    D={D}: top5 = {[short(c) for c in rk[:5]]}")

    # write csv
    csvp = OUT / "hmtf_samples.csv"
    if rows_out:
        with csvp.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            for r in rows_out:
                w.writerow(r)
    print(f"\nWROTE {csvp}")


if __name__ == "__main__":
    main()
