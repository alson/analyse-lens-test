"""Algorithm comparison framework for the long-distance wide-angle scenes
(2026-01-24 / 2026-01-26 — sloped-stair scene per SHARPNESS_METRICS_LONGDIST.md).

Four sharpness algorithms compared on the same tile selections, with
movement (cyclist / pedestrian) rejection via cross-replicate consensus.

Algorithms
----------
1. ``radial_cutoff``: normalised radial-spectrum cutoff in cy/sensor-pixel
   (same family as the telephoto primary). Frequency-domain, threshold-based.
2. ``mtf50_slanted_edge``: ISO 12233-style slanted-edge MTF50 in cy/sensor-px.
   Edge-based, physical units. Returns NaN where no strong slanted edge is
   present (e.g., uniform sky tile).
3. ``vol`` (variance of Laplacian): gradient-domain, classic. Scene-amplitude-
   biased but for matched-scene comparison the bias cancels.
4. ``brenner`` (Brenner gradient): squared pixel differences at lag 2. Different
   gradient-domain formulation; serves as a same-family agreement check vs VOL.

Cross-replicate consensus tile selection
----------------------------------------
For each (date, lens, FL, aperture, search-box):
1. Per replicate, compute the gradient-energy map across candidate 256x256 tile
   positions.
2. Take the MEDIAN gradient-energy across replicates at each candidate position.
3. Pick the candidate position with the highest median — this is the most
   consistently-high-gradient feature across the burst (static structure:
   wall horizon, lamp post, stair tread, zigzag railing). A cyclist's
   high-gradient content appears in only one replicate, so the median
   suppresses it.
4. Measure all four algorithms on each replicate's tile at that consensus
   position. Report top / median / min / top_vs_median / range_pct per
   algorithm per cell.

Output dir: poc_longdist_algorithms_out/<dataset_key>/
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.stats import spearmanr, pearsonr

OUT_BASE = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT_BASE.mkdir(exist_ok=True)

# Sensor pixel pitches (mm). Only matters for converting cy/sensor-px to
# cy/mm-sensor; rankings within a camera use cy/sensor-px which is
# pitch-agnostic. Cross-camera comparisons aren't apples-to-apples and
# are noted in the result docs.
Z7_PIXEL_PITCH_MM = 4.35e-3
D7200_PIXEL_PITCH_MM = 3.91e-3

TILE = 256
SEARCH_STEP = 64
FIELD_POSITIONS = [0.18, 0.34, 0.50, 0.66, 0.82]
FIELD_BOX_W_FRAC = 0.15
FIELD_BOX_H_FRAC = 0.20

REF_BAND = (0.01, 0.10)        # for radial_cutoff in cy/sensor-px
CUTOFF_THRESHOLD = 0.05
# Gaussian smoothing of the normalised radial spectrum before locating
# the cutoff. Suppresses bin-to-bin oscillations in the mid-frequency
# range that otherwise let the first-crossing logic fire on noise dips.
# Sigma is in radial-bin units (1 bin = 1/n cy/px ≈ 0.0039 for n=256).
RADIAL_SMOOTH_SIGMA = 2.0


# --------------------------------------------------------------------- algorithms

def radial_spectrum(tile: np.ndarray) -> np.ndarray:
    tile = tile - tile.mean()
    n = tile.shape[0]
    w = np.hanning(n)
    tile = tile * np.outer(w, w)
    F = np.fft.fftshift(np.fft.fft2(tile))
    P = (F.real ** 2 + F.imag ** 2)
    cy, cx = n // 2, n // 2
    y, x = np.indices(P.shape)
    r = np.sqrt((y - cy) ** 2 + (x - cx) ** 2).astype(np.int32)
    rmax = n // 2
    radial = np.bincount(r.ravel(), P.ravel(), minlength=rmax + 1)[: rmax + 1]
    counts = np.bincount(r.ravel(), minlength=rmax + 1)[: rmax + 1]
    counts = np.maximum(counts, 1)
    return radial / counts


def alg_radial_cutoff(tile: np.ndarray) -> float:
    """Normalised radial-spectrum cutoff in cy/sensor-pixel.

    Three layers of robustness compared to the original implementation:

    1. **Lower ref band** (§5.3): ``REF_BAND = (0.01, 0.10)`` instead
       of the original (0.01, 0.20). On softer datasets (D7200
       wide-angle, Z7 wide with soft corners) the spectrum drops below
       the threshold inside the old ref band, so the metric saturated
       at 0.2031 cy/px. Lowering REF_BAND[1] gives those datasets
       headroom while still capturing the low-frequency reference.
    2. **Gaussian smoothing** (§5.3): the radial spectrum has
       bin-to-bin oscillations (visible at sigma=0). Smoothing with
       sigma=2 bins removes spurious noise dips that would otherwise
       cause the first-crossing logic to fire at the wrong frequency.
    3. **Last-crossing + linear sub-bin interp** (§5.2 + §5.3):
       finds the highest frequency where the smoothed spectrum is
       still above ``CUTOFF_THRESHOLD = 0.05``, then linearly
       interpolates to where it would cross. More robust than
       first-crossing on noisy spectra and gives sub-bin precision.

    Returns NaN if the entire post-ref-band spectrum is already
    below threshold (extremely soft tile — usually means no usable
    sharpness signal at all).
    """
    spec = radial_spectrum(tile)
    n = tile.shape[0]
    freq = np.arange(n // 2 + 1) / n
    band = (freq >= REF_BAND[0]) & (freq <= REF_BAND[1])
    if band.sum() == 0:
        return float("nan")
    ref = spec[band].mean()
    if ref <= 0:
        return float("nan")
    norm = spec / ref
    if RADIAL_SMOOTH_SIGMA > 0:
        norm = ndi.gaussian_filter1d(norm, sigma=RADIAL_SMOOTH_SIGMA)
    start = int(np.argmax(freq > REF_BAND[1]))
    if start == 0:
        start = 1
    above = np.where(norm[start:] > CUTOFF_THRESHOLD)[0]
    if len(above) == 0:
        return float("nan")
    i = start + int(above[-1])
    # Crossing is between bin i (above) and bin i+1 (below)
    if i + 1 >= len(norm):
        return float(freq[i])
    v_prev = float(norm[i])
    v_curr = float(norm[i + 1])
    if v_prev != v_curr and v_prev > CUTOFF_THRESHOLD:
        frac = (v_prev - CUTOFF_THRESHOLD) / (v_prev - v_curr)
        return float(freq[i] + frac * (freq[i + 1] - freq[i]))
    return float(freq[i])


def alg_vol(tile: np.ndarray) -> float:
    """Variance of Laplacian (3x3 kernel)."""
    return float(ndi.laplace(tile).var())


def alg_brenner(tile: np.ndarray) -> float:
    """Brenner gradient: squared pixel differences at lag 2."""
    dx = tile[:, 2:] - tile[:, :-2]
    dy = tile[2:, :] - tile[:-2, :]
    return float((dx * dx).mean() + (dy * dy).mean())


def alg_mtf50_slanted_edge(tile: np.ndarray) -> float:
    """ISO-12233-style slanted-edge MTF50 in cy/sensor-pixel.

    Strategy: detect the dominant gradient direction, project all pixels
    onto a line perpendicular to that direction to build a super-sampled
    ESF, differentiate to LSF, FFT to MTF, find the lowest frequency
    where MTF drops to 0.5. Returns NaN if there's no strong dominant
    edge direction in the tile (uniform region, isotropic texture).
    """
    # Gradient
    gy = ndi.sobel(tile, axis=0)
    gx = ndi.sobel(tile, axis=1)
    mag = np.hypot(gx, gy)
    if mag.max() < 1.0:
        return float("nan")
    # Pick the top X% of gradient pixels as edge-belonging
    threshold = mag.max() * 0.3
    edge_mask = mag > threshold
    n_edge = int(edge_mask.sum())
    if n_edge < 100:
        return float("nan")
    # Dominant gradient direction (use double-angle averaging for robustness)
    angles = np.arctan2(gy[edge_mask], gx[edge_mask])
    sin2 = np.mean(np.sin(2 * angles))
    cos2 = np.mean(np.cos(2 * angles))
    # Concentration: low → no dominant direction → isotropic, skip
    concentration = float(np.hypot(sin2, cos2))
    if concentration < 0.30:
        return float("nan")
    dom_angle = 0.5 * np.arctan2(sin2, cos2)
    # Project all pixel coords onto the gradient direction
    h, w = tile.shape
    yy, xx = np.indices((h, w))
    dist = (xx - w / 2) * np.cos(dom_angle) + (yy - h / 2) * np.sin(dom_angle)
    # Bin pixels into a super-sampled grid (0.25 px bins)
    bin_size = 0.25
    d_min, d_max = float(dist.min()), float(dist.max())
    n_bins = int(np.ceil((d_max - d_min) / bin_size)) + 1
    if n_bins < 16:
        return float("nan")
    bin_idx = ((dist - d_min) / bin_size).astype(np.int32)
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    esf_sum = np.bincount(bin_idx.ravel(), tile.ravel(), minlength=n_bins)
    esf_count = np.bincount(bin_idx.ravel(), minlength=n_bins)
    counts = np.maximum(esf_count, 1)
    esf = esf_sum / counts
    # Drop bins with insufficient sampling
    valid = esf_count > 2
    if valid.sum() < 16:
        return float("nan")
    # Use only the contiguous valid range
    first = int(np.argmax(valid))
    last = n_bins - 1 - int(np.argmax(valid[::-1]))
    esf = esf[first:last + 1]
    if len(esf) < 16:
        return float("nan")
    # Smooth ESF very lightly to reduce binning noise
    esf = ndi.gaussian_filter1d(esf, sigma=1.0)
    # LSF = derivative; Hann-window to suppress edge artefacts
    lsf = np.diff(esf)
    if len(lsf) < 16:
        return float("nan")
    win = np.hanning(len(lsf))
    lsf = lsf * win
    # FFT → MTF; sampling rate = 1/bin_size cycles/px
    mtf = np.abs(np.fft.fft(lsf))
    if mtf[0] <= 0:
        return float("nan")
    mtf = mtf / mtf[0]
    n = len(lsf)
    freqs = np.arange(n) / (n * bin_size)   # cycles per pixel
    half = n // 2
    f = freqs[:half]
    m = mtf[:half]
    # Cap freq at Nyquist (0.5 cy/px). Higher would be aliased.
    cap = np.searchsorted(f, 0.5)
    f = f[:max(cap, 4)]
    m = m[:len(f)]
    # MTF50: first crossing of 0.5
    below = np.where(m < 0.5)[0]
    if len(below) == 0:
        return float("nan")
    i = int(below[0])
    if i == 0:
        return float("nan")
    m_prev, m_curr = m[i - 1], m[i]
    if m_prev == m_curr:
        return float(f[i])
    frac = (0.5 - m_prev) / (m_curr - m_prev)
    return float(f[i - 1] + frac * (f[i] - f[i - 1]))


ALGORITHMS = {
    "radial_cutoff":      alg_radial_cutoff,
    "mtf50_slanted_edge": alg_mtf50_slanted_edge,
    "vol":                alg_vol,
    "brenner":            alg_brenner,
}


# --------------------------------------------------------------------- field sweep + consensus

def gradient_energy_map(luma: np.ndarray, y0: int, x0: int, h: int, w: int) -> np.ndarray:
    """Compute gradient-energy at each candidate tile position in a box.
    Returns a 2D map indexed by (ty, tx) over the search-step grid."""
    region = luma[y0:y0+h, x0:x0+w]
    nys = max(1, (region.shape[0] - TILE) // SEARCH_STEP + 1)
    nxs = max(1, (region.shape[1] - TILE) // SEARCH_STEP + 1)
    out = np.full((nys, nxs), np.nan, dtype=np.float32)
    for iy in range(nys):
        for ix in range(nxs):
            y = iy * SEARCH_STEP
            x = ix * SEARCH_STEP
            if y + TILE > region.shape[0] or x + TILE > region.shape[1]:
                continue
            t = region[y:y+TILE, x:x+TILE]
            gy = np.diff(t, axis=0); gx = np.diff(t, axis=1)
            out[iy, ix] = (gy * gy).mean() + (gx * gx).mean()
    return out


def field_boxes(shape: tuple[int, int]):
    H, W = shape
    bw = int(W * FIELD_BOX_W_FRAC)
    bh = int(H * FIELD_BOX_H_FRAC)
    y0 = (H - bh) // 2
    out = []
    for fx in FIELD_POSITIONS:
        cx = int(W * fx)
        x0 = max(0, cx - bw // 2)
        if x0 + bw > W:
            x0 = W - bw
        out.append((fx, (y0, x0, bh, bw)))
    return out


# --------------------------------------------------------------------- dataset

_RE_FL    = re.compile(r"^(\d+(?:\.\d+)?)\s*mm$")
_RE_APER  = re.compile(r"^F(\d+(?:\.\d+)?)$")

@dataclass
class Config:
    date: str
    lens_dir: str
    focal_mm: float
    aperture: str
    aperture_f: float
    jpegs: list[Path] = field(default_factory=list)


def discover(root: Path, date: str,
             lens_filter: Optional[Callable[[str], bool]] = None) -> list[Config]:
    out: list[Config] = []
    if not root.is_dir():
        return out
    for lens in sorted(root.iterdir()):
        if not lens.is_dir():
            continue
        if lens_filter is not None and not lens_filter(lens.name):
            continue
        for fl in sorted(lens.iterdir()):
            if not fl.is_dir():
                continue
            m = _RE_FL.match(fl.name)
            if not m:
                continue
            focal = float(m.group(1))
            for ap in sorted(fl.iterdir()):
                if not ap.is_dir():
                    continue
                m = _RE_APER.match(ap.name)
                if not m:
                    continue
                ap_f = float(m.group(1))
                jpegs = sorted(ap.glob("*.jpg"))
                if not jpegs:
                    continue
                out.append(Config(
                    date=date, lens_dir=lens.name, focal_mm=focal,
                    aperture=ap.name, aperture_f=ap_f, jpegs=jpegs,
                ))
    return out


def load_luma(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("L"), dtype=np.float32)


# --------------------------------------------------------------------- measurement

@dataclass
class Measurement:
    date: str
    lens_dir: str
    focal_mm: float
    aperture: str
    position_frac: float
    algorithm: str
    top: float
    median: float
    minv: float
    top_vs_median: float
    range_pct: float
    n_replicates: int
    consensus_tile_yx: tuple[int, int]
    movement_flag: bool          # True if replicate tile positions disagreed


def measure_config(cfg: Config) -> list[Measurement]:
    """Per (config, position): consensus tile -> measure all 4 algorithms
    on each replicate at that tile -> aggregate top/median/min/range."""
    # Load replicates once
    luma_list = [load_luma(jp) for jp in cfg.jpegs]
    if len(luma_list) == 0:
        return []
    H, W = luma_list[0].shape

    rows: list[Measurement] = []
    for fx, (y0, x0, bh, bw) in field_boxes((H, W)):
        # Per-replicate gradient maps
        grad_maps = [gradient_energy_map(L, y0, x0, bh, bw) for L in luma_list]
        # Sanity: shapes match
        if not all(gm.shape == grad_maps[0].shape for gm in grad_maps):
            continue
        stack = np.stack(grad_maps, axis=0)
        # Median across replicates (NaN-safe)
        with np.errstate(all="ignore"):
            med_map = np.nanmedian(stack, axis=0)
        if np.all(np.isnan(med_map)):
            continue
        # Best position by median-gradient
        flat_idx = int(np.nanargmax(med_map))
        iy, ix = np.unravel_index(flat_idx, med_map.shape)
        # Per-replicate position-of-max for movement detection
        per_repl_pos = []
        for gm in grad_maps:
            if np.all(np.isnan(gm)):
                continue
            fi = int(np.nanargmax(gm))
            per_repl_pos.append(np.unravel_index(fi, gm.shape))
        # Movement flag: positions disagree across replicates
        if per_repl_pos:
            ys = np.array([p[0] for p in per_repl_pos])
            xs = np.array([p[1] for p in per_repl_pos])
            # Tile spans SEARCH_STEP px per index step. "Disagreement" = >2 steps in either axis.
            movement = bool(ys.std() > 2.0 or xs.std() > 2.0)
        else:
            movement = False

        # Absolute tile coordinates of the consensus position
        consensus_yx = (y0 + iy * SEARCH_STEP, x0 + ix * SEARCH_STEP)

        # Measure 4 algorithms on each replicate's tile at the consensus position
        per_alg_vals: dict[str, list[float]] = {k: [] for k in ALGORITHMS}
        for L in luma_list:
            ty, tx = consensus_yx
            if ty + TILE > L.shape[0] or tx + TILE > L.shape[1]:
                continue
            tile = L[ty:ty+TILE, tx:tx+TILE]
            for name, fn in ALGORITHMS.items():
                v = fn(tile)
                if not np.isnan(v):
                    per_alg_vals[name].append(v)

        for name, vals in per_alg_vals.items():
            if not vals:
                continue
            top = max(vals)
            med = float(statistics.median(vals))
            mn = min(vals)
            tvm = top / med if med > 0 else float("nan")
            rng_pct = (top - mn) / med * 100 if med > 0 else float("nan")
            rows.append(Measurement(
                date=cfg.date, lens_dir=cfg.lens_dir,
                focal_mm=cfg.focal_mm, aperture=cfg.aperture,
                position_frac=fx, algorithm=name,
                top=top, median=med, minv=mn,
                top_vs_median=tvm, range_pct=rng_pct,
                n_replicates=len(vals),
                consensus_tile_yx=consensus_yx,
                movement_flag=movement,
            ))
    return rows


# --------------------------------------------------------------------- lighting robustness

def lighting_robustness(tile: np.ndarray) -> dict[str, list[tuple[str, float]]]:
    """Apply transforms to ``tile`` and report each algorithm's value."""
    transforms = [
        ("baseline",            lambda t: t),
        ("brightness -0.5EV",   lambda t: t * 0.707),
        ("brightness +0.5EV",   lambda t: np.minimum(t * 1.414, 255)),
        ("brightness -1.0EV",   lambda t: t * 0.5),
        ("brightness +1.0EV",   lambda t: np.minimum(t * 2.0, 255)),
        ("contrast x0.7",       lambda t: (t - t.mean()) * 0.7 + t.mean()),
        ("contrast x1.3",       lambda t: np.clip((t - t.mean()) * 1.3 + t.mean(), 0, 255)),
        ("gamma 0.7",           lambda t: 255 * (np.clip(t, 0, 255) / 255) ** 0.7),
        ("gamma 1.3",           lambda t: 255 * (np.clip(t, 0, 255) / 255) ** 1.3),
    ]
    out: dict[str, list[tuple[str, float]]] = {k: [] for k in ALGORITHMS}
    for label, fn in transforms:
        x = fn(tile.astype(np.float32))
        for name, alg in ALGORITHMS.items():
            out[name].append((label, alg(x)))
    return out


