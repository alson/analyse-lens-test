"""Bounded periodic-FFT contrast — a ceiling-valid MTF read at a structure's
fundamental spatial frequency.

Motivation (see ``MTF_TARGET_ACQUISITION.md`` and ``REPORT_taskAD_2026-06-28.md``
§E/§F): slanted-edge / LSF MTF50 *over-reads* the diffraction ceiling on the wafer
because the scribe is a lit-vs-shadow groove, not a clean reflectance step. A
*periodic* target sidesteps this entirely: it measures contrast **at its own
fundamental frequency**, the contrast is bounded in ``[0,1]`` by construction, and it
*under*-reads to 0 past the optical cutoff — so it physically cannot over-read the
diffraction ceiling. ``maze_fft.maze_amp`` already did this for the universal 13 µm
maze; here we generalise it to read a *normalised* (Michelson-style) contrast at an
*atlas-known* structure pitch, so configs compare at a common subject-space frequency.

The output is a Michelson-like contrast:

    C = 2 · |F(f0)| / |F(0)|

where ``F`` is the 2-D FFT of the Hann-windowed (but **not** mean-subtracted) ROI,
``F(0)`` is the DC term (windowed mean × area) and ``|F(f0)|`` is the amplitude at the
fundamental. For an ideal sinusoid ``m + a·cos(2π f0 x)`` this equals ``a/m`` — the
Michelson contrast — and it is bounded in ``[0,1]`` for any non-negative modulation.
Read at the structure fundamental and compared against ``optics.diffraction_mtf_*``
at the same frequency, ``C`` is a ceiling-valid relative MTF.
"""

from __future__ import annotations

import numpy as np

from tile_sharpness.methods.maze_fft import (
    maze_freq_cy_per_px,
    MAZE_PITCH_UM,
    SENSOR_PITCH_UM_Z7,
)

try:  # cv2 only needed for de-rotation; degrade gracefully without it
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

# Subject↔sensor frequency conversion (M=1): f_subj(lp/mm) = f_px(cy/px) · LPMM_PER_CYPX · M.
LPMM_PER_CYPX = 1000.0 / SENSOR_PITCH_UM_Z7   # ≈229.9 lp/mm per cy/px at M=1
NYQUIST = 0.5


def _hann2d(h: int, w: int) -> np.ndarray:
    return np.outer(np.hanning(h), np.hanning(w))


def maze_band_cy_per_px(
    M: float, half_bw_frac: float = 0.10
) -> tuple[float, float, float] | None:
    """The universal 13 µm maze's exclusion band ``(f_maze, lo, hi)`` in cy/px for this
    magnification ``M``, or ``None`` if the maze aliases past Nyquist.

    The maze frequency is M-dependent (``f_px = 4.35/(13·M)`` cy/px: ~0.335 @ M=1 but
    ~0.167 @ M=2), so at high M it slides DOWN into the static discovery band and a
    static exclusion misses it. The exclusion half-width is a fraction of the maze
    frequency so the window tracks the maze as it moves with M."""
    fz = maze_freq_cy_per_px(M)
    if fz <= 0 or fz + half_bw_frac * fz > NYQUIST:
        return None
    hw = half_bw_frac * fz
    return fz, max(0.0, fz - hw), min(NYQUIST, fz + hw)


STATIC_BAND: tuple[float, float] = (0.06, 0.30)


def resolvable_band_cy_per_px(
    M: float,
    pad_f1_subj_lpmm: float = 18.0,
    static_band: tuple[float, float] = STATIC_BAND,
    f1_margin: float = 0.8,
) -> tuple[float, float]:
    """M-aware resolvable discovery band ``(lo, hi)`` in cy/px.

    The static 0.06 cy/px floor is M-naive: the pad fundamental's pixel frequency is
    ``f_px = f_subj/(229.9·M)``, so at high M (e.g. M≈2) an ~18 lp/mm pad fundamental
    drops to ~0.039 cy/px — *below* the static 0.06 floor — and would be clipped. The
    floor is therefore lowered **only when the static floor would actually clip the pad
    fundamental** (``f1_px < static_lo``); until then it stays *exactly* at the static
    0.06, so the whole low-M regime (the pad fundamental sits at ≥0.06 for M ≲ 1.16)
    reproduces the static band unchanged — the regression invariant. Once the static
    floor would clip f1, the floor drops to ``f1_margin·f1_px`` (a small margin below the
    pad fundamental). The ceiling is the static 0.30: the pad comb lives below it at every
    M, and the maze line (when it slides in at high M) is removed by the M-aware
    ``exclude`` band, not by the ceiling."""
    f1_px = pad_f1_subj_lpmm / (LPMM_PER_CYPX * M)
    lo = static_band[0] if f1_px >= static_band[0] else f1_margin * f1_px
    hi = static_band[1]
    lo = min(lo, 0.8 * hi)           # never let the floor exceed the ceiling
    return float(lo), float(hi)


