"""Step 2 — per-lens-config magnification verification.

The wafer target has a regular grid of dies; their boundary "scribe
lines" run across the entire wafer. We count die-pitch (in pixels)
per lens-config; the magnification ratio between two configs is
the ratio of their die pitches.

Algorithm (production, validated on 2026-01-29 ground truth: mean
abs err 4.9 %, median 3.2 % across 1× to 2× magnification):

1. Find the **sharpest f/11 frame** per lens-config (max JPEG file
   size in ``<config>/F11/cropped/center/``).
2. Downsample to 1024 px wide.
3. Segment the wafer region (bright-area bounding box).
4. **Detect wafer tilt** via gradient-direction histogram on strong
   edges within the wafer region. (Vertical scribes' gradients
   cluster around the wafer's tilt angle.) Single pass; no
   wasteful angle sweep.
5. **Rotate** to make scribes vertical.
6. Band-pass the rotated image (subtract slow gradient with
   σ=40 px; light low-pass with σ=1.5 px to suppress sub-pixel
   noise + very-fine sub-features).
7. Threshold |Sobel_X| at the 80th percentile to a binary edge map.
8. **Morphological opening with a tall thin (L, 1) kernel** —
   ``L = 40 % of wafer height`` — keeps only edges that are part
   of a *long vertical run*. Sub-features within dies (which exist
   only in some rows) are removed; die-boundary scribes (long lines
   spanning the wafer) survive.
9. Per-column count of remaining edge pixels has sharp peaks at
   each die boundary. ``find_peaks`` with distance ≥ p_min // 3
   and prominence ≥ 0.15 of the normalised signal.
10. Median peak-to-peak spacing within ``[p_min, p_max]`` rail-step
    bounds → die period in pixels.

Magnification = ``period_px(config) / period_px(anchor)`` where
the anchor is Sigma 150 bare at 1:1.

Approaches tried that DIDN'T work (preserved as a no-go log for
future-me):

- 1D / 2D FFT, cepstrum, autocorrelation: wafer's
  multi-scale-structure has no clean fundamental; spectrum is
  broadband.
- Grid-fit with sum/mean/peak-to-trough score: rewards "some
  lines strong" — picks 2× overtones because dies cluster in
  bronze/dark pairs.
- Grid-fit with midpoint contrast: marginal improvement.
- Sobel-X column projection + median peak spacing: picks
  sub-feature scale because sub-features have more total edge
  energy than die boundaries.
- High-pass on the 1D edge signal: bronze/dark alternation
  doesn't create a 1D envelope (Sobel sees only the sharp
  transition).

What broke the deadlock: **explicit enforcement of "lines must
span the whole wafer"** via morphological opening. This is a
*structural* test that no Fourier-based method can replicate.
Plus tilt detection as a separate up-front step (one pass)
instead of a tilt × period brute search.

Usage:

  # Prepare manifest from a tree of lens-config dirs:
  python -m archive_2026_05.measure_wafer_squares prepare \\
      --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \\
      --out /tmp/wafer-manifest.csv

  # Optionally fill in visual_count via vision review of low-confidence
  # rows, then compare to claimed_mag:
  python -m archive_2026_05.measure_wafer_squares evaluate \\
      --manifest /tmp/wafer-manifest.csv \\
      --anchor "Sigma APO Macro 150mm F2.8 EX DG OS HSM"

Validation against 2026-01-29 path-encoded labels: see
``tests/test_measure_wafer_squares_validation.py``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image
from scipy.ndimage import (
    binary_closing, binary_opening, gaussian_filter,
    rotate as ndi_rotate, sobel,
)
from scipy.signal import find_peaks


# ---- Image I/O ------------------------------------------------------------


DOWNSAMPLE_W = 1024


def sharpest_f11_centre_crop(config_dir: Path) -> Path | None:
    """Return the JPEG with the **largest** centre-crop file size under
    ``<config_dir>/F11/cropped/center/``. The returned path is the
    **full-frame** sibling in ``<config_dir>/F11/``.
    """
    crop_dir = config_dir / "F11" / "cropped" / "center"
    if not crop_dir.is_dir():
        return None
    candidates = sorted(
        (p for p in crop_dir.glob("*.jpg") if p.is_file()),
        key=lambda p: p.stat().st_size, reverse=True,
    )
    for c in candidates:
        full = config_dir / "F11" / c.name
        if full.is_file():
            return full
    return None


def sharpest_per_aperture(config_dir: Path) -> list[tuple[str, Path]]:
    """Return ``[(aperture_name, full_frame_path), ...]`` — the
    largest-centre-crop JPEG from every ``F<n>/`` aperture in the
    config dir (one entry per aperture). Used by ``measure_config()``
    for cross-aperture sanity-checking; lighting is fixed within a
    lens-config across apertures (the user moves the tripod between
    configs but not between aperture changes), so the *physical*
    magnification is the same across these frames — disagreement
    between aperture-level measurements is a strong signal that
    one of the per-frame measurements is wrong rather than the rig
    moved.
    """
    out: list[tuple[str, Path]] = []
    for f_ap in sorted(config_dir.glob("F*")):
        if not f_ap.is_dir() or f_ap.name == "F" or not f_ap.name.startswith("F"):
            continue
        crop_dir = f_ap / "cropped" / "center"
        if not crop_dir.is_dir():
            continue
        cands = sorted(
            (p for p in crop_dir.glob("*.jpg")
             if p.is_file() and p.name != "pick.jpg"),
            key=lambda p: p.stat().st_size, reverse=True,
        )
        for c in cands:
            full = f_ap / c.name
            if full.is_file():
                out.append((f_ap.name, full))
                break
    return out


def load_gray(path: Path, *, target_width: int = DOWNSAMPLE_W) -> np.ndarray:
    img = Image.open(path).convert("L")
    if target_width and img.width > target_width:
        ratio = target_width / img.width
        img = img.resize(
            (target_width, int(img.height * ratio)), Image.LANCZOS,
        )
    return np.asarray(img, dtype=np.float32)


# ---- Wafer segmentation ---------------------------------------------------


def detect_wafer_mask(img: np.ndarray, *, percentile: float = 50.0):
    """Bounding-box slice of the bright (wafer) region."""
    threshold = np.percentile(img, percentile)
    bright = img > threshold
    col_fill = bright.mean(axis=0)
    row_fill = bright.mean(axis=1)
    bright_cols = np.where(col_fill > 0.30)[0]
    bright_rows = np.where(row_fill > 0.30)[0]
    h, w = img.shape
    if len(bright_cols) < 10 or len(bright_rows) < 10:
        return np.s_[int(h * 0.10):int(h * 0.90), int(w * 0.10):int(w * 0.90)]
    return np.s_[
        bright_rows[0]:bright_rows[-1] + 1,
        bright_cols[0]:bright_cols[-1] + 1,
    ]


# ---- Tilt detection -------------------------------------------------------


def detect_tilt_via_gradient(
    img: np.ndarray, *,
    angle_range_deg: float = 6.0,
    bin_width_deg: float = 0.25,
    edge_threshold_pct: float = 80.0,
) -> float:
    """Estimate wafer tilt (degrees, +ve = clockwise rotation needed
    to make vertical scribes truly vertical) by histogramming the
    gradient angle of strong edge pixels.

    A vertical line in image (top-to-bottom column) has gradient
    purely horizontal → angle = 0°. Tilt θ shifts the histogram
    peak by θ.

    The two bins immediately adjacent to 0° are zeroed before argmax
    to suppress a narrow spike caused by Lanczos-downsample aliasing
    of tilted scribe edges: the 8.06× resize in ``load_gray`` sometimes
    presents a tilted edge as a locally horizontal gradient, depositing
    a single-bin-wide pile-up at exactly 0°. On well-focused frames the
    real tilted-scribe signal wins anyway; on weak-signal frames
    (out-of-focus stack ends, sub-1:1 framing) the aliasing spike used
    to dominate and the downstream long-line extraction then operated
    on incorrectly rotated input. Wafers in this dataset are
    consistently placed at +2-5° tilt, so excluding the central two
    bins is safe; a truly 0°-aligned wafer would need this prior
    relaxed.
    """
    sx = sobel(img, axis=1)
    sy = sobel(img, axis=0)
    mag = np.hypot(sx, sy)
    thr = np.percentile(mag, edge_threshold_pct)
    strong = mag > thr
    angle = np.degrees(np.arctan2(sy[strong], sx[strong]))
    angle = (angle + 90) % 180 - 90  # wrap to [-90, 90]
    bins = np.arange(-angle_range_deg, angle_range_deg + bin_width_deg,
                     bin_width_deg)
    if len(bins) < 3:
        return 0.0
    hist, _ = np.histogram(angle, bins=bins)
    bin_centers = bins[:-1] + bin_width_deg / 2
    hist[np.abs(bin_centers) < bin_width_deg] = 0
    return float(bins[hist.argmax()] + bin_width_deg / 2)


# ---- Filtering + line extraction ------------------------------------------


def bandpass_image(
    img: np.ndarray, *, low_cut_sigma: float = 40.0, high_cut_sigma: float = 1.5,
) -> np.ndarray:
    """Subtract slow gradient (kills bronze/dark die-pair alternation),
    then light low-pass (suppresses sub-pixel noise + very fine
    sub-feature scale)."""
    hp = img - gaussian_filter(img, sigma=low_cut_sigma)
    return gaussian_filter(hp, sigma=high_cut_sigma)


def extract_long_line_columns(
    img: np.ndarray, *,
    edge_threshold_pct: float = 80.0,
    min_line_length_frac: float = 0.40,
    gap_bridge_px: int = 0,
) -> np.ndarray:
    """Per-column count of pixels that are part of a vertical edge
    segment ≥ ``min_line_length_frac`` × image height. Sub-features
    (short edges) are filtered out by the morphological opening.

    ``gap_bridge_px``: if > 0, a vertical ``(gap_bridge_px, 1)``
    binary closing is applied to the edge mask before the long-line
    opening. This bridges short vertical gaps in otherwise-long
    scribes — useful when dust spots or other localised obstructions
    visibly interrupt the scribe in the captured frame. The caller
    chooses when to enable this; ``measure()`` retries with
    ``gap_bridge_px=15`` as a fallback when the primary pass returns
    fewer than 4 line peaks.
    """
    h, w = img.shape
    edges = np.abs(sobel(img, axis=1))
    thr = np.percentile(edges, edge_threshold_pct)
    edge_mask = edges > thr
    if gap_bridge_px > 0:
        edge_mask = binary_closing(
            edge_mask,
            structure=np.ones((gap_bridge_px, 1), dtype=bool),
        )
    L = max(5, int(h * min_line_length_frac))
    opened = binary_opening(edge_mask, structure=np.ones((L, 1), dtype=bool))
    return opened.sum(axis=0).astype(np.float32)


def _long_line_mask_2d(
    img: np.ndarray, *,
    edge_threshold_pct: float = 80.0, min_line_length_frac: float = 0.40,
) -> np.ndarray:
    """2D binary mask of pixels on a long vertical OR long horizontal
    edge. Sub-features (short edges) are zeroed; only the
    wafer-spanning scribes remain. Used by the 2D-FFT cross-check."""
    h, w = img.shape
    sx = np.abs(sobel(img, axis=1))
    sy = np.abs(sobel(img, axis=0))
    thr_x = np.percentile(sx, edge_threshold_pct)
    thr_y = np.percentile(sy, edge_threshold_pct)
    Lv = max(5, int(h * min_line_length_frac))
    Lh = max(5, int(w * min_line_length_frac))
    v_long = binary_opening(sx > thr_x, structure=np.ones((Lv, 1), dtype=bool))
    h_long = binary_opening(sy > thr_y, structure=np.ones((1, Lh), dtype=bool))
    return (v_long | h_long).astype(np.float32)


def _fft_score_at_period(spec: np.ndarray, P: float) -> float:
    """Sum magnitudes at the expected 2D-FFT peak locations for a
    square grid at period P. ``spec`` is the **centred** 2D magnitude
    spectrum (post-fftshift)."""
    n_rows, n_cols = spec.shape
    cy, cx = n_rows // 2, n_cols // 2
    if P <= 0:
        return 0.0
    kx = n_cols / P
    ky = n_rows / P
    if kx > cx - 1 or ky > cy - 1:
        return 0.0
    def at(y: float, x: float) -> float:
        y0, x0 = int(np.floor(y)), int(np.floor(x))
        dy, dx = y - y0, x - x0
        if y0 < 0 or x0 < 0 or y0 + 1 >= n_rows or x0 + 1 >= n_cols:
            return 0.0
        return float(
            spec[y0, x0] * (1 - dy) * (1 - dx)
            + spec[y0 + 1, x0] * dy * (1 - dx)
            + spec[y0, x0 + 1] * (1 - dy) * dx
            + spec[y0 + 1, x0 + 1] * dy * dx
        )
    s_v = at(cy, cx + kx) + at(cy, cx - kx)           # vertical-scribe peaks
    s_h = at(cy + ky, cx) + at(cy - ky, cx)           # horizontal-scribe peaks
    s_cross = (
        at(cy + ky, cx + kx) + at(cy + ky, cx - kx)
        + at(cy - ky, cx + kx) + at(cy - ky, cx - kx)
    )
    return s_v + s_h + 0.5 * s_cross


def cross_check_period_2dfft(
    img: np.ndarray, *, p_min: int = 40, p_max: int = 400,
) -> float | None:
    """Independent period estimate via 2D-FFT on the long-line mask.

    Fails differently from the median-of-spacings primary, so a
    disagreement is a useful "needs vision review" signal. Also
    serves as a fallback when the primary returns None (insufficient
    detected lines)."""
    mask = _long_line_mask_2d(img)
    if mask.sum() < 50:                # essentially no long lines
        return None
    signal = mask - mask.mean()
    win_y = np.hanning(signal.shape[0])[:, None]
    win_x = np.hanning(signal.shape[1])[None, :]
    spec = np.abs(np.fft.fftshift(np.fft.fft2(signal * win_y * win_x)))
    p_max_eff = min(p_max, min(signal.shape) // 2)
    if p_max_eff <= p_min:
        return None
    scores: dict[int, float] = {}
    best = (None, -np.inf)
    for P_int in range(p_min, p_max_eff + 1):
        s = _fft_score_at_period(spec, float(P_int))
        scores[P_int] = s
        if s > best[1]:
            best = (P_int, s)
    P_init = best[0]
    if P_init is None:
        return None
    # Sub-bin parabolic refinement when both neighbours are in range.
    if (P_init - 1) in scores and (P_init + 1) in scores:
        a, b, c = scores[P_init - 1], scores[P_init], scores[P_init + 1]
        denom = a - 2 * b + c
        offset = 0.5 * (a - c) / denom if denom != 0 else 0.0
        return float(P_init) + offset
    return float(P_init)


def find_line_peaks(sig: np.ndarray, *, p_min: int = 40):
    if sig.max() <= 0:
        return np.array([])
    sig_n = sig / sig.max()
    peaks, _ = find_peaks(
        sig_n, distance=max(3, p_min // 3),
        prominence=0.15, height=0.1,
    )
    return peaks


def refine_peaks_subpixel(sig: np.ndarray, peaks: np.ndarray) -> np.ndarray:
    """Refine each integer peak position to sub-pixel precision via a
    parabolic fit on its 3-pixel neighbourhood. Critical at high
    magnifications where only 2-3 die-pitches fit in the frame — a
    ±1 px localization error on a 300-px period is +/-0.3 %; without
    this refinement, the median-of-3 integer spacings would
    quantize the magnification estimate.
    """
    refined = []
    for idx in peaks:
        i = int(idx)
        if 0 < i < len(sig) - 1:
            a, b, c = float(sig[i - 1]), float(sig[i]), float(sig[i + 1])
            denom = a - 2 * b + c
            offset = 0.5 * (a - c) / denom if denom != 0 else 0.0
            refined.append(i + offset)
        else:
            refined.append(float(i))
    return np.asarray(refined)


# ---- Pipeline -------------------------------------------------------------


@dataclass(frozen=True)
class WaferMeasurement:
    period_px: float | None
    tilt_deg: float
    n_lines: int
    spacings: tuple[float, ...]
    image_width_px: int
    wafer_width_px: int
    confidence: str = ""    # "high" / "medium" / "low" — combined flag
    cross_check_period_px: float | None = None
    """2D-FFT-based period from the same image. Used as an
    independent cross-check; when it disagrees with the primary
    period_px by >10% the confidence is downgraded."""
    reason: str = ""


CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2, "": 3}
"""Sort order for ``measure_config`` to pick the best per-aperture
measurement: HIGH-confidence beats MEDIUM beats LOW. Within a band,
higher n_lines is preferred."""

CROSS_APERTURE_AGREEMENT_THRESHOLD_PCT = 10.0
"""When the period measured from frames of *different* apertures of
the *same* lens-config disagrees by more than this percentage, mark
the config with a warning. Lighting and rig position are fixed
across apertures of one config (the user moves the tripod between
configs but not between aperture changes), so the magnification is
physically the same — cross-aperture disagreement means one or more
of the per-aperture measurements latched onto a wrong harmonic or
sub-feature pitch, regardless of how confident each individual
measurement claims to be."""


@dataclass(frozen=True)
class ConfigMeasurement:
    """Aggregated multi-aperture measurement for a lens-config dir.

    ``best`` is the picked per-aperture measurement (highest
    confidence, ties broken by n_lines). ``per_aperture`` retains
    every aperture's result for diagnostics. ``warning`` is non-empty
    when ``max_cross_aperture_dev_pct`` exceeds the threshold.
    """
    best_path: Path
    best: WaferMeasurement
    per_aperture: tuple[tuple[str, Path, WaferMeasurement], ...]
    max_cross_aperture_dev_pct: float = 0.0
    warning: str = ""


CROSS_CHECK_AGREEMENT_THRESHOLD_PCT = 10.0
"""When the 2D-FFT cross-check disagrees with the primary
``period_px`` by more than this percentage, downgrade the
confidence by one bucket. Set at 10 % because cross-check
disagreements within that band are usually quantisation noise
(sub-pixel limits at high mag) rather than algorithm conflict."""


def _periods_agree(p_primary: float, p_cross: float | None) -> bool:
    """True iff the cross-check period is within
    ``CROSS_CHECK_AGREEMENT_THRESHOLD_PCT`` of the primary."""
    if p_cross is None or p_primary <= 0:
        return False
    return abs(p_primary - p_cross) / p_primary * 100.0 <= CROSS_CHECK_AGREEMENT_THRESHOLD_PCT


def _confidence_label(n_lines: int, cross_check_agrees: bool) -> str:
    """Combined confidence bucket based on (a) how many distinct die
    boundaries the primary pipeline detected and (b) whether the
    2D-FFT cross-check agrees with the primary period.

    HIGH:   n_lines ≥ 5 AND cross-check agrees
    MEDIUM: (n_lines ≥ 5 AND disagreement) OR (n_lines ∈ [3, 4] AND agreement)
    LOW:    n_lines ≤ 2 OR (n_lines ∈ [3, 4] AND disagreement)

    The agreement leg matters most at high mag where n_lines is
    naturally small; a disagreement there means either pipeline
    picked a harmonic, and the result needs vision review.
    """
    if n_lines >= 5 and cross_check_agrees:
        return "high"
    if n_lines >= 5:
        return "medium"
    if n_lines >= 3 and cross_check_agrees:
        return "medium"
    return "low"


RELAX_GAP_BRIDGE_PX = 15
"""Vertical closing kernel height used by ``measure()`` when the
primary long-line opening returns fewer than ``RELAX_TRIGGER_N_LINES``
peaks. 15 was empirically the largest value that recovered
dust-broken scribes (frame 16667 in 55mm AIS 537016 / 1_1 / F11)
without fusing adjacent dies in any of the 16 path-encoded
validation cases. K ≥ 20 starts merging real die boundaries on
high-mag cases (200mm + 6T) and the algorithm collapses to a 2x
or sub-feature harmonic. K = 10 still leaves 16667 at +8% error."""

RELAX_TRIGGER_N_LINES = 2
"""``measure()`` retries the long-line extraction with
``gap_bridge_px=RELAX_GAP_BRIDGE_PX`` only when the primary pass
returns strictly fewer than this many peaks — i.e. when the primary
would otherwise have nothing to compute a period from and fall back
to the (less-trustworthy) 2D-FFT cross-check. A more eager trigger
(``< 3`` / ``< 4``) was tried and regressed Sigma 150 + TC-2001 /
1.5_1 and /2_1 (n_lines=3 primary returns the correct period; the
retry-bridged map finds 4-5 extra spurious peaks at sub-feature
pitch, throws off the median spacing). Restricting the retry to
primary-failure cases preserves every currently-passing
measurement and adds new measurements only where there was none
before (e.g. 55mm AIS 537016 / 1_1 / F11 frame 16667 where dust
spots interrupt the scribes, and the 100-400 + Z TC-1.4x / 1_1.86
sub-1:1 case)."""


def measure(
    path: Path, *,
    low_cut_sigma: float = 40.0, high_cut_sigma: float = 1.5,
    edge_threshold_pct: float = 80.0,
    min_line_length_frac: float = 0.40,
    p_min: int = 40, p_max: int = 400,
) -> WaferMeasurement:
    """Run the full pipeline on a single image; return measurement.

    Primary pass uses a (L=40%-of-height, 1) morphological opening to
    find scribe columns. If that returns fewer than
    ``RELAX_TRIGGER_N_LINES`` peaks, retry with a
    ``(RELAX_GAP_BRIDGE_PX, 1)`` binary closing pre-step to bridge
    short vertical gaps (e.g. dust spots from shallow lighting that
    locally interrupt scribes); the relaxed result is taken only if
    it produces more peaks than the primary did.
    """
    img = load_gray(path)
    mask = detect_wafer_mask(img)
    masked = img[mask]
    tilt = detect_tilt_via_gradient(masked, edge_threshold_pct=edge_threshold_pct)
    rotated = ndi_rotate(masked, tilt, reshape=False, order=1, mode="reflect")
    bp = bandpass_image(rotated, low_cut_sigma=low_cut_sigma, high_cut_sigma=high_cut_sigma)
    sig = extract_long_line_columns(
        bp, edge_threshold_pct=edge_threshold_pct,
        min_line_length_frac=min_line_length_frac,
    )
    peaks = find_line_peaks(sig, p_min=p_min)
    relaxed_reason = ""
    if len(peaks) < RELAX_TRIGGER_N_LINES:
        sig_relaxed = extract_long_line_columns(
            bp, edge_threshold_pct=edge_threshold_pct,
            min_line_length_frac=min_line_length_frac,
            gap_bridge_px=RELAX_GAP_BRIDGE_PX,
        )
        peaks_relaxed = find_line_peaks(sig_relaxed, p_min=p_min)
        if len(peaks_relaxed) > len(peaks):
            sig = sig_relaxed
            peaks = peaks_relaxed
            relaxed_reason = (
                f"used_gap_bridge_px={RELAX_GAP_BRIDGE_PX}_"
                f"primary_n_lines<{RELAX_TRIGGER_N_LINES}"
            )
    # 2D-FFT cross-check on the same band-passed image.
    cross_period = cross_check_period_2dfft(bp, p_min=p_min, p_max=p_max)
    if len(peaks) < 2:
        # Primary failed (insufficient lines). Fall back to the 2D-FFT
        # cross-check if it produced anything — useful at sub-1:1 mag
        # where the wafer doesn't fill the frame and the primary
        # can't detect ≥2 long-line peaks.
        if cross_period is not None:
            return WaferMeasurement(
                period_px=cross_period, tilt_deg=tilt, n_lines=0,
                spacings=(), image_width_px=img.shape[1],
                wafer_width_px=masked.shape[1],
                confidence="low",
                cross_check_period_px=cross_period,
                reason="primary_failed_using_fft_fallback",
            )
        return WaferMeasurement(
            period_px=None, tilt_deg=tilt, n_lines=int(len(peaks)),
            spacings=(), image_width_px=img.shape[1], wafer_width_px=masked.shape[1],
            confidence="low", reason="fewer_than_2_lines",
        )
    # Sub-pixel refine each peak position, then compute spacings as
    # float differences. At >1:1 mag only 2-3 spacings exist; the
    # parabolic refinement keeps each one ±0.1-0.3 px instead of ±1 px.
    refined = refine_peaks_subpixel(sig, peaks)
    spacings = np.diff(refined)
    valid = spacings[(spacings >= p_min) & (spacings <= p_max)]
    if len(valid) >= 2:
        period = float(np.median(valid))
    elif len(valid) == 1:
        period = float(valid[0])
    else:
        period = float(np.median(spacings))
    agrees = _periods_agree(period, cross_period)
    return WaferMeasurement(
        period_px=period, tilt_deg=tilt, n_lines=int(len(peaks)),
        spacings=tuple(float(s) for s in spacings),
        image_width_px=img.shape[1], wafer_width_px=masked.shape[1],
        confidence=_confidence_label(int(len(peaks)), agrees),
        cross_check_period_px=cross_period,
        reason=relaxed_reason,
    )


# ---- Multi-aperture aggregation ------------------------------------------


def measure_config(config_dir: Path, **measure_kwargs) -> ConfigMeasurement | None:
    """Measure the sharpest centre-crop frame from every aperture in
    ``config_dir`` and pick the best result by confidence.

    Returns ``None`` if the directory has no centre crops in any
    aperture (e.g. mag dir without an ``F<n>/cropped/center/``
    subtree). Otherwise returns a ``ConfigMeasurement`` whose
    ``best`` field is the per-frame ``WaferMeasurement`` to use
    downstream, plus per-aperture diagnostics and a cross-aperture
    disagreement warning when applicable.

    Use this instead of ``measure(sharpest_f11_centre_crop(...))``
    when you have multiple apertures of one config: the sharpest F11
    frame happens to be unmeasurable on some configs (dust spots,
    framing edge cases), and another aperture's sharpest frame may
    succeed where F11 didn't.
    """
    frames = sharpest_per_aperture(config_dir)
    if not frames:
        return None
    per_aperture: list[tuple[str, Path, WaferMeasurement]] = []
    for ap, path in frames:
        m = measure(path, **measure_kwargs)
        per_aperture.append((ap, path, m))
    # Best-pick policy: prefer F11 when it produced a usable period
    # (i.e. didn't fall back to the FFT cross-check). F11 was the
    # algorithm's tuned-for aperture; empirically when F11 disagrees
    # with another aperture, F11 is closer to the truth more often
    # than not. The FFT-fallback path explicitly opts out of this
    # preference — that case is what the multi-aperture mechanism
    # exists to rescue.
    f11 = next(
        ((ap, p, m) for ap, p, m in per_aperture
         if ap == "F11" and m.period_px is not None
         and "primary_failed_using_fft_fallback" not in m.reason),
        None,
    )
    valid = [(ap, p, m) for ap, p, m in per_aperture if m.period_px is not None]
    if f11 is not None:
        best_ap, best_path, best_m = f11
    elif valid:
        # F11 entirely failed (or FFT-fallback'd). Pick highest-
        # confidence other aperture; ties broken by larger n_lines.
        valid_sorted = sorted(
            valid,
            key=lambda t: (CONFIDENCE_RANK.get(t[2].confidence, 9), -t[2].n_lines),
        )
        best_ap, best_path, best_m = valid_sorted[0]
    else:
        # No measurement produced a period anywhere. Return the first
        # aperture's result so callers still get the failure reason.
        best_ap, best_path, best_m = per_aperture[0]
    # Cross-aperture disagreement: max relative deviation among ALL
    # valid measurements (not just same-confidence ones — the warning
    # is most useful when one HIGH agrees with another HIGH on the
    # wrong harmonic).
    max_dev = 0.0
    if len(valid) >= 2 and best_m.period_px:
        for _ap, _p, m in valid:
            if m is best_m or m.period_px is None:
                continue
            dev = abs(m.period_px - best_m.period_px) / best_m.period_px * 100.0
            if dev > max_dev:
                max_dev = dev
    warning = ""
    if max_dev > CROSS_APERTURE_AGREEMENT_THRESHOLD_PCT:
        disagreeing_apertures = []
        for ap, _p, m in valid:
            if m.period_px and m is not best_m:
                d = abs(m.period_px - best_m.period_px) / best_m.period_px * 100.0
                if d > CROSS_APERTURE_AGREEMENT_THRESHOLD_PCT:
                    disagreeing_apertures.append(f"{ap}:{m.period_px:.1f}px")
        warning = (
            f"cross_aperture_disagreement_{max_dev:.1f}pct "
            f"(best={best_ap}:{best_m.period_px:.1f}px; "
            f"others={','.join(disagreeing_apertures)})"
        )
    return ConfigMeasurement(
        best_path=best_path,
        best=best_m,
        per_aperture=tuple(per_aperture),
        max_cross_aperture_dev_pct=max_dev,
        warning=warning,
    )


# ---- Path-encoded ground truth + manifest --------------------------------


def parse_mag_label(mag_str: str) -> float:
    """Convert a magnification dir name to a float ratio."""
    if "_" not in mag_str:
        return float("nan")
    a, b = mag_str.split("_", 1)
    try:
        return float(a) / float(b)
    except ValueError:
        return float("nan")


MANIFEST_COLUMNS = [
    "slug", "mag_label", "claimed_mag", "image_path", "image_size_bytes",
    "algo_period_px", "algo_tilt_deg", "algo_n_lines", "algo_confidence",
    "algo_cross_check_period_px", "algo_measured_mag", "algo_deviation_pct",
    "algo_apertures_tried", "algo_best_aperture",
    "algo_cross_aperture_dev_pct", "algo_aperture_warning",
    "visual_count", "visual_count_anchor", "vision_measured_mag",
    "vision_confidence", "notes",
]


def _iter_lens_configs(root: Path, *, has_focal_subdir: bool = False) -> Iterable[Path]:
    """Yield each lens-config-mag dir under ``root``."""
    for slug_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for mag_dir in sorted(p for p in slug_dir.iterdir() if p.is_dir()):
            if mag_dir.name.endswith("-resized"):
                continue
            if (mag_dir / "F11").is_dir():
                yield mag_dir
            elif has_focal_subdir:
                for focal_dir in mag_dir.iterdir():
                    if focal_dir.is_dir() and (focal_dir / "F11").is_dir():
                        yield focal_dir


def prepare_manifest(
    root: Path, out_csv: Path, *, anchor_slug: str | None = None,
) -> int:
    """Walk ``root``, find sharpest f/11 per config, run the
    morphological algorithm, write CSV. If ``anchor_slug`` is given
    (e.g. ``"Sigma APO Macro 150mm F2.8 EX DG OS HSM"``), the
    1:1 anchor's period is used to populate ``algo_measured_mag``.
    """
    has_focal = root.name == "2026-02-18"
    rows = []
    anchor_period = None
    for config_dir in _iter_lens_configs(root, has_focal_subdir=has_focal):
        rel = config_dir.relative_to(root)
        parts = rel.parts
        if has_focal and len(parts) == 3:
            slug, mag_label, _focal = parts
        elif len(parts) == 2:
            slug, mag_label = parts
        else:
            continue
        cm = measure_config(config_dir)
        if cm is None:
            continue
        m = cm.best
        path = cm.best_path
        # Best aperture is the path's parent dir's name (the F<n>/ part).
        best_aperture = path.parent.name
        apertures_tried = ";".join(ap for ap, _p, _m in cm.per_aperture)
        row = {
            "slug": slug,
            "mag_label": mag_label,
            "claimed_mag": parse_mag_label(mag_label),
            "image_path": str(path),
            "image_size_bytes": path.stat().st_size,
            "algo_period_px": f"{m.period_px:.2f}" if m.period_px else "",
            "algo_tilt_deg": f"{m.tilt_deg:+.2f}",
            "algo_n_lines": m.n_lines,
            "algo_confidence": m.confidence,
            "algo_cross_check_period_px": (
                f"{m.cross_check_period_px:.2f}" if m.cross_check_period_px else ""
            ),
            "algo_apertures_tried": apertures_tried,
            "algo_best_aperture": best_aperture,
            "algo_cross_aperture_dev_pct": (
                f"{cm.max_cross_aperture_dev_pct:.1f}"
                if cm.max_cross_aperture_dev_pct > 0 else ""
            ),
            "algo_aperture_warning": cm.warning,
            "notes": m.reason or "",
        }
        rows.append(row)
        if anchor_slug and slug == anchor_slug and mag_label == "1_1" and m.period_px:
            anchor_period = m.period_px

    # Second pass: compute algo_measured_mag against anchor.
    if anchor_period:
        for r in rows:
            if r["algo_period_px"]:
                p = float(r["algo_period_px"])
                measured = p / anchor_period
                r["algo_measured_mag"] = f"{measured:.3f}"
                claimed = float(r["claimed_mag"]) if r["claimed_mag"] else float("nan")
                if claimed > 0:
                    r["algo_deviation_pct"] = f"{(measured - claimed) / claimed * 100:+.1f}"

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for r in rows:
            for col in MANIFEST_COLUMNS:
                r.setdefault(col, "")
            writer.writerow(r)
    return len(rows)


def evaluate(manifest_path: Path, anchor_slug: str) -> int:
    """Recompute vision_measured_mag from visual_count column;
    deviations are written to vision_confidence and notes."""
    with manifest_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    anchor_count = None
    for r in rows:
        if r["slug"] == anchor_slug and r["mag_label"] == "1_1" and r["visual_count"]:
            anchor_count = float(r["visual_count"])
            break
    if anchor_count is None:
        print(f"ERROR: no visual_count for anchor {anchor_slug} / 1_1", file=sys.stderr)
        return 1
    for r in rows:
        if not r["visual_count"]:
            continue
        vc = float(r["visual_count"])
        if vc <= 0:
            continue
        measured = anchor_count / vc
        r["visual_count_anchor"] = f"{anchor_count:g}"
        r["vision_measured_mag"] = f"{measured:.3f}"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for r in rows:
            for col in MANIFEST_COLUMNS:
                r.setdefault(col, "")
            writer.writerow(r)
    return 0


# ---- CLI -----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="measure_wafer_squares",
        description="Per-lens-config magnification verification via wafer-square measurement.",
    )
    subs = parser.add_subparsers(dest="cmd", required=True)

    p = subs.add_parser("prepare", help="Build the manifest CSV.")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--anchor", default="Sigma APO Macro 150mm F2.8 EX DG OS HSM",
                   help="Anchor slug whose 1:1 magnification anchors the ratio.")

    e = subs.add_parser("evaluate",
                        help="Compute vision_measured_mag from visual_count column.")
    e.add_argument("--manifest", type=Path, required=True)
    e.add_argument("--anchor", required=True)

    args = parser.parse_args()
    if args.cmd == "prepare":
        n = prepare_manifest(args.root, args.out, anchor_slug=args.anchor)
        print(f"Wrote {n} rows to {args.out}")
        return 0
    if args.cmd == "evaluate":
        return evaluate(args.manifest, args.anchor)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
