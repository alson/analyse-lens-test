"""Stage AltEst driver — approaches 3 (blind PSF / spectrum-falloff) and 4
(through-focus response shape). Both are per-image / per-stack: NO shared-patch
registration of the target spectrum needed (3 estimates the PSF from the natural-image
power-law falloff; 4 uses the stack's defocus response, target-content-independent).

We still register each config to pick the SAME physical atlas patches (so field
position is matched), and operate on SENSOR-space crops (not resampled) so the PSF
width is in real sensor px and the focus curve is in real rail steps.

Approach 3 — blind PSF per config:
  On the best-focus sat crop of each patch, fit log PSD(f) = log A - beta*log f
  - (2 pi^2 sigma^2) f^2  (natural f^-beta spectrum x Gaussian-PSF MTF^2). sigma is the
  Gaussian blur in sensor px; convert to SUBJECT um (sigma*4.35/M) for cross-M compare.
  Also a cepstral blur-radius estimate as a cross-check.

Approach 4 — through-focus response:
  Full lapvar-vs-frame stack curve per patch. Fit the peak; report peak-normalised FWHM
  in frames and a curvature (2nd deriv at peak). A sharper optic at the same N_eff/M has
  a TIGHTER focus response. We report raw FWHM and an N_eff/M-aware normalisation.

Sharded by SHARD="i/N".
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

SUBSET = HERE / "poc_comb_chain_subset.csv"
OUT = HERE / "poc_comb_chain_out" / "altest"

PATCH_UNITS = 0.5
GLOBAL_CL = (1.5, 11.0)
GLOBAL_RL = (0.5, 6.0)
SENSOR_NYQ = 0.5


def ap_to_n(a): return float(a.replace("F", "").replace("f_", "").replace("f", ""))


def short_id(c):
    lens = c["lens"]
    base = (lens.split(" + ")[0]
            .replace("NIKKOR Z MC 105mm f_2.8 VR S", "Z105")
            .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
            .replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "S105")
            .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "S150")
            .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100400"))
    acc = ""
    if " + " in lens:
        acc = "+" + lens.split(" + ", 1)[1].replace(" ", "").replace("Olympus", "") \
            .replace("Canon", "C").replace("Nikon", "")
    return f"{base}{acc}_{c['mag_label']}".replace(" ", "").replace("/", "")


def patch_layout():
    out = []
    cl = GLOBAL_CL[0]; i = 0
    while cl + PATCH_UNITS <= GLOBAL_CL[1]:
        rl = GLOBAL_RL[0]; j = 0
        while rl + PATCH_UNITS <= GLOBAL_RL[1]:
            out.append((cl, rl, cl + PATCH_UNITS, rl + PATCH_UNITS, f"A{i:02d}{j:02d}"))
            rl += PATCH_UNITS; j += 1
        cl += PATCH_UNITS; i += 1
    return out


def radial_psd_1d(crop):
    a = crop - crop.mean()
    h, w = a.shape
    a = a * np.outer(np.hanning(h), np.hanning(w))
    F = np.fft.fftshift(np.fft.fft2(a))
    P = F.real ** 2 + F.imag ** 2
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fr = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)  # cy/px
    bins = np.linspace(0, 0.5, 60)
    idx = np.digitize(fr.ravel(), bins) - 1
    psd = np.full(len(bins) - 1, np.nan)
    for b in range(len(bins) - 1):
        m = idx == b
        if m.any():
            psd[b] = P.ravel()[m].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, psd


def fit_gaussian_psf(fcen, psd):
    """Fit log psd = c - beta*log f - (2 pi^2 sigma^2) f^2 over a mid-band where SNR is
    good. Returns sigma (sensor px) or nan."""
    from numpy.polynomial import polynomial as P  # noqa
    m = np.isfinite(psd) & (fcen > 0.04) & (fcen < 0.42)
    if m.sum() < 8:
        return np.nan, np.nan
    f = fcen[m]; y = np.log(np.clip(psd[m], 1e-30, None))
    # design: [1, -log f, -f^2]; coefs [c, beta, k] with k = 2 pi^2 sigma^2
    A = np.column_stack([np.ones_like(f), -np.log(f), -f * f])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    c, beta, k = coef
    if k <= 0:
        return np.nan, float(beta)
    sigma = np.sqrt(k / (2 * np.pi ** 2))
    return float(sigma), float(beta)


def cepstral_blur(crop):
    """Cepstrum-based blur radius: the log-power-spectrum's inverse FFT shows a dip at
    the blur scale. Crude but target-agnostic; returns a radius proxy (px)."""
    a = crop - crop.mean()
    h, w = a.shape
    a = a * np.outer(np.hanning(h), np.hanning(w))
    F = np.fft.fft2(a)
    logp = np.log1p(np.abs(F))
    cep = np.abs(np.fft.ifft2(logp))
    cep = np.fft.fftshift(cep)
    cy, cx = h // 2, w // 2
    # radial profile of the cepstrum away from the origin; first strong min ~ blur scale
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    prof = []
    for rr in range(2, min(cy, cx)):
        m = (r >= rr) & (r < rr + 1)
        prof.append(cep[m].mean() if m.any() else np.nan)
    prof = np.array(prof)
    if len(prof) < 5 or not np.any(np.isfinite(prof)):
        return np.nan
    # the blur scale ~ location of the cepstral peak in 3..30 px range
    lo, hi = 1, min(40, len(prof))
    seg = prof[lo:hi]
    if not np.any(np.isfinite(seg)):
        return np.nan
    return float(np.nanargmax(seg) + lo + 2)


def focus_curve_metrics(seqs, lvs):
    """Peak-normalised FWHM (in frames) + curvature of the through-focus lapvar curve."""
    if len(lvs) < 7:
        return dict(fwhm=np.nan, peak_frac=np.nan, curv=np.nan, peak_idx=np.nan)
    lv = lvs.astype(float)
    base = np.percentile(lv, 10)
    lv0 = lv - base
    pk = np.argmax(lv0)
    peak = lv0[pk]
    if peak <= 0:
        return dict(fwhm=np.nan, peak_frac=np.nan, curv=np.nan, peak_idx=pk)
    half = peak / 2.0
    # FWHM by crossing search around the peak (in frame units)
    above = lv0 >= half
    # contiguous run containing pk
    lo = pk
    while lo > 0 and above[lo - 1]:
        lo -= 1
    hi = pk
    while hi < len(above) - 1 and above[hi + 1]:
        hi += 1
    fwhm = float(seqs[hi] - seqs[lo]) if hi > lo else 1.0
    # curvature: 2nd derivative at peak (normalised by peak)
    if 1 <= pk < len(lv0) - 1:
        curv = float((lv0[pk - 1] - 2 * lv0[pk] + lv0[pk + 1]) / max(peak, 1e-9))
    else:
        curv = np.nan
    return dict(fwhm=fwhm, peak_frac=float(peak / (lv.max() or 1)), curv=curv,
                peak_idx=float(seqs[pk]))


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
        print(f"=== {sid} M={M:.3f} N_eff={n_eff:.1f} ===", flush=True)
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
        curves = L.scan_all_boxes(jpgs, [x[1] for x in active])
        by_frame = {}
        fcmap = {}
        for bi, (plab, box) in enumerate(active):
            seqs, lvs = curves[bi]
            if len(seqs) == 0:
                continue
            fcmap[plab] = (box, focus_curve_metrics(seqs, lvs))
            seq = int(seqs[int(np.argmax(lvs))])
            by_frame.setdefault(seq, []).append(plab)
        boxof = {plab: box for plab, box in active}
        for seq, group in by_frame.items():
            chan = L.decode_channel(jpgs[seq], "sat")
            if chan is None:
                continue
            for plab in group:
                box, fc = fcmap[plab]
                x0, y0, x1, y1 = box
                crop = chan[y0:y1, x0:x1]
                if crop.size == 0 or min(crop.shape) < 32:
                    continue
                fcen, psd = radial_psd_1d(crop)
                sigma_px, beta = fit_gaussian_psf(fcen, psd)
                cep = cepstral_blur(crop)
                sigma_subj_um = sigma_px * 4.35 / M if np.isfinite(sigma_px) else np.nan
                rows.append(dict(config=cid, sid=sid, patch=plab, M=M, n_marked=n_marked,
                                 n_eff=n_eff, sigma_px=sigma_px, sigma_subj_um=sigma_subj_um,
                                 beta=beta, cepstral_px=cep,
                                 foc_fwhm=fc["fwhm"], foc_curv=fc["curv"],
                                 foc_peakfrac=fc["peak_frac"], foc_peakidx=fc["peak_idx"]))
        print(f"  {len(active)} patches, {len(by_frame)} focus frames", flush=True)
    tag = (shard or "0_1").replace("/", "_")
    with (OUT / f"psffoc_shard_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "sid", "patch", "M", "n_marked",
                                           "n_eff", "sigma_px", "sigma_subj_um", "beta",
                                           "cepstral_px", "foc_fwhm", "foc_curv",
                                           "foc_peakfrac", "foc_peakidx"])
        w.writeheader(); w.writerows(rows)
    print(f"WROTE psffoc shard {tag}: {len(rows)} rows", flush=True)


if __name__ == "__main__":
    main()
