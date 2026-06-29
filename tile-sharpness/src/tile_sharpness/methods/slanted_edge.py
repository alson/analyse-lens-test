"""Super-resolved slanted-edge MTF50 (ISO-12233 style), atlas-geometry-fed.

The 2026-06-28 diagnosis (REPORT_taskAD §E) showed the trough-split FFT-threshold
``lsf_mtf50`` over-reads the diffraction ceiling on sharp / asymmetric scribe walls:
one wall can read exactly at the ceiling while the other reads ~1.6× high. Causes:
(1) the edge-normal is sampled at INTEGER pixels (1 sample/px) — no slanted-edge
super-resolution; (2) a short window truncates the PSF skirts (→ LSF looks too
narrow); (3) a first-0.5-crossing on a noisy spectrum has no shape constraint.

This module fixes all three by doing proper ISO-12233 on a SINGLE groove wall, using
the EXACT scribe line (from atlas registration — not LSD/Hough endpoints, which
biased the earlier sub-pixel POC):

  * ``superres_esf``  — bin every pixel in a wide window by its signed perpendicular
    distance to the line; the slant gives dense sub-pixel coverage → an oversampled
    ESF with real bandwidth and no aliasing.
  * ``mtf50_erf``     — PRIMARY readout: fit an error-function edge and derive
    MTF50 = 0.18739/σ (Gaussian-equivalent LSF). A shape fit cannot float up off the
    noise floor, and it is symmetric across walls by construction.
  * ``mtf50_iso``     — model-free cross-check: Hamming-windowed derivative → FFT,
    DC-normalised, first 0.5 crossing on the (smooth, oversampled) MTF.

All MTF50 values are sensor cycles-per-pixel. The diffraction ceiling
(``optics.diffraction_mtf50_sensor_lpmm/229.9``) is the physical truth gate.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit
from scipy.special import erf

from .lsf import Segment

_MTF50_PER_INV_SIGMA = float(np.sqrt(np.log(2.0) / 2.0) / np.pi)  # 0.18739 cy/px·σ


def superres_esf(image_2d: np.ndarray, seg: Segment, *, half_window_px: float = 40.0,
                 bins_per_px: float = 4.0, min_count: int = 3
                 ) -> tuple[np.ndarray, np.ndarray] | None:
    """Super-resolved edge-spread profile across the scribe.

    Returns ``(d_centres, esf)`` sampled every ``1/bins_per_px`` px in signed
    perpendicular distance ``d`` (px) over ``[-half_window, +half_window]``; ``d=0``
    is the atlas line (groove centre). ``None`` if too few pixels.
    """
    L = seg.length_px
    if L < 8:
        return None
    ux, uy = (seg.x1 - seg.x0) / L, (seg.y1 - seg.y0) / L   # along
    px, py = -uy, ux                                        # perpendicular
    H, W = image_2d.shape
    # bounding box of the segment grown by the window
    xs = [seg.x0, seg.x1]; ys = [seg.y0, seg.y1]
    m = half_window_px + 2
    x0 = max(0, int(min(xs) - m)); x1 = min(W, int(max(xs) + m) + 1)
    y0 = max(0, int(min(ys) - m)); y1 = min(H, int(max(ys) + m) + 1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    yy, xx = np.mgrid[y0:y1, x0:x1]
    rx = xx - seg.x0; ry = yy - seg.y0
    t = rx * ux + ry * uy                  # along-coord
    d = rx * px + ry * py                  # signed perpendicular distance
    vals = image_2d[y0:y1, x0:x1].astype(np.float64)
    keep = (t >= 0) & (t <= L) & (np.abs(d) <= half_window_px)
    if keep.sum() < 50:
        return None
    d = d[keep]; v = vals[keep]
    nb = int(round(2 * half_window_px * bins_per_px))
    edges = np.linspace(-half_window_px, half_window_px, nb + 1)
    idx = np.clip(np.digitize(d, edges) - 1, 0, nb - 1)
    sums = np.bincount(idx, weights=v, minlength=nb)
    cnts = np.bincount(idx, minlength=nb)
    good = cnts >= min_count
    if good.sum() < 8:
        return None
    centres = 0.5 * (edges[:-1] + edges[1:])
    return centres[good], sums[good] / cnts[good]


def _erf_edge(d, a, b, d0, sigma):
    return b + a * erf((d - d0) / (sigma * np.sqrt(2.0)))


def _fit_wall(d: np.ndarray, esf: np.ndarray) -> float | None:
    """Fit an erf edge to one wall ESF; return MTF50 (cy/px) or None."""
    if d.size < 6:
        return None
    span = float(esf.max() - esf.min())
    if span <= 0:
        return None
    # falling or rising determined by sign of (end - start)
    a0 = (esf[-1] - esf[0]) / 2.0
    b0 = float(np.mean(esf))
    d0_0 = float(d[int(np.argmax(np.abs(np.gradient(esf))))])
    try:
        popt, _ = curve_fit(_erf_edge, d, esf, p0=[a0, b0, d0_0, 1.5],
                            bounds=([-3 * span, esf.min() - span, d.min(), 0.30],
                                    [3 * span, esf.max() + span, d.max(), 30.0]),
                            maxfev=10000)
    except Exception:
        return None
    sigma = abs(popt[3])
    if not np.isfinite(sigma) or sigma <= 0:
        return None
    return _MTF50_PER_INV_SIGMA / sigma


def _split_walls(centres: np.ndarray, esf: np.ndarray):
    """Split the super-resolved trough at its minimum into two background→bottom
    wall ESFs (left reads left→centre; right reversed so both read background→dark)."""
    c = int(np.argmin(esf))
    if c < 3 or c > esf.size - 4:
        return None
    left = (centres[:c + 1], esf[:c + 1])
    right = (centres[c:][::-1], esf[c:][::-1])
    return left, right


def mtf50_erf(image_2d: np.ndarray, seg: Segment, *, half_window_px: float = 40.0,
              bins_per_px: float = 4.0, combine: str = "min") -> float | None:
    """PRIMARY: erf-fit MTF50 (cy/px) from the super-resolved scribe, per wall.

    ``combine`` = 'min' | 'mean' | 'max' over the two walls (default 'min',
    the conservative/cleaner wall, consistent with the lsf_mtf50 mitigation)."""
    out = superres_esf(image_2d, seg, half_window_px=half_window_px, bins_per_px=bins_per_px)
    if out is None:
        return None
    walls = _split_walls(*out)
    if walls is None:
        return None
    vals = [m for m in (_fit_wall(c, e) for c, e in walls) if m is not None]
    if not vals:
        return None
    return {"min": min, "max": max, "mean": lambda xs: float(np.mean(xs))}[combine](vals)


def mtf50_iso(image_2d: np.ndarray, seg: Segment, *, half_window_px: float = 40.0,
              bins_per_px: float = 4.0, combine: str = "min") -> float | None:
    """Model-free cross-check: Hamming-windowed derivative → DC-normalised MTF →
    first 0.5 crossing, on the super-resolved ESF (per wall)."""
    out = superres_esf(image_2d, seg, half_window_px=half_window_px, bins_per_px=bins_per_px)
    if out is None:
        return None
    walls = _split_walls(*out)
    if walls is None:
        return None
    vals = []
    for c, e in walls:
        m = _iso_wall(e, bins_per_px)
        if m is not None:
            vals.append(m)
    if not vals:
        return None
    return {"min": min, "max": max, "mean": lambda xs: float(np.mean(xs))}[combine](vals)


def _iso_wall(esf: np.ndarray, bins_per_px: float) -> float | None:
    if esf.size < 8:
        return None
    lsf = np.gradient(esf.astype(np.float64))
    peak = int(np.argmax(np.abs(lsf)))
    n = lsf.size
    idx = np.arange(n)
    win = 0.54 - 0.46 * np.cos(np.pi * (1 - np.abs(idx - peak) / max(peak, n - 1 - peak, 1)))
    lsf_w = lsf * win
    pad = max(256, 1 << int(np.ceil(np.log2(n)) + 2))
    buf = np.zeros(pad); off = (pad - n) // 2; buf[off:off + n] = lsf_w
    mag = np.abs(np.fft.rfft(buf))
    # freq axis in cy/px: bin spacing is 1/bins_per_px px
    freqs = np.fft.rfftfreq(pad, d=1.0 / bins_per_px)
    if mag[0] <= 0:
        return None
    norm = mag / mag[0]
    for k in range(1, norm.size):
        if norm[k] <= 0.5:
            f0, f1 = freqs[k - 1], freqs[k]; m0, m1 = norm[k - 1], norm[k]
            return float(f0 + (f1 - f0) * ((m0 - 0.5) / (m0 - m1))) if m0 != m1 else float(f1)
    return None
