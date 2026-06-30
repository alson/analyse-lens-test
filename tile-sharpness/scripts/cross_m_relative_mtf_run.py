#!/usr/bin/env python
"""Driver / CLI for the PRODUCTION cross-magnification relative glass-MTF estimator.

This is the committed driver for ``tile_sharpness.cross_m_relative_mtf``. It does the
heavy image extraction (which reuses the production registration + optics infra
READ-ONLY) and then calls the validated estimator core to produce the ranking, the
cross-estimator agreement, the consensus, and a markdown report — all with the
mandatory caveats header baked in.

  ---------------------------------------------------------------------------------
  THIS IS A FENCED TOOL. The output is a RELATIVE, FIXED-SENSOR-FREQUENCY glass-MTF
  ranking ("which lens has the higher MTF at this pixel frequency"), NOT an absolute
  MTF and NOT a subject-resolution ranking. Trustworthy only at f_px = 0.08-0.15.
  See the cross_m_relative_mtf module docstring before using the numbers.
  ---------------------------------------------------------------------------------

Stages (sharded on nufan; each writes per-shard CSVs that the analyse stage pools):

    extract   register each config; resample the SAME physical atlas patch onto a
              common subject-space grid; radial PSD per patch (PRIMARY estimator
              substrate). Also the pad-edge averaged-ESF MTF (P3.1) and the focus-stack
              through-focus defocus response — per-patch Gaussian-of-defocus FWHM (P2),
              both cross-checks. Sharded by --shard i/N.
    analyse   pool the shards, run the estimator core (chain + gates + bootstrap +
              jackknife + split-half), compute the cross-estimator consensus over the
              four corroborators (P1 spectral, P3.1 pad-edge, P3.2 deconvolution, P2
              through-focus), and write the ranking CSV + markdown report.

Usage (on nufan via the per-host venv):

    PYTHONPATH=src python scripts/cross_m_relative_mtf_run.py extract --shard 0/16
    ... (all shards) ...
    PYTHONPATH=src python scripts/cross_m_relative_mtf_run.py analyse --fpx 0.10

The validated 38-config subset lives in ``cross_m_relative_mtf_subset.csv`` (a copy of
the AltEst-2 subset). The estimator is target-/subset-agnostic; the gates refuse or
flag an input set on which the relative axis does not hold.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TS = HERE.parent
sys.path.insert(0, str(TS / "src"))

from tile_sharpness import cross_m_relative_mtf as X  # noqa: E402
from tile_sharpness import optics  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# production registration infra (read-only) + the warm/saturation channel decode.
apf = _load("apf", HERE / "atlas_periodic_fft.py")
reg_auto = apf.reg_auto
ccolor = _load("ccolor", HERE / "poc_comb_chain_contrast_color.py")
M_ANCHOR_SCALE = apf.M_ANCHOR_SCALE
IMAGE_W, IMAGE_H = apf.IMAGE_W, apf.IMAGE_H

SUBSET = HERE / "cross_m_relative_mtf_subset.csv"
OUT = HERE / "cross_m_relative_mtf_out"

# common-grid layout (validated AltEst-2 values).
PATCH_UNITS = 0.5
SAMPLES_PER_UNIT = int(X.SAMPLES_PER_UNIT)
GLOBAL_CL = (1.5, 11.0)
GLOBAL_RL = (0.5, 6.0)

# §L reference groupings for the known-orders gate report.
MODERN_MACRO_BARE = ["Z105_1_1_F8", "AF200_1_1_F8", "S105_1_1_F8", "S150_1_1_F8"]
VINTAGE = ["V55f28287318_1_1_F8", "V55f28537016_1_1_F8", "V55f35209088_1_1_F8",
           "V55f35258263_1_1_F8", "AF60_1_1_F8"]
DIOPTER_TAIL = ["Z100400+MCON-35_1_1.16_F8", "AF200+5T+6T_2_1_F8",
                "S150+5T+6T_1.8_1_F8", "AF200+6T_1.7_1_F8"]


# --------------------------------------------------------------------------- #
# config id helpers
# --------------------------------------------------------------------------- #

def short_id(c):
    lens = c["lens"]
    base = (lens.split(" + ")[0]
            .replace("NIKKOR Z MC 105mm f_2.8 VR S", "Z105")
            .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
            .replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "S105")
            .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "S150")
            .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100400")
            .replace("Nikon AF Micro-Nikkor 60mm f_2.8D", "AF60")
            .replace("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED", "Z70180")
            .replace("Nikon Micro-Nikkor 55mm f_2.8 AIS", "V55f28")
            .replace("Nikon Micro-Nikkor Auto 55mm f_3.5", "V55f35"))
    acc = ""
    if " + " in lens:
        acc = "+" + lens.split(" + ", 1)[1].replace(" ", "").replace("Olympus", "") \
            .replace("Canon", "C").replace("Nikon", "").replace("KenkoPro300DG1.4x", "Kenko14")
    return f"{base}{acc}_{c['mag_label']}_{c['aperture']}".replace(" ", "").replace("/", "")


def config_id(c):
    return f"{c['lens']} | {c['mag_label']} | {c['aperture']}"


def ap_to_n(a):
    return float(a.replace("F", "").replace("f_", "").replace("f", ""))


def patch_layout():
    out = []
    cl = GLOBAL_CL[0]
    i = 0
    while cl + PATCH_UNITS <= GLOBAL_CL[1]:
        rl = GLOBAL_RL[0]
        j = 0
        while rl + PATCH_UNITS <= GLOBAL_RL[1]:
            out.append((cl, rl, cl + PATCH_UNITS, rl + PATCH_UNITS, f"A{i:02d}{j:02d}"))
            rl += PATCH_UNITS
            j += 1
        cl += PATCH_UNITS
        i += 1
    return out


# --------------------------------------------------------------------------- #
# extraction primitives (port of the validated POC logic; reg_auto read-only)
# --------------------------------------------------------------------------- #

def register_config(sweep_dir):
    sweep_dir = Path(sweep_dir)
    jpgs = sorted(sweep_dir.glob("*.jpg")) + sorted(sweep_dir.glob("*.JPG"))
    if not jpgs:
        return None, None, []
    p = apf.register(jpgs)
    if p is None:
        return None, None, jpgs
    M = p["scale"] / M_ANCHOR_SCALE
    if not (0.2 < M < 3.5):
        return None, None, jpgs
    return p, M, jpgs


def _lapvar(a):
    return float(cv2.Laplacian(a.astype(np.float32), cv2.CV_32F).var())


def scan_all_boxes(jpgs, boxes):
    ib = {i: tuple(int(v) for v in b) for i, b in enumerate(boxes)}
    seqs = {i: [] for i in ib}
    lvs = {i: [] for i in ib}
    for seq, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        for i, (x0, y0, x1, y1) in ib.items():
            roi = g[y0:y1, x0:x1]
            if roi.size == 0 or min(roi.shape) < 16:
                continue
            seqs[i].append(seq)
            lvs[i].append(_lapvar(roi))
    return {i: (np.asarray(seqs[i], float), np.asarray(lvs[i], float)) for i in ib}


def _cum_vec(d4, k):
    d4 = np.asarray(d4, float)
    k = np.asarray(k, float)
    out = np.zeros_like(k)
    pos = k > 0
    kp = k[pos]
    k_int = np.floor(kp).astype(int)
    frac = kp - k_int
    full = k_int // 4
    rem = k_int % 4
    csum = np.concatenate([[0.0], np.cumsum(d4)])
    c = full * d4.sum() + csum[rem] + frac * d4[rem % 4]
    out[pos] = c
    return out


def atlas_rect_to_common_grid(img, p, cl0, rl0, cl1, rl1, samples_per_unit,
                              interp=cv2.INTER_CUBIC):
    """Resample the SAME physical atlas rectangle onto a fixed common subject grid.

    Each config is independently remapped onto the SAME grid (neither is resampled
    onto the other's pixels) so interpolation cannot bias the same-patch ratio.
    """
    W = int(round((cl1 - cl0) * samples_per_unit))
    H = int(round((rl1 - rl0) * samples_per_unit))
    if W < 16 or H < 16:
        return None
    cls = cl0 + (np.arange(W) + 0.5) / samples_per_unit
    rls = rl0 + (np.arange(H) + 0.5) / samples_per_unit
    CL, RL = np.meshgrid(cls, rls)
    th = p["theta_rad"]; x0 = p["x0_img"]; y0 = p["y0_img"]; s = p["scale"]
    U = _cum_vec(reg_auto.D_COL, CL.ravel()).reshape(CL.shape)
    V = _cum_vec(reg_auto.D_ROW, RL.ravel()).reshape(RL.shape)
    c, sn = np.cos(th), np.sin(th)
    xu = x0 + s * (c * U + sn * V)
    yu = y0 + s * (sn * U - c * V)
    if "k1" in p:
        dx = xu - reg_auto.DIST_CENTER[0]; dy = yu - reg_auto.DIST_CENTER[1]
        r2 = (dx * dx + dy * dy) / reg_auto.DIST_NORM ** 2
        f = 1.0 + p["k1"] * r2 + p["k2"] * r2 * r2
        xu = reg_auto.DIST_CENTER[0] + dx * f
        yu = reg_auto.DIST_CENTER[1] + dy * f
    mapx = xu.astype(np.float32); mapy = yu.astype(np.float32)
    if (mapx.min() < 2 or mapx.max() > IMAGE_W - 2
            or mapy.min() < 2 or mapy.max() > IMAGE_H - 2):
        return None
    return cv2.remap(img.astype(np.float32), mapx, mapy, interp,
                     borderMode=cv2.BORDER_REFLECT)


def decode_sat(jp):
    bgr = cv2.imread(str(jp), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return ccolor.channel_stack(bgr)["sat"].astype(np.float32)


def _hann2d(h, w):
    return np.outer(np.hanning(h), np.hanning(w))


def radial_psd(patch, nbins=64):
    """Windowed radial PSD; freq in cy per common-grid px (units cancel in the ratio)."""
    a = patch - patch.mean()
    h, w = a.shape
    a = a * _hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a))
    P = F.real ** 2 + F.imag ** 2
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fr = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    bins = np.linspace(0, 0.5, nbins + 1)
    idx = np.digitize(fr.ravel(), bins) - 1
    Pf = P.ravel()
    psd = np.full(nbins, np.nan)
    for b in range(nbins):
        m = idx == b
        if m.any():
            psd[b] = Pf[m].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, psd


def directional_psd(patch, radial_angle_deg, nbins=64, wedge_deg=35.0):
    """Radial PSD split into SAGITTAL vs TANGENTIAL wedges (for astigmatism).

    ``radial_angle_deg`` is the patch's field azimuth (the direction from the FRAME
    CENTRE to the patch, in the same flipped-y math convention as
    ``cross_m_relative_mtf.field_geometry``). The sagittal axis is ALONG that radial
    direction; the tangential axis is perpendicular. The 2D PSD is averaged only over
    the frequency-plane wedge within ``wedge_deg`` of each axis (both lobes), so the
    sagittal curve carries the spatial frequencies oriented along the field radius and
    the tangential curve those across it. Returns ``(fcen, psd_sag, psd_tan)`` with the
    SAME frequency bins as :func:`radial_psd` (cy per common-grid px; units cancel in
    the ratio). NaN bins where a wedge has no samples.
    """
    a = patch - patch.mean()
    h, w = a.shape
    a = a * _hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a))
    P = F.real ** 2 + F.imag ** 2
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fxn = (xx - cx) / w
    fyn = (yy - cy) / h
    fr = np.sqrt(fxn ** 2 + fyn ** 2)
    # frequency-plane azimuth, flipped-y to match field_geometry's convention.
    fang = np.degrees(np.arctan2(-fyn, fxn))
    # angular distance to the sagittal (radial) axis, folded to [0, 90].
    def _axis_mask(axis_deg):
        d = np.abs(((fang - axis_deg + 90.0) % 180.0) - 90.0)
        return d <= wedge_deg
    sag = _axis_mask(radial_angle_deg)
    tan = _axis_mask(radial_angle_deg + 90.0)
    bins = np.linspace(0, 0.5, nbins + 1)
    idx = np.digitize(fr.ravel(), bins) - 1
    Pf = P.ravel()
    sagf = sag.ravel()
    tanf = tan.ravel()
    psd_sag = np.full(nbins, np.nan)
    psd_tan = np.full(nbins, np.nan)
    for b in range(nbins):
        m = idx == b
        ms = m & sagf
        mt = m & tanf
        if ms.any():
            psd_sag[b] = Pf[ms].mean()
        if mt.any():
            psd_tan[b] = Pf[mt].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, psd_sag, psd_tan


# pad-edge averaged ESF (cross-check P3.1) ----------------------------------- #
HALF, BPP = 8.0, 4.0
TILT_LO, TILT_HI = 1.0, 14.0


def averaged_esf(g, half=HALF, bpp=BPP):
    g = g.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 99.0)
    H, W = g.shape
    nb = int(round(2 * half * bpp))
    edges_bins = np.linspace(-half, half, nb + 1)
    sums = np.zeros(nb); cnts = np.zeros(nb)
    n_used = 0
    ang = np.degrees(np.arctan2(gy, gx))
    strong = mag > thr
    sel_v = strong & (((np.abs(ang) > TILT_LO) & (np.abs(ang) < TILT_HI))
                      | ((np.abs(np.abs(ang) - 180) > TILT_LO)
                         & (np.abs(np.abs(ang) - 180) < TILT_HI)))
    ys, xs = np.where(sel_v)
    for x, y in zip(xs, ys):
        if x < half + 2 or x > W - half - 2:
            continue
        row = g[y, int(x - half - 1):int(x + half + 2)]
        if row.size < 2 * half:
            continue
        d = np.arange(row.size) - (half + 1)
        v = row.astype(np.float64)
        if gx[y, x] < 0:
            v = v[::-1]; d = -d[::-1]
        idx = np.clip(np.digitize(d, edges_bins) - 1, 0, nb - 1)
        np.add.at(sums, idx, v); np.add.at(cnts, idx, 1.0)
        n_used += 1
    sel_h = strong & ((np.abs(np.abs(ang) - 90) > TILT_LO)
                      & (np.abs(np.abs(ang) - 90) < TILT_HI))
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
    if centres is None or len(centres) < 12:
        return None
    step = np.median(np.diff(centres))
    esf = np.asarray(esf, float)
    lo, hi = np.percentile(esf, 5), np.percentile(esf, 95)
    if hi - lo < 1e-6:
        return None
    e = (esf - lo) / (hi - lo)
    lsf = np.gradient(e, centres)
    win = np.hanning(len(lsf))
    F = np.fft.rfft(lsf * win)
    freqs = np.fft.rfftfreq(len(lsf), d=step)
    mtf = np.abs(F)
    m0 = mtf[0]
    if not np.isfinite(m0) or m0 <= 0:
        return None
    mtf = mtf / m0
    return freqs, mtf


# relative deconvolution (cross-check P3.2) ---------------------------------- #
FPX_LO, FPX_HI = 0.06, 0.22


def amp_radial(patch, nbins=48):
    a = patch.astype(np.float64); a = a - a.mean()
    h, w = a.shape
    a = a * _hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a))
    A = np.abs(F)
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fr = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    bins = np.linspace(0, 0.5, nbins + 1)
    idx = np.digitize(fr.ravel(), bins) - 1
    Af = A.ravel()
    amp = np.full(nbins, np.nan)
    for b in range(nbins):
        m = idx == b
        if m.any():
            amp[b] = Af[m].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, amp


# --------------------------------------------------------------------------- #
# extract stage
# --------------------------------------------------------------------------- #

def _apply_out_override(args):
    """Point the module-global OUT at ``--out`` so a subset run uses its own subdir."""
    global OUT
    if getattr(args, "out", None):
        OUT = Path(args.out)


def cmd_extract(args):
    _apply_out_override(args)
    subset_path = Path(args.subset) if getattr(args, "subset", None) else SUBSET
    with subset_path.open() as fh:
        configs = list(csv.DictReader(fh))
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        configs = [c for k, c in enumerate(configs) if k % n == i]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "patches").mkdir(exist_ok=True)
    patches = patch_layout()
    psd_rows, meta_rows, padedge_rows, psffoc_rows = [], [], [], []
    fieldtag_rows = []
    # frame centre = registration/optical centre (~ image centre).
    cx_frame, cy_frame = reg_auto.DIST_CENTER
    FIELD_FPX = (0.10, 0.15)  # operating points the field amps are read at
    for c in configs:
        cid = config_id(c); sid = short_id(c)
        sd = Path(c["sample"]).parent
        p, M, jpgs = register_config(sd)
        if p is None:
            print(f"DROP {cid}: reg fail", flush=True)
            continue
        n_marked = ap_to_n(c["aperture"])
        ccl = 0.5 * (GLOBAL_CL[0] + GLOBAL_CL[1]); crl = 0.5 * (GLOBAL_RL[0] + GLOBAL_RL[1])
        x00, y00 = reg_auto.grid_xy_distorted(ccl, crl, p)
        xu, yu = reg_auto.grid_xy_distorted(ccl + 1.0, crl, p)
        xv, yv = reg_auto.grid_xy_distorted(ccl, crl + 1.0, p)
        px_per_unit = 0.5 * (np.hypot(xu - x00, yu - y00) + np.hypot(xv - x00, yv - y00))
        n_eff = optics.effective_fnumber(n_marked, M)
        ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / 229.9
        print(f"=== {sid} M={M:.3f} rmse={p['reg_fit_rmse_px']:.1f} "
              f"px/unit={px_per_unit:.0f} ===", flush=True)
        meta_rows.append(dict(config=cid, sid=sid, M=M, rmse=p["reg_fit_rmse_px"],
                              n_marked=n_marked, n_eff=n_eff, px_per_unit=px_per_unit,
                              lens=c["lens"], mag_label=c["mag_label"],
                              aperture=c["aperture"]))
        active = []
        for (a, b, a1, b1, plab) in patches:
            corners = [reg_auto.grid_xy_distorted(cc, rr, p)
                       for (cc, rr) in [(a, b), (a, b1), (a1, b), (a1, b1)]]
            xs = [pt[0] for pt in corners]; ys = [pt[1] for pt in corners]
            if (min(xs) < 60 or max(xs) > IMAGE_W - 60
                    or min(ys) < 60 or max(ys) > IMAGE_H - 60):
                continue
            active.append((plab, a, b, a1, b1,
                           (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))))
        if not active:
            print("  no in-FOV patches", flush=True)
            continue
        curves = scan_all_boxes(jpgs, [x[5] for x in active])
        # P2 through-focus defocus response: the SAME per-frame lapvar curves the
        # PSD/pad-edge stage scans for best focus also carry the focus-response SHAPE.
        # Per patch fit a Gaussian-of-defocus to the lapvar(z) peak -> sub-frame FWHM.
        n_psffoc = 0
        for bi, (plab, a, b, a1, b1, box) in enumerate(active):
            seqs, lvs = curves[bi]
            _, fwhm, _ = X.gaussian_defocus_fwhm(seqs, lvs)
            if np.isfinite(fwhm):
                psffoc_rows.append(dict(config=cid, sid=sid, patch=plab, M=M,
                                        n_marked=n_marked, n_eff=n_eff,
                                        nstack=len(jpgs), fwhm=fwhm))
                n_psffoc += 1
        by_frame = {}
        for bi, (plab, a, b, a1, b1, box) in enumerate(active):
            seqs, lvs = curves[bi]
            if len(seqs) == 0:
                continue
            seq = int(seqs[int(np.argmax(lvs))])
            by_frame.setdefault(seq, []).append((plab, a, b, a1, b1, box))
        per_patch_mtf = []
        ncfg_edges = 0
        for seq, group in by_frame.items():
            chan = decode_sat(jpgs[seq])
            gray = cv2.imread(str(jpgs[seq]), cv2.IMREAD_GRAYSCALE)
            if chan is None:
                continue
            for (plab, a, b, a1, b1, box) in group:
                patch = atlas_rect_to_common_grid(chan, p, a, b, a1, b1,
                                                  samples_per_unit=SAMPLES_PER_UNIT)
                if patch is None:
                    continue
                np.save(OUT / "patches" / f"{sid}__{plab}.npy", patch.astype(np.float32))
                f_grid, psd = radial_psd(patch)
                for fg, ps in zip(f_grid, psd):
                    if np.isfinite(ps):
                        psd_rows.append(dict(config=cid, sid=sid, patch=plab, M=M,
                                             n_marked=n_marked, f_grid=fg, psd=ps))
                # ---- LOCATION-AWARE field tag for this patch -------------------- #
                # patch grid centre -> image px -> distance/angle from frame centre.
                pcx, pcy = reg_auto.grid_xy_distorted(0.5 * (a + a1),
                                                      0.5 * (b + b1), p)
                geo = X.field_geometry(pcx, pcy, cx_frame, cy_frame,
                                       IMAGE_W, IMAGE_H, m=M)
                ft = dict(config=cid, sid=sid, patch=plab, M=M,
                          px=float(pcx), py=float(pcy),
                          dist_px=geo["dist_px"], field_height=geo["field_height"],
                          angle_deg=geo["angle_deg"],
                          dist_subject_mm=geo["dist_subject_mm"])
                # isotropic per-patch amplitude at each operating sensor frequency.
                amp_iso = np.sqrt(np.clip(psd, 1e-30, None))
                # sagittal / tangential amplitude wedges (relative to field radial dir).
                fsag, psd_sag, psd_tan = directional_psd(patch, geo["angle_deg"])
                amp_sag = np.sqrt(np.clip(psd_sag, 1e-30, None))
                amp_tan = np.sqrt(np.clip(psd_tan, 1e-30, None))
                for fpx in FIELD_FPX:
                    fg_sensor = fpx * px_per_unit / SAMPLES_PER_UNIT
                    def _read(fcurve, vcurve):
                        ok = np.isfinite(vcurve)
                        if ok.sum() < 2 or not (fcurve[ok].min() <= fg_sensor
                                                <= fcurve[ok].max()):
                            return float("nan")
                        return float(np.interp(fg_sensor, fcurve[ok], vcurve[ok]))
                    ft[f"amp_fpx{fpx}"] = _read(f_grid, amp_iso)
                    ft[f"amp_sag_fpx{fpx}"] = _read(fsag, amp_sag)
                    ft[f"amp_tan_fpx{fpx}"] = _read(fsag, amp_tan)
                fieldtag_rows.append(ft)
                # pad-edge ESF cross-check on the sensor-space crop
                if gray is not None:
                    x0, y0, x1, y1 = box
                    crop = gray[y0:y1, x0:x1].astype(np.float32)
                    if crop.size and min(crop.shape) >= 40:
                        cen, esf, ne = averaged_esf(crop)
                        ncfg_edges += ne
                        res = esf_to_mtf(cen, esf)
                        if res is not None:
                            per_patch_mtf.append((res[0], res[1], ne))
        if per_patch_mtf:
            common_f = np.linspace(0.0, 0.5, 64)
            stacks = [np.interp(common_f, fr, mt) for fr, mt, _ in per_patch_mtf]
            ws = np.array([ne for *_, ne in per_patch_mtf], float)
            ws = ws / ws.sum()
            mtf_agg = np.average(np.array(stacks), axis=0, weights=ws)
            rec = dict(config=cid, sid=sid, M=M, n_eff=n_eff, ceil_cypx=ceil_cypx,
                       n_edge_samples=ncfg_edges, n_patches=len(per_patch_mtf))
            for fpx in (0.10, 0.15):
                rec[f"mtf_fpx{fpx}"] = float(np.interp(fpx, common_f, mtf_agg))
            padedge_rows.append(rec)
        print(f"  {len(active)} in-FOV patches, {len(by_frame)} focus frames, "
              f"{ncfg_edges} pad edges, {n_psffoc} through-focus fits", flush=True)

    tag = (args.shard or "0_1").replace("/", "_")
    pd.DataFrame(psd_rows).to_csv(OUT / f"psd_shard_{tag}.csv", index=False)
    pd.DataFrame(meta_rows).to_csv(OUT / f"meta_shard_{tag}.csv", index=False)
    pd.DataFrame(padedge_rows).to_csv(OUT / f"padedge_shard_{tag}.csv", index=False)
    pd.DataFrame(psffoc_rows).to_csv(OUT / f"psffoc_shard_{tag}.csv", index=False)
    pd.DataFrame(fieldtag_rows).to_csv(OUT / f"fieldtag_shard_{tag}.csv", index=False)
    print(f"WROTE shard {tag}: {len(psd_rows)} psd, {len(meta_rows)} meta, "
          f"{len(padedge_rows)} padedge, {len(psffoc_rows)} psffoc, "
          f"{len(fieldtag_rows)} fieldtag", flush=True)


# --------------------------------------------------------------------------- #
# cross-check estimator: relative deconvolution (from the saved patches)
# --------------------------------------------------------------------------- #

def decon_scores(meta):
    ppu = dict(zip(meta.sid, meta.px_per_unit))
    files = sorted((OUT / "patches").glob("*__*.npy"))
    by_cell = {}
    for f in files:
        sid, cell = f.stem.split("__")
        by_cell.setdefault(cell, []).append((sid, f))
    cache = {}
    edges = []
    for cell, items in by_cell.items():
        cur = {}
        for sid, f in items:
            if (sid, cell) not in cache:
                cache[(sid, cell)] = amp_radial(np.load(f))
            cur[sid] = cache[(sid, cell)]
        sids = [s for s in cur if s in ppu]
        for ia in range(len(sids)):
            for ib in range(ia + 1, len(sids)):
                sa, sb = sids[ia], sids[ib]
                fa, Aa = cur[sa]; fb, Ab = cur[sb]
                fpx = np.linspace(FPX_LO, FPX_HI, 16)
                fga = fpx * ppu[sa] / X.SAMPLES_PER_UNIT
                fgb = fpx * ppu[sb] / X.SAMPLES_PER_UNIT
                if not (fa.min() <= fga.min() and fga.max() <= fa.max()
                        and fb.min() <= fgb.min() and fgb.max() <= fb.max()):
                    continue
                va = np.interp(fga, fa, Aa); vb = np.interp(fgb, fb, Ab)
                m = (va > 0) & (vb > 0)
                if m.sum() < 6:
                    continue
                lr = np.log(va[m] / vb[m])
                x = fpx[m] ** 2
                w = 1.0 / (1.0 + 10 * fpx[m] ** 2)
                A1 = np.column_stack([np.ones_like(x), x])
                coef, *_ = np.linalg.lstsq(A1 * w[:, None], lr * w, rcond=None)
                delta = -coef[1] / (2 * np.pi ** 2)  # sa^2 - sb^2 (px^2)
                edges.append((sa, sb, float(delta), float(m.sum())))
    if len({e[0] for e in edges} | {e[1] for e in edges}) < 3:
        return {}
    scores = X.chain_solve(edges, sorted({e[0] for e in edges} | {e[1] for e in edges}))
    # blur-variance: smaller = sharper -> negate so higher == sharper.
    return {s: -v for s, v in scores.items()}


# --------------------------------------------------------------------------- #
# cross-check estimator: P2 through-focus defocus response (from the shards)
# --------------------------------------------------------------------------- #

def p2_scores(meta):
    """Pool the psffoc shards and compute per-config P2 scores (higher == sharper).

    Returns ``{sid: score}`` (empty if no through-focus shards were written, e.g. an
    extract run from before P2 was added — keeps analyse backward-compatible).
    """
    files = list(OUT.glob("psffoc_shard_*.csv"))
    frames = [pd.read_csv(f) for f in files]
    frames = [d for d in frames if not d.empty and "fwhm" in d.columns]
    if not frames:
        return {}
    tf = pd.concat(frames, ignore_index=True)
    return X.through_focus_scores(tf)


# --------------------------------------------------------------------------- #
# analyse stage
# --------------------------------------------------------------------------- #

def cmd_analyse(args):
    _apply_out_override(args)
    psd = pd.concat([pd.read_csv(f) for f in OUT.glob("psd_shard_*.csv")],
                    ignore_index=True)
    meta = pd.concat([pd.read_csv(f) for f in OUT.glob("meta_shard_*.csv")],
                     ignore_index=True).drop_duplicates("config")
    m_by_sid = dict(zip(meta.sid, meta.M))
    print(f"loaded {psd.sid.nunique()} configs, {psd.patch.nunique()} patches")

    # ---- f_px window sweep (gate transparency) ------------------------------ #
    print("\n" + "=" * 72 + "\nf_px window sweep (primary estimator P1)\n" + "=" * 72)
    sweep_rows = []
    for f_px in (0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25):
        try:
            gate, _, _ = X.gate_self_check(psd, meta, f_px)
        except ValueError as e:
            print(f"f_px={f_px}: {e}")
            continue
        sweep_rows.append(dict(f_px=f_px, n_nodes=gate.n_nodes, n_edges=gate.n_edges,
                               ncomp=gate.n_components, resid=round(gate.resid_rms, 3),
                               corr_M=round(gate.corr_M, 3),
                               empty_mag=";".join(gate.empty_mag_floats) or "none",
                               in_window=gate.in_window, passed=gate.passed))
        print(f"f_px={f_px:.2f}: nodes={gate.n_nodes:2d} edges={gate.n_edges:5d} "
              f"comp={gate.n_components} resid={gate.resid_rms:.3f} "
              f"corr(M,score)={gate.corr_M:+.3f} floats={gate.empty_mag_floats or 'none'} "
              f"{'PASS' if gate.passed else 'OUTSIDE-WINDOW/FAIL'}")
    pd.DataFrame(sweep_rows).to_csv(OUT / "fpx_sweep.csv", index=False)

    # ---- primary ranking at the chosen f_px --------------------------------- #
    f_px = args.fpx
    ranking = X.rank_configs(psd, meta, f_px, n_boot=args.n_boot, strict=False)
    gate = ranking.gate
    print("\n" + "=" * 72 + f"\nPRIMARY cross-M relative-MTF ranking @ f_px={f_px}\n"
          + "=" * 72)
    for msg in gate.messages():
        print("  [GATE] " + msg)
    print(ranking.table.round(4).to_string(index=False))

    # split-half repeatability + jackknife the M~2 bridge
    rho, ncommon = X.split_half_spearman(psd, meta, f_px)
    print(f"\nsplit-half repeatability: Spearman={rho:+.3f} (n={ncommon})")
    _, _, pair_cells = X.gate_self_check(psd, meta, f_px)
    m2 = [s for s in m_by_sid if m_by_sid.get(s, 0) > 1.9 and s in set(ranking.table.sid)]
    jk = X.jackknife_bridge(psd, meta, f_px, m2, pair_cells)
    if jk:
        print("M~2 transitive-bridge jackknife (worst single-anchor score shift):")
        for t, w in sorted(jk.items()):
            print(f"   {t:30s} worst shift {w:.3f}  "
                  f"({'ROBUST' if w < 0.15 else 'SENSITIVE'})")

    # §L known-orders report
    rk = {s: i for i, s in enumerate(ranking.table.sid)}

    def med_rank(group):
        v = [rk[s] for s in group if s in rk]
        return float(np.median(v)) if v else float("nan")

    print(f"\n§L known orders (lower=sharper): modern-macro={med_rank(MODERN_MACRO_BARE):.1f}"
          f" vintage55/60={med_rank(VINTAGE):.1f} diopter-tail={med_rank(DIOPTER_TAIL):.1f}"
          " (want macro<vintage<diopter)")

    # ---- cross-estimator agreement + consensus ------------------------------ #
    series = {}
    for fp in (0.10, 0.12, 0.15):
        try:
            _, sc, _ = X.gate_self_check(psd, meta, fp)
            series[f"P1_fpx{fp}"] = sc
        except ValueError:
            pass
    pe = OUT.glob("padedge_shard_*.csv")
    pe_files = list(pe)
    if pe_files:
        ped = pd.concat([pd.read_csv(f) for f in pe_files], ignore_index=True)
        ped = ped.dropna(subset=["mtf_fpx0.1"]) if "mtf_fpx0.1" in ped else ped
        if "mtf_fpx0.1" in ped:
            series["P31_padedge"] = dict(zip(ped.sid, ped["mtf_fpx0.1"]))
    dec = decon_scores(meta)
    if dec:
        series["P32_decon"] = dec

    # ---- P2 through-focus defocus-response corroborator (4th estimator) ------ #
    p2 = p2_scores(meta)
    if p2:
        series["P2_psffoc"] = p2
        n_eff_by_sid = dict(zip(meta.sid, meta.n_eff))
        corr_neff = X.p2_deconfound_corr(p2, n_eff_by_sid)
        corr_m = X.deconfound_corr(p2, m_by_sid)  # reuse: corr(M, score)
        from scipy.stats import spearmanr as _spearman
        print("\n" + "=" * 72 + "\nP2 through-focus corroborator (defocus response)\n"
              + "=" * 72)
        print(f"de-confound self-check: corr(N_eff, P2)={corr_neff:+.3f} "
              f"(want |.| <= {X.P2_DECONFOUND_MAX_ABS_CORR}; "
              f"{'OK' if X.p2_deconfound_ok(corr_neff) else 'FAIL'}); "
              f"corr(M, P2)={corr_m:+.3f}")
        for fp in (0.10, 0.12, 0.15):
            key = f"P1_fpx{fp}"
            if key not in series:
                continue
            common = sorted(set(series[key]) & set(p2))
            if len(common) >= 6:
                rho, _ = _spearman([series[key][k] for k in common],
                                   [p2[k] for k in common])
                print(f"  P2 vs {key}: Spearman={rho:+.3f} (n={len(common)})")

    print("\n" + "=" * 72 + "\nCross-estimator agreement (Spearman)\n" + "=" * 72)
    mat = X.cross_estimator_agreement(series)
    print(mat.to_string())
    mat.to_csv(OUT / "cross_estimator_agreement.csv")

    members = [k for k in ("P1_fpx0.1", "P1_fpx0.12", "P31_padedge", "P32_decon",
                           "P2_psffoc")
               if k in series]
    cons = X.consensus_ranking(series, members)
    print("\n" + "=" * 72 + "\nConsensus cross-M relative ranking\n" + "=" * 72)
    print(cons[["consensus_rank", "sid", "mean_rank", "rank_std",
                "n_estimators"]].to_string(index=False))

    # ---- write the committed ranking CSV + markdown report ------------------ #
    p2_selfcheck = None
    if p2:
        p2_selfcheck = dict(corr_neff=X.p2_deconfound_corr(p2, dict(zip(meta.sid, meta.n_eff))),
                            corr_m=X.deconfound_corr(p2, m_by_sid), n=len(p2))
    write_ranking_csv(OUT / "cross_m_relative_mtf_ranking.csv", ranking)
    write_report(OUT / "cross_m_relative_mtf_REPORT.md", ranking, mat, cons,
                 rho, ncommon, jk, sweep_rows, med_rank, p2_selfcheck)
    print(f"\nWROTE {OUT / 'cross_m_relative_mtf_ranking.csv'} and the markdown report")

    # ---- LOCATION-AWARE field analysis (additive; needs fieldtag shards) ----- #
    run_field_analysis(meta, f_px=f_px)


# --------------------------------------------------------------------------- #
# LOCATION-AWARE field analysis stage (additive)
# --------------------------------------------------------------------------- #

def _load_fieldtags():
    files = list(OUT.glob("fieldtag_shard_*.csv"))
    frames = [pd.read_csv(f) for f in files]
    frames = [d for d in frames if not d.empty and "field_height" in d.columns]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def run_field_analysis(meta=None, f_px=X.FPX_DEFAULT):
    """Derive + emit the location-aware field products from the fieldtag shards.

    Emits (under OUT):
      * per-patch field-tagged record CSV (the raw deliverable),
      * field-coverage descriptor CSV (per-config; where patches exist),
      * radial-falloff zone + ratio CSVs,
      * azimuthal-asymmetry (decentering) CSV,
      * astigmatism-index CSV,
      * field-resolved relative ranking CSV (centre/mid/corner),
      * a field-map PNG for a sharp and a soft config,
      * a markdown field note with the caveats header.
    """
    ft = _load_fieldtags()
    if ft is None:
        print("\n[field] no fieldtag shards found — run extract to produce them; "
              "skipping location-aware analysis.")
        return
    if meta is None:
        meta = pd.concat([pd.read_csv(f) for f in OUT.glob("meta_shard_*.csv")],
                         ignore_index=True).drop_duplicates("config")
    # The fieldtag shards only carry amps at the operating points the extract stage
    # emitted (FIELD_FPX = 0.10, 0.15). If the requested f_px lacks a column, fall
    # back to 0.10 AND relabel f_px to that fallback so every caveat / header / print
    # matches the data actually used (no mislabelling, e.g. an --fpx 0.12 request).
    if f"amp_fpx{f_px}" not in ft.columns:
        fallback = 0.10
        print(f"\n[field] no per-patch amp column for f_px={f_px}; the fieldtag shards "
              f"only carry {sorted(c.split('amp_fpx')[1] for c in ft.columns if c.startswith('amp_fpx'))} "
              f"-> using f_px={fallback} for the field analysis.")
        f_px = fallback
    amp_col = f"amp_fpx{f_px}"
    sag_col = amp_col.replace("amp_", "amp_sag_")
    tan_col = amp_col.replace("amp_", "amp_tan_")
    ft = ft.rename(columns={amp_col: "amp", sag_col: "amp_sag", tan_col: "amp_tan"})

    print("\n" + "=" * 72 + "\nLOCATION-AWARE field analysis "
          f"(f_px={f_px}; per-patch frame position)\n" + "=" * 72)

    # raw per-patch field-tagged record (the core deliverable)
    raw = X.assign_field_zones(ft)
    with (OUT / "field_per_patch.csv").open("w", newline="") as fh:
        fh.write(_field_caveats(f_px) + "\n")
        raw.round(5).to_csv(fh, index=False)

    cov = X.field_coverage(ft)
    cov.round(4).to_csv(OUT / "field_coverage.csv", index=False)
    print("\nField coverage (richest first; field_supported=False => do NOT "
          "over-interpret):")
    print(cov[["sid", "n_patches", "field_height_min", "field_height_max",
               "field_height_span", "angle_span_deg", "zones_populated",
               "field_supported"]].round(3).to_string(index=False))

    zone_tbl, ratio_tbl = X.radial_falloff(ft, value_col="amp")
    zone_tbl.round(4).to_csv(OUT / "field_radial_zone.csv", index=False)
    ratio_tbl.round(4).to_csv(OUT / "field_radial_ratio.csv", index=False)
    print("\nRadial falloff (corner/centre amp ratio; <1 = softens to corner; "
          "NaN = corner or centre not sampled):")
    print(ratio_tbl.round(3).to_string(index=False))

    azi = X.azimuthal_asymmetry(ft, value_col="amp")
    azi.round(4).to_csv(OUT / "field_azimuthal.csv", index=False)
    print("\nAzimuthal asymmetry / decentering (lr>0 => right sharper; "
          "supported=False => too few in-band patches):")
    print(azi[["sid", "n_in_band", "lr", "tb", "asymmetry_mag",
               "asymmetry_dir_deg", "supported"]].round(3).to_string(index=False))

    astig = X.astigmatism_index(ft, sag_col="amp_sag", tan_col="amp_tan")
    astig.round(4).to_csv(OUT / "field_astigmatism.csv", index=False)
    n_astig = int(astig["supported"].sum())
    print(f"\nAstigmatism index (log(sag/tan); >0 sag sharper; "
          f"{n_astig}/{len(astig)} configs supported):")
    print(astig[["sid", "n_in_band", "astig_index", "supported"]]
          .round(3).to_string(index=False))

    # field-resolved relative ranking (per zone)
    psd = pd.concat([pd.read_csv(f) for f in OUT.glob("psd_shard_*.csv")],
                    ignore_index=True)
    zrank = X.field_resolved_ranking(psd, meta, ft[["sid", "patch", "field_height"]],
                                     f_px=f_px)
    zr_rows = []
    for z, rk in zrank.items():
        for i, row in rk.table.iterrows():
            zr_rows.append(dict(zone=z, rank=i + 1, sid=row.sid,
                                score=row.score, M=row.M, n_cells=int(row.n_cells)))
    if zr_rows:
        pd.DataFrame(zr_rows).to_csv(OUT / "field_resolved_ranking.csv", index=False)
        print("\nField-resolved relative ranking (which configs hold their corners):")
        for z in X.FIELD_ZONES:
            zz = [r for r in zr_rows if r["zone"] == z]
            if zz:
                top = ", ".join(r["sid"] for r in zz[:3])
                print(f"  {z:7s} ({len(zz)} configs): top-3 {top}")

    _write_field_maps(raw, cov, f_px)
    _write_field_report(cov, ratio_tbl, azi, astig, zrank, f_px)
    print(f"\nWROTE location-aware field products under {OUT}")


def _field_caveats(f_px):
    lines = [
        "LOCATION-AWARE (field-position) sharpness — companion to the cross-M relative",
        "glass-MTF ranking. Per-patch sharpness is the RELATIVE, FIXED-SENSOR-FREQUENCY",
        f"amplitude at f_px={f_px} cy/px (same axis + fence as the ranking; NOT absolute",
        "MTF, NOT subject resolution). Position is DISTANCE + ANGLE from the FRAME CENTRE;",
        "field_height = dist / frame half-diagonal (0=centre, 1=corner).",
        "COVERAGE IS M-DEPENDENT + INCOMPLETE: high-M patches cluster (small field span,",
        "see field_coverage.field_supported); low-M wafer covers only PART of the frame so",
        "the true corners may be unsampled. Field maps are meaningful ONLY where patches",
        "exist — do NOT extrapolate into empty zones; trust configs with the richest",
        "coverage. Subset only; production-ready for the full reprocess.",
    ]
    return "\n".join("# " + ln for ln in lines)


def _write_field_maps(raw, cov, f_px):
    """Per-patch field-map scatter (frame x,y coloured by relative amp) for a sharp
    and a soft config with decent coverage."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # pragma: no cover - plotting optional
        print(f"[field] matplotlib unavailable ({e}); skipping field-map PNGs")
        return
    supported = cov[cov.field_supported]
    sids = list(supported.sid) if not supported.empty else list(cov.sid)
    if not sids:
        return
    # pick the sharpest- and softest-mean-amp supported configs
    mean_amp = (raw[raw.sid.isin(sids)].groupby("sid")["amp"].mean()
                .sort_values(ascending=False))
    if mean_amp.empty:
        return
    picks = [mean_amp.index[0], mean_amp.index[-1]]
    fig, axes = plt.subplots(1, len(picks), figsize=(6 * len(picks), 5.2),
                             squeeze=False)
    for ax, sid in zip(axes[0], picks):
        g = raw[raw.sid == sid]
        sc = ax.scatter(g.px, g.py, c=g.amp, s=140, cmap="viridis",
                        edgecolors="k", linewidths=0.4)
        ax.scatter([IMAGE_W / 2], [IMAGE_H / 2], marker="+", s=240, c="red")
        ax.set_xlim(0, IMAGE_W); ax.set_ylim(IMAGE_H, 0)  # image y down
        ax.set_aspect("equal")
        ax.set_title(f"{sid}\nrel amp @ f_px={f_px} (frame map)", fontsize=9)
        ax.set_xlabel("x px"); ax.set_ylabel("y px")
        fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle("Location-aware sharpness field map (sharp vs soft) — subset; "
                 "relative/fixed-sensor-freq", fontsize=10)
    fig.tight_layout()
    out = OUT / "field_map.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"[field] wrote {out} for {picks}")


