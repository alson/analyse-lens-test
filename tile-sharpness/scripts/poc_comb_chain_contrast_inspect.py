"""Diagnostic: reconcile pad-vs-substrate contrast with the FFT-fundamental Michelson C.

For ONE low-M config (bare Sigma 105 @ 1:1) and ONE high-M config (Sigma 105 + TC-2001
@ 2:1), using the SAME registered magenta pad-array ROIs the A1 driver used:
  1. save the best-focus pad ROI crop as a grayscale PNG, NN-upscaled ~6x;
  2. save a pixel-value histogram PNG with the Otsu threshold marked;
  3. tabulate three contrasts: percentile-Michelson (p95,p5), Otsu-bimodal Michelson,
     and the FFT-fundamental Michelson C = 2|F(f0)|/|F(0)| (same as A1).

Outputs under poc_comb_chain_out/contrast_inspect/. Run on nufan.
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402
from tile_sharpness.methods.periodic_fft import derotate  # noqa: E402

OUT = HERE / "poc_comb_chain_out" / "contrast_inspect"
OUT.mkdir(parents=True, exist_ok=True)

CONFIGS = [
    ("low_M_bareSigma105_1to1", 8.0,
     "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Sigma Macro 105mm F2.8 EX DG OS HSM/1_1/F8"),
    ("high_M_Sigma105_TC2001_2to1", 22.0,
     "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001/2_1/F11"),
]


def otsu_threshold(vals):
    """Otsu threshold on a 1-D float array (256-bin)."""
    v = vals.astype(np.float64)
    lo, hi = v.min(), v.max()
    if hi <= lo:
        return lo, 0.0
    hist, edges = np.histogram(v, bins=256, range=(lo, hi))
    hist = hist.astype(np.float64)
    total = hist.sum()
    centers = 0.5 * (edges[:-1] + edges[1:])
    w0 = np.cumsum(hist)
    w1 = total - w0
    mu0 = np.cumsum(hist * centers) / np.maximum(w0, 1e-9)
    mu_tot = (hist * centers).sum() / total
    mu1 = (mu_tot * total - np.cumsum(hist * centers)) / np.maximum(w1, 1e-9)
    between = w0 * w1 * (mu0 - mu1) ** 2
    k = int(np.argmax(between[:-1]))
    return float(centers[k]), float(between[k] / between.max() if between.max() > 0 else 0)


def fft_fundamental_C(der):
    """The A1 FFT-fundamental Michelson C: discover the pad fundamental (A5 band) on the
    de-rotated ROI, read bounded periodic_contrast at it. Returns (C, f0_cy_px, axis)."""
    from tile_sharpness.methods.periodic_fft import periodic_contrast
    rec, _mb = L.discover_pad_fundamental(der, 1.0)  # M only affects band; we want px-freq read
    # discover_pad_fundamental uses M for band placement; redo with the config M below.
    return rec


def best_pad_region(jpgs, p, M, theta):
    """Pick the magenta pad region with the strongest discoverable pad fundamental on its
    best-focus frame (good coverage proxy), return (region, best_roi, der, focus_seq)."""
    import heapq
    regions = [r for r in apf.enumerate_regions(p, p["scale"]) if r["cls"] == "magenta"]
    # one decode per frame, keep top-3 focus ROI per region
    boxes = {i: [int(v) for v in r["bbox"]] for i, r in enumerate(regions)}
    heaps = {i: [] for i in range(len(regions))}
    for seq, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        for i, (x0, y0, x1, y1) in boxes.items():
            roi = g[y0:y1, x0:x1]
            if roi.size == 0 or min(roi.shape) < 24:
                continue
            lv = float(cv2.Laplacian(roi.astype(np.float32), cv2.CV_32F).var())
            h = heaps[i]
            if len(h) < 3:
                heapq.heappush(h, (lv, seq, roi.copy()))
            elif lv > h[0][0]:
                heapq.heapreplace(h, (lv, seq, roi.copy()))
    best = None
    for i, h in heaps.items():
        if not h:
            continue
        lv, seq, roi = sorted(h, reverse=True)[0]
        der = derotate(roi.astype(np.float64), theta)
        rec, _ = L.discover_pad_fundamental(der, M)
        if rec is None:
            continue
        # coverage proxy: prefer a region big enough and with a clear bimodal spread
        spread = float(np.percentile(roi, 95) - np.percentile(roi, 5))
        score = rec["amp"] * spread
        if best is None or score > best[0]:
            best = (score, regions[i], roi, der, seq, rec)
    return best


def main():
    table = []
    for name, n_marked, sweep_dir in CONFIGS:
        sd = Path(sweep_dir)
        jpgs = sorted(sd.glob("*.jpg")) + sorted(sd.glob("*.JPG"))
        print(f"\n=== {name} ({len(jpgs)} frames) ===")
        p = apf.register(jpgs)
        if p is None:
            print("  REG FAILED"); continue
        M = p["scale"] / apf.M_ANCHOR_SCALE
        theta = p["theta_deg"]
        sel = best_pad_region(jpgs, p, M, theta)
        if sel is None:
            print("  no pad region"); continue
        _score, region, roi, der, seq, rec = sel
        print(f"  M={M:.3f} theta={theta:.2f} region={region['label']} zone={region['zone']} "
              f"roi={roi.shape} focus_shot_seq={seq} pad_f0={rec['f0_cy_per_px']:.3f}cy/px")

        # --- 1. ROI crop PNG (NN upscale 6x) ---
        crop = roi.astype(np.uint8)
        up = cv2.resize(crop, (crop.shape[1] * 6, crop.shape[0] * 6),
                        interpolation=cv2.INTER_NEAREST)
        crop_png = OUT / f"{name}__roi.png"
        cv2.imwrite(str(crop_png), up)

        # --- 2. histogram + Otsu ---
        vals = roi.astype(np.float64).ravel()
        thr, _ = otsu_threshold(vals)
        dark = vals[vals <= thr]; bright = vals[vals > thr]
        frac_dark = dark.size / vals.size
        frac_bright = bright.size / vals.size
        mean_dark = float(dark.mean()) if dark.size else 0.0
        mean_bright = float(bright.mean()) if bright.size else 0.0
        # valley depth: histogram count at threshold vs the two modal peaks
        hist, edges = np.histogram(vals, bins=64)
        centers = 0.5 * (edges[:-1] + edges[1:])
        ti = int(np.argmin(np.abs(centers - thr)))
        left_peak = hist[:max(1, ti)].max() if ti > 0 else hist[0]
        right_peak = hist[ti:].max() if ti < len(hist) else hist[-1]
        valley = hist[ti]
        valley_depth = 1.0 - valley / max(1, min(left_peak, right_peak))

        plt.figure(figsize=(6, 4))
        plt.hist(vals, bins=64, color="steelblue", alpha=0.85)
        plt.axvline(thr, color="red", ls="--", label=f"Otsu={thr:.0f}")
        plt.axvline(mean_dark, color="black", ls=":", label=f"dark μ={mean_dark:.0f} ({frac_dark*100:.0f}%)")
        plt.axvline(mean_bright, color="orange", ls=":", label=f"bright μ={mean_bright:.0f} ({frac_bright*100:.0f}%)")
        plt.title(f"{name}\n{region['label']} M={M:.2f} valley_depth={valley_depth:.2f}")
        plt.xlabel("pixel value (8-bit)"); plt.ylabel("count"); plt.legend(fontsize=7)
        plt.tight_layout()
        hist_png = OUT / f"{name}__hist.png"
        plt.savefig(str(hist_png), dpi=110); plt.close()

        # --- 3. three contrasts ---
        p5, p95 = np.percentile(vals, 5), np.percentile(vals, 95)
        C_pct = float((p95 - p5) / (p95 + p5)) if (p95 + p5) > 0 else 0.0
        C_otsu = float((mean_bright - mean_dark) / (mean_bright + mean_dark)) if (mean_bright + mean_dark) > 0 else 0.0
        # FFT-fundamental C, identical recipe to A1 (locked pad pitch on the same der ROI)
        from tile_sharpness.methods.periodic_fft import periodic_contrast
        c = periodic_contrast(der, pitch_px=1.0 / rec["f0_cy_per_px"], axis="auto")
        C_fft = float(c["contrast"]) if c else float("nan")
        snr_fft = float(c["snr"]) if c else float("nan")

        peak_sep = mean_bright - mean_dark
        print(f"  C_percentile(p95,p5) = {C_pct:.3f}")
        print(f"  C_otsu_bimodal       = {C_otsu:.3f}  (dark μ={mean_dark:.0f} {frac_dark*100:.0f}%, "
              f"bright μ={mean_bright:.0f} {frac_bright*100:.0f}%)")
        print(f"  C_fft_fundamental    = {C_fft:.3f}  (snr={snr_fft:.1f}, f0={rec['f0_cy_per_px']:.3f}cy/px)")
        print(f"  peak_sep={peak_sep:.0f}  valley_depth={valley_depth:.2f}")
        table.append(dict(config=name, M=round(M, 3), region=region["label"],
                          zone=region["zone"], roi_h=roi.shape[0], roi_w=roi.shape[1],
                          focus_seq=seq, pad_f0_cypx=round(rec["f0_cy_per_px"], 4),
                          C_percentile=round(C_pct, 4), C_otsu=round(C_otsu, 4),
                          C_fft_fundamental=round(C_fft, 4), snr_fft=round(snr_fft, 2),
                          mean_dark=round(mean_dark, 1), mean_bright=round(mean_bright, 1),
                          frac_dark=round(frac_dark, 3), frac_bright=round(frac_bright, 3),
                          peak_sep=round(peak_sep, 1), valley_depth=round(valley_depth, 3),
                          roi_png=str(crop_png), hist_png=str(hist_png)))

    csv_path = OUT / "contrast_stats.csv"
    if table:
        with csv_path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
            w.writeheader()
            for row in table:
                w.writerow(row)
    print(f"\nWROTE {csv_path}")
    for row in table:
        print(f"  {row['config']}: C_pct={row['C_percentile']} C_otsu={row['C_otsu']} "
              f"C_fft={row['C_fft_fundamental']}")


if __name__ == "__main__":
    main()
