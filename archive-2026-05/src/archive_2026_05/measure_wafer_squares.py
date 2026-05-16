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
    binary_opening, gaussian_filter, rotate as ndi_rotate, sobel,
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
) -> np.ndarray:
    """Per-column count of pixels that are part of a vertical edge
    segment ≥ ``min_line_length_frac`` × image height. Sub-features
    (short edges) are filtered out by the morphological opening.
    """
    h, w = img.shape
    edges = np.abs(sobel(img, axis=1))
    thr = np.percentile(edges, edge_threshold_pct)
    edge_mask = edges > thr
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


def measure(
    path: Path, *,
    low_cut_sigma: float = 40.0, high_cut_sigma: float = 1.5,
    edge_threshold_pct: float = 80.0,
    min_line_length_frac: float = 0.40,
    p_min: int = 40, p_max: int = 400,
) -> WaferMeasurement:
    """Run the full pipeline on a single image; return measurement."""
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
        path = sharpest_f11_centre_crop(config_dir)
        if path is None:
            continue
        m = measure(path)
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
