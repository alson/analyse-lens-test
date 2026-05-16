"""Fine-maze 2D-FFT amplitude — high-resolution discriminator at M ≥ ~0.7×.

Per the 2026-05-16 methodology update in ``SHARPNESS_METRICS.md``: the
wafer carries a fine maze/grid structure (physical pitch ~13 µm,
~3 px on Z7 at 1:1) that's universal across every die except inside
the scribes themselves. We 2D-FFT the ROI, sum |FFT| amplitude in an
annulus around the maze fundamental frequency, and read off the
result as "how much high-frequency maze contrast survives the optical
chain". Two orders of magnitude more sensitive to real lens-quality
differences than bulk-energy proxies (5.5× cross-copy ratio at the
maze fundamental vs ~2 % CV in filesize across same-model copies).

The annulus centre is M-dependent: maze period in pixels scales
linearly with M (more magnification → more sensor pixels per maze
period → lower spatial frequency). Below ~0.7× the period aliases
(sub-Nyquist on the sensor) and ``maze_amp`` returns ``None``,
signalling the caller to fall back to scribe-LSF only.
"""

from __future__ import annotations

import numpy as np


# Z7 sensor pitch and wafer maze pitch (back-solved from one AIS 55mm
# 1:1 tile; period 3 px × 4.35 µm). Validate against one frame per
# dataset family if a new wafer shows different pitch.
SENSOR_PITCH_UM_Z7 = 4.35
MAZE_PITCH_UM = 13.0


def maze_freq_cy_per_px(
    M: float,
    pitch_um: float = SENSOR_PITCH_UM_Z7,
    maze_pitch_um: float = MAZE_PITCH_UM,
) -> float:
    """Fundamental spatial frequency of the maze grid in cycles per sensor pixel.

    Derivation: one maze period spans ``maze_pitch_um`` on the subject;
    on the sensor it spans ``maze_pitch_um * M`` µm = ``maze_pitch_um *
    M / pitch_um`` pixels. The frequency is the reciprocal.

    M=1.0, pitch=4.35, maze_pitch=13.0 → 4.35 / 13.0 = 0.3346 cy/px
    (matches the prototype's hand-tuned 0.30-0.36 band).
    """
    if M <= 0:
        return float("inf")
    period_px = maze_pitch_um * M / pitch_um
    return 1.0 / period_px


def maze_amp(
    image_2d: np.ndarray,
    M: float,
    *,
    pitch_um: float = SENSOR_PITCH_UM_Z7,
    maze_pitch_um: float = MAZE_PITCH_UM,
    half_bandwidth: float = 0.03,
) -> float | None:
    """Mean |FFT| amplitude in the annulus around the maze fundamental.

    Returns ``None`` if the maze aliases at this M (maze_freq + half_bandwidth
    exceeds Nyquist of 0.5 cy/px). Returns 0.0 when the ROI is too small
    to resolve the band.

    The ROI is mean-subtracted and Hann-windowed in 2-D to suppress DC
    and edge leakage. Output scales with ROI area, so cross-tile
    comparison should use ROIs of the same size — Phase 1's maze ROI
    is M-driven but uniform per (sweep, tile).
    """
    if image_2d.ndim != 2:
        raise ValueError(f"expected 2-D image, got shape {image_2d.shape}")
    h, w = image_2d.shape
    if h < 8 or w < 8:
        return 0.0

    maze_freq = maze_freq_cy_per_px(M, pitch_um=pitch_um, maze_pitch_um=maze_pitch_um)
    nyquist = 0.5
    if maze_freq + half_bandwidth > nyquist:
        return None

    arr = image_2d.astype(np.float64) - image_2d.mean()
    win = np.outer(np.hanning(h), np.hanning(w))
    f = np.fft.fftshift(np.fft.fft2(arr * win))
    amp = np.abs(f)

    fy = np.fft.fftshift(np.fft.fftfreq(h))
    fx = np.fft.fftshift(np.fft.fftfreq(w))
    fxx, fyy = np.meshgrid(fx, fy)
    r = np.sqrt(fxx * fxx + fyy * fyy)

    lo = maze_freq - half_bandwidth
    hi = maze_freq + half_bandwidth
    mask = (r >= lo) & (r <= hi)
    if not mask.any():
        return 0.0
    # Per-pixel mean amplitude in the annulus, scaled to make the
    # numbers human-readable (divide by ROI area) — matches the
    # prototype at /tmp/ais_fft_worker.py.
    return float(amp[mask].sum() / (h * w))