# --------------------------------------------------------------------- datasets

def _skip_macro_mag(name: str) -> bool:
    """Filter for older D7200 lens-dir naming where macro 1:1/1:3 magnification
    folders sit alongside 'inf' (infinity) folders. Skip 1_1/1_3; keep inf and
    anything else (D7200 wide-angle datasets don't use the suffix)."""
    return not (name.endswith(" 1_1") or name.endswith(" 1_3"))


DATASETS = {
    # --- Z7 (FX, 4.35um) ---
    "wide2026_01_24": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-24"),
        date="2026-01-24",
        lens_filter=lambda name: not name.endswith("AF for every pic"),
        pixel_pitch_mm=Z7_PIXEL_PITCH_MM,
        camera="Z7",
    ),
    "wide2026_01_26": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-26"),
        date="2026-01-26",
        lens_filter=None,
        pixel_pitch_mm=Z7_PIXEL_PITCH_MM,
        camera="Z7",
    ),
    "wide2026_02_07": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-02-07/20 mm"),
        date="2026-02-07",
        lens_filter=None,
        pixel_pitch_mm=Z7_PIXEL_PITCH_MM,
        camera="Z7",
    ),
    "tele2026_02_07": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-02-07/telephoto"),
        date="2026-02-07",
        lens_filter=None,
        pixel_pitch_mm=Z7_PIXEL_PITCH_MM,
        camera="Z7",
    ),

    # --- D7200 (DX, 3.91um) — older tests, possibly less strict methodology ---
    "tele2025_07_05": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2025-07-05"),
        date="2025-07-05",
        lens_filter=_skip_macro_mag,
        pixel_pitch_mm=D7200_PIXEL_PITCH_MM,
        camera="D7200",
    ),
    "tele2025_07_09": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2025-07-09"),
        date="2025-07-09",
        lens_filter=_skip_macro_mag,
        pixel_pitch_mm=D7200_PIXEL_PITCH_MM,
        camera="D7200",
    ),
    "tele2025_09_06": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2025-09-06"),
        date="2025-09-06",
        lens_filter=_skip_macro_mag,
        pixel_pitch_mm=D7200_PIXEL_PITCH_MM,
        camera="D7200",
    ),
    "wide2025_09_10": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2025-09-10"),
        date="2025-09-10",
        lens_filter=None,
        pixel_pitch_mm=D7200_PIXEL_PITCH_MM,
        camera="D7200",
    ),
    "mid2025_09_11": dict(
        root=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2025-09-11"),
        date="2025-09-11",
        lens_filter=None,
        pixel_pitch_mm=D7200_PIXEL_PITCH_MM,
        camera="D7200",
    ),
}


