"""Stage AltEst-2 — P2 REFINED through-focus estimator (the de-confounded 2nd signal).

The Stage-AltEst A4 finding: the through-focus lapvar-vs-frame FWHM is genuinely
de-confounded (corr with N_eff ~ 0.00) but too COARSE — FWHM quantises to a few integer
frame counts and the modern macros tie. This driver extracts a battery of FINER, sub-bin
focus-response descriptors per patch, from the SAME full focus stack:

  * Gaussian-of-defocus fit to the lapvar(z) peak -> continuous sigma_z (frames) and a
    smooth FWHM (sub-frame, not quantised);
  * log-parabola peak fit -> sub-frame curvature kappa (2nd deriv of log-lapvar at peak),
    a scale-free acutance that a sharper optic maximises;
  * normalised peak sharpness = peak_height / area-under-curve (taller+tighter = sharper);
  * a high-frequency through-focus variant: instead of full-band lapvar, the energy in a
    FIXED SENSOR band (a band-pass via DoG) vs z -> its peak/width isolate the glass MTF
    at a chosen pixel frequency (the de-confounding principle), giving a P2 read that is
    directly comparable to P1's fixed-sensor-frequency axis.

Per patch we operate on a fixed-size SENSOR crop (no resample — focus width must stay in
real frames), so the descriptor is target-content-robust (relative across the same stack).
Sharded by SHARD. Reuses poc_altest_lib (read-only). Writes to altest2/.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_altest_lib as L
from poc_altest2_patch_driver import short_id, ap_to_n, patch_layout, GLOBAL_CL, GLOBAL_RL

SUBSET = HERE / "poc_altest2_subset.csv"
OUT = HERE / "poc_comb_chain_out" / "altest2"

# fixed-sensor band for the band-pass through-focus variant (cy/px); DoG sigmas chosen so
# the band centre ~ 0.12 cy/px (inside the P1 trustworthy window 0.10-0.15).
DOG_LO, DOG_HI = 1.2, 2.4   # px; band-pass ~ 0.07-0.14 cy/px


def bandpass_energy(crop):
    a = crop.astype(np.float32)
    g1 = cv2.GaussianBlur(a, (0, 0), DOG_LO)
    g2 = cv2.GaussianBlur(a, (0, 0), DOG_HI)
    d = g1 - g2
    return float(np.mean(d * d))


def scan_curves(jpgs, boxes):
    """ONE grayscale decode per frame -> per-box (seqs, full-band lapvar, bandpass energy)."""
    ib = {i: tuple(int(v) for v in b) for i, b in enumerate(boxes)}
    seqs = {i: [] for i in ib}; lvs = {i: [] for i in ib}; bps = {i: [] for i in ib}
    for seq, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        for i, (x0, y0, x1, y1) in ib.items():
            roi = g[y0:y1, x0:x1]
            if roi.size == 0 or min(roi.shape) < 24:
                continue
            seqs[i].append(seq); lvs[i].append(L.lapvar(roi)); bps[i].append(bandpass_energy(roi))
    return {i: (np.asarray(seqs[i], float), np.asarray(lvs[i], float), np.asarray(bps[i], float))
            for i in ib}


def gauss_fwhm(seqs, vals):
    """Fit a Gaussian to the baseline-subtracted peak region of vals(z). Returns
    (sigma_z frames, fwhm_subframe, peak_z). NaN if no clean peak."""
    if len(vals) < 7:
        return np.nan, np.nan, np.nan
    v = vals.astype(float)
    base = np.percentile(v, 10)
    v0 = np.clip(v - base, 0, None)
    pk = int(np.argmax(v0))
    peak = v0[pk]
    if peak <= 0:
        return np.nan, np.nan, np.nan
    # weighted-LS Gaussian on the upper half region around the peak
    sel = v0 >= 0.25 * peak
    z = seqs[sel]; y = v0[sel]
    if len(z) < 5 or np.ptp(z) < 2:
        return np.nan, np.nan, float(seqs[pk])
    # fit log(y) ~ a - (z-mu)^2/(2 sig^2)  => quadratic in z, weighted by y
    w = y / y.max()
    A = np.column_stack([np.ones_like(z), z, z * z])
    coef, *_ = np.linalg.lstsq(A * w[:, None], np.log(np.clip(y, 1e-9, None)) * w, rcond=None)
    c0, c1, c2 = coef
    if c2 >= 0:
        return np.nan, np.nan, float(seqs[pk])
    sigma_z = float(np.sqrt(-1.0 / (2 * c2)))
    mu = float(-c1 / (2 * c2))
    fwhm = 2.3548 * sigma_z
    return sigma_z, fwhm, mu


def log_parabola_curvature(seqs, vals):
    """Sub-frame 2nd-deriv of log-lapvar at the peak (acutance; sharper=more negative,
    we return its magnitude). Robust 3-pt parabola in log space around argmax."""
    if len(vals) < 5:
        return np.nan
    v = vals.astype(float)
    base = np.percentile(v, 10)
    v0 = np.clip(v - base, 1e-9, None)
    pk = int(np.argmax(v0))
    if pk < 1 or pk > len(v0) - 2:
        return np.nan
    ly = np.log(v0[pk - 1:pk + 2])
    # uniform frame spacing assumed locally; curvature = ly[0]-2ly[1]+ly[2]
    return float(-(ly[0] - 2 * ly[1] + ly[2]))


def peak_over_area(seqs, vals):
    if len(vals) < 7:
        return np.nan
    v = vals.astype(float)
    base = np.percentile(v, 10)
    v0 = np.clip(v - base, 0, None)
    area = np.trapezoid(v0, seqs)
    return float(v0.max() / area) if area > 0 else np.nan


def main():
    with SUBSET.open() as fh:
        configs = list(csv.DictReader(fh))
    shard = os.environ.get("SHARD")
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        configs = [c for k, c in enumerate(configs) if k % n == i]
    OUT.mkdir(parents=True, exist_ok=True)
    patches = patch_layout()
    rows = []
    for c in configs:
        cid = f"{c['lens']} | {c['mag_label']} | {c['aperture']}"
        sid = short_id(c); sd = Path(c["sample"]).parent
        p, M, jpgs = L.register_config(sd)
        if p is None:
            print(f"DROP {cid}", flush=True); continue
        n_marked = ap_to_n(c["aperture"]); n_eff = L.optics.effective_fnumber(n_marked, M)
        print(f"=== {sid} M={M:.3f} N_eff={n_eff:.1f} nstack={len(jpgs)} ===", flush=True)
        active = []
        for (a, b, a1, b1, plab) in patches:
            corners = [L.reg_auto.grid_xy_distorted(cc, rr, p)
                       for (cc, rr) in [(a, b), (a, b1), (a1, b), (a1, b1)]]
            xs = [pt[0] for pt in corners]; ys = [pt[1] for pt in corners]
            if (min(xs) < 60 or max(xs) > L.IMAGE_W - 60 or min(ys) < 60 or max(ys) > L.IMAGE_H - 60):
                continue
            active.append((plab, (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))))
        if not active:
            print("  no in-FOV patches", flush=True); continue
        curves = scan_curves(jpgs, [x[1] for x in active])
        for bi, (plab, box) in enumerate(active):
            seqs, lvs, bps = curves[bi]
            if len(seqs) < 7:
                continue
            sg, fw, mu = gauss_fwhm(seqs, lvs)
            kap = log_parabola_curvature(seqs, lvs)
            poa = peak_over_area(seqs, lvs)
            sg_b, fw_b, mu_b = gauss_fwhm(seqs, bps)
            kap_b = log_parabola_curvature(seqs, bps)
            rows.append(dict(config=cid, sid=sid, patch=plab, M=M, n_marked=n_marked,
                             n_eff=n_eff, nstack=len(jpgs),
                             g_sigma=sg, g_fwhm=fw, lp_curv=kap, peak_over_area=poa,
                             g_sigma_bp=sg_b, g_fwhm_bp=fw_b, lp_curv_bp=kap_b))
        print(f"  {len(active)} patches", flush=True)
    tag = (shard or "0_1").replace("/", "_")
    with (OUT / f"psffoc2_shard_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "sid", "patch", "M", "n_marked",
                                           "n_eff", "nstack", "g_sigma", "g_fwhm",
                                           "lp_curv", "peak_over_area", "g_sigma_bp",
                                           "g_fwhm_bp", "lp_curv_bp"])
        w.writeheader(); w.writerows(rows)
    print(f"WROTE psffoc2 shard {tag}: {len(rows)} rows", flush=True)


if __name__ == "__main__":
    main()
