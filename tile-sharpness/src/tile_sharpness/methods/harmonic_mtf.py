"""Route 1 — harmonic-decay MTF on a flat periodic grating.

On a FLAT periodic reflectance grating the captured signal is
``s(x) = (lens MTF) * (target)``. In Fourier space the target's line at harmonic
``n`` carries amplitude ``T_n``; the captured amplitude is ``A_n = MTF(n·f0)·T_n``
(ignoring noise). The ratio ``A_n / A_1`` therefore equals
``MTF(n·f0)/MTF(f0) · (T_n/T_1)`` — and ``T_n/T_1`` is the target's *intrinsic*
harmonic content, a fixed property of the grating's duty cycle. Dividing it out
gives a SELF-NORMALISED MTF shape ``MTF(n·f0)/MTF(f0)`` at known subject
frequencies, with NO external absolute anchor — the target modulation cancels.

For an ideal square-wave grating of duty cycle ``D`` the Fourier amplitudes are
``T_n ∝ |sinc(n·D)|`` (``sinc(x)=sin(pi x)/(pi x)``); for D=0.5 the even harmonics
vanish and the odd ratios are 1 : 1/3 : 1/5 : … We estimate ``D`` from the
captured profile (it is robust: the lens preserves the mean/area ratio of a
high-contrast grating well enough for a duty-cycle estimate) so we don't have to
assume a perfect square wave.

This is the SHARPNESS_METRICS.md §3 "harmonic analysis of the bump grid" method,
realised on the 2B serpent/horizontal-line grating (flat → no emboss over-read).
The output ``mtf_ratio[n]`` is bounded by construction (a real MTF is monotone
non-increasing, so each ratio should be <= 1) and each point must also sit <= the
diffraction MTF at ``n·f0`` — the two physical gates.
"""
from __future__ import annotations

import numpy as np


def _sinc(x):
    return np.sinc(x)   # numpy sinc = sin(pi x)/(pi x)


def estimate_duty_cycle(prof: np.ndarray) -> float:
    """Estimate the grating duty cycle (bright fraction) from a 1-D profile by
    thresholding at the mid-level between robust dark/bright plateaus."""
    p = np.asarray(prof, float)
    dark = np.percentile(p, 15)
    bright = np.percentile(p, 85)
    if bright <= dark:
        return 0.5
    mid = 0.5 * (dark + bright)
    return float(np.clip(np.mean(p > mid), 0.05, 0.95))


def harmonic_amplitudes(prof: np.ndarray, f0_cy_per_px: float,
                        n_harmonics: int = 5, half_bw_frac: float = 0.30
                        ) -> dict | None:
    """FFT a 1-D profile (already collapsed across the grating lines), return the
    amplitude at the fundamental ``f0`` and harmonics ``2f0..n_harmonics·f0``.

    Returns a dict with ``amps`` (list, index 0 = fundamental), ``freqs`` (the
    actual bin frequencies used), ``noise`` (local sideband median per harmonic for
    SNR), and ``dc``. ``None`` if the profile is too short or f0 aliases.
    """
    p = np.asarray(prof, float)
    n = p.size
    if n < 16 or f0_cy_per_px <= 0 or f0_cy_per_px >= 0.5:
        return None
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft((p - p.mean()) * win))
    freqs = np.fft.rfftfreq(n, 1.0)
    dcspec = np.abs(np.fft.rfft(p * win))[0]
    amps, fused, noise = [], [], []
    for k in range(1, n_harmonics + 1):
        fk = k * f0_cy_per_px
        if fk >= 0.5:
            break
        bw = max(1, int(round(half_bw_frac * f0_cy_per_px * n)))
        idx0 = int(np.argmin(np.abs(freqs - fk)))
        lo, hi = max(1, idx0 - bw), min(len(spec), idx0 + bw + 1)
        if hi <= lo:
            break
        kpk = lo + int(np.argmax(spec[lo:hi]))
        amps.append(float(spec[kpk]))
        fused.append(float(freqs[kpk]))
        # sideband noise for SNR (exclude the peak neighbourhood)
        slo, shi = max(1, kpk - 4 * bw), min(len(spec), kpk + 4 * bw + 1)
        side = np.concatenate([spec[slo:max(slo, kpk - bw)], spec[min(shi, kpk + bw + 1):shi]])
        noise.append(float(np.median(side)) if side.size else 0.0)
    if len(amps) < 2:
        return None
    return dict(amps=amps, freqs=fused, noise=noise, dc=float(dcspec),
                duty=estimate_duty_cycle(p))


def harmonic_mtf(prof: np.ndarray, f0_cy_per_px: float, *, n_harmonics: int = 5,
                 snr_min: float = 3.0) -> dict | None:
    """Self-normalised MTF shape ``MTF(n·f0)/MTF(f0)`` from a flat-grating profile.

    Corrects the captured harmonic ratios by the target's intrinsic ``|sinc(nD)|``
    content (duty cycle ``D`` estimated from the profile). Returns a dict:
      * ``f_cy_per_px`` — frequencies ``[f0, 2f0, ...]`` actually measured (sensor),
      * ``mtf_ratio``   — ``MTF(n·f0)/MTF(f0)`` (index 0 == 1.0 by definition),
      * ``snr``         — amplitude SNR per harmonic (gate: >= snr_min to trust),
      * ``duty``        — estimated duty cycle,
      * ``raw_ratio``   — uncorrected ``A_n/A_1`` (for diagnostics).
    Harmonics whose intrinsic content is near a sinc null (|sinc(nD)| ~ 0) are
    dropped (the correction would blow up). ``None`` if < 2 usable harmonics.
    """
    h = harmonic_amplitudes(prof, f0_cy_per_px, n_harmonics=n_harmonics)
    if h is None:
        return None
    amps = np.array(h["amps"]); noise = np.array(h["noise"]); D = h["duty"]
    a1 = amps[0]
    if a1 <= 0:
        return None
    raw = amps / a1
    snr = np.array([a / no if no > 0 else np.inf for a, no in zip(amps, noise)])
    f_used = np.array(h["freqs"])
    # intrinsic target harmonic content for the estimated duty cycle
    ns = np.arange(1, len(amps) + 1)
    intrinsic = np.abs(_sinc(ns * D))
    out_f, out_ratio, out_snr = [], [], []
    i1 = intrinsic[0]
    for j in range(len(amps)):
        if intrinsic[j] < 0.08 * (i1 if i1 > 0 else 1.0):   # near a sinc null -> skip
            continue
        corr = (intrinsic[0] / intrinsic[j])
        out_f.append(float(f_used[j]))
        out_ratio.append(float(raw[j] * corr))
        out_snr.append(float(snr[j]))
    if len(out_ratio) < 2:
        return None
    return dict(f_cy_per_px=out_f, mtf_ratio=out_ratio, snr=out_snr,
                duty=float(D), raw_ratio=[float(x) for x in raw],
                f0=float(f_used[0]))
