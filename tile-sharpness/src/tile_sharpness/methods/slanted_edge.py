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


# ---------------------------------------------------------------------------
# SINGLE-STEP edges (bond-pad metal→substrate reflectance edges).
#
# A groove scribe is a TROUGH (two walls — ``_split_walls``). A bond-pad edge is
# a single monotone STEP, so the whole super-resolved ESF is one erf: no split,
# fit it directly. This is the right tool for the true-reflectance-edge metric
# (REPORT_taskAD §E.4) — a designed groove is a lit/shadow emboss that
# specular-over-reads; a single metal→substrate step has no second wall to glint.
# ---------------------------------------------------------------------------


def _trim_to_dominant_step(centres: np.ndarray, esf: np.ndarray):
    """Crop the ESF window to the SINGLE dominant step. The super-res window can
    overrun a small pad onto a neighbouring pad/edge (→ a second step that would
    bias the erf fit). We locate the largest-|gradient| transition, then walk out
    from it until the profile reverses curvature (a second edge) or the window
    ends, keeping a symmetric-ish span around the step centre."""
    n = esf.size
    if n < 8:
        return centres, esf
    g = np.gradient(np.asarray(esf, float))
    pk = int(np.argmax(np.abs(g)))
    s = float(np.sign(g[pk])) or 1.0
    sg = s * g                          # step's rise is positive in sg
    # Walk out from the peak until the gradient falls into the flat band (the
    # step has ended). Stop there — do NOT walk through a flat gap into a second
    # step (a neighbouring pad edge), which would bias the erf fit.
    thr = 0.15 * abs(g[pk])
    lo = pk
    while lo > 0 and sg[lo - 1] > thr:
        lo -= 1
    hi = pk
    while hi < n - 1 and sg[hi + 1] > thr:
        hi += 1
    # keep a background shoulder on each side for the erf asymptotes
    pad = 4
    lo = max(0, lo - pad); hi = min(n - 1, hi + pad)
    if hi - lo < 6:
        return centres, esf
    return centres[lo:hi + 1], esf[lo:hi + 1]


_SIGMA_FLOOR = 0.30   # _fit_wall lower bound; a fit here means an UNRESOLVED step


def _step_quality_ok(centres: np.ndarray, esf: np.ndarray, *, min_contrast: float = 12.0,
                     max_overshoot_frac: float = 0.25) -> bool:
    """Gate a candidate ESF (the FULL super-res window, BEFORE trimming) as a
    GENUINE single reflectance step.

    Rejects the artefacts the pad-array selector produces (REPORT_taskAD pad-edge
    validation): a thin bright RIDGE (rise-then-fall), a TROUGH, or a noise-only
    profile. Must be called on the full window — after ``_trim_to_dominant_step``
    a ridge already looks monotone, so the rise-then-fall is only visible here.
    Requirements:
      * real contrast end-to-end (``|esf[-1]-esf[0]| >= min_contrast`` DN),
      * the interior must not excurse far BEYOND either endpoint (a ridge peaks
        above both ends, a trough dips below both) — i.e. monotone-ish, not a bump."""
    if esf.size < 8:
        return False
    a, b = float(esf[0]), float(esf[-1])
    step = abs(b - a)
    if step < min_contrast:
        return False
    hi_end, lo_end = max(a, b), min(a, b)
    over = max(0.0, float(esf.max()) - hi_end)      # excursion above the top plateau
    under = max(0.0, lo_end - float(esf.min()))     # excursion below the bottom plateau
    # A clean step's interior stays between its plateaus (allow a little noise/ringing).
    if (over + under) > max_overshoot_frac * step:
        return False
    return True


def mtf50_step_erf(image_2d: np.ndarray, seg: Segment, *, half_window_px: float = 30.0,
                   bins_per_px: float = 4.0, quality_gate: bool = True) -> float | None:
    """PRIMARY single-step readout: erf-fit MTF50 (cy/px) on a monotone bond-pad
    edge. Unlike ``mtf50_erf`` (groove → two walls) there is ONE edge, so the
    super-resolved ESF is cropped to its dominant step and fit with a single erf.
    A shape fit cannot float up off the noise floor, and there is no second
    (shadow/lit) wall to introduce specular asymmetry.

    ``quality_gate`` (default on) rejects candidates that are NOT a genuine single
    step — a bright-trace ridge, a trough, a low-contrast/noise profile, or a fit
    railing at the sigma floor (an unresolved/aliased pixel edge). Such candidates
    return ``None`` rather than a spurious over-read; the pad-array structure on
    this wafer produces many of them, so this gate is load-bearing for the metric's
    validity (see REPORT pad-edge validation)."""
    out = superres_esf(image_2d, seg, half_window_px=half_window_px, bins_per_px=bins_per_px)
    if out is None:
        return None
    if quality_gate and not _step_quality_ok(*out):   # gate on the FULL window
        return None
    c, e = _trim_to_dominant_step(*out)
    m = _fit_wall(c, e)
    if m is None:
        return None
    if quality_gate:
        sigma = _MTF50_PER_INV_SIGMA / m
        if sigma <= _SIGMA_FLOOR * 1.05:    # railed at the floor -> unresolved, reject
            return None
    return m


