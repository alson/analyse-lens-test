"""Scribe-LSF MTF50 and amplitude readouts.

Per the 2026-05-16 methodology update in ``SHARPNESS_METRICS.md``, the
dark-trough cross-section of a wafer scribe is treated directly as a
line-spread function (no ESF differentiation step — scribes are
narrow dark lines, not step edges, so ESF math leaks the opposite side
of the scribe into the integration window). FFT the perpendicular
cross-section, read MTF50 and amplitude at a reference frequency
straight off the resulting |FFT| curve.

Detection uses OpenCV's Line Segment Detector (LSD) on the ROI; we
keep the longest near-full-span segment. Slant is preserved — no
tilt-correction in ``cross_section``, since the FFT readout absorbs
the orientation naturally via bilinear perpendicular sampling.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.ndimage import map_coordinates
from skimage.feature import canny
from skimage.transform import probabilistic_hough_line


@dataclass(frozen=True)
class Segment:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def length_px(self) -> float:
        return float(np.hypot(self.x1 - self.x0, self.y1 - self.y0))

    @property
    def angle_rad(self) -> float:
        return float(np.arctan2(self.y1 - self.y0, self.x1 - self.x0))


_lsd_detector = None


def _get_lsd():
    global _lsd_detector
    if _lsd_detector is None:
        _lsd_detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    return _lsd_detector


def detect_scribe(
    image_2d: np.ndarray,
    *,
    min_length_ratio: float = 0.15,
    min_length_px: int = 200,
    darkness_margin: float = 15.0,
    hough_fallback: bool = True,
) -> Segment | None:
    """Return the longest sufficiently-dark line in ``image_2d``.

    Two-stage detector:

    1. **LSD** (OpenCV) finds intensity-edge segments. We keep the
       longest segment whose along-line mean is at least
       ``darkness_margin`` units below the ROI mean. The wafer
       scribes appear in LSD output as 400-700 px segments inside a
       ~3456 px ROI — fragmented enough that the original
       60 %-of-ROI threshold rejected real scribes.
    2. **Hough fallback** (when ``hough_fallback=True`` and LSD finds
       nothing): :func:`detect_scribe_hough` runs
       ``probabilistic_hough_line`` on Canny edges, groups lines by
       angle, clusters by perpendicular offset, and spans each
       cluster's endpoints to recover a single long composite line.
       On the 2026-05-16 AIS POC this raised per-tile detection from
       66 % to 89 %.

    Returns ``None`` if neither stage finds a qualifying dark line.
    """
    seg = _detect_scribe_lsd(
        image_2d,
        min_length_ratio=min_length_ratio,
        min_length_px=min_length_px,
        darkness_margin=darkness_margin,
    )
    if seg is not None:
        return seg
    if hough_fallback:
        return detect_scribe_hough(image_2d, darkness_margin=darkness_margin)
    return None


def _detect_scribe_lsd(
    image_2d: np.ndarray,
    *,
    min_length_ratio: float,
    min_length_px: int,
    darkness_margin: float,
) -> Segment | None:
    """OpenCV LSD pass. Internal — call :func:`detect_scribe` instead."""
    if image_2d.ndim != 2:
        raise ValueError(f"expected 2-D image, got shape {image_2d.shape}")
    h, w = image_2d.shape
    min_len = max(min(h, w) * min_length_ratio, float(min_length_px))

    arr8 = _to_uint8(image_2d)
    lsd = _get_lsd()
    lines, *_ = lsd.detect(arr8)
    if lines is None or len(lines) == 0:
        return None

    roi_mean = float(arr8.mean())
    cutoff = roi_mean - darkness_margin
    best: Segment | None = None
    best_len = 0.0
    for ln in lines:
        x0, y0, x1, y1 = ln.ravel()
        length = float(np.hypot(x1 - x0, y1 - y0))
        if length < min_len:
            continue
        ts = np.linspace(0.0, 1.0, 32)
        xs = x0 + (x1 - x0) * ts
        ys = y0 + (y1 - y0) * ts
        samples = map_coordinates(arr8, np.vstack([ys, xs]), order=1, mode="nearest")
        if float(samples.mean()) >= cutoff:
            continue
        if length > best_len:
            best_len = length
            best = Segment(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))
    return best


def detect_scribe_hough(
    image_2d: np.ndarray,
    *,
    canny_sigma: float = 2.0,
    hough_threshold: int = 150,
    hough_min_length: int = 250,
    hough_max_gap: int = 30,
    angle_bin_deg: float = 5.0,
    perp_distance_px: float = 8.0,
    darkness_margin: float = 15.0,
    min_spanned_length_px: int = 600,
) -> Segment | None:
    """Recover a single long scribe by linking collinear Hough fragments.

    Pipeline:

    1. Canny edge map on the ROI.
    2. :func:`skimage.transform.probabilistic_hough_line` on the edges.
    3. Bin lines by angle (``angle_bin_deg`` bins); the dominant bin
       is the candidate scribe orientation.
    4. Within the dominant bin, cluster lines by perpendicular offset
       from the ROI centre (``perp_distance_px`` tolerance) — lines
       on the same infinite line have similar offset.
    5. For each cluster, project all endpoints onto the cluster's
       direction vector; the extremes span a composite line segment.
    6. Reject spans below ``min_spanned_length_px`` or above the
       darkness threshold (``roi_mean - darkness_margin``).
    7. Return the longest dark span, or ``None``.

    POC'd 2026-05-16 on AIS 287318 1:1 F8: 8 of 35 tile-shots that LSD
    rejected got a usable scribe through this path. Composite spans
    average ~3240 px vs LSD's ~690 px (4.7× longer cross-section
    anchor), so the resulting LSF profile averages over more pixels
    and is less noise-prone. Compute cost is ~3 s on a 3456 px ROI;
    Phase 1 only calls scribe detection once per (sweep, tile) at
    the filesize-argmax shot, so this is sweep-level overhead, not
    per-shot.
    """
    if image_2d.ndim != 2:
        raise ValueError(f"expected 2-D image, got shape {image_2d.shape}")

    arr = image_2d.astype(np.float32)
    arr_norm = arr / 255.0 if float(arr.max()) > 1.5 else arr
    edges = canny(arr_norm, sigma=canny_sigma)
    if int(edges.sum()) < 100:
        return None

    raw_lines = probabilistic_hough_line(
        edges,
        threshold=hough_threshold,
        line_length=hough_min_length,
        line_gap=hough_max_gap,
    )
    if not raw_lines:
        return None

    h, w = arr.shape
    cx0, cy0 = w / 2, h / 2
    n = len(raw_lines)
    angles = np.zeros(n)
    offsets = np.zeros(n)
    lengths = np.zeros(n)
    p0s = np.zeros((n, 2))
    p1s = np.zeros((n, 2))
    for i, (p0, p1) in enumerate(raw_lines):
        x0, y0 = p0
        x1, y1 = p1
        # Line direction is undirected → fold angle into [0, 180).
        ang = np.arctan2(y1 - y0, x1 - x0) * 180 / np.pi
        angles[i] = ang % 180.0
        dx, dy = x1 - x0, y1 - y0
        L = float(np.hypot(dx, dy))
        # Signed perpendicular distance from (cx0, cy0) to the line.
        offsets[i] = (dy * (cx0 - x0) - dx * (cy0 - y0)) / L
        lengths[i] = L
        p0s[i] = (x0, y0)
        p1s[i] = (x1, y1)

    # Find the dominant angle bin by total line length.
    bin_count = max(int(180 / angle_bin_deg), 1)
    bin_total = [0.0] * bin_count
    bin_members: list[list[int]] = [[] for _ in range(bin_count)]
    for i, a in enumerate(angles):
        b = int(a // angle_bin_deg) % bin_count
        bin_total[b] += lengths[i]
        bin_members[b].append(i)
    dominant_bin = int(np.argmax(bin_total))
    candidates = bin_members[dominant_bin]
    if not candidates:
        return None

    # Cluster the dominant bin's lines by perpendicular offset.
    cand_arr = np.array(candidates)
    sort_idx = np.argsort(offsets[cand_arr])
    sorted_offsets = offsets[cand_arr][sort_idx]
    sorted_cands = cand_arr[sort_idx]

    clusters: list[list[int]] = []
    current = [int(sorted_cands[0])]
    current_off = sorted_offsets[0]
    for j in range(1, len(sorted_cands)):
        if abs(sorted_offsets[j] - current_off) <= perp_distance_px:
            current.append(int(sorted_cands[j]))
        else:
            clusters.append(current)
            current = [int(sorted_cands[j])]
        current_off = sorted_offsets[j]
    clusters.append(current)

    cutoff = float(arr.mean()) - darkness_margin
    best: Segment | None = None
    best_len = 0.0
    for cl in clusters:
        cl_ang_rad = np.deg2rad(angles[cl].mean())
        ux, uy = np.cos(cl_ang_rad), np.sin(cl_ang_rad)
        endpts = np.vstack([p0s[cl], p1s[cl]])
        projections = endpts @ np.array([ux, uy])
        i_lo, i_hi = int(np.argmin(projections)), int(np.argmax(projections))
        x_lo, y_lo = endpts[i_lo]
        x_hi, y_hi = endpts[i_hi]
        span = float(np.hypot(x_hi - x_lo, y_hi - y_lo))
        if span < min_spanned_length_px:
            continue
        ts = np.linspace(0.0, 1.0, 32)
        xs = x_lo + (x_hi - x_lo) * ts
        ys = y_lo + (y_hi - y_lo) * ts
        samples = map_coordinates(arr, np.vstack([ys, xs]), order=1, mode="nearest")
        if float(samples.mean()) >= cutoff:
            continue
        if span > best_len:
            best_len = span
            best = Segment(x0=float(x_lo), y0=float(y_lo),
                           x1=float(x_hi), y1=float(y_hi))
    return best


def _to_uint8(arr: np.ndarray) -> np.ndarray:
    if arr.dtype == np.uint8:
        return arr
    a = np.asarray(arr, dtype=np.float32)
    lo, hi = float(a.min()), float(a.max())
    if hi - lo < 1e-9:
        return np.zeros(arr.shape, dtype=np.uint8)
    scaled = (a - lo) * (255.0 / (hi - lo))
    return scaled.astype(np.uint8)


def cross_section(
    image_2d: np.ndarray, seg: Segment, *, half_window_px: int = 24,
    samples_per_pixel: float = 1.0,
) -> np.ndarray:
    """Sample the dark-trough perpendicular cross-section.

    Returns a 1-D averaged profile of length ``2*half_window_px + 1``,
    where index ``half_window_px`` is on the line itself.

    Along the segment we sample one anchor per pixel of segment length
    (so longer scribes give more averaging). At each anchor we sample
    a perpendicular line with bilinear interpolation.
    """
    length = seg.length_px
    if length < 4:
        return np.zeros(2 * half_window_px + 1, dtype=np.float64)
    n_anchors = max(int(length * samples_per_pixel), 4)

    # Unit vectors: along the segment, and perpendicular (rotate 90°).
    dx, dy = (seg.x1 - seg.x0) / length, (seg.y1 - seg.y0) / length
    px, py = -dy, dx  # perpendicular

    ts = np.linspace(0.0, 1.0, n_anchors)
    ax = seg.x0 + dx * length * ts
    ay = seg.y0 + dy * length * ts

    offsets = np.arange(-half_window_px, half_window_px + 1, dtype=np.float64)
    # 2-D meshgrid of sample coordinates: shape (n_offsets, n_anchors).
    sample_x = ax[None, :] + px * offsets[:, None]
    sample_y = ay[None, :] + py * offsets[:, None]
    coords = np.vstack([sample_y.ravel(), sample_x.ravel()])
    sampled = map_coordinates(
        image_2d.astype(np.float64), coords, order=1, mode="nearest",
    ).reshape(offsets.size, n_anchors)
    # Average across anchors → 1-D profile.
    return sampled.mean(axis=1)


def _fft_mag_spectrum(profile: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(freqs_cy_per_px, mag)`` of a centred 1-D profile.

    The profile is centred (DC subtracted) and Hann-windowed before the
    FFT to suppress edge leakage. Returns the positive-frequency half;
    DC bin is dropped (it would always sum to ~0 after centring anyway).
    """
    if profile.size < 4:
        return np.array([]), np.array([])
    centred = profile - profile.mean()
    win = np.hanning(centred.size)
    f = np.fft.rfft(centred * win)
    mag = np.abs(f)
    freqs = np.fft.rfftfreq(centred.size, d=1.0)
    # Drop DC.
    return freqs[1:], mag[1:]


