"""POC library — non-comb cross-magnification sharpness estimators (Stage AltEst).

UNTRACKED / exploratory. We import production + the committed comb-chain helpers
READ-ONLY; nothing here mutates a production module.

The periodic-comb cross-M approach is dead (target harmonic content is genuinely
unstable; see poc_comb_chain_REPORT.md). This module provides the shared machinery
for estimators that SIDESTEP the unstable target spectrum:

  * register a config once (reg_auto, via atlas_periodic_fft.register),
  * resample the SAME physical atlas patch onto a COMMON subject-space grid for any
    config pair (so the intrinsic target content cancels / is shared),
  * decode warm/saturation channel (the comb-POC SNR win),
  * full focus-stack access (the single-best-frame analyses threw the rest away).

Coordinate system (validated on nufan 2026-06-30):
  reg_auto's `grid_xy_distorted(cl, rl, p)` maps atlas die-grid LINE-PAIR coordinates
  (cl,rl) -> image pixels for a given config's registration `p`. Atlas grid units are
  PHYSICAL (M-invariant), so a fixed (cl,rl) rectangle is the SAME physical wafer
  region in every config. We sample that rectangle on a dense (cl,rl) lattice, map to
  each config's pixels, and cv2.remap -> a common HxW subject-space patch. The patch's
  physical extent (in grid units) is identical across configs; only the lens/sensor MTF
  differs. That is what lets the intrinsic spectrum cancel in a PSD ratio.

Physics constants: f_subj(lp/mm) = f_px(cy/px) * 229.9 * M ; Nyquist 0.5 cy/px.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np

TS = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness")
sys.path.insert(0, str(TS / "src"))
sys.path.insert(0, str(TS / "scripts"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


apf = _load("apf", TS / "scripts" / "atlas_periodic_fft.py")
reg_auto = apf.reg_auto
ccolor = _load("ccolor", TS / "scripts" / "poc_comb_chain_contrast_color.py")

from tile_sharpness import optics  # noqa: E402

M_ANCHOR_SCALE = apf.M_ANCHOR_SCALE
LPMM_PER_CYPX = 1000.0 / 4.35   # 229.9 lp/mm per cy/px at M=1 (Z7 4.35 um pitch)
NYQUIST = 0.5
IMAGE_W, IMAGE_H = apf.IMAGE_W, apf.IMAGE_H


# --------------------------------------------------------------------------- #
# registration + per-config metadata
# --------------------------------------------------------------------------- #

def register_config(sweep_dir):
    """Register a sweep dir once. Returns (p, M, jpgs) or (None, None, jpgs)."""
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


# --------------------------------------------------------------------------- #
# focus-stack access (full stack — not just best frame)
# --------------------------------------------------------------------------- #

def lapvar(a):
    return float(cv2.Laplacian(a.astype(np.float32), cv2.CV_32F).var())


def stack_lapvar_in_box(jpgs, box):
    """Through-focus laplacian-variance curve for an image-pixel box (x0,y0,x1,y1).
    One grayscale decode per frame; returns (seqs, lapvars) arrays."""
    x0, y0, x1, y1 = (int(v) for v in box)
    seqs, lvs = [], []
    for seq, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        roi = g[y0:y1, x0:x1]
        if roi.size == 0 or min(roi.shape) < 16:
            continue
        seqs.append(seq)
        lvs.append(lapvar(roi))
    return np.asarray(seqs, float), np.asarray(lvs, float)


def best_focus_frame(jpgs, box, topk=1):
    """Return list of (seq, jpg) for the topk sharpest frames in a box (by lapvar)."""
    seqs, lvs = stack_lapvar_in_box(jpgs, box)
    if len(seqs) == 0:
        return []
    order = np.argsort(lvs)[::-1][:topk]
    return [(int(seqs[i]), jpgs[int(seqs[i])]) for i in order]


def scan_all_boxes(jpgs, boxes):
    """ONE grayscale decode per frame; return per-box through-focus lapvar curves.
    boxes = list of (x0,y0,x1,y1). Returns dict box_index -> (seqs, lvs) arrays.
    O(frames) full-res decodes regardless of #boxes — the scalable shape."""
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
            lvs[i].append(lapvar(roi))
    return {i: (np.asarray(seqs[i], float), np.asarray(lvs[i], float)) for i in ib}


# --------------------------------------------------------------------------- #
# SAME-PHYSICAL-PATCH resampling to a common subject-space grid
# --------------------------------------------------------------------------- #

