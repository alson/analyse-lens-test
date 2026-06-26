"""POC: inventory wider-than-scribe edge features for a low-M MTF50 fallback.

Hypothesis (2026-05-17): at low magnifications (M ~ 0.4) the wafer scribes
are only ~7-8 px FWHM on the Z7 sensor. The scribe-LSF MTF50 path under-
reads because the two edges of the scribe trough are too close for ESF
math to separate (PSF tails of edge A leak into edge B). If the wafer also
contains wider, isolated dark/bright bands aligned with the scribe (bond-
pad rows, metal blocks, test-pattern boundaries) at >20 px on-sensor
width, slanted-edge ESF -> LSF on a single side of such a feature would
escape the cross-talk and return a clean optical-MTF reading.

This script does NOT compute MTF50 from anything. It surveys what's
present on this wafer at this M, across the centre and several off-axis
tiles, and reports:

  - per-tile count of candidate wider features (width > 20 px,
    length > 200 px, slant within +-5 deg of the detected scribe),
  - their width / length / type (dark / bright / step) distribution,
  - coverage across tiles (does every tile in the on-target region have
    at least one usable wider feature?),
  - lighting-variation check: re-run detection on 2-3 shots at the same
    tile and report how stable widths and counts are (specular-highlight
    sensitivity proxy).

Source: Task 2 sweep
``older-2026-01-29/2026-01-29__NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S__1_2.60__F11``
at shot_idx=137 (centre LSF-argmax). Tile geometry from
``out_task2/per_shot_per_tile.csv`` (lsf_roi_px=1328).

Verdict: see ``poc_wide_feature_inventory.md`` written next to this file,
or the printed summary at the end of a run.

Usage:
  direnv exec . uv run python scripts/poc_wide_feature_inventory.py
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, label
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Make tile_sharpness importable when run from scripts/.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from tile_sharpness.methods.lsf import detect_scribe, Segment  # noqa: E402

# ---------------------------------------------------------------------------
# Sweep + tile selection
# ---------------------------------------------------------------------------

SWEEP_DIR = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11"
)
# Centre LSF-argmax shot. Filename ordering matches the rail_step that
# Phase 1 emits as shot_idx; verified by counting files (0-based, 137 -> 138th).
ARGMAX_SHOT_IDX = 137
# A few neighbour shots to assess specular / lighting variation.
# Sweep has 142 JPEGs (indices 0..141). Use neighbours that span the rail
# around argmax 137 without going past the end.
NEARBY_SHOT_IDXS = (125, 137, 141)

# (tile_ix, tile_iy, tile_x_px, tile_y_px) per per_shot_per_tile.csv, shot 137,
# lsf_roi_px=1328.
TILES = [
    # Centre.
    (0, 0, 4128, 2752),
    # Mid-edges of on-target region.
    (0, -1, 4128, 1728),
    (0, 1, 4128, 3776),
    (-1, 0, 3104, 2752),
    (1, 0, 5152, 2752),
    # Corners of on-target region.
    (-2, -1, 2080, 1728),
    (2, 1, 6176, 3776),
]
LSF_ROI_PX = 1328

# ---------------------------------------------------------------------------
# Wider-feature detection
# ---------------------------------------------------------------------------

# A "wider feature" is a connected dark or bright region whose principal
# axis is aligned within ALIGN_TOL_DEG of the scribe slant, with a
# minor-axis ("width") > MIN_WIDTH_PX and a major-axis ("length") >
# MIN_LENGTH_PX on the sensor.
MIN_WIDTH_PX = 20.0      # > 3x the ~7 px scribe FWHM at M=0.385
MAX_WIDTH_PX = 250.0     # avoid the giant bright background blob
MIN_LENGTH_PX = 200.0    # enough samples for edge averaging
MIN_ASPECT = 3.0         # length / width
ALIGN_TOL_DEG = 5.0      # slant agreement with the detected scribe
ISOLATION_PAD_PX = 8     # buffer around feature; checks for nearby edges


@dataclass
class WideFeature:
    feature_id: int
    bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1) within ROI
    length_px: float
    width_px: float
    slant_deg: float                 # principal-axis angle, 0..180
    kind: str                        # 'dark' or 'bright'
    isolated: bool                   # buffer-zone has no other extreme
    intensity: float                 # mean grey inside the region


def _decode_gray(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.float32)


def _crop_roi(arr: np.ndarray, cx: int, cy: int, side: int) -> np.ndarray:
    half = side // 2
    h, w = arr.shape
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(w, cx + half), min(h, cy + half)
    return arr[y0:y1, x0:x1].copy()


def _segment_angle_deg(seg: Segment) -> float:
    """Return seg orientation in degrees, folded to [0, 180)."""
    a = np.degrees(seg.angle_rad)
    return float(a % 180.0)


def _mask_scribes(roi: np.ndarray, scribe_seg: Segment | None) -> np.ndarray:
    """Build a boolean mask True wherever the dominant scribe lives, dilated
    by ~10 px perpendicular so the scribe trough doesn't dominate the wide-
    feature dark-region detection.
    """
    h, w = roi.shape
    mask = np.zeros((h, w), dtype=bool)
    if scribe_seg is None:
        return mask
    # Rasterise the segment; dilate.
    xs = np.linspace(scribe_seg.x0, scribe_seg.x1, max(2, int(scribe_seg.length_px)))
    ys = np.linspace(scribe_seg.y0, scribe_seg.y1, len(xs))
    ix = np.clip(xs.astype(int), 0, w - 1)
    iy = np.clip(ys.astype(int), 0, h - 1)
    mask[iy, ix] = True
    return binary_dilation(mask, iterations=12)


def _components(binary: np.ndarray) -> tuple[np.ndarray, int]:
    """Connected-component label with 8-connectivity."""
    structure = np.ones((3, 3), dtype=bool)
    return label(binary, structure=structure)


def _component_geometry(coords: np.ndarray) -> tuple[float, float, float]:
    """Return (length_px, width_px, slant_deg) from a PCA on pixel coords.

    coords: (N, 2) array of (y, x) integer pixel positions.
    """
    if coords.shape[0] < 5:
        return 0.0, 0.0, 0.0
    yx = coords.astype(np.float64)
    yx -= yx.mean(axis=0)
    # Covariance with (y, x) ordering; flip to (x, y) for an intuitive angle.
    cov = np.cov(yx.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # Sorted ascending; eigvals[1] is major-axis variance.
    major_var, minor_var = float(eigvals[1]), float(eigvals[0])
    # 4 sigma ~ characteristic extent; works well for elongated regions.
    length = 4.0 * np.sqrt(max(major_var, 0.0))
    width = 4.0 * np.sqrt(max(minor_var, 0.0))
    # Eigenvector of major axis in (y, x); angle from +x axis.
    vy, vx = eigvecs[:, 1]
    angle = np.degrees(np.arctan2(vy, vx)) % 180.0
    return float(length), float(width), float(angle)


def _angle_diff_deg(a: float, b: float) -> float:
    """Angular distance in [0, 90] (lines are undirected)."""
    d = abs(a - b) % 180.0
    return float(min(d, 180.0 - d))


def _isolation_ok(
    roi: np.ndarray,
    feat_mask: np.ndarray,
    pad_px: int,
    *,
    is_dark: bool,
    feat_intensity: float,
    bg_intensity: float,
) -> bool:
    """Check that an annular buffer outside the feature is close to local bg
    intensity (no other dark/bright extremes leaking in).

    Heuristic: in the dilated-buffer ring (not in feat_mask), the mean
    intensity should be within 30% of (bg_intensity - feat_intensity) of
    bg_intensity. Tightens with deeper features.
    """
    if pad_px <= 0:
        return True
    dil = binary_dilation(feat_mask, iterations=pad_px)
    ring = dil & (~feat_mask)
    if int(ring.sum()) < 50:
        return True  # too small to test; allow it
    ring_mean = float(roi[ring].mean())
    extreme = abs(feat_intensity - bg_intensity)
    if extreme <= 1e-6:
        return True
    deviation = abs(ring_mean - bg_intensity) / extreme
    return deviation < 0.30


def find_wide_features(
    roi: np.ndarray,
    scribe_seg: Segment | None,
    *,
    align_tol_deg: float = ALIGN_TOL_DEG,
    min_width_px: float = MIN_WIDTH_PX,
    max_width_px: float = MAX_WIDTH_PX,
    min_length_px: float = MIN_LENGTH_PX,
    min_aspect: float = MIN_ASPECT,
) -> list[WideFeature]:
    """Detect dark and bright bands aligned with the scribe.

    Approach:
      1. Mask out the dominant scribe (dilated by 12 px) so its dark
         trough doesn't dominate any threshold.
      2. Threshold-darkest = below the 8th percentile of unmasked pixels.
      3. Threshold-brightest = above the 95th percentile.
      4. Connected components; for each, PCA -> (length, width, slant).
      5. Keep those whose slant is within align_tol_deg of EITHER the
         detected scribe's slant OR the perpendicular orientation
         (wafers have an orthogonal scribe grid; the LSF method needs an
         edge aligned with one direction, so either works as a target).
         Meet length/width/aspect gates AND pass isolation.
    """
    h, w = roi.shape
    scribe_mask = _mask_scribes(roi, scribe_seg)
    valid = ~scribe_mask
    valid_pix = roi[valid]
    if valid_pix.size == 0:
        return []
    bg_intensity = float(np.median(valid_pix))
    p_dark = float(np.percentile(valid_pix, 8.0))
    p_bright = float(np.percentile(valid_pix, 95.0))

    if scribe_seg is not None:
        scribe_angle = _segment_angle_deg(scribe_seg)
        scribe_perp_angle = (scribe_angle + 90.0) % 180.0
        # Accept features aligned with either grid axis.
        accepted_angles: tuple[float, ...] = (scribe_angle, scribe_perp_angle)
    else:
        scribe_angle = 0.0
        accepted_angles = ()

    out: list[WideFeature] = []
    next_id = 1
    for kind, mask in (
        ("dark", (roi <= p_dark) & valid),
        ("bright", (roi >= p_bright) & valid),
    ):
        # Small opening to drop salt-noise stragglers.
        mask_u8 = mask.astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        opened = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel)
        labeled, n = _components(opened.astype(bool))
        for ci in range(1, n + 1):
            coords = np.argwhere(labeled == ci)
            if coords.shape[0] < 200:
                continue
            length, width, slant = _component_geometry(coords)
            if length < min_length_px or width < min_width_px:
                continue
            if width > max_width_px:
                continue
            if length / max(width, 1e-6) < min_aspect:
                continue
            if accepted_angles:
                if all(_angle_diff_deg(slant, a) > align_tol_deg for a in accepted_angles):
                    continue
            # bbox
            y0, x0 = coords.min(axis=0)
            y1, x1 = coords.max(axis=0) + 1
            # Avoid pinning the ROI border (likely truncated feature).
            if x0 < 4 or y0 < 4 or x1 > w - 4 or y1 > h - 4:
                continue
            feat_mask = (labeled == ci)
            feat_intensity = float(roi[feat_mask].mean())
            isolated = _isolation_ok(
                roi, feat_mask, ISOLATION_PAD_PX,
                is_dark=(kind == "dark"),
                feat_intensity=feat_intensity,
                bg_intensity=bg_intensity,
            )
            out.append(WideFeature(
                feature_id=next_id,
                bbox=(int(x0), int(y0), int(x1), int(y1)),
                length_px=length,
                width_px=width,
                slant_deg=slant,
                kind=kind,
                isolated=isolated,
                intensity=feat_intensity,
            ))
            next_id += 1
    # Highest-quality first: isolated & widest & longest.
    out.sort(key=lambda f: (f.isolated, f.length_px), reverse=True)
    return out


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def visualise_tile(
    roi: np.ndarray, seg: Segment | None, feats: list[WideFeature],
    out_path: Path, *, title: str,
) -> None:
    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    ax.imshow(roi, cmap="gray", interpolation="nearest")
    if seg is not None:
        ax.plot([seg.x0, seg.x1], [seg.y0, seg.y1],
                color="#ff3333", linewidth=1.6, label="scribe")
    for f in feats:
        x0, y0, x1, y1 = f.bbox
        edge_color = "#33ddff" if f.isolated else "#ffaa33"
        ax.add_patch(
            plt.Rectangle((x0, y0), x1 - x0, y1 - y0,
                          fill=False, edgecolor=edge_color, linewidth=1.4)
        )
        ax.text(x0, max(0, y0 - 4),
                f"#{f.feature_id} {f.kind} w={f.width_px:.0f} L={f.length_px:.0f}",
                color=edge_color, fontsize=7)
    ax.set_xlim(0, roi.shape[1])
    ax.set_ylim(roi.shape[0], 0)
    ax.set_title(title, fontsize=10)
    if seg is not None:
        ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main: survey all tiles, write report
# ---------------------------------------------------------------------------

def shot_path_for_idx(idx: int) -> Path:
    files = sorted(SWEEP_DIR.glob("*.jpg"))
    return files[idx]


def survey_tile(
    full_gray: np.ndarray, tile: tuple[int, int, int, int],
) -> tuple[Segment | None, list[WideFeature], np.ndarray]:
    _ix, _iy, cx, cy = tile
    roi = _crop_roi(full_gray, cx, cy, LSF_ROI_PX)
    seg = detect_scribe(roi)
    feats = find_wide_features(roi, seg)
    return seg, feats, roi


def main() -> int:
    shot_path = shot_path_for_idx(ARGMAX_SHOT_IDX)
    print(f"Decoding argmax shot {ARGMAX_SHOT_IDX}: {shot_path.name}")
    full = _decode_gray(shot_path)

    rows: list[dict] = []
    viz_dir = HERE
    seen_viz = 0
    for tile in TILES:
        ix, iy, cx, cy = tile
        seg, feats, roi = survey_tile(full, tile)
        scribe_present = seg is not None
        scribe_angle = _segment_angle_deg(seg) if seg is not None else float("nan")
        n_iso = sum(1 for f in feats if f.isolated)
        rows.append({
            "tile_ix": ix, "tile_iy": iy,
            "scribe_present": scribe_present,
            "scribe_angle_deg": f"{scribe_angle:.2f}",
            "n_wider_features": len(feats),
            "n_isolated": n_iso,
            "features": [
                {
                    "id": f.feature_id, "kind": f.kind,
                    "width_px": round(f.width_px, 1),
                    "length_px": round(f.length_px, 1),
                    "slant_deg": round(f.slant_deg, 2),
                    "isolated": f.isolated,
                    "bbox": f.bbox,
                }
                for f in feats
            ],
        })
        # Save all PNGs so the user can eyeball each tile if they like.
        out_png = Path("/tmp") / f"poc_wide_features_tile_{ix}_{iy}.png"
        visualise_tile(
            roi, seg, feats, out_png,
            title=(f"tile ({ix},{iy}) at shot {ARGMAX_SHOT_IDX}: "
                   f"scribe={'y' if scribe_present else 'n'}, "
                   f"wider={len(feats)} (iso={n_iso})"),
        )
        if seen_viz < 3:
            print(f"  saved {out_png}")
            seen_viz += 1

    # Lighting / specular check on the centre tile across nearby shots.
    centre = TILES[0]
    centre_runs: list[tuple[int, int, int, list[WideFeature]]] = []
    for sidx in NEARBY_SHOT_IDXS:
        path = shot_path_for_idx(sidx)
        full_s = _decode_gray(path)
        seg, feats, roi_s = survey_tile(full_s, centre)
        centre_runs.append((sidx, len(feats), sum(1 for f in feats if f.isolated), feats))
        out_png = Path("/tmp") / f"poc_wide_features_centre_shot_{sidx}.png"
        visualise_tile(
            roi_s, seg, feats, out_png,
            title=f"centre tile (0,0) at shot {sidx}: wider={len(feats)}",
        )

    # --- Print findings table.
    print("\n=== Per-tile inventory (shot {}) ===".format(ARGMAX_SHOT_IDX))
    print(f"{'tile':>10}  {'scribe':>6}  {'angle':>6}  {'N_wide':>6}  "
          f"{'iso':>4}  features (w,L,type,iso)")
    for r in rows:
        feats_str = "; ".join(
            f"({f['width_px']}, {f['length_px']}, {f['kind'][0]}, "
            f"{'I' if f['isolated'] else 'n'})"
            for f in r["features"]
        ) or "-"
        print(f"  ({r['tile_ix']:+d},{r['tile_iy']:+d})  "
              f"{'y' if r['scribe_present'] else 'n':>6}  "
              f"{r['scribe_angle_deg']:>6}  {r['n_wider_features']:>6d}  "
              f"{r['n_isolated']:>4d}  {feats_str}")

    print("\n=== Centre-tile specular check (3 shots) ===")
    print(f"{'shot_idx':>8}  {'N_wide':>6}  {'iso':>4}  widths_px")
    for sidx, n_wide, n_iso, feats in centre_runs:
        ws = ",".join(f"{f.width_px:.0f}" for f in feats) or "-"
        print(f"  {sidx:>8d}  {n_wide:>6d}  {n_iso:>4d}  {ws}")

    # Coverage summary.
    n_tiles = len(rows)
    n_with_iso = sum(1 for r in rows if r["n_isolated"] >= 1)
    n_with_any = sum(1 for r in rows if r["n_wider_features"] >= 1)
    print(f"\nCoverage: {n_with_iso}/{n_tiles} tiles have >=1 isolated wider"
          f" feature; {n_with_any}/{n_tiles} have any wider feature.")
    widths = [f["width_px"] for r in rows for f in r["features"]]
    if widths:
        print(f"Width distribution (px): min={min(widths):.1f} "
              f"p25={np.percentile(widths,25):.1f} "
              f"median={np.median(widths):.1f} "
              f"p75={np.percentile(widths,75):.1f} max={max(widths):.1f}")

    # Write CSV for the per-tile-per-feature table.
    csv_out = HERE / "poc_wide_feature_inventory.csv"
    with csv_out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["tile_ix", "tile_iy", "scribe_present", "scribe_angle_deg",
                    "feature_id", "kind", "width_px", "length_px", "slant_deg",
                    "isolated", "bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1"])
        for r in rows:
            if not r["features"]:
                w.writerow([r["tile_ix"], r["tile_iy"], r["scribe_present"],
                            r["scribe_angle_deg"], "", "", "", "", "", "",
                            "", "", "", ""])
                continue
            for f in r["features"]:
                w.writerow([r["tile_ix"], r["tile_iy"], r["scribe_present"],
                            r["scribe_angle_deg"], f["id"], f["kind"],
                            f["width_px"], f["length_px"], f["slant_deg"],
                            f["isolated"], *f["bbox"]])
    print(f"\nWrote per-feature CSV: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
