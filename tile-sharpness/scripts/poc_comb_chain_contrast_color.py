"""Diagnostic 2: is the pad STRUCTURAL contrast hiding in a color-opponent channel?

The feature class is named "magenta". Luma (_decode_gray) may discard chromatic pad
structure. On the SAME registered pad ROI used in poc_comb_chain_contrast_inspect.py,
decode the best-focus JPEG in COLOR and recompute the three-way contrast per channel:
R, G, B, luma, and Mag=(R+B)/2 - G (magenta opponent), plus R-G and B-G.

Reuses the A1/inspect registration + region selection so the ROI bbox + focus shot are
IDENTICAL to the prior grayscale run. Outputs under .../contrast_inspect/.
Run on nufan.
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
spec2 = importlib.util.spec_from_file_location("ci", HERE / "poc_comb_chain_contrast_inspect.py")
ci = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(ci)  # noqa: E402
from tile_sharpness.methods.periodic_fft import derotate, periodic_contrast  # noqa: E402

OUT = HERE / "poc_comb_chain_out" / "contrast_inspect"
OUT.mkdir(parents=True, exist_ok=True)

# (name, n_marked, sweep_dir, also_run?) — high-M kept (cheap enough, one frame decode)
CONFIGS = ci.CONFIGS


def channel_stack(bgr):
    """Return dict channel_name -> float32 2-D array (raw, un-normalised).

    Coordinator correction: the structure is DARK SPECULAR METAL cells on a LIGHT-BROWN
    substrate, and "magenta" is only the GIMP marking colour. The discriminating axis is
    WARM/chroma, so the headline channels are R-B (warm) and saturation; the magenta
    opponent (R+B)/2-G is deprioritised (kept only for the record).
    """
    b, g, r = bgr[:, :, 0].astype(np.float64), bgr[:, :, 1].astype(np.float64), bgr[:, :, 2].astype(np.float64)
    luma = 0.114 * b + 0.587 * g + 0.299 * r
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0) * 255.0  # HSV S, 0..255
    mag = (r + b) / 2.0 - g          # magenta opponent (deprioritised; for the record)
    return {"R": r, "G": g, "B": b, "luma": luma,
            "R-B": r - b, "sat": sat, "Mag": mag}


def three_contrasts(chan, pad_f0_cypx, theta, spec_mask=None):
    """chan: 2-D float ROI (already cropped, NOT de-rotated). Returns dict of the three
    contrasts + bimodality stats. FFT C uses the de-rotated ROI at the locked pad pitch.

    spec_mask: bool 2-D, True at achromatic specular-dot pixels (from luma p99.5). We
    report `spec_lift` = (median value at specular pixels - global median) / global IQR
    for this channel: large positive = the dots still read as bright outliers in this
    channel; ~0 or negative = the dots are SUPPRESSED. Also `spec_p999` = this channel's
    own 99.9th pct minus its median in IQR units (how extreme its own bright tail is)."""
    vals = chan.ravel()
    # contrasts (a) and (b) are computed on the channel as-is, after shifting to >=0 so
    # opponent channels (which can be negative) have a meaningful Michelson denominator.
    shift = max(0.0, -float(vals.min()))
    v = vals + shift
    p5, p95 = np.percentile(v, 5), np.percentile(v, 95)
    C_pct = float((p95 - p5) / (p95 + p5)) if (p95 + p5) > 0 else 0.0
    thr, _ = ci.otsu_threshold(v)
    dark = v[v <= thr]; bright = v[v > thr]
    md = float(dark.mean()) if dark.size else 0.0
    mb = float(bright.mean()) if bright.size else 0.0
    C_otsu = float((mb - md) / (mb + md)) if (mb + md) > 0 else 0.0
    frac_dark = dark.size / v.size
    hist, edges = np.histogram(v, bins=64)
    centers = 0.5 * (edges[:-1] + edges[1:])
    ti = int(np.argmin(np.abs(centers - thr)))
    left_peak = hist[:max(1, ti)].max() if ti > 0 else hist[0]
    right_peak = hist[ti:].max() if ti < len(hist) else hist[-1]
    valley = hist[ti]
    valley_depth = 1.0 - valley / max(1, min(left_peak, right_peak))
    bimodal = valley_depth > 0.15
    # (c) FFT fundamental on de-rotated channel at the locked pad pitch
    der = derotate(chan.astype(np.float64), theta)
    c = periodic_contrast(der, pitch_px=1.0 / pad_f0_cypx, axis="auto")
    C_fft = float(c["contrast"]) if c else float("nan")
    snr_fft = float(c["snr"]) if c else float("nan")
    # specular-dot suppression: how strongly do the achromatic luma-defined dots show up
    # in THIS channel, in robust (IQR) units relative to the channel's own median.
    med = float(np.median(vals))
    q1, q3 = np.percentile(vals, 25), np.percentile(vals, 75)
    iqr = max(1e-6, float(q3 - q1))
    spec_lift = float((np.median(chan[spec_mask]) - med) / iqr) if (spec_mask is not None and spec_mask.any()) else float("nan")
    spec_p999 = float((np.percentile(vals, 99.9) - med) / iqr)
    return dict(C_pct=C_pct, C_otsu=C_otsu, C_fft=C_fft, snr_fft=snr_fft,
                valley_depth=valley_depth, bimodal=bimodal,
                mean_dark=md - shift, mean_bright=mb - shift, frac_dark=frac_dark,
                peak_sep=mb - md, spec_lift=spec_lift, spec_p999=spec_p999)


def norm8(a):
    lo, hi = np.percentile(a, 1), np.percentile(a, 99)
    if hi <= lo:
        return np.zeros_like(a, np.uint8)
    return np.clip((a - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)


def main():
    table = []
    for name, n_marked, sweep_dir in CONFIGS:
        sd = Path(sweep_dir)
        jpgs = sorted(sd.glob("*.jpg")) + sorted(sd.glob("*.JPG"))
        print(f"\n=== {name} ({len(jpgs)} frames) ===", flush=True)
        p = apf.register(jpgs)
        if p is None:
            print("  REG FAILED"); continue
        M = p["scale"] / apf.M_ANCHOR_SCALE
        theta = p["theta_deg"]
        sel = ci.best_pad_region(jpgs, p, M, theta)   # identical selection to inspect run
        if sel is None:
            print("  no region"); continue
        _score, region, roi_gray, der_gray, seq, rec = sel
        x0, y0, x1, y1 = [int(v) for v in region["bbox"]]
        pad_f0 = rec["f0_cy_per_px"]
        print(f"  M={M:.3f} region={region['label']} roi=({y1-y0}x{x1-x0}) "
              f"focus_seq={seq} pad_f0={pad_f0:.4f}cy/px", flush=True)
        # decode the SAME best-focus frame in COLOR, crop the SAME bbox
        bgr_full = cv2.imread(str(jpgs[seq]), cv2.IMREAD_COLOR)
        bgr = bgr_full[y0:y1, x0:x1]
        chans = channel_stack(bgr)
        # achromatic specular dots = top 0.5% of LUMA (bright neutral specks)
        spec_mask = chans["luma"] >= np.percentile(chans["luma"], 99.5)
        print(f"  specular mask: {int(spec_mask.sum())} px ({100*spec_mask.mean():.2f}% of ROI)", flush=True)
        print(f"  {'chan':<6} {'C_pct':>7} {'C_otsu':>7} {'C_fft':>7} {'valley':>7} {'bimodal':>8} {'specLift':>9} {'specP999':>9}")
        per = {}
        for cname, arr in chans.items():
            r = three_contrasts(arr, pad_f0, theta, spec_mask=spec_mask)
            per[cname] = r
            print(f"  {cname:<6} {r['C_pct']:7.3f} {r['C_otsu']:7.3f} {r['C_fft']:7.3f} "
                  f"{r['valley_depth']:7.2f} {str(r['bimodal']):>8} {r['spec_lift']:9.2f} {r['spec_p999']:9.2f}", flush=True)
            table.append(dict(config=name, M=round(M, 3), channel=cname,
                              C_percentile=round(r['C_pct'], 4), C_otsu=round(r['C_otsu'], 4),
                              C_fft_fundamental=round(r['C_fft'], 4), snr_fft=round(r['snr_fft'], 2),
                              valley_depth=round(r['valley_depth'], 3), bimodal=r['bimodal'],
                              peak_sep=round(r['peak_sep'], 1),
                              spec_lift=round(r['spec_lift'], 3), spec_p999=round(r['spec_p999'], 3)))
        # best channel by structural contrast = max of (C_otsu, C_fft) excluding luma
        best = max((c for c in per if c != "luma"),
                   key=lambda c: max(per[c]['C_otsu'], per[c]['C_fft'] if per[c]['C_fft'] == per[c]['C_fft'] else 0))
        print(f"  BEST structural channel: {best} (C_otsu={per[best]['C_otsu']:.3f} "
              f"C_fft={per[best]['C_fft']:.3f} specLift={per[best]['spec_lift']:.2f}) "
              f"vs luma (C_otsu={per['luma']['C_otsu']:.3f} C_fft={per['luma']['C_fft']:.3f} "
              f"specLift={per['luma']['spec_lift']:.2f})", flush=True)
        # save ROI + hist PNGs for best channel and luma
        for tag, cname in (("best_" + best, best), ("luma", "luma")):
            arr = chans[cname]
            up = cv2.resize(norm8(arr), ((x1 - x0) * 4, (y1 - y0) * 4), interpolation=cv2.INTER_NEAREST)
            cv2.imwrite(str(OUT / f"{name}__chan_{tag}__roi.png"), up)
            v = arr.ravel() + max(0.0, -float(arr.min()))
            thr, _ = ci.otsu_threshold(v)
            plt.figure(figsize=(6, 4))
            plt.hist(v, bins=64, color="purple" if cname != "luma" else "steelblue", alpha=0.8)
            plt.axvline(thr, color="red", ls="--", label=f"Otsu={thr:.0f}")
            plt.title(f"{name}  channel={cname}\nvalley_depth={per[cname]['valley_depth']:.2f} "
                      f"bimodal={per[cname]['bimodal']}")
            plt.xlabel(f"{cname} value (1-99% norm)"); plt.ylabel("count"); plt.legend(fontsize=8)
            plt.tight_layout()
            plt.savefig(str(OUT / f"{name}__chan_{tag}__hist.png"), dpi=110); plt.close()

    csv_path = OUT / "contrast_color_stats.csv"
    if table:
        with csv_path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
            w.writeheader()
            for row in table:
                w.writerow(row)
    print(f"\nWROTE {csv_path}", flush=True)


if __name__ == "__main__":
    main()
