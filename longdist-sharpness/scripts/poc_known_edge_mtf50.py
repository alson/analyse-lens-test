"""CV-based known-edge slanted-edge MTF50 — prototype.

The auto-detect ``mtf50_slanted_edge`` in ``poc_longdist_algorithms.py``
fails on 60-70 % of real wide-angle tiles because its in-tile gradient
direction estimate doesn't fire on the scene's actual long edges (wall
horizon, stair-tread boundaries, pavement edge). The fix: locate the
long edges per-(lens, FL) reference image via Canny + Hough, then
measure each test image's MTF50 with the *given* edge direction rather
than auto-detecting.

This script supports three modes:

- ``discover``: take one reference JPEG, find top-K candidate edges,
  emit an overlay PNG + JSON specs. The first deliverable — lets the
  user eyeball whether the right edges were picked.
- ``measure``: take a JSON spec + a test JPEG, return MTF50 per edge.
- ``dataset``: walk a dataset like ``poc_longdist_algorithms.py``,
  pick a per-(lens, FL) sharp reference, discover edges, measure on
  every replicate, and write per_measurement.csv.

Run via ``direnv exec . uv run python scripts/poc_known_edge_mtf50.py``.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

# Reuse dataset definitions + config discovery from the algorithm script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poc_longdist_algorithms as pla  # noqa: E402

# ----- tunables -----------------------------------------------------------

# Hough line minimum length (in the original full-resolution frame).
# Bumped from 200 → 400 to reject grass-texture short edges that
# otherwise out-score the long structural edges (pavement boundary,
# hill horizon) on the wide-angle stairs scene. Tele datasets with
# shorter structural features (e.g. 2025-07-09 sign-post pole)
# need a lower setting; CLI flag --min-line-px overrides.
HOUGH_MIN_LINE_PX = 400
# Hough max gap that still merges two collinear segments.
HOUGH_MAX_GAP_PX = 24
# Canny thresholds (on 0..255 luma). Low edge of L=30 catches the
# grass/asphalt and grass/sky boundaries which are moderate contrast.
CANNY_LOW = 30
CANNY_HIGH = 90
# After Hough, segments closer in (rho, theta) than this are merged.
# Bumped to 100 px so the many parallel sub-edges along the
# pavement/grass boundary (paver grout lines etc.) collapse to one.
NMS_RHO_PX = 100.0
NMS_THETA_RAD = math.radians(5.0)
# Spatial-diversity binning: split the frame into N_BIN_X × N_BIN_Y
# cells and keep at most MAX_PER_BIN candidates per cell.
N_BIN_X = 4
N_BIN_Y = 3
MAX_PER_BIN = 2
# ROI shape (long axis along the edge, short axis across).
EDGE_ROI_LEN = 256
EDGE_ROI_WID = 128
# Minimum slant from axis-aligned, in either direction. Without slant
# the ESF has no sub-pixel sampling and the MTF caps at Nyquist.
MIN_SLANT_DEG = 1.0
# Top-K edges to keep after scoring.
DEFAULT_TOP_K = 12
# Reference-MTF50 floor for accepting a candidate edge. Texture and
# soft / partial edges fall well below 0.15 on the Z7 sharp F8 frame.
MTF_REF_FLOOR = 0.20
# Local refinement search radius perpendicular to the edge (px in the
# original image). Handles micro-shifts in edge position between
# replicates (subject motion, JPEG noise, slight rig vibration).
# Kept small (5) so the search can't hop onto a nearby parallel
# feature (e.g. a paver grout line ~10 px from the main boundary).
LOCAL_REFINE_RADIUS = 5
# After refinement, the gradient-peak strength must be at least this
# fraction of the reference strength; otherwise the edge is occluded
# (pedestrian / cyclist / moving cloud) and MTF50 is NaN.
MIN_PEAK_RATIO = 0.40
# Final MTF50 floor — values below this are FFT-bin-noise artefacts
# (the LSF is too noisy to give a meaningful spectrum). Drops the
# 0.02-0.08 cy/px outliers that occasionally survive the refinement
# step and inflate replicate-spread CV.
MTF50_RESULT_FLOOR = 0.10

# ----- edge spec ----------------------------------------------------------

@dataclass
class EdgeSpec:
    """One candidate edge in image coordinates.

    ``angle_rad`` is the orientation of the edge line itself (NOT the
    gradient normal). ``length_px`` is the Hough segment length. Score
    is the product of mean gradient strength and two-sided contrast.
    """
    mid_x: float
    mid_y: float
    angle_rad: float
    length_px: float
    grad_mean: float
    contrast: float
    score: float

    # Reference gradient-peak strength (across-edge ΔI mean over the
    # length-aligned sample line). Filled in by ``discover_edges`` and
    # used at measurement time to detect occluded edges in test frames.
    ref_peak: float = 0.0

    # Optional metadata
    edge_id: Optional[int] = None
    label: Optional[str] = None

    def to_json(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "EdgeSpec":
        return cls(**d)


# ----- discovery ----------------------------------------------------------

def _canny_hough_segments(luma: np.ndarray,
                          min_line_px: int = HOUGH_MIN_LINE_PX) -> np.ndarray:
    """Run Canny + probabilistic Hough on a uint8 luma image. Returns
    an (N, 4) array of segments [x1, y1, x2, y2]."""
    if luma.dtype != np.uint8:
        luma = luma.astype(np.uint8)
    edges = cv2.Canny(luma, CANNY_LOW, CANNY_HIGH, apertureSize=3, L2gradient=True)
    segs = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=math.pi / 720,           # 0.25 deg resolution
        threshold=80,
        minLineLength=min_line_px,
        maxLineGap=HOUGH_MAX_GAP_PX,
    )
    if segs is None:
        return np.empty((0, 4), dtype=np.int32)
    return segs.reshape(-1, 4)


def _segment_to_polar(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    """Return (rho, theta) for the infinite line containing the segment.
    theta is the angle of the line (not the normal); rho is the
    signed perpendicular distance from origin in pixel units."""
    angle = math.atan2(y2 - y1, x2 - x1)
    # Normal direction (perpendicular to segment direction)
    nx = -math.sin(angle)
    ny = math.cos(angle)
    rho = nx * x1 + ny * y1
    # Canonicalise: keep theta in [-pi/2, pi/2)
    if angle >= math.pi / 2:
        angle -= math.pi
        rho = -rho
    elif angle < -math.pi / 2:
        angle += math.pi
        rho = -rho
    return rho, angle


def _nms_merge(segments: list[tuple[float, float, float, float, float]],
               rho_tol: float, theta_tol: float) -> list[tuple[float, float, float, float, float]]:
    """Greedy NMS: keep the longest segment in each (rho, theta) cluster.
    Each input tuple is (rho, theta, x1, y1, x2, y2)? Actually use what
    the caller passes."""
    kept: list[tuple[float, float, float, float, float]] = []
    for seg in segments:
        rho, theta, length, mid_x, mid_y, *rest = seg
        keep = True
        for k_rho, k_theta, *_ in kept:
            d_theta = abs(theta - k_theta)
            d_theta = min(d_theta, math.pi - d_theta)
            if d_theta < theta_tol and abs(rho - k_rho) < rho_tol:
                keep = False
                break
        if keep:
            kept.append(seg)
    return kept


def _gradient_along_normal(luma: np.ndarray, mid_x: float, mid_y: float,
                           angle_rad: float, half_length: int,
                           probe_offset: int = 6) -> tuple[float, float]:
    """Sample brightness on either side of the edge.

    Returns ``(grad_mean, contrast)`` where:
    - ``grad_mean`` = mean absolute brightness gradient across the edge
      (samples along the edge, finite-diff perpendicular).
    - ``contrast`` = mean(|side_a - side_b|), where side_a and side_b
      are sampled along strips parallel to the edge offset by
      ``probe_offset`` px on either side."""
    nx = -math.sin(angle_rad)
    ny = math.cos(angle_rad)
    tx = math.cos(angle_rad)
    ty = math.sin(angle_rad)
    h, w = luma.shape
    s = np.linspace(-half_length, half_length, num=2 * half_length + 1)
    pts_x = mid_x + s * tx
    pts_y = mid_y + s * ty
    a_x = pts_x + probe_offset * nx
    a_y = pts_y + probe_offset * ny
    b_x = pts_x - probe_offset * nx
    b_y = pts_y - probe_offset * ny

    def sample(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        xi = np.clip(np.round(xs).astype(np.int32), 0, w - 1)
        yi = np.clip(np.round(ys).astype(np.int32), 0, h - 1)
        return luma[yi, xi].astype(np.float32)

    a = sample(a_x, a_y)
    b = sample(b_x, b_y)
    contrast = float(np.mean(np.abs(a - b)))
    # Gradient: short finite-difference perpendicular at each midpoint
    p_x = mid_x + s * tx + 1.5 * nx
    p_y = mid_y + s * ty + 1.5 * ny
    m_x = mid_x + s * tx - 1.5 * nx
    m_y = mid_y + s * ty - 1.5 * ny
    grad_mean = float(np.mean(np.abs(sample(p_x, p_y) - sample(m_x, m_y))))
    return grad_mean, contrast


def _is_too_axis_aligned(angle_rad: float) -> bool:
    """Reject edges that are within MIN_SLANT_DEG of horizontal or vertical
    AND axis-aligned (i.e., within the dead zone where the slanted-edge ESF
    can't be sub-pixel sampled)."""
    deg = math.degrees(angle_rad) % 180
    # Distance to nearest axis (0 or 90 or 180)
    d0 = min(deg, 180 - deg)              # to horizontal
    d90 = abs(deg - 90)                   # to vertical
    return min(d0, d90) < MIN_SLANT_DEG


def all_hough_segments_for_debug(luma: np.ndarray,
                                 min_line_px: int = HOUGH_MIN_LINE_PX
                                 ) -> list[tuple[int, int, int, int, float, float]]:
    """Return (x1, y1, x2, y2, length, angle_deg) for every Hough segment
    that passes the minimum-length filter, for debug overlays."""
    segs = _canny_hough_segments(luma, min_line_px=min_line_px)
    out = []
    for x1, y1, x2, y2 in segs:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < min_line_px:
            continue
        _, theta = _segment_to_polar(float(x1), float(y1), float(x2), float(y2))
        out.append((int(x1), int(y1), int(x2), int(y2), float(length),
                    float(math.degrees(theta))))
    return out


def discover_edges(luma: np.ndarray, top_k: int = DEFAULT_TOP_K,
                   roi_len: int = EDGE_ROI_LEN,
                   min_line_px: int = HOUGH_MIN_LINE_PX) -> list[EdgeSpec]:
    """Find candidate edges via Canny+Hough; rank by gradient*contrast."""
    segs = _canny_hough_segments(luma, min_line_px=min_line_px)
    raw: list[tuple] = []
    for x1, y1, x2, y2 in segs:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < min_line_px:
            continue
        rho, theta = _segment_to_polar(float(x1), float(y1), float(x2), float(y2))
        # Use the line angle relative to x-axis in [-pi/2, pi/2)
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        raw.append((rho, theta, length, mid_x, mid_y, x1, y1, x2, y2))

    # NMS by (rho, theta)
    raw.sort(key=lambda r: -r[2])  # sort longest first so longest wins ties
    merged = _nms_merge(raw, rho_tol=NMS_RHO_PX, theta_tol=NMS_THETA_RAD)

    # Score each by gradient*contrast over the segment, with axis-aligned reject
    specs: list[EdgeSpec] = []
    for rho, theta, length, mid_x, mid_y, x1, y1, x2, y2 in merged:
        # The "line angle" we record is the segment direction; reject
        # if too close to perfectly axis-aligned (no slant for ESF).
        if _is_too_axis_aligned(theta):
            continue
        half = min(int(length / 2), roi_len // 2)
        grad_mean, contrast = _gradient_along_normal(luma, mid_x, mid_y, theta, half)
        # Length factor: long, low-contrast structural edges should beat
        # short, high-contrast grass-texture edges for slanted-edge MTF.
        # sqrt(length) gives a gentle reward without saturating.
        score = grad_mean * contrast * math.sqrt(length)
        specs.append(EdgeSpec(
            mid_x=float(mid_x), mid_y=float(mid_y),
            angle_rad=float(theta), length_px=float(length),
            grad_mean=grad_mean, contrast=contrast, score=score,
        ))

    specs.sort(key=lambda s: -s.score)

    # Drop candidates whose MTF50 on the reference falls below
    # MTF_REF_FLOOR. Texture / soft / partial edges produce values
    # near 0.05; clean step edges land at 0.25-0.50 on this Z7 JPEG.
    h, w = luma.shape
    cleaned: list[EdgeSpec] = []
    for s in specs:
        m = mtf50_known_edge(luma, s)
        if math.isnan(m) or m < MTF_REF_FLOOR:
            continue
        cleaned.append(s)

    # Spatial-diversity filter: bin into N_BIN_X × N_BIN_Y cells and
    # keep MAX_PER_BIN candidates per cell (taken in score order).
    bin_w = w / N_BIN_X
    bin_h = h / N_BIN_Y
    per_bin: dict[tuple[int, int], int] = {}
    diverse: list[EdgeSpec] = []
    for s in cleaned:
        bx = min(N_BIN_X - 1, int(s.mid_x / bin_w))
        by = min(N_BIN_Y - 1, int(s.mid_y / bin_h))
        if per_bin.get((bx, by), 0) >= MAX_PER_BIN:
            continue
        per_bin[(bx, by)] = per_bin.get((bx, by), 0) + 1
        diverse.append(s)
        if len(diverse) >= top_k:
            break

    for i, s in enumerate(diverse):
        s.edge_id = i
        # Record the reference gradient-peak strength so test-frame
        # measurements can detect occluded / moved-subject edges.
        _, _, peak = _refine_edge_position(luma, s)
        s.ref_peak = peak
    return diverse


# ----- overlay ------------------------------------------------------------

OVERLAY_MAX_WIDTH = 1800  # downsample overlays to this before saving


def render_overlay(rgb: np.ndarray, specs: list[EdgeSpec],
                   out_path: Path, roi_len: int = EDGE_ROI_LEN,
                   roi_wid: int = EDGE_ROI_WID) -> None:
    """Draw selected edges + their ROIs on the colour image. The
    output is downsampled to OVERLAY_MAX_WIDTH px to keep the file
    git-friendly — visual inspection only needs ~1800 px wide."""
    canvas = rgb.copy()
    h, w = canvas.shape[:2]
    for spec in specs:
        angle = spec.angle_rad
        tx = math.cos(angle); ty = math.sin(angle)
        nx = -math.sin(angle); ny = math.cos(angle)
        half_len = roi_len / 2
        half_wid = roi_wid / 2
        # Edge line endpoints (yellow)
        ex1 = int(spec.mid_x - half_len * tx); ey1 = int(spec.mid_y - half_len * ty)
        ex2 = int(spec.mid_x + half_len * tx); ey2 = int(spec.mid_y + half_len * ty)
        cv2.line(canvas, (ex1, ey1), (ex2, ey2), (255, 255, 0), 3)
        # ROI box (cyan)
        corners = []
        for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
            cx = spec.mid_x + sx * half_len * tx + sy * half_wid * nx
            cy = spec.mid_y + sx * half_len * ty + sy * half_wid * ny
            corners.append((int(cx), int(cy)))
        for i in range(4):
            cv2.line(canvas, corners[i], corners[(i + 1) % 4], (0, 255, 255), 2)
        # Label (red)
        cv2.putText(canvas, f"#{spec.edge_id} {math.degrees(angle):+.1f}°",
                    (int(spec.mid_x) + 8, int(spec.mid_y) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 0, 0), 3)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(canvas)
    if img.width > OVERLAY_MAX_WIDTH:
        new_h = int(round(img.height * OVERLAY_MAX_WIDTH / img.width))
        img = img.resize((OVERLAY_MAX_WIDTH, new_h), Image.LANCZOS)
    img.save(out_path, quality=85)


# ----- MTF50 with known angle --------------------------------------------

def _extract_axis_aligned_roi(luma: np.ndarray, mid_x: float, mid_y: float,
                              angle_rad: float, length: int = EDGE_ROI_LEN,
                              width: int = EDGE_ROI_WID) -> Optional[np.ndarray]:
    """Extract an axis-aligned bounding box around the oriented edge.

    The box has to be big enough to contain the edge segment (length
    along the edge, width across the edge) regardless of orientation,
    so its sides are ``L = |length * cos(θ)| + |width * sin(θ)|`` and
    ``H = |length * sin(θ)| + |width * cos(θ)|``. We pad slightly so
    that pixels well outside the ROI don't get binned. Returns the
    box (as a luma sub-array) plus the (x0, y0) origin in the original
    image — caller needs origin to map ROI coords back to image coords."""
    h, w = luma.shape
    cos_a = math.cos(angle_rad); sin_a = math.sin(angle_rad)
    box_w = int(math.ceil(abs(length * cos_a) + abs(width * sin_a))) + 4
    box_h = int(math.ceil(abs(length * sin_a) + abs(width * cos_a))) + 4
    x0 = int(round(mid_x - box_w / 2))
    y0 = int(round(mid_y - box_h / 2))
    if x0 < 0 or y0 < 0 or x0 + box_w > w or y0 + box_h > h:
        return None
    return luma[y0:y0 + box_h, x0:x0 + box_w], (x0, y0)


def _refine_edge_position(luma: np.ndarray, spec: EdgeSpec,
                          length: int = EDGE_ROI_LEN,
                          width: int = EDGE_ROI_WID,
                          search_radius: int = LOCAL_REFINE_RADIUS
                          ) -> tuple[float, float, float]:
    """Search ±search_radius px perpendicular to the edge for the
    gradient-energy maximum; return (new_mid_x, new_mid_y, peak_strength).

    Sub-pixel refinement is done by a parabolic fit to the 3 strongest
    perpendicular offsets. Peak strength is the average across-edge
    gradient at the refined position, which lets the caller reject
    occluded edges (cyclist crossing) where the local gradient
    collapses.
    """
    h, w = luma.shape
    angle = spec.angle_rad
    nx = -math.sin(angle); ny = math.cos(angle)
    tx = math.cos(angle); ty = math.sin(angle)
    half_len = min(length / 2, spec.length_px / 2)
    n_samples = max(32, int(half_len))
    s = np.linspace(-half_len, half_len, num=2 * n_samples + 1)
    pts_t_x = spec.mid_x + s * tx
    pts_t_y = spec.mid_y + s * ty

    offsets = np.arange(-search_radius, search_radius + 1)
    energies = np.zeros_like(offsets, dtype=np.float64)
    for i, off in enumerate(offsets):
        # Sample brightness profile across the edge at this offset
        a_x = pts_t_x + (off + 1.5) * nx
        a_y = pts_t_y + (off + 1.5) * ny
        b_x = pts_t_x + (off - 1.5) * nx
        b_y = pts_t_y + (off - 1.5) * ny
        ax = np.clip(np.round(a_x).astype(np.int32), 0, w - 1)
        ay = np.clip(np.round(a_y).astype(np.int32), 0, h - 1)
        bx = np.clip(np.round(b_x).astype(np.int32), 0, w - 1)
        by = np.clip(np.round(b_y).astype(np.int32), 0, h - 1)
        diff = luma[ay, ax].astype(np.float32) - luma[by, bx].astype(np.float32)
        energies[i] = float(np.mean(np.abs(diff)))

    i_max = int(np.argmax(energies))
    peak_strength = float(energies[i_max])
    # Parabolic sub-pixel refinement
    if 0 < i_max < len(offsets) - 1:
        y0, y1, y2 = energies[i_max - 1], energies[i_max], energies[i_max + 1]
        denom = (y0 - 2 * y1 + y2)
        if denom != 0:
            sub = 0.5 * (y0 - y2) / denom
        else:
            sub = 0.0
    else:
        sub = 0.0
    refined_off = float(offsets[i_max]) + sub
    return (spec.mid_x + refined_off * nx,
            spec.mid_y + refined_off * ny,
            peak_strength)


def measure_edge_metrics(luma: np.ndarray, spec: EdgeSpec,
                         length: int = EDGE_ROI_LEN,
                         width: int = EDGE_ROI_WID,
                         refine: bool = True,
                         min_peak: float = 0.0) -> dict:
    """Compute three complementary edge-sharpness metrics on a single
    ROI. Returns a dict with::

        {
            "mtf50":          MTF50 frequency (cy/sensor-pixel),
            "mtf_at_nyquist": MTF value AT 0.5 cy/sensor-pixel,
            "mtf10_freq":     MTF10 frequency (cy/sensor-pixel),
        }

    Why three?

    - **MTF50** (frequency where MTF crosses 0.5) is the standard
      reading. It saturates at Nyquist (≈ 0.49 cy/px) for the sharpest
      edges; sharper edges all read 0.49 and become indistinguishable.
    - **MTF@Nyquist** (the actual MTF value AT 0.5 cy/px) keeps
      discriminating in the saturated regime — a soft edge reads
      ~0.10, a sharp Z7 wide-angle edge reads 0.5–0.7+.
    - **MTF10_freq** (frequency where MTF drops to 0.1) captures the
      high-frequency tail. For very sharp edges it exceeds Nyquist
      and is clipped at 0.5 (cap); for typical edges it lies past
      MTF50 and resolves which lens has more aliased-but-real
      detail.

    All three are reported in the same units (cy per ORIGINAL image
    pixel) and follow the same NaN policy: NaN when the edge can't be
    measured (occluded, low-contrast, ROI escapes the image).
    """
    nan_result = dict(mtf50=float("nan"),
                      mtf_at_nyquist=float("nan"),
                      mtf10_freq=float("nan"))
    built = _build_esf(luma, spec, length=length, width=width,
                       refine=refine, min_peak=min_peak)
    if built is None:
        return nan_result
    esf, bin_size = built
    return _esf_to_metrics(esf, bin_size, **LSF_PROFILE)


def _build_esf(luma: np.ndarray, spec: EdgeSpec,
               length: int = EDGE_ROI_LEN, width: int = EDGE_ROI_WID,
               refine: bool = True,
               min_peak: float = 0.0) -> Optional[tuple]:
    """Extract + supersample the edge-spread function for one ROI.

    Returns ``(esf, bin_size)`` (esf already Gaussian-smoothed, the same
    array the original code fed to the LSF stage) or ``None`` when the
    edge can't be measured. Factored out so the over-read POC can run
    every LSF-handling variant on one shared ESF per edge.
    """
    if refine:
        mx, my, peak = _refine_edge_position(luma, spec, length=length,
                                             width=width)
        if min_peak > 0 and peak < min_peak:
            return None
    else:
        mx, my = spec.mid_x, spec.mid_y
    out = _extract_axis_aligned_roi(luma, mx, my, spec.angle_rad,
                                    length=length, width=width)
    if out is None:
        return None
    roi, (x0, y0) = out
    angle = spec.angle_rad
    cos_a = math.cos(angle); sin_a = math.sin(angle)
    nx = -sin_a; ny = cos_a
    tx = cos_a; ty = sin_a

    h, w = roi.shape
    yy, xx = np.indices((h, w))
    # Coords relative to the (possibly refined) edge midpoint, in
    # original image pixels.
    dx = (x0 + xx) - mx
    dy = (y0 + yy) - my
    # Distance along edge normal (across-edge)
    dist_n = dx * nx + dy * ny
    # Distance along edge tangent (along-edge)
    dist_t = dx * tx + dy * ty
    # Mask: keep pixels within length/2 along edge and width/2 across
    mask = (np.abs(dist_t) <= length / 2) & (np.abs(dist_n) <= width / 2)
    if mask.sum() < length * 4:
        return None

    bin_size = 0.25
    d = dist_n[mask].ravel()
    v = roi[mask].ravel()
    d_min = float(d.min()); d_max = float(d.max())
    n_bins = int(math.ceil((d_max - d_min) / bin_size)) + 1
    if n_bins < 32:
        return None
    bin_idx = np.clip(((d - d_min) / bin_size).astype(np.int32), 0, n_bins - 1)
    esf_sum = np.bincount(bin_idx, v.astype(np.float64), minlength=n_bins)
    esf_count = np.bincount(bin_idx, minlength=n_bins)
    esf = esf_sum / np.maximum(esf_count, 1)
    valid = esf_count > 2
    if valid.sum() < 32:
        return None
    first = int(np.argmax(valid))
    last = n_bins - 1 - int(np.argmax(valid[::-1]))
    esf = esf[first:last + 1]
    if len(esf) < 32:
        return None
    esf = ndi.gaussian_filter1d(esf, sigma=1.0)
    return esf, bin_size


# ---------------------------------------------------------------------------
# LSF -> MTF stage (factored out 2026-06-29 so the over-read-fix POC and
# production share one code path). The DEFAULT arguments reproduce the
# original behaviour byte-for-byte; the keyword options drive the POC
# variants (see scripts/poc_lsf_overread_fix.py).
# ---------------------------------------------------------------------------

# Chosen LSF-handling profile (set 2026-06-29 by the over-read POC
# `poc_lsf_overread_fix.py`; see §5.6e of LONGDIST_HANDOVER.md).
# `centroid_hann` windows the LSF with a Hann centred on its centroid and
# renormalises by the DC bin — the standard ISO-12233 fix for the
# asymmetric-noisy-tail over-read. On the 2026-06-28 brick RAW (diffraction
# -ceiling validated) it moves the f/16 median MTF50 from +12 % over the
# ceiling onto it, ~halves the over-ceiling fraction, drops the MTF@Nyquist
# tail (p95 0.44->0.33, Nyq>1 ~0 %), and ~triples the usable edge count
# (lower NaN rate). It beat fixed-width Tukey windows (which clip the lobe
# when narrow), `mirror` (no gain on single step edges), and a
# derivative/sinc correction (negligible). `window="endtaper"` is the
# pre-fix behaviour, kept for the POC.
LSF_PROFILE = dict(window="centroid_hann")


def _mtf_readout(lsf: np.ndarray, bin_size: float, *,
                 deriv_correct: bool = False,
                 renorm_dc: bool = False) -> Optional[dict]:
    """|FFT(LSF)| -> (mtf50, mtf_at_nyquist, mtf10_freq) in cy/orig-px.

    Returns None on a pathological spectrum (caller maps to NaN).
    """
    n = len(lsf)
    if n < 32:
        return None
    mtf = np.abs(np.fft.fft(lsf))
    # Smooth the bin-by-bin MTF (oscillates from finite-ROI windowing +
    # noise) over ~1/100 of the spectrum so the readings track the
    # envelope, not spurious bin spikes.
    mtf = ndi.gaussian_filter1d(mtf, sigma=max(2.0, len(mtf) / 200))
    freqs = np.arange(n) / (n * bin_size)    # cy per original-image pixel
    half = n // 2
    f = freqs[:half]; m = mtf[:half]
    if deriv_correct:
        # Undo the forward-difference (np.diff) magnitude response
        # |1-e^{-iω}| / ω = sinc(f·bin_size); tiny (<3 %) at 4× oversample.
        sinc = np.ones_like(f)
        nz = f > 0
        x = np.pi * f[nz] * bin_size
        sinc[nz] = np.sin(x) / x
        m = m / np.maximum(sinc, 1e-6)
    if renorm_dc:
        # MTF(0)=1 by definition. Correct when a centroid window has
        # truncated part of the LSF lobe so the ESF-contrast scaling no
        # longer makes m[0]≈1.
        if m[0] <= 0:
            return None
        m = m / m[0]
    # Cap at sensor Nyquist (0.5 cy/px). Beyond it the supersampled ESF
    # mixes real lens-MTF with aliased content (Z7 has no OLPF) and the
    # separation is ill-defined.
    cap = np.searchsorted(f, 0.5)
    f = f[:max(cap, 4)]; m = m[:len(f)]
    if len(f) == 0:
        return None
    # Sanity: reject the worst pathological LSFs (m[0] far from 1, or a
    # spectrum bump well past unity).
    if float(m[0]) < 0.3 or float(m.max()) > 2.5:
        return None

    def _cross(level: float, first: bool = True) -> float:
        below = np.where(m < level)[0]
        if len(below) == 0:
            return float(f[-1])   # stays above `level` through the cap
        i = int(below[0])
        if i == 0:
            return float("nan")
        m_prev, m_curr = float(m[i - 1]), float(m[i])
        if m_prev == m_curr:
            return float(f[i])
        frac = (m_prev - level) / (m_prev - m_curr)
        return float(f[i - 1] + frac * (f[i] - f[i - 1]))

    mtf50 = _cross(0.5)
    if mtf50 == mtf50 and mtf50 < MTF50_RESULT_FLOOR:
        mtf50 = float("nan")

    nyq = 0.5
    if f[-1] >= nyq:
        idx = int(np.searchsorted(f, nyq))
        if idx == 0:
            mtf_at_nyq = float(m[0])
        elif idx >= len(f):
            mtf_at_nyq = float(m[-1])
        else:
            f0, f1 = float(f[idx - 1]), float(f[idx])
            m0, m1 = float(m[idx - 1]), float(m[idx])
            frac = (nyq - f0) / (f1 - f0) if f1 != f0 else 0.0
            mtf_at_nyq = max(0.0, m0 + frac * (m1 - m0))
    else:
        mtf_at_nyq = float(m[-1])

    mtf10 = _cross(0.1)
    return dict(mtf50=mtf50, mtf_at_nyquist=mtf_at_nyq, mtf10_freq=mtf10)


def _esf_to_metrics(esf: np.ndarray, bin_size: float = 0.25, *,
                    window: str = "endtaper",
                    taper_frac: float = 0.05,
                    half_window_px: Optional[float] = None,
                    deriv_correct: bool = False,
                    mirror: Optional[str] = None) -> dict:
    """Smoothed ESF -> three edge-MTF metrics.

    ``window="endtaper"`` (+ all other defaults) is the original code:
    contrast-normalise the LSF, taper only the ROI ends (5 % each side),
    FFT, read MTF50 / MTF@Nyquist / MTF10. The other ``window`` values
    centre a symmetric window on the LSF centroid (the over-read fix:
    asymmetric noisy LSF tails are what inflate the high-frequency tail
    and push MTF past the diffraction ceiling). ``mirror`` instead
    splits the LSF at its centroid, reflects each half into a symmetric
    LSF, and combines the two readouts ("min" = conservative cleaner
    half, the single-edge analogue of macro ``lsf_mtf50(combine='min')``).
    """
    nan_result = dict(mtf50=float("nan"),
                      mtf_at_nyquist=float("nan"),
                      mtf10_freq=float("nan"))
    # Normalise the LSF by the ESF endpoint contrast (the brightness
    # step the edge actually traverses) so mtf[0] = 1 for a full,
    # centred LSF without needing a window that distorts sum(LSF).
    n_endpt = max(4, len(esf) // 10)
    low = float(np.median(esf[:n_endpt]))
    high = float(np.median(esf[-n_endpt:]))
    contrast = abs(high - low)
    if contrast < 1.0:
        return nan_result
    lsf = np.diff(esf) / contrast
    n = len(lsf)
    if n < 32:
        return nan_result

    if window == "endtaper":
        # Light Tukey-style taper only at the very ends (5 % each side).
        taper = np.ones(n)
        n_taper = max(2, n // 20)
        ramp = 0.5 * (1 - np.cos(np.pi * np.arange(n_taper) / n_taper))
        taper[:n_taper] = ramp
        taper[-n_taper:] = ramp[::-1]
        out = _mtf_readout(lsf * taper, bin_size,
                           deriv_correct=deriv_correct, renorm_dc=False)
        return out if out is not None else nan_result

    # --- centroid-based handling ------------------------------------
    sign = 1.0 if lsf.sum() >= 0 else -1.0
    lsf_o = lsf * sign                       # main lobe positive
    w = np.clip(lsf_o, 0.0, None)
    if w.sum() <= 0:
        return nan_result
    idx = np.arange(n, dtype=np.float64)
    centroid = float((idx * w).sum() / w.sum())

    if mirror is not None:
        c = int(round(centroid))
        c = min(max(c, 1), n - 2)
        left = lsf_o[:c + 1]
        left_sym = np.concatenate([left, left[-2::-1]])
        right = lsf_o[c:]
        right_sym = np.concatenate([right[:0:-1], right])
        outs = []
        for half_lsf in (left_sym, right_sym):
            r = _mtf_readout(half_lsf, bin_size,
                             deriv_correct=deriv_correct, renorm_dc=True)
            if r is not None:
                outs.append(r)
        if not outs:
            return nan_result
        comb = np.min if mirror == "min" else np.mean
        keys = ("mtf50", "mtf_at_nyquist", "mtf10_freq")
        return {k: float(comb([o[k] for o in outs if o[k] == o[k]]))
                if any(o[k] == o[k] for o in outs) else float("nan")
                for k in keys}

    # Single symmetric window centred on the centroid.
    if half_window_px is None:
        hw = max(centroid, n - 1 - centroid)
    else:
        hw = half_window_px / bin_size
    hw = max(hw, 4.0)
    dist = np.abs(idx - centroid)
    if window == "centroid_hann":
        win = np.where(dist <= hw, 0.5 * (1 + np.cos(np.pi * dist / hw)), 0.0)
    elif window == "centroid_hamming":
        win = np.where(dist <= hw, 0.54 + 0.46 * np.cos(np.pi * dist / hw), 0.0)
    elif window == "centroid_tukey":
        flat = (1.0 - taper_frac) * hw
        denom = max(hw - flat, 1e-9)
        win = np.where(dist <= flat, 1.0, 0.0)
        ramp_region = (dist > flat) & (dist <= hw)
        win = np.where(ramp_region,
                       0.5 * (1 + np.cos(np.pi * (dist - flat) / denom)), win)
    else:
        raise ValueError(f"unknown window {window!r}")
    out = _mtf_readout(lsf * win, bin_size,
                       deriv_correct=deriv_correct, renorm_dc=True)
    return out if out is not None else nan_result


def mtf50_known_edge(luma: np.ndarray, spec: EdgeSpec,
                     length: int = EDGE_ROI_LEN,
                     width: int = EDGE_ROI_WID,
                     refine: bool = True,
                     min_peak: float = 0.0) -> float:
    """Backward-compatible scalar API returning just MTF50."""
    return measure_edge_metrics(luma, spec, length=length, width=width,
                                refine=refine, min_peak=min_peak)["mtf50"]


# ----- IO -----------------------------------------------------------------

def load_luma(path: Path) -> np.ndarray:
    """Luma plane as float32 in [0, 255]."""
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def specs_to_json(specs: list[EdgeSpec]) -> str:
    return json.dumps([s.to_json() for s in specs], indent=2)


def specs_from_json(text: str) -> list[EdgeSpec]:
    return [EdgeSpec.from_json(d) for d in json.loads(text)]


# ----- main ---------------------------------------------------------------

def cmd_discover(args: argparse.Namespace) -> int:
    ref = Path(args.reference)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    luma = load_luma(ref)
    print(f"[discover] reference {ref.name} shape={luma.shape} "
          f"min_line_px={args.min_line_px}", flush=True)
    if args.debug_all_segments:
        rgb = load_rgb(ref)
        canvas = rgb.copy()
        for x1, y1, x2, y2, length, ang in all_hough_segments_for_debug(
                luma, min_line_px=args.min_line_px):
            cv2.line(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
        debug_path = out_dir / "all_hough_segments.jpg"
        Image.fromarray(canvas).save(debug_path, quality=85)
        print(f"[discover] all hough segments → {debug_path}")
    specs = discover_edges(luma, top_k=args.top_k,
                           min_line_px=args.min_line_px)
    print(f"[discover] found {len(specs)} edges (top-{args.top_k})", flush=True)
    for s in specs:
        print(f"  #{s.edge_id} mid=({s.mid_x:.0f},{s.mid_y:.0f}) "
              f"angle={math.degrees(s.angle_rad):+.1f}° len={s.length_px:.0f} "
              f"grad={s.grad_mean:.1f} contrast={s.contrast:.1f} score={s.score:.0f}")
    (out_dir / "edges.json").write_text(specs_to_json(specs))
    # MTF50 sanity check on the reference itself
    mtfs = [mtf50_known_edge(luma, s) for s in specs]
    print("[discover] reference MTF50 per edge (cy/px):")
    for s, m in zip(specs, mtfs):
        print(f"  #{s.edge_id}: {m if not math.isnan(m) else float('nan'):.3f}")
    rgb = load_rgb(ref)
    overlay_path = out_dir / "overlay.jpg"
    render_overlay(rgb, specs, overlay_path)
    print(f"[discover] overlay → {overlay_path}")
    return 0


# ----- dataset mode -------------------------------------------------------

# Aperture preference order for picking a "sharp reference" frame per
# (lens, FL). F8 is the canonical optimum on FX glass; lower-aperture
# falls back to F5.6 → F11 → F4 etc.
REF_APERTURE_ORDER = ["F8", "F11", "F5.6", "F4", "F2.8", "F16", "F22"]


def _pick_reference_jpeg(configs_for_lens_fl: list["pla.Config"]) -> Optional[Path]:
    """Pick one sharp-aperture JPEG to discover edges on. Prefer F8;
    fall back through REF_APERTURE_ORDER. Within the chosen aperture
    pick the largest-file replicate (sharpest by file-size proxy)."""
    by_aper = {c.aperture: c for c in configs_for_lens_fl}
    for aper in REF_APERTURE_ORDER:
        if aper in by_aper:
            cfg = by_aper[aper]
            if not cfg.jpegs:
                continue
            return max(cfg.jpegs, key=lambda p: p.stat().st_size)
    # No preferred aperture found; use whatever's available
    for c in configs_for_lens_fl:
        if c.jpegs:
            return max(c.jpegs, key=lambda p: p.stat().st_size)
    return None


def _safe_slug(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)


def cmd_dataset(args: argparse.Namespace) -> int:
    """Walk a dataset, per (lens, FL): discover edges on a sharp F8
    reference, measure MTF50 on every replicate-aperture frame."""
    key = args.dataset
    if key not in pla.DATASETS:
        print(f"unknown dataset {key!r}; choose from {list(pla.DATASETS)}",
              file=sys.stderr)
        return 2
    cfg = pla.DATASETS[key]
    out_root = Path(__file__).parent / (Path(__file__).stem + "_out")
    out_dir = out_root / key
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[dataset] {key} → {out_dir}", flush=True)

    configs = pla.discover(cfg["root"], cfg["date"], cfg["lens_filter"])
    print(f"[dataset] discovered {len(configs)} configs", flush=True)

    # Group by (lens_dir, focal_mm)
    by_lens_fl: dict[tuple[str, float], list[pla.Config]] = {}
    for c in configs:
        by_lens_fl.setdefault((c.lens_dir, c.focal_mm), []).append(c)

    rows: list[dict] = []
    items = sorted(by_lens_fl.items())
    if args.limit:
        items = items[:args.limit]
    for (lens, fl), group in items:
        slug = f"{_safe_slug(lens)}__{fl:.1f}mm"
        sub_out = out_dir / slug
        sub_out.mkdir(parents=True, exist_ok=True)
        ref_path = _pick_reference_jpeg(group)
        if ref_path is None:
            print(f"[dataset] {slug}: no reference JPEG, skip", flush=True)
            continue
        print(f"[dataset] {slug}: reference={ref_path.name}", flush=True)

        ref_luma = load_luma(ref_path)
        specs = discover_edges(ref_luma, top_k=args.top_k,
                               min_line_px=args.min_line_px)
        if not specs:
            print(f"[dataset] {slug}: no usable edges found, skip", flush=True)
            continue
        (sub_out / "edges.json").write_text(specs_to_json(specs))
        render_overlay(load_rgb(ref_path), specs, sub_out / "overlay.jpg")
        for s in specs:
            metrics = measure_edge_metrics(ref_luma, s)
            rows.append(dict(
                date=cfg["date"], camera=cfg["camera"], lens_dir=lens,
                focal_mm=fl, aperture="REF", aperture_f=float("nan"),
                jpeg=ref_path.name, edge_id=s.edge_id,
                edge_mid_x=s.mid_x, edge_mid_y=s.mid_y,
                edge_angle_deg=math.degrees(s.angle_rad),
                edge_length_px=s.length_px, edge_score=s.score,
                mtf50=metrics["mtf50"],
                mtf_at_nyquist=metrics["mtf_at_nyquist"],
                mtf10_freq=metrics["mtf10_freq"],
                role="reference",
            ))

        # Measure on every replicate at every aperture (optionally strided —
        # focus-shift step-1 stacks are dense, so every Nth frame still
        # brackets each edge's peak within ~1 step).
        stride = max(1, getattr(args, "stride", 1))
        for c in sorted(group, key=lambda c: c.aperture_f):
            for jp in c.jpegs[::stride]:
                luma = load_luma(jp)
                for s in specs:
                    metrics = measure_edge_metrics(
                        luma, s, min_peak=s.ref_peak * MIN_PEAK_RATIO)
                    rows.append(dict(
                        date=cfg["date"], camera=cfg["camera"], lens_dir=lens,
                        focal_mm=fl, aperture=c.aperture, aperture_f=c.aperture_f,
                        jpeg=jp.name, edge_id=s.edge_id,
                        edge_mid_x=s.mid_x, edge_mid_y=s.mid_y,
                        edge_angle_deg=math.degrees(s.angle_rad),
                        edge_length_px=s.length_px, edge_score=s.score,
                        mtf50=metrics["mtf50"],
                        mtf_at_nyquist=metrics["mtf_at_nyquist"],
                        mtf10_freq=metrics["mtf10_freq"],
                        role="test",
                    ))
            print(f"[dataset]   {slug} aper {c.aperture}: {len(c.jpegs)} reps",
                  flush=True)

    csv_path = out_dir / "per_measurement.csv"
    if rows:
        import csv as _csv
        with csv_path.open("w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"[dataset] wrote {csv_path} ({len(rows)} rows)")
    else:
        print("[dataset] no rows to write", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("discover", help="Find top-K edges on a reference image")
    sp.add_argument("--reference", required=True)
    sp.add_argument("--out-dir", required=True)
    sp.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    sp.add_argument("--min-line-px", type=int, default=HOUGH_MIN_LINE_PX,
                    help="Override Hough min line length. Default 400 "
                    "(wide-angle stairs); use ~150 for tele datasets "
                    "with shorter structural features.")
    sp.add_argument("--debug-all-segments", action="store_true",
                    help="Also dump all surviving Hough segments overlay.")
    sp.set_defaults(fn=cmd_discover)

    sp = sub.add_parser("dataset", help="Walk a dataset; per (lens, FL) "
                        "discover edges and measure MTF50 across replicates.")
    sp.add_argument("dataset", choices=list(pla.DATASETS),
                    help="Dataset key from poc_longdist_algorithms.py")
    sp.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    sp.add_argument("--min-line-px", type=int, default=HOUGH_MIN_LINE_PX,
                    help="Override Hough min line length (default 400).")
    sp.add_argument("--limit", type=int, default=0,
                    help="Process only the first N (lens, FL) groups; 0 = all.")
    sp.add_argument("--stride", type=int, default=1,
                    help="Measure every Nth frame per aperture (default 1 = all). "
                    "Use 3 for dense focus-shift stacks to ~3x speed up with "
                    "negligible peak-focus loss.")
    sp.set_defaults(fn=cmd_dataset)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