def mtf50_step_iso(image_2d: np.ndarray, seg: Segment, *, half_window_px: float = 30.0,
                   bins_per_px: float = 4.0) -> float | None:
    """Model-free single-step cross-check: ISO-12233 windowed-derivative MTF50 on
    the monotone ESF (no wall split). Uses the FULL super-res window — ISO-12233
    wants generous flat shoulders for an unbiased DC term, so it is NOT trimmed to
    the step core (unlike the erf path, where a parametric fit prefers a clean
    single step). The Hamming window centred on the LSF peak suppresses any distant
    second-step energy."""
    out = superres_esf(image_2d, seg, half_window_px=half_window_px, bins_per_px=bins_per_px)
    if out is None:
        return None
    return _iso_wall(out[1], bins_per_px)


def _is_trough(esf: np.ndarray) -> bool:
    """True if the ESF looks like a groove (a TROUGH: dips below both ends) rather
    than a single step. Decision: the interior minimum sits clearly below both
    endpoints by more than a fraction of the end-to-end change."""
    if esf.size < 8:
        return False
    a, b = float(esf[0]), float(esf[-1])
    mn = float(esf.min())
    end = max(a, b)
    span = float(esf.max() - esf.min())
    if span <= 0:
        return False
    # trough: the dip below the higher endpoint is large vs the |endpoint step|.
    dip = end - mn
    step = abs(b - a)
    return dip > step + 0.25 * span


def mtf50_auto(image_2d: np.ndarray, seg: Segment, *, half_window_px: float = 30.0,
               bins_per_px: float = 4.0, combine: str = "min") -> float | None:
    """Auto entry point: measure MTF50 (cy/px) whether the feature under ``seg`` is
    a single STEP (bond-pad / reflectance edge → single-erf path) or a groove
    TROUGH (two walls → ``mtf50_erf`` with ``combine``). Detected from the ESF
    shape so a caller need not know the feature type in advance."""
    out = superres_esf(image_2d, seg, half_window_px=half_window_px, bins_per_px=bins_per_px)
    if out is None:
        return None
    if _is_trough(out[1]):
        walls = _split_walls(*out)
        if walls is None:
            return None
        vals = [m for m in (_fit_wall(c, e) for c, e in walls) if m is not None]
        if not vals:
            return None
        return {"min": min, "max": max, "mean": lambda xs: float(np.mean(xs))}[combine](vals)
    c, e = _trim_to_dominant_step(*out)
    return _fit_wall(c, e)


# ---------------------------------------------------------------------------
# RE-CENTRED single-step ESF for LONG isolated edges.
#
# ``superres_esf`` bins pixels by perpendicular distance to ONE fixed straight
# line (the ``Segment``). That is correct only if the real edge IS that straight
# line. On the wafer's long designed bar the per-row edge position scatters ~±4 px
# around the best-fit line (jagged detection + a slight bow); binning to the fixed
# line then convolves the true ESF with that ±4 px scatter, so the longer the edge
# the WIDER the ESF and the LOWER the MTF50 — a pure straight-line-model artefact
# (REPORT longedge §G). Re-centring each row on its own sub-pixel edge position
# (robust low-order polynomial across rows) removes the scatter: σ then stays flat
# vs edge length. This is the standard ISO-12233 centroid step done properly for a
# long edge.
# ---------------------------------------------------------------------------


def _subpix_grad_peak(mag: np.ndarray, k: int) -> float:
    if k <= 0 or k >= len(mag) - 1:
        return 0.0
    denom = mag[k - 1] - 2 * mag[k] + mag[k + 1]
    return 0.5 * (mag[k - 1] - mag[k + 1]) / denom if denom != 0 else 0.0