def _write_field_report(cov, ratio_tbl, azi, astig, zrank, f_px):
    lines = ["# Location-aware (field-position) sharpness — subset\n"]
    lines.append("> " + _field_caveats(f_px).replace("# ", "").replace("\n", "\n> "))
    lines.append("")
    lines.append("## Field coverage (where patches actually exist)\n")
    lines.append("| config | n | fh_min | fh_max | fh_span | az_span° | zones | supported |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for _, r in cov.iterrows():
        lines.append(f"| {r.sid} | {int(r.n_patches)} | {r.field_height_min:.2f} | "
                     f"{r.field_height_max:.2f} | {r.field_height_span:.2f} | "
                     f"{r.angle_span_deg:.0f} | {r.zones_populated} | {r.field_supported} |")
    lines.append("")
    lines.append("## Radial falloff (corner/centre relative-amp ratio; <1 softens to corner)\n")
    lines.append("| config | corner/centre | mid/centre | supported |")
    lines.append("|---|---|---|---|")
    for _, r in ratio_tbl.iterrows():
        cc = "" if pd.isna(r.corner_centre_ratio) else f"{r.corner_centre_ratio:.3f}"
        mc = "" if pd.isna(r.mid_centre_ratio) else f"{r.mid_centre_ratio:.3f}"
        lines.append(f"| {r.sid} | {cc} | {mc} | {r.falloff_supported} |")
    lines.append("")
    lines.append("## Azimuthal asymmetry / decentering "
                 "(lr>0 right sharper; tb>0 top sharper)\n")
    lines.append("| config | n_band | lr | tb | mag | dir° | supported |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, r in azi.iterrows():
        if not r.supported:
            lines.append(f"| {r.sid} | {int(r.n_in_band)} | | | | | False |")
            continue
        lines.append(f"| {r.sid} | {int(r.n_in_band)} | {r.lr:+.3f} | {r.tb:+.3f} | "
                     f"{r.asymmetry_mag:.3f} | {r.asymmetry_dir_deg:+.0f} | True |")
    lines.append("")
    lines.append("## Astigmatism index (mean log(sag/tan); >0 sagittal sharper)\n")
    lines.append("| config | n_band | astig_index | supported |")
    lines.append("|---|---|---|---|")
    for _, r in astig.iterrows():
        ai = "" if pd.isna(r.astig_index) else f"{r.astig_index:+.3f}"
        lines.append(f"| {r.sid} | {int(r.n_in_band)} | {ai} | {r.supported} |")
    lines.append("")
    if zrank:
        lines.append("## Field-resolved relative ranking (top configs per zone)\n")
        for z in X.FIELD_ZONES:
            if z not in zrank:
                continue
            tops = ", ".join(zrank[z].table.sid.head(5))
            lines.append(f"- **{z}** ({len(zrank[z].table)} configs): {tops}")
        lines.append("")
    (OUT / "field_REPORT.md").write_text("\n".join(lines))


def _df_to_markdown(df, index_name=""):
    """Minimal markdown table (no tabulate dependency)."""
    cols = [index_name] + [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join(["---"] * len(cols)) + "|"]
    for idx, row in df.iterrows():
        cells = [str(idx)] + ["" if pd.isna(v) else f"{v}" for v in row]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def write_ranking_csv(path, ranking):
    with path.open("w", newline="") as fh:
        fh.write(X.caveats_header(ranking.f_px, comment="# ") + "\n")
        ranking.table.round(4).to_csv(fh, index=False)


def write_report(path, ranking, mat, cons, rho, ncommon, jk, sweep_rows, med_rank,
                 p2_selfcheck=None):
    g = ranking.gate
    lines = []
    lines.append("# Cross-magnification RELATIVE glass-MTF ranking\n")
    lines.append("> " + X.caveats_header(ranking.f_px, comment="").replace("\n", "\n> "))
    lines.append("")
    lines.append("## Gates (self-check on this input set)\n")
    lines.append(f"- f_px = **{ranking.f_px}** cy/px "
                 f"(in trustworthy window {X.FPX_WINDOW}: {g.in_window})")
    lines.append(f"- de-confound corr(M, score) = **{g.corr_M:+.3f}** "
                 f"(want <= {X.DECONFOUND_MAX_CORR}; {'OK' if g.deconfound_ok else 'FAIL'})")
    lines.append(f"- empty-magnification floats: "
                 f"**{g.empty_mag_floats or 'none'}** ({'OK' if g.empty_mag_ok else 'FAIL'})")
    lines.append(f"- graph: **{g.n_components} component(s)**, {g.n_edges} edges, "
                 f"residual {g.resid_rms:.3f}; "
                 f"under-bridged configs: {g.isolated_configs or 'none'}")
    lines.append(f"- split-half repeatability: Spearman **{rho:+.3f}** (n={ncommon})")
    if jk:
        worst = max(jk.values())
        lines.append(f"- M~2 transitive-bridge jackknife worst shift: **{worst:.3f}** "
                     f"({'ROBUST' if worst < 0.15 else 'SENSITIVE'})")
    lines.append(f"- §L known orders (lower rank = sharper): "
                 f"modern-macro {med_rank(MODERN_MACRO_BARE):.1f} < "
                 f"vintage55/60 {med_rank(VINTAGE):.1f} < "
                 f"diopter-tail {med_rank(DIOPTER_TAIL):.1f}")
    lines.append(f"- ALL GATES PASS: **{g.passed}**\n")
    lines.append("## f_px window sweep\n")
    lines.append("| f_px | nodes | edges | comp | resid | corr(M,score) | floats | in-window |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in sweep_rows:
        lines.append(f"| {r['f_px']} | {r['n_nodes']} | {r['n_edges']} | {r['ncomp']} | "
                     f"{r['resid']} | {r['corr_M']:+} | {r['empty_mag']} | {r['in_window']} |")
    lines.append("")
    lines.append(f"## Primary ranking @ f_px={ranking.f_px} "
                 "(higher score = sharper; sigma = bootstrap)\n")
    lines.append("| rank | config | score | M | sigma | n_cells |")
    lines.append("|---|---|---|---|---|---|")
    for i, row in ranking.table.iterrows():
        lines.append(f"| {i + 1} | {row.sid} | {row.score:+.3f} | {row.M:.2f} | "
                     f"{row.sigma:.3f} | {int(row.n_cells)} |")
    lines.append("")
    if p2_selfcheck is not None:
        ok = X.p2_deconfound_ok(p2_selfcheck["corr_neff"])
        lines.append("## P2 through-focus corroborator (defocus response)\n")
        lines.append(
            f"- de-confound self-check: corr(N_eff, P2) = **{p2_selfcheck['corr_neff']:+.3f}** "
            f"(want |.| <= {X.P2_DECONFOUND_MAX_ABS_CORR}; {'OK' if ok else 'FAIL'}); "
            f"corr(M, P2) = {p2_selfcheck['corr_m']:+.3f} "
            f"(n={p2_selfcheck['n']} configs)")
        lines.append(
            "- P2 is a PER-CONFIG defocus-based corroborator on a different physical "
            "principle (focus-stack response width, no spectrum): its self-check is "
            "corr(N_eff)~0, not the f_px window the spectral estimators fence.\n")
    lines.append("## Cross-estimator agreement (Spearman; higher-aligned = sharper)\n")
    lines.append(_df_to_markdown(mat, index_name="estimator"))
    lines.append("\n*Independent physical principles (same-patch spectral ratio P1, "
                 "pad-edge averaged-ESF P3.1, relative deconvolution P3.2, through-focus "
                 "defocus response P2) mutually positive = the cross-M relative signal "
                 "is real, not a single-method artifact.*\n")
    lines.append("## Consensus cross-M relative ranking "
                 "(rank-average; rank_std = disagreement = uncertainty)\n")
    lines.append("| consensus_rank | config | mean_rank | rank_std | n_estimators |")
    lines.append("|---|---|---|---|---|")
    for _, row in cons.iterrows():
        lines.append(f"| {int(row.consensus_rank)} | {row.sid} | {row.mean_rank:.2f} | "
                     f"{row.rank_std:.2f} | {int(row.n_estimators)} |")
    lines.append("")
    path.write_text("\n".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("extract", help="register + resample + PSD/pad-edge (sharded)")
    pe.add_argument("--shard", help="i/N shard selector")
    pe.add_argument("--subset", help="override the subset CSV (default the validated 38)")
    pe.add_argument("--out", help="override the output dir (default cross_m_relative_mtf_out)")
    pe.set_defaults(func=cmd_extract)
    pa = sub.add_parser("analyse", help="pool shards, run estimator core, write outputs")
    pa.add_argument("--fpx", type=float, default=X.FPX_DEFAULT,
                    help=f"sensor frequency cy/px (window {X.FPX_WINDOW}); default "
                         f"{X.FPX_DEFAULT}")
    pa.add_argument("--n-boot", dest="n_boot", type=int, default=120)
    pa.add_argument("--out", help="override the output dir")
    pa.set_defaults(func=cmd_analyse)
    pf = sub.add_parser("field", help="location-aware field analysis from existing "
                                      "fieldtag/psd shards (no re-extract)")
    pf.add_argument("--fpx", type=float, default=X.FPX_DEFAULT,
                    help=f"sensor frequency cy/px (window {X.FPX_WINDOW}); default "
                         f"{X.FPX_DEFAULT}")
    pf.add_argument("--out", help="override the output dir")

    def _field_cmd(a):
        _apply_out_override(a)
        run_field_analysis(f_px=a.fpx)
    pf.set_defaults(func=_field_cmd)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
