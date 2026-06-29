"""TASK 1.4 — Radial PSD cross-check at fixed sensor frequency (cy/px).

UNTRACKED / exploratory. Decodes best-focus magenta-pad ROIs (must run on nufan),
computes a windowed 2-D radial power spectral density, and reads the PSD at a fixed
f_px (cy/px). Target-AGNOSTIC (no fundamental-discovery / harmonic locking) and works
at low M. Caveat: PSD = MTF^2 * intrinsic-target-spectrum, so absolute level mixes the
target spectrum in; we report a NORMALIZED PSD (fraction of in-band power above the f_px
floor) AND the raw radial PSD at the target f_px, and rank configs both ways.

Reuses atlas_periodic_fft registration + region enumeration + the inspect best_pad_region
focus selection (same plumbing as A1). Reads SATURATION channel (the diagnostic-2 winner)
for the structural read, with luma for comparison.

Outputs: poc_comb_chain_out/contrast_inspect/psd/  (curves PNG + psd_fpx.csv).
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

OUT = HERE / "poc_comb_chain_out" / "contrast_inspect" / "psd"
OUT.mkdir(parents=True, exist_ok=True)

TARGETS_FPX = [0.10, 0.15, 0.20]

# (config-name, n_marked-ignored, sweep_dir) — all 16 spanning configs.
def cfg_list():
    rows = list(csv.DictReader(open(HERE / "poc_comb_chain_subset.csv")))
    out = []
    for r in rows:
        sample = r["sample"].split("|")[0]
        d = str(Path(sample).parent)
        name = f"{r['lens']} | {r['mag_label']} | {r['aperture']}"
        out.append((name, d))
    return out


def sat_channel(bgr):
    b, g, rr = (bgr[:, :, 0].astype(np.float64), bgr[:, :, 1].astype(np.float64),
                bgr[:, :, 2].astype(np.float64))
    mx = np.maximum(np.maximum(rr, g), b); mn = np.minimum(np.minimum(rr, g), b)
    sat = np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0) * 255.0
    luma = 0.114 * b + 0.587 * g + 0.299 * rr
    return sat, luma


def radial_psd(img):
    """Windowed 2-D PSD collapsed to a radial profile. Returns (f_cycles_per_px, psd)."""
    a = img.astype(np.float64)
    a = a - a.mean()
    h, w = a.shape
    wy = np.hanning(h)[:, None]; wx = np.hanning(w)[None, :]
    a = a * (wy * wx)
    F = np.fft.fftshift(np.fft.fft2(a))
    P = (np.abs(F) ** 2)
    cy, cx = h // 2, w // 2
    yy, xx = np.mgrid[0:h, 0:w]
    # radial frequency in cy/px: fx = (x-cx)/w, fy=(y-cy)/h ; r = sqrt(fx^2+fy^2)
    fx = (xx - cx) / w; fy = (yy - cy) / h
    r = np.sqrt(fx ** 2 + fy ** 2)
    nb = 60
    redges = np.linspace(0, 0.5, nb + 1)
    rc = 0.5 * (redges[:-1] + redges[1:])
    prof = np.zeros(nb)
    for i in range(nb):
        m = (r >= redges[i]) & (r < redges[i + 1])
        prof[i] = P[m].mean() if m.any() else 0.0
    return rc, prof


def psd_at(rc, prof, fpx):
    return float(np.interp(fpx, rc, prof))


def main():
    table = []
    curves = {}
    for name, sweep_dir in cfg_list():
        sd = Path(sweep_dir)
        jpgs = sorted(sd.glob("*.jpg")) + sorted(sd.glob("*.JPG"))
        if not jpgs:
            print(f"=== {name}: NO JPGS at {sweep_dir}"); continue
        print(f"\n=== {name} ({len(jpgs)} frames) ===", flush=True)
        p = apf.register(jpgs)
        if p is None:
            print("  REG FAILED"); continue
        M = p["scale"] / apf.M_ANCHOR_SCALE
        theta = p["theta_deg"]
        sel = ci.best_pad_region(jpgs, p, M, theta)
        if sel is None:
            print("  no region"); continue
        _score, region, roi_gray, der_gray, seq, rec = sel
        x0, y0, x1, y1 = [int(v) for v in region["bbox"]]
        bgr = cv2.imread(str(jpgs[seq]), cv2.IMREAD_COLOR)[y0:y1, x0:x1]
        sat, luma = sat_channel(bgr)
        rc_s, prof_s = radial_psd(sat)
        rc_l, prof_l = radial_psd(luma)
        # normalize PSD by integral over the resolvable band (0.04..0.45) so the
        # absolute target brightness / ROI size scale out; the SHAPE is what MTF affects.
        band = (rc_s >= 0.04) & (rc_s <= 0.45)
        norm_s = prof_s[band].sum() if prof_s[band].sum() > 0 else 1.0
        norm_l = prof_l[band].sum() if prof_l[band].sum() > 0 else 1.0
        curves[name] = (M, rc_s, prof_s / norm_s, rc_l, prof_l / norm_l)
        row = dict(config=name, M=round(M, 3), region=region["label"],
                   roi=f"{y1-y0}x{x1-x0}", seq=seq)
        for ft in TARGETS_FPX:
            row[f"sat_psd_{ft}"] = round(psd_at(rc_s, prof_s / norm_s, ft), 6)
            row[f"luma_psd_{ft}"] = round(psd_at(rc_l, prof_l / norm_l, ft), 6)
        table.append(row)
        print(f"  M={M:.3f} region={region['label']} roi={y1-y0}x{x1-x0} seq={seq}  "
              + " ".join(f"sat@{ft}={row[f'sat_psd_{ft}']:.5f}" for ft in TARGETS_FPX),
              flush=True)

    # rank by normalized-sat-PSD at each f_px
    print("\n" + "=" * 70)
    print("RADIAL-PSD RANKING (normalized sat-PSD at fixed f_px)")
    print("=" * 70)
    for ft in TARGETS_FPX:
        key = f"sat_psd_{ft}"
        ranked = sorted(table, key=lambda r: -r[key])
        print(f"\n  f_px={ft}:")
        for i, r in enumerate(ranked, 1):
            print(f"    {i:>2}. psd={r[key]:.5f}  M={r['M']:.2f}  {r['config'][:50]}")

    # write csv
    csvp = OUT / "psd_fpx.csv"
    if table:
        with csvp.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
            w.writeheader()
            for r in table:
                w.writerow(r)
    print(f"\nWROTE {csvp}")

    # plot curves
    plt.figure(figsize=(9, 6))
    for name, (M, rc, ps, rcl, pl) in sorted(curves.items(), key=lambda kv: kv[1][0]):
        plt.semilogy(rc, ps, label=f"M={M:.2f} {name.split(' | ')[0][:18]}", alpha=0.8)
    for ft in TARGETS_FPX:
        plt.axvline(ft, color="gray", ls=":", lw=0.8)
    plt.xlabel("f_px (cy/px)"); plt.ylabel("normalized radial PSD (sat)")
    plt.title("Radial PSD of best-focus magenta-pad ROI (saturation channel)")
    plt.legend(fontsize=6, ncol=2); plt.xlim(0, 0.45); plt.tight_layout()
    plt.savefig(str(OUT / "psd_curves_sat.png"), dpi=120); plt.close()
    print(f"WROTE {OUT/'psd_curves_sat.png'}")


if __name__ == "__main__":
    main()