def _cum_vec(d4, k):
    """Vectorised cumulative-pitch over the irregular 4-period super-cell (matches
    anchor_fit_sweep._cum elementwise). d4 = 4-vector of grid pitches; k = array of
    fractional line indices. The atlas grid has an irregular pitch repeating every 4
    lines (one wide column / one tall row), so the cumulative distance to line k is
    full super-cells * sum(d4) + partial cells + a fractional step."""
    d4 = np.asarray(d4, float)
    k = np.asarray(k, float)
    out = np.zeros_like(k)
    pos = k > 0
    kp = k[pos]
    k_int = np.floor(kp).astype(int)
    frac = kp - k_int
    full = k_int // 4
    rem = k_int % 4
    csum = np.concatenate([[0.0], np.cumsum(d4)])   # csum[r] = sum(d4[:r])
    c = full * d4.sum() + csum[rem] + frac * d4[rem % 4]
    out[pos] = c
    return out


def atlas_rect_to_common_grid(img, p, cl0, rl0, cl1, rl1, samples_per_unit,
                              interp=cv2.INTER_CUBIC):
    """Resample the SAME physical atlas rectangle [cl0,cl1] x [rl0,rl1] (grid-line-pair
    units) from `img` onto a regular common grid of (samples_per_unit) px per grid unit.

    The output's physical sampling density is FIXED by samples_per_unit (identical for
    every config), so two configs resampled with the same samples_per_unit live on the
    same subject-space grid and can be compared frequency-by-frequency. We map each
    output cell centre (cl,rl) -> image pixel via reg_auto.grid_xy_distorted (the full
    distortion-aware forward model) and cv2.remap with high-quality interpolation.

    Returns float32 HxW patch (or None if it falls outside the frame)."""
    W = int(round((cl1 - cl0) * samples_per_unit))
    H = int(round((rl1 - rl0) * samples_per_unit))
    if W < 16 or H < 16:
        return None
    cls = cl0 + (np.arange(W) + 0.5) / samples_per_unit
    rls = rl0 + (np.arange(H) + 0.5) / samples_per_unit
    CL, RL = np.meshgrid(cls, rls)
    # vectorised forward model (mirror reg_auto._forward; handles distortion if present)
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
    if (mapx.min() < 2 or mapx.max() > IMAGE_W - 2 or
            mapy.min() < 2 or mapy.max() > IMAGE_H - 2):
        return None
    patch = cv2.remap(img.astype(np.float32), mapx, mapy, interp,
                      borderMode=cv2.BORDER_REFLECT)
    return patch


def decode_channel(jp, channel="sat"):
    """Decode one frame to a single float32 channel (default saturation — the comb-POC
    SNR win that suppresses achromatic speculars)."""
    bgr = cv2.imread(str(jp), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return ccolor.channel_stack(bgr)[channel].astype(np.float32)


# --------------------------------------------------------------------------- #
# common-patch frequency analysis
# --------------------------------------------------------------------------- #

def _hann2d(h, w):
    return np.outer(np.hanning(h), np.hanning(w))


def radial_psd(patch, nbins=64):
    """Windowed radial power spectral density of a patch. Returns (freq_cycles_per_px_of
    the COMMON GRID, psd). Frequency is in cycles per output-grid-pixel; multiply by
    samples_per_unit conversions externally if a physical axis is wanted. We keep it in
    common-grid cy/px because the ratio of two patches at the same common grid cancels
    units."""
    a = patch - patch.mean()
    h, w = a.shape
    a = a * _hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a))
    P = (F.real ** 2 + F.imag ** 2)
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    # radial frequency in cycles per pixel of the (square-ish) patch
    fr = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    fr_flat = fr.ravel(); P_flat = P.ravel()
    fmax = 0.5
    bins = np.linspace(0, fmax, nbins + 1)
    idx = np.digitize(fr_flat, bins) - 1
    psd = np.full(nbins, np.nan)
    for b in range(nbins):
        m = idx == b
        if m.any():
            psd[b] = P_flat[m].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, psd


def detail_metrics(patch):
    """Non-spectral detail metrics on a common-grid patch (approach #2). All are
    'more = sharper' ONLY valid for the SAME physical patch at the SAME common grid."""
    a = patch.astype(np.float64)
    a = a - a.mean()
    gx = cv2.Sobel(a, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(a, cv2.CV_64F, 0, 1, ksize=3)
    tenengrad = float(np.mean(gx * gx + gy * gy))
    lap = cv2.Laplacian(a, cv2.CV_64F, ksize=3)
    lap_energy = float(np.mean(lap * lap))
    var = float(np.var(a))
    # high-frequency wavelet energy: simple Haar-ish detail via decimated diff
    d = a[::2, ::2] - cv2.resize(cv2.resize(a, (a.shape[1] // 2, a.shape[0] // 2)),
                                 (a.shape[1], a.shape[0]))[::2, ::2]
    hf = float(np.mean(d * d))
    return dict(tenengrad=tenengrad, lap_energy=lap_energy, variance=var, hf_energy=hf)


def ceiling_subject(n_marked, M, nu_subject_lpmm):
    """Diffraction ceiling MTF at a subject-space frequency (sanity gate)."""
    return optics.diffraction_mtf_subject_at(nu_subject_lpmm, n_marked, M)
