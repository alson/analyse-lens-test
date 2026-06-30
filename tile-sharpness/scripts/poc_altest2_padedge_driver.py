"""Stage AltEst-2 — P3.1 PAD-EDGE MTF (the most-promising variant).

The Approach-5 SE-edge died on COVERAGE: the designed slanted-edge die is sparse and the
single-step quality gate rejects the bare macros. P3.1 fixes coverage by NOT relying on
one designed edge. Instead, inside each in-FOV atlas patch (sensor-space, where edges keep
the ~5 deg grid tilt that gives slanted-edge phase diversity) we detect ALL strong, locally
straight metal->substrate reflectance edges, and bin EVERY edge's perpendicular intensity
profile into ONE massively-averaged super-resolved ESF per config. Averaging over hundreds
of edges (a) beats the single-edge SNR/quality gate, (b) averages out the unstable interior
texture (we keep only the geometric step), (c) yields a clean LSF -> MTF read at a FIXED
SENSOR frequency (cy/px, common sensor MTF) -> a glass-MTF axis like P1.

Principle compliance: edges are LINEAR profiles (no thresholding/binarisation that would
destroy MTF); we keep the stable step geometry and discard interior. We aggregate, per
config, the polarity-consistent edge profiles, fit an ERF (sigma in px) + read MTF at fixed
cy/px and MTF50; we also report the diffraction-ceiling headroom and edge count (coverage).

Sharded by SHARD. Sensor-space (no resample). Reuses poc_altest_lib (read-only).
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
from poc_altest2_patch_driver import short_id, ap_to_n, patch_layout

SUBSET = HERE / "poc_altest2_subset.csv"
OUT = HERE / "poc_comb_chain_out" / "altest2"

HALF = 8.0          # perpendicular half-window (px) for the ESF
BPP = 4.0           # bins per px in the ESF
MIN_GRAD = None     # set per-patch as a percentile
MIN_EDGE_LEN = 9    # px, min straight run to accept an edge
TILT_LO, TILT_HI = 1.0, 14.0   # deg off-axis: need a slanted (not axis-aligned) edge


def detect_edges(g):
    """Return a list of (cx,cy, nx,ny, polarity) edge samples: strong gradient pixels
    whose local edge direction is near-vertical or near-horizontal but TILTED a few deg
    (so ESF binning gets sub-pixel phase). polarity = +1 if bright-on-high-x side."""
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 96)
    ys, xs = np.where(mag > thr)
    return xs, ys, gx, gy, mag, thr


def averaged_esf(g, half=HALF, bpp=BPP):
    """Massively-averaged ESF over all tilted metal/substrate edges in g.
    We split into near-vertical and near-horizontal edge families, sign-normalise each
    profile so the step rises the same way, and co-bin. Returns (centres, esf, n_edges)."""
    g = g.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    # only the strongest gradients = true metal/substrate pad boundaries (not interior
    # texture); a high percentile keeps the count manageable and the edges clean.
    thr = np.percentile(mag, 99.0)
    H, W = g.shape
    nb = int(round(2 * half * bpp))
    edges_bins = np.linspace(-half, half, nb + 1)
    sums = np.zeros(nb); cnts = np.zeros(nb)
    n_used = 0
    # angle of gradient; near-vertical edge => gradient near-horizontal (angle ~0/180)
    ang = np.degrees(np.arctan2(gy, gx))
    strong = mag > thr
    # near-vertical edges: |ang| within [TILT_LO,TILT_HI] of 0 or 180
    for fam, (amin, amax) in (("vert", (TILT_LO, TILT_HI)),):
        # vertical-ish edges (gradient horizontal, slightly tilted)
        sel_v = strong & (((np.abs(ang) > TILT_LO) & (np.abs(ang) < TILT_HI)) |
                          ((np.abs(np.abs(ang) - 180) > TILT_LO) & (np.abs(np.abs(ang) - 180) < TILT_HI)))
        ys, xs = np.where(sel_v)
        for x, y in zip(xs, ys):
            if x < half + 2 or x > W - half - 2:
                continue
            row = g[y, int(x - half - 1):int(x + half + 2)]
            if row.size < 2 * half:
                continue
            d = np.arange(row.size) - (half + 1)
            v = row.astype(np.float64)
            # sign so the step is rising (bright on +d). use local gradient sign
            if gx[y, x] < 0:
                v = v[::-1]; d = -d[::-1]
            idx = np.clip(np.digitize(d, edges_bins) - 1, 0, nb - 1)
            np.add.at(sums, idx, v); np.add.at(cnts, idx, 1.0)
            n_used += 1
        # horizontal-ish edges
        sel_h = strong & (((np.abs(np.abs(ang) - 90) > TILT_LO) & (np.abs(np.abs(ang) - 90) < TILT_HI)))
        ys, xs = np.where(sel_h)
        for x, y in zip(xs, ys):
            if y < half + 2 or y > H - half - 2:
                continue
            col = g[int(y - half - 1):int(y + half + 2), x]
            if col.size < 2 * half:
                continue
            d = np.arange(col.size) - (half + 1)
            v = col.astype(np.float64)
            if gy[y, x] < 0:
                v = v[::-1]; d = -d[::-1]
            idx = np.clip(np.digitize(d, edges_bins) - 1, 0, nb - 1)
            np.add.at(sums, idx, v); np.add.at(cnts, idx, 1.0)
            n_used += 1
    good = cnts >= 8
    if good.sum() < 10:
        return None, None, n_used
    centres = 0.5 * (edges_bins[:-1] + edges_bins[1:])
    return centres[good], sums[good] / cnts[good], n_used


def esf_to_mtf(centres, esf):
    """Differentiate ESF -> LSF, FFT -> MTF (cy/px). Returns (freqs cy/px, mtf, mtf50,
    sigma_px from an ERF fit). centres step = 1/BPP px."""
    if centres is None or len(centres) < 12:
        return None
    step = np.median(np.diff(centres))
    esf = np.asarray(esf, float)
    # normalise
    lo, hi = np.percentile(esf, 5), np.percentile(esf, 95)
    if hi - lo < 1e-6:
        return None
    e = (esf - lo) / (hi - lo)
    # LSF = derivative of the (monotone, normalised) ESF -> integrates to ~edge height.
    lsf = np.gradient(e, centres)
    # window to suppress truncation ripple, then FFT WITHOUT mean-subtraction so the DC
    # bin = the edge height (the correct MTF normaliser).
    win = np.hanning(len(lsf))
    F = np.fft.rfft(lsf * win)
    freqs = np.fft.rfftfreq(len(lsf), d=step)  # cy/px
    mtf = np.abs(F)
    m0 = mtf[0]
    if not np.isfinite(m0) or m0 <= 0:
        return None
    mtf = mtf / m0
    # MTF50 (first downward 0.5 crossing)
    half_idx = np.where(mtf < 0.5)[0]
    mtf50 = float(freqs[half_idx[0]]) if len(half_idx) else float(freqs[-1])
    # ERF sigma fit (the robust scalar blur, px) — fit the normalised ESF directly
    from scipy.optimize import curve_fit
    from scipy.special import erf
    sigma = np.nan
    try:
        def erf_model(d, a, b, d0, s):
            return a + b * 0.5 * (1 + erf((d - d0) / (np.sqrt(2) * s)))
        p0 = [float(e.min()), float(np.ptp(e)), 0.0, 1.0]
        popt, _ = curve_fit(erf_model, centres, e, p0=p0, maxfev=6000,
                            bounds=([-1, 0, -3, 0.2], [2, 3, 3, 8]))
        sigma = abs(float(popt[3]))
    except Exception:
        pass
    return freqs, mtf, mtf50, sigma


def mtf_at(freqs, mtf, f_px):
    if freqs is None:
        return np.nan
    return float(np.interp(f_px, freqs, mtf))


def main():
    with SUBSET.open() as fh:
        configs = list(csv.DictReader(fh))
    shard = os.environ.get("SHARD")
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        configs = [c for k, c in enumerate(configs) if k % n == i]
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    patches = patch_layout()
    for c in configs:
        cid = f"{c['lens']} | {c['mag_label']} | {c['aperture']}"
        sid = short_id(c); sd = Path(c["sample"]).parent
        p, M, jpgs = L.register_config(sd)
        if p is None:
            print(f"DROP {cid}", flush=True); continue
        n_marked = ap_to_n(c["aperture"]); n_eff = L.optics.effective_fnumber(n_marked, M)
        ceil_cypx = L.optics.diffraction_mtf50_sensor_lpmm(n_eff) / 229.9
        active = []
        for (a, b, a1, b1, plab) in patches:
            corners = [L.reg_auto.grid_xy_distorted(cc, rr, p)
                       for (cc, rr) in [(a, b), (a, b1), (a1, b), (a1, b1)]]
            xs = [pt[0] for pt in corners]; ys = [pt[1] for pt in corners]
            if (min(xs) < 60 or max(xs) > L.IMAGE_W - 60 or min(ys) < 60 or max(ys) > L.IMAGE_H - 60):
                continue
            active.append((plab, (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))))
        if not active:
            print(f"  {sid}: no in-FOV patches", flush=True); continue
        # best-focus once per box (scan grayscale full-band)
        curves = L.scan_all_boxes(jpgs, [x[1] for x in active])
        by_frame = {}
        for bi, (plab, box) in enumerate(active):
            seqs, lvs = curves[bi]
            if len(seqs) == 0:
                continue
            seq = int(seqs[int(np.argmax(lvs))])
            by_frame.setdefault(seq, []).append((plab, box))
        # accumulate one global ESF per config across all patches/edges
        all_sums = None
        ncfg_edges = 0
        per_patch_mtf = []
        for seq, group in by_frame.items():
            g = cv2.imread(str(jpgs[seq]), cv2.IMREAD_GRAYSCALE)
            if g is None:
                continue
            for (plab, box) in group:
                x0, y0, x1, y1 = box
                crop = g[y0:y1, x0:x1].astype(np.float32)
                if crop.size == 0 or min(crop.shape) < 40:
                    continue
                cen, esf, ne = averaged_esf(crop)
                ncfg_edges += ne
                res = esf_to_mtf(cen, esf)
                if res is not None:
                    freqs, mtf, mtf50, sigma = res
                    per_patch_mtf.append((freqs, mtf, mtf50, sigma, ne))
        if not per_patch_mtf:
            print(f"  {sid} M={M:.2f}: no valid averaged ESF ({ncfg_edges} edge samples)", flush=True)
            continue
        # aggregate: median MTF50/sigma + MTF read at fixed sensor freqs, weighted by edge count
        common_f = np.linspace(0.0, 0.5, 64)
        stacks = []
        ws = []
        mtf50s, sigmas = [], []
        for freqs, mtf, mtf50, sigma, ne in per_patch_mtf:
            stacks.append(np.interp(common_f, freqs, mtf))
            ws.append(ne); mtf50s.append(mtf50)
            if np.isfinite(sigma):
                sigmas.append(sigma)
        ws = np.array(ws, float); ws = ws / ws.sum()
        mtf_agg = np.average(np.array(stacks), axis=0, weights=ws)
        mtf50_med = float(np.median(mtf50s))
        sigma_med = float(np.median(sigmas)) if sigmas else np.nan
        rec = dict(config=cid, sid=sid, M=M, n_marked=n_marked, n_eff=n_eff,
                   ceil_cypx=ceil_cypx, n_patches=len(per_patch_mtf),
                   n_edge_samples=ncfg_edges, mtf50_cypx=mtf50_med,
                   mtf50_subj=mtf50_med * M, over=mtf50_med / ceil_cypx if ceil_cypx > 0 else np.nan,
                   sigma_px=sigma_med)
        for fpx in (0.10, 0.15, 0.20, 0.25):
            rec[f"mtf_fpx{fpx}"] = float(np.interp(fpx, common_f, mtf_agg))
        rows.append(rec)
        print(f"  {sid} M={M:.2f} N_eff={n_eff:.1f} patches={len(per_patch_mtf)} "
              f"edges={ncfg_edges} MTF50={mtf50_med:.3f}cy/px MTF@.15={rec['mtf_fpx0.15']:.3f} "
              f"sigma={sigma_med:.2f}px ceil={ceil_cypx:.3f}", flush=True)
    tag = (shard or "0_1").replace("/", "_")
    fields = ["config", "sid", "M", "n_marked", "n_eff", "ceil_cypx", "n_patches",
              "n_edge_samples", "mtf50_cypx", "mtf50_subj", "over", "sigma_px",
              "mtf_fpx0.1", "mtf_fpx0.15", "mtf_fpx0.2", "mtf_fpx0.25"]
    with (OUT / f"padedge_shard_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    print(f"WROTE padedge shard {tag}: {len(rows)} configs", flush=True)


if __name__ == "__main__":
    main()