def lsf_peak_amp(profile: np.ndarray, ref_freq_cy_per_px: float = 0.10) -> float:
    """Magnitude of |FFT(profile)| at the closest bin to ``ref_freq_cy_per_px``.

    Returns 0.0 on degenerate input. Higher = sharper at this reference
    frequency. The default reference (0.10 cy/px on sensor) sits well
    below Nyquist and above the noise floor on JPEG-quantised tiles.
    """
    freqs, mag = _fft_mag_spectrum(profile)
    if freqs.size == 0:
        return 0.0
    idx = int(np.argmin(np.abs(freqs - ref_freq_cy_per_px)))
    return float(mag[idx])


def lsf_mtf50(profile: np.ndarray) -> float | None:
    """Return the frequency at which |FFT(profile)| falls to half its peak.

    Looks for the first crossing past the global magnitude maximum. If
    the spectrum stays above 0.5 × peak out to Nyquist (rare —
    indicates a near-impulse profile, i.e. extremely sharp scribe with
    almost no leakage), returns ``None``. Caller should treat ``None``
    as "MTF50 saturated at Nyquist" for ranking.
    """
    freqs, mag = _fft_mag_spectrum(profile)
    if freqs.size == 0 or mag.max() <= 0:
        return None
    # Search past the global peak — the LSF spectrum should be
    # monotonically decreasing after its low-frequency lobe.
    peak_idx = int(np.argmax(mag))
    peak = mag[peak_idx]
    half = 0.5 * peak
    for k in range(peak_idx + 1, mag.size):
        if mag[k] <= half:
            # Linear interpolate the crossing for sub-bin accuracy.
            if k == 0:
                return float(freqs[0])
            f0, f1 = freqs[k - 1], freqs[k]
            m0, m1 = mag[k - 1], mag[k]
            if m0 == m1:
                return float(f1)
            t = (m0 - half) / (m0 - m1)
            return float(f0 + (f1 - f0) * t)
    return None