# --------------------------------------------------------------------- main

def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in DATASETS:
        print("usage: poc_longdist_algorithms.py {" + "|".join(DATASETS) + "}")
        return 2
    key = sys.argv[1]
    cfg = DATASETS[key]
    out_dir = OUT_BASE / key
    out_dir.mkdir(exist_ok=True)
    print(f"output dir: {out_dir}")

    configs = discover(cfg["root"], cfg["date"], cfg["lens_filter"])
    print(f"[{key}] discovered {len(configs)} configs", flush=True)

    all_rows: list[Measurement] = []
    for i, c in enumerate(configs, 1):
        print(f"  [{i}/{len(configs)}] {c.lens_dir} | {c.focal_mm}mm | {c.aperture} ({len(c.jpegs)} repl)", flush=True)
        all_rows.extend(measure_config(c))

    # Raw CSV
    csv_path = out_dir / "per_measurement.csv"
    with csv_path.open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["date", "lens_dir", "focal_mm", "aperture", "position_frac",
                     "algorithm", "top", "median", "min", "top_vs_median",
                     "range_pct", "n_replicates", "consensus_y", "consensus_x", "movement_flag"])
        for m in all_rows:
            wr.writerow([m.date, m.lens_dir, m.focal_mm, m.aperture, m.position_frac,
                         m.algorithm, f"{m.top:.4f}", f"{m.median:.4f}", f"{m.minv:.4f}",
                         f"{m.top_vs_median:.3f}", f"{m.range_pct:.1f}",
                         m.n_replicates, m.consensus_tile_yx[0], m.consensus_tile_yx[1],
                         int(m.movement_flag)])

    # Per-algorithm stability (median CV across replicates)
    md = [f"# Algorithm comparison — {key}",
          "",
          f"Discovered {len(configs)} configs, generated {len(all_rows)} per-(algorithm, cell) measurements.",
          "Consensus tile selection uses cross-replicate median-gradient",
          "(rejects moving content like cyclists/pedestrians).",
          ""]
    md.append("## Stability per algorithm (replicate spread)")
    md.append("")
    md.append("Per cell, CV = (top - min) / median * 100. Lower = the algorithm")
    md.append("returns consistent values across the burst of replicates.")
    md.append("")
    md.append("| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |")
    md.append("|---|---|---|---|---|")
    by_alg: dict[str, list[Measurement]] = {}
    for m in all_rows:
        by_alg.setdefault(m.algorithm, []).append(m)
    for name in ALGORITHMS:
        ms = by_alg.get(name, [])
        cvs = [m.range_pct for m in ms if not np.isnan(m.range_pct)]
        n_total = sum(1 for m in all_rows if m.algorithm == name)
        # NaN-rate: tile cells where the algorithm produced no valid measurement
        # are absent from all_rows; per-cell expected count = n_cells_other_algorithms
        # Approximate by comparing to the most prolific algorithm
        if cvs:
            md.append(f"| {name} | {statistics.median(cvs):.1f}% | {np.percentile(cvs, 90):.1f}% | {len(ms)} | (cells absent if algorithm returned NaN) |")
        else:
            md.append(f"| {name} | — | — | {len(ms)} | — |")

    # Cross-algorithm rank agreement (over (lens, FL, ap, position) using `top`)
    md.append("")
    md.append("## Cross-algorithm rank agreement (Spearman ρ on `top`)")
    md.append("")
    keys = list(ALGORITHMS.keys())
    by_cell: dict[tuple, dict[str, float]] = {}
    for m in all_rows:
        ck = (m.lens_dir, m.focal_mm, m.aperture, m.position_frac)
        by_cell.setdefault(ck, {})[m.algorithm] = m.top

    sp_mat = np.zeros((len(keys), len(keys))); ps_mat = np.zeros_like(sp_mat)
    for i, a in enumerate(keys):
        for j, b in enumerate(keys):
            xa = []; xb = []
            for cell in by_cell.values():
                if a in cell and b in cell:
                    xa.append(cell[a]); xb.append(cell[b])
            if len(xa) < 3:
                sp_mat[i, j] = ps_mat[i, j] = float("nan"); continue
            sp_mat[i, j] = spearmanr(xa, xb).statistic
            ps_mat[i, j] = pearsonr(xa, xb).statistic

    md.append("|  | " + " | ".join(keys) + " |")
    md.append("|---|" + "|".join(["---"] * len(keys)) + "|")
    for i, a in enumerate(keys):
        md.append(f"| {a} | " + " | ".join(f"{sp_mat[i,j]:.2f}" if not np.isnan(sp_mat[i,j]) else "—" for j in range(len(keys))) + " |")

    md.append("")
    md.append("## Pearson linear correlation")
    md.append("")
    md.append("|  | " + " | ".join(keys) + " |")
    md.append("|---|" + "|".join(["---"] * len(keys)) + "|")
    for i, a in enumerate(keys):
        md.append(f"| {a} | " + " | ".join(f"{ps_mat[i,j]:.2f}" if not np.isnan(ps_mat[i,j]) else "—" for j in range(len(keys))) + " |")

    # Lighting robustness on a reference tile
    best = None
    for m in all_rows:
        if m.algorithm == "radial_cutoff" and not np.isnan(m.top):
            if best is None or m.top > best.top:
                best = m
    if best is not None:
        # Re-locate & re-load the tile
        for cfg_obj in configs:
            if (cfg_obj.lens_dir == best.lens_dir
                    and cfg_obj.focal_mm == best.focal_mm
                    and cfg_obj.aperture == best.aperture):
                # Use the first replicate
                luma = load_luma(cfg_obj.jpegs[0])
                ty, tx = best.consensus_tile_yx
                tile = luma[ty:ty+TILE, tx:tx+TILE] if (ty+TILE <= luma.shape[0] and tx+TILE <= luma.shape[1]) else None
                if tile is not None:
                    light = lighting_robustness(tile)
                    md.append("")
                    md.append("## Lighting-robustness probe (one reference sharp tile)")
                    md.append("")
                    md.append(f"Reference: {best.lens_dir} {best.focal_mm}mm {best.aperture} x={best.position_frac}")
                    md.append("")
                    md.append("| Transform | " + " | ".join(keys) + " |")
                    md.append("|---|" + "|".join(["---"] * len(keys)) + "|")
                    labels = [lbl for lbl, _ in light[keys[0]]]
                    baselines = {k: light[k][0][1] for k in keys}
                    for idx, lbl in enumerate(labels):
                        vals = []
                        for k in keys:
                            v = light[k][idx][1]
                            base = baselines[k]
                            if base == 0 or np.isnan(v):
                                vals.append("—")
                            else:
                                rel = (v / base - 1) * 100
                                vals.append(f"{v:.3f} ({rel:+.0f}%)")
                        md.append(f"| {lbl} | " + " | ".join(vals) + " |")
                break

    # Movement-flag summary
    movement_cells = [m for m in all_rows if m.movement_flag and m.algorithm == "radial_cutoff"]
    md.append("")
    md.append("## Movement detection (cross-replicate position-disagreement)")
    md.append("")
    md.append(f"- {len(movement_cells)} cells flagged as having moving content")
    md.append(f"  (replicate tile positions disagreed by > 2 search steps).")
    if movement_cells:
        md.append("- Affected (lens, FL, aperture, position) — top 10:")
        for m in movement_cells[:10]:
            md.append(f"  - {m.lens_dir} | {m.focal_mm:.0f}mm | {m.aperture} | x={m.position_frac}")

    (out_dir / "algorithms_summary.md").write_text("\n".join(md) + "\n")

    # Save matrices as PNG
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, mat, title in [(axes[0], sp_mat, "Spearman ρ on `top`"),
                            (axes[1], ps_mat, "Pearson r on `top`")]:
        im = ax.imshow(mat, cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(keys))); ax.set_yticks(range(len(keys)))
        ax.set_xticklabels(keys, rotation=30, fontsize=9); ax.set_yticklabels(keys, fontsize=9)
        for i in range(len(keys)):
            for j in range(len(keys)):
                ax.text(j, i, f"{mat[i,j]:.2f}", ha="center", va="center",
                        color="white" if abs(mat[i,j]) > 0.6 else "black", fontsize=9)
        ax.set_title(title)
        plt.colorbar(im, ax=ax, fraction=0.04)
    fig.suptitle(f"Algorithm agreement — {key}")
    fig.tight_layout()
    fig.savefig(out_dir / "correlation_matrices.png", dpi=120)
    plt.close(fig)

    print(f"Wrote {out_dir}/{{per_measurement.csv,algorithms_summary.md,correlation_matrices.png}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