def derotate(roi: np.ndarray, theta_deg: float, trim_frac: float = 0.08) -> np.ndarray:
    """Rotate ``roi`` by ``-theta_deg`` so the wafer's u/v axes become image-aligned,
    then trim the rotation seam. Requires cv2; returns the ROI unchanged if cv2 is
    missing or theta is ~0."""
    if cv2 is None or abs(theta_deg) < 1e-3:
        return roi
    h, w = roi.shape
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), theta_deg, 1.0)
    der = cv2.warpAffine(roi.astype(np.float32), M, (w, h),
                         flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    t = max(2, int(trim_frac * min(h, w)))
    der = der[t:h - t, t:w - t]
    return der


def discover_fundamental(
    roi: np.ndarray,
    *,
    axis: str = "auto",
    band: tuple[float, float] = (0.06, 0.30),
    exclude: tuple[float, float] | None = (0.31, 0.36),
    M: float | None = None,
) -> dict | None:
    """Find the dominant periodic fundamental of ``roi`` inside a discriminating
    frequency ``band`` (cy/px), avoiding DC bleed and (optionally) the universal
    13 µm maze line near 0.33 cy/px (``exclude``).

    The atlas super-element pitch (~100-230 px) sits far below the optical cutoff and
    carries no MTF information; the *measurable* fundamental is the structure's
    sub-element periodicity (the caveat's "FFT may lock onto sub-element periodicity"
    — which for MTF is exactly the high-frequency target we want). Returns a dict with
    ``pitch_px``, ``f0_cy_per_px``, ``axis`` and the peak amplitude, or ``None``.

    ``M`` (optional magnification): when ``None`` (the default) the static ``band`` and
    ``exclude`` are used exactly as passed — fully backward-compatible. When ``M`` is
    given, the band and maze exclusion become M-aware (``resolvable_band_cy_per_px`` and
    ``maze_band_cy_per_px``), which is what keeps the discovery off the maze at high M
    where the maze frequency slides DOWN into the static band. By construction the
    M-aware band/exclusion reproduce the static (0.06,0.30)/(0.31,0.36) picks across the
    whole low-M regime (the floor only drops once the static 0.06 would clip the pad
    fundamental, ~M≳1.2, and the maze near 0.32 cy/px stays excluded), so low-M reads do
    not change — the only intended behaviour change is at high M. An explicitly passed
    ``band``/``exclude`` still wins over the M-derived defaults if a caller overrides
    them (i.e. M only supplies the defaults)."""
    if roi.ndim != 2 or roi.size == 0:
        return None
    if M is not None:
        # M-aware defaults; an explicit override of band/exclude (non-default) wins.
        if band == (0.06, 0.30):
            band = resolvable_band_cy_per_px(M)
        if exclude == (0.31, 0.36):
            mb = maze_band_cy_per_px(M)
            exclude = (mb[1], mb[2]) if mb is not None else None
    if band[0] >= band[1]:
        return None
    axes = ("u", "v") if axis == "auto" else (axis,)
    best = None
    for ax in axes:
        prof = roi.mean(axis=0) if ax == "u" else roi.mean(axis=1)
        n = prof.size
        if n < 32:
            continue
        prof = prof - prof.mean()
        amp = np.abs(np.fft.rfft(prof * np.hanning(n)))
        freqs = np.fft.rfftfreq(n, d=1.0)
        m = (freqs >= band[0]) & (freqs <= band[1])
        if exclude is not None:
            m &= ~((freqs >= exclude[0]) & (freqs <= exclude[1]))
        idx = np.where(m)[0]
        if idx.size == 0:
            continue
        k = idx[int(np.argmax(amp[idx]))]
        # require a real peak: above the in-band median and a tiny absolute floor,
        # else there is no periodicity (flat / pure-noise field).
        in_band_med = float(np.median(amp[idx]))
        if amp[k] <= max(1e-9, 2.0 * in_band_med):
            continue
        rec = dict(pitch_px=float(1.0 / freqs[k]), f0_cy_per_px=float(freqs[k]),
                   axis=ax, amp=float(amp[k]))
        if best is None or rec["amp"] > best["amp"]:
            best = rec
    return best


def periodic_contrast(
    roi: np.ndarray,
    pitch_px: float,
    *,
    axis: str = "auto",
    half_bw_frac: float = 0.25,
    min_periods: float = 3.0,
) -> dict | None:
    """Bounded Michelson-style periodic contrast at the fundamental ``f0 = 1/pitch_px``.

    ``axis`` selects which 1-D profile to FFT:
      * ``"u"``  — average rows, FFT along columns (horizontal periodicity / vertical
        stripes); pitch_px is the column (u) pitch.
      * ``"v"``  — average columns, FFT along rows (vertical periodicity); pitch_px is
        the row (v) pitch.
      * ``"auto"`` — try both and return the higher-contrast one (the ROI may only
        carry one clean axis).

    The 1-D collapse (averaging the orthogonal axis) is the matched filter for a
    1-D grating and rejects the orthogonal-axis structure + noise; this is what makes
    the contrast clean enough to compare across configs. Returns ``None`` if the pitch
    aliases (``f0`` ≥ Nyquist), the ROI holds < ``min_periods`` periods, or the ROI is
    degenerate. Otherwise a dict with ``contrast`` (in [0,1]), ``f0_cy_per_px``,
    ``axis`` chosen, ``n_periods``, and ``snr`` (fundamental / local sideband median).
    """
    if roi.ndim != 2 or roi.size == 0:
        return None
    if pitch_px is None or pitch_px < 2.5:
        return None
    f0 = 1.0 / pitch_px
    if f0 >= 0.5 - 1e-6:            # aliases at/above Nyquist
        return None

    axes = ("u", "v") if axis == "auto" else (axis,)
    best = None
    for ax in axes:
        prof = roi.mean(axis=0) if ax == "u" else roi.mean(axis=1)
        n = prof.size
        if n < 8 or n * f0 < min_periods:
            continue
        win = np.hanning(n)
        wmean = float((prof * win).sum())
        if wmean <= 0:
            continue
        spec = np.fft.rfft((prof - 0.0) * win)   # keep DC: F(0) = sum(prof*win)
        amp = np.abs(spec)
        freqs = np.fft.rfftfreq(n, d=1.0)
        dc = amp[0]
        if dc <= 0:
            continue
        # locate the fundamental bin, allow +-half_bw_frac*f0 search to absorb
        # small pitch/scale error; take the local max as the fundamental amplitude.
        bw = max(1, int(round(half_bw_frac * f0 * n)))
        idx0 = int(np.argmin(np.abs(freqs - f0)))
        lo, hi = max(1, idx0 - bw), min(len(amp), idx0 + bw + 1)
        if hi <= lo:
            continue
        kpk = lo + int(np.argmax(amp[lo:hi]))
        fund = amp[kpk]
        # local sideband median for SNR (exclude the fundamental neighbourhood)
        side_lo, side_hi = max(1, kpk - 4 * bw), min(len(amp), kpk + 4 * bw + 1)
        side = np.concatenate([amp[side_lo:max(side_lo, kpk - bw)],
                               amp[min(side_hi, kpk + bw + 1):side_hi]])
        side_med = float(np.median(side)) if side.size else 0.0
        contrast = float(min(1.0, 2.0 * fund / dc))
        snr = float(fund / side_med) if side_med > 0 else float("inf")
        rec = dict(contrast=contrast, f0_cy_per_px=float(freqs[kpk]),
                   axis=ax, n_periods=float(n * f0), snr=snr,
                   pitch_px=float(pitch_px))
        if best is None or rec["contrast"] > best["contrast"]:
            best = rec
    return best