def superres_esf_recentred(image_2d: np.ndarray, seg: Segment, *,
                           half_window_px: float = 16.0, bins_per_px: float = 4.0,
                           poly_deg: int = 2, robust_iter: int = 2, min_count: int = 3
                           ) -> tuple[np.ndarray, np.ndarray] | None:
    """Super-resolved single-step ESF that re-centres every along-edge sample on the
    local sub-pixel edge position (robust polynomial of degree ``poly_deg`` across
    the edge), instead of a single straight line. Removes the per-row position
    scatter that otherwise widens the ESF on long, slightly-non-straight edges.

    ``seg`` only needs to be APPROXIMATELY on the edge (atlas/Hough accuracy); the
    refinement re-finds the edge. Returns ``(d_centres, esf)`` in signed
    perpendicular distance to the fitted edge curve, or ``None``.
    """
    L = seg.length_px
    if L < 8:
        return None
    ux, uy = (seg.x1 - seg.x0) / L, (seg.y1 - seg.y0) / L     # along-edge
    px, py = -uy, ux                                          # perpendicular
    H, W = image_2d.shape
    m = half_window_px + 3
    xs_b = [seg.x0, seg.x1]; ys_b = [seg.y0, seg.y1]
    bx0 = max(0, int(min(xs_b) - m)); bx1 = min(W, int(max(xs_b) + m) + 1)
    by0 = max(0, int(min(ys_b) - m)); by1 = min(H, int(max(ys_b) + m) + 1)
    if bx1 - bx0 < 4 or by1 - by0 < 4:
        return None
    yy, xx = np.mgrid[by0:by1, bx0:bx1]
    rx = xx - seg.x0; ry = yy - seg.y0
    t = rx * ux + ry * uy                  # along-edge coord
    d0 = rx * px + ry * py                 # signed perpendicular to the SEED line
    vals = image_2d[by0:by1, bx0:bx1].astype(np.float64)
    inwin = (t >= 0) & (t <= L) & (np.abs(d0) <= half_window_px)
    if inwin.sum() < 50:
        return None
    # Per along-edge ROW (integer t), find the sub-pixel edge offset along d via the
    # steepest |gradient| of the d-profile. Determine step sign from the global ends.
    t_int = np.round(t).astype(int)
    offs_t, offs_off = [], []
    for tv in range(0, int(np.floor(L)) + 1):
        sel = inwin & (t_int == tv)
        if sel.sum() < 6:
            continue
        dvals = d0[sel]; vv = vals[sel]
        order = np.argsort(dvals)
        dv = dvals[order]; vp = vv[order]
        g = np.gradient(vp)
        ag = np.abs(g)
        k = int(np.argmax(ag))
        if 1 <= k <= len(vp) - 2:
            off = _subpix_grad_peak(ag, k)
            offs_t.append(tv)
            offs_off.append(dv[k] + (off * (dv[k + 1] - dv[k]) if k + 1 < len(dv) else 0.0))
    if len(offs_t) < 10:
        return None
    tt = np.asarray(offs_t, float); oo = np.asarray(offs_off, float)
    deg = min(poly_deg, 3)
    A = np.polyfit(tt, oo, deg)
    for _ in range(robust_iter):
        r = oo - np.polyval(A, tt)
        keep = np.abs(r) < 2.0 * (np.std(r) + 1e-6)
        if keep.sum() < 10:
            break
        A = np.polyfit(tt[keep], oo[keep], deg)
    # re-centred perpendicular distance: d0 minus the edge curve at each sample's t
    d = d0[inwin] - np.polyval(A, t[inwin])
    v = vals[inwin]
    keep = np.abs(d) <= half_window_px
    d = d[keep]; v = v[keep]
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


def mtf50_long_edge(image_2d: np.ndarray, seg: Segment, *, half_window_px: float = 16.0,
                    bins_per_px: float = 4.0, poly_deg: int = 2,
                    min_contrast: float = 12.0) -> float | None:
    """PRIMARY long-isolated-edge readout: erf-fit MTF50 (cy/px) on a re-centred
    super-resolved single-step ESF (``superres_esf_recentred``). For a long,
    slightly-non-straight reflectance edge (the wafer's designed bar) this is the
    correct estimator — a fixed-line ESF artefactually softens with length.

    Returns ``None`` on low contrast or a failed/railed fit (the same conservative
    gates as ``mtf50_step_erf``)."""
    out = superres_esf_recentred(image_2d, seg, half_window_px=half_window_px,
                                 bins_per_px=bins_per_px, poly_deg=poly_deg)
    if out is None:
        return None
    c, e = out
    if abs(float(e[-1]) - float(e[0])) < min_contrast and float(e.max() - e.min()) < min_contrast:
        return None
    m = _fit_wall(c, e)
    if m is None:
        return None
    sigma = _MTF50_PER_INV_SIGMA / m
    if sigma <= _SIGMA_FLOOR * 1.05:
        return None
    return m
