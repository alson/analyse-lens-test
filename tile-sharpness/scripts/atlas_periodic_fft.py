"""Atlas-anchored periodic-FFT MTF on the wafer's marked periodic structures.

Two target classes (reported separately):
  * CYAN  `use_for_fft` experimental structures: die types (0,1) 4B 3x3 cell grid,
    (0,2) 4C two-columns, (2,1) 2B horizontal-line grating + serpent, (2,2) 2C
    large region. Plus the (0,3) 4D slanted-edge bar (read as periodic here too).
  * MAGENTA bond-pad arrays: `feature_inventory.bond_pads` in nearly every die — the
    user's primary periodic class (the atlas parser computed `pad_pitch_px` only on
    these). Broad field coverage.

Per region we register the sweep once (reg_auto, robust multi-frame picker), project
the die-local bbox to image coords, crop + de-rotate to wafer axes, and read a BOUNDED
Michelson periodic contrast (methods.periodic_fft) at the region's measurable
fundamental. The atlas SUPER-pitch (pad/cell spacing, 80-330 px) sits far below the
optical cutoff and carries no MTF info; the discriminating signal is the SUB-element
periodicity (~3-16 px, 0.06-0.30 cy/px). We therefore DISCOVER the dominant
band-limited fundamental on the region's own best-focus frame, LOCK that pitch, and
read peak contrast across the through-focus stack at the locked pitch (field-tilt-aware).

Each read is converted to subject lp/mm via atlas-M and ceiling-validated against the
diffraction MTF at that same frequency (optics.diffraction_mtf_at). Periodic contrast
is bounded [0,1] and under-reads to 0 past cutoff, so it cannot over-read the ceiling.

Ranking mode (env): RANK_CONFIGS=path.csv RANK_OUT=path.csv [SHARD=i/N].
Single-config probe:  python atlas_periodic_fft.py SWEEP_DIR [N_marked]
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from tile_sharpness.methods.periodic_fft import periodic_contrast, derotate, discover_fundamental
from tile_sharpness import optics

WA = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/wafer-atlas/scripts")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


reg_auto = _load("reg_auto", WA / "reg_auto.py")
af = _load("anchor_fit_sweep", WA / "anchor_fit_sweep.py")
ATLAS = json.load(open(WA.parent / "atlas.json"))

IMAGE_W, IMAGE_H = 8256, 5504
M_ANCHOR_SCALE = 1.6549
SENSOR_PITCH_UM = 4.35
FFT_DIES = ["(0, 1)", "(0, 2)", "(2, 1)", "(2, 2)"]
SE_DIE = "(0, 3)"
# discriminating band: above the atlas super-pitch (<0.05), below/excluding the
# universal 13um maze line near 0.33 cy/px, below Nyquist.
BAND = (0.06, 0.30)
MAZE_EXCLUDE = (0.31, 0.36)


def die_uv_to_img(col, row, u, v, p):
    if "k1" in p:
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return af.grid_xy(col + u, row + v, p, ATLAS)


def central_lapvar(g):
    c = g[IMAGE_H // 2 - 800:IMAGE_H // 2 + 800, IMAGE_W // 2 - 800:IMAGE_W // 2 + 800]
    return cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var()


def register(jpgs):
    # Rank candidate frames by central focus on a SUBSAMPLE (every ~3rd frame) — the
    # focus plateau is wide, so we don't need all frames just to pick the sharpest few.
    step = max(1, len(jpgs) // 40)
    sub = jpgs[::step]
    lv = []
    for jp in sub:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((central_lapvar(g) if g is not None else -1.0, jp))
    lv.sort(reverse=True)
    cand = [jp for _, jp in lv[:3]] + [jpgs[int(len(jpgs) * f)] for f in (0.4, 0.6)]
    best = None
    for jp in dict.fromkeys(cand):
        try:
            p = reg_auto.register_and_refine("x", path=str(jp), anchors=None)
        except Exception:
            continue
        if p is None or not p.get("n_refine_intersections"):
            continue
        r = p["reg_fit_rmse_px"]
        if not (0.15 < (p["scale"] / M_ANCHOR_SCALE) < 3.5):  # scale-collapse guard
            continue
        if best is None or r < best[0]:
            best = (r, p)
    return best[1] if best else None


def field_zone(cx, cy):
    fx, fy = cx / IMAGE_W, cy / IMAGE_H
    if abs(fx - 0.5) < 0.18 and abs(fy - 0.5) < 0.18:
        return "centre"
    return f"{'T' if fy < 0.5 else 'B'}{'L' if fx < 0.5 else 'R'}"


def enumerate_regions(p, scale):
    """In-FOV cyan use_for_fft/SE structures and magenta bond-pad arrays."""
    regions = []
    for col in range(0, 11):
        for row in range(0, 6):
            typ = f"({col % 4}, {row % 4})"
            dt = ATLAS["die_types"].get(typ, {})
            fi = dt.get("feature_inventory", {})
            blocks = []
            if typ in FFT_DIES:
                for bi, bp in enumerate(fi.get("experimental", [])):
                    blocks.append(("cyan", bi, bp))
            if typ == SE_DIE:
                for bi, bp in enumerate(fi.get("slanted_edge", [])):
                    blocks.append(("cyan_se", bi, bp))
            for bi, bp in enumerate(fi.get("bond_pads", [])):
                blocks.append(("magenta", bi, bp))
            for cls, bi, bp in blocks:
                u0, v0, u1, v1 = bp["bbox_uv"]
                corners = [die_uv_to_img(col, row, u, v, p)
                           for (u, v) in [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
                xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
                cx, cy = float(np.mean(xs)), float(np.mean(ys))
                m = 80
                if not (m < cx < IMAGE_W - m and m < cy < IMAGE_H - m):
                    continue
                if min(xs) < 0 or max(xs) >= IMAGE_W or min(ys) < 0 or max(ys) >= IMAGE_H:
                    continue
                regions.append(dict(
                    col=col, row=row, type=typ, cls=cls, comp=bi,
                    label=f"{col}{'ABCDEF'[row]}/{typ}#{bi}",
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    cx=cx, cy=cy, zone=field_zone(cx, cy)))
    return regions


def measure_region(jpgs, region, theta_deg, scale):
    """Backward-compatible single-region wrapper (used by tests/probes). Prefer
    ``measure_all_regions`` which decodes each frame once for the whole sweep."""
    out = measure_all_regions(jpgs, [region], theta_deg)
    return out.get(0)


def measure_all_regions(jpgs, regions, theta_deg, topk=5):
    """One decode per frame; score every region's ROI. For each region keep the
    ``topk`` highest-lapvar (best-focus) frames, discover the sub-element pitch on the
    sharpest, then take the peak Michelson contrast over those frames at that locked
    pitch. Returns {region_index: result-dict or absent if no valid periodicity}.

    O(frames) full-res decodes regardless of region count — the only scalable shape
    for the cross-config ranking."""
    import heapq
    boxes = {i: [int(v) for v in r["bbox"]] for i, r in enumerate(regions)}
    # per region: a min-heap of (lapvar, seq, roi) holding the topk sharpest ROIs
    heaps = {i: [] for i in range(len(regions))}
    for seq, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        for i, (x0, y0, x1, y1) in boxes.items():
            roi = g[y0:y1, x0:x1]
            if roi.size == 0 or min(roi.shape) < 16:
                continue
            lv = float(cv2.Laplacian(roi.astype(np.float32), cv2.CV_32F).var())
            h = heaps[i]
            if len(h) < topk:
                heapq.heappush(h, (lv, seq, roi.copy()))
            elif lv > h[0][0]:
                heapq.heapreplace(h, (lv, seq, roi.copy()))
    results = {}
    for i, h in heaps.items():
        if not h:
            continue
        frames = sorted(h, reverse=True)            # sharpest first
        der_bf = derotate(frames[0][2].astype(np.float64), theta_deg)
        d = discover_fundamental(der_bf, band=BAND, exclude=MAZE_EXCLUDE)
        if d is None:
            continue
        pitch, ax = d["pitch_px"], d["axis"]
        peak_c, peak_idx, peak_snr, peak_f0 = -1.0, None, 0.0, d["f0_cy_per_px"]
        for lv, seq, roi in frames:
            der = derotate(roi.astype(np.float64), theta_deg)
            c = periodic_contrast(der, pitch_px=pitch, axis=ax)
            if c and c["contrast"] > peak_c:
                peak_c, peak_idx, peak_snr, peak_f0 = c["contrast"], seq, c["snr"], c["f0_cy_per_px"]
        if peak_idx is None:
            continue
        results[i] = dict(pitch_px=pitch, axis=ax, f0_cy_per_px=peak_f0,
                          contrast=peak_c, snr=peak_snr, focus_idx=peak_idx,
                          lapvar=frames[0][0])
    return results


def run(sweep_dir: Path, n_marked: float, *, verbose=True):
    jpgs = sorted(sweep_dir.glob("*.jpg")) + sorted(sweep_dir.glob("*.JPG"))
    if not jpgs:
        return None
    p = register(jpgs)
    if p is None:
        if verbose:
            print(f"{sweep_dir}: registration FAILED")
        return None
    scale = p["scale"]; M = scale / M_ANCHOR_SCALE; theta = p["theta_deg"]
    n_eff = optics.effective_fnumber(n_marked, M)
    regions = enumerate_regions(p, scale)
    measured = measure_all_regions(jpgs, regions, theta)
    rows = []
    for ri, reg in enumerate(regions):
        m = measured.get(ri)
        if m is None:
            continue
        f_sensor = m["f0_cy_per_px"] * (1000.0 / SENSOR_PITCH_UM)
        f_subj = f_sensor * M
        ceil = optics.diffraction_mtf_at(f_sensor, n_eff)
        rows.append(dict(label=reg["label"], cls=reg["cls"], type=reg["type"],
                         zone=reg["zone"], axis=m["axis"], pitch_px=m["pitch_px"],
                         f_subj_lpmm=f_subj, contrast=m["contrast"], ceiling=ceil,
                         over=m["contrast"] - ceil, snr=m["snr"],
                         focus_idx=m["focus_idx"]))
    if verbose:
        print(f"reg rmse={p['reg_fit_rmse_px']:.2f} M={M:.3f} N_eff={n_eff:.1f} "
              f"regions={len(regions)} measured={len(rows)}")
        for d in sorted(rows, key=lambda r: (r["cls"], r["zone"], r["type"])):
            fl = " OVER" if d["over"] > 0.03 else ""
            print(f"  {d['cls']:<8}{d['label']:<14}{d['zone']:<7}{d['axis']} "
                  f"pitch={d['pitch_px']:5.1f} f_subj={d['f_subj_lpmm']:5.1f} "
                  f"C={d['contrast']:.4f} ceil={d['ceiling']:.3f} over={d['over']:+.3f} "
                  f"snr={d['snr']:.1f}{fl}")
    return dict(M=M, n_eff=n_eff, rmse=p["reg_fit_rmse_px"], rows=rows)


# --------------------------------------------------------------------------- #
# Ranking driver (sharded)
# --------------------------------------------------------------------------- #

def _ap_to_n(aperture: str) -> float:
    return float(aperture.replace("F", "").replace("f_", "").replace("f", ""))


def rank_mode():
    cfg_csv = Path(os.environ["RANK_CONFIGS"])
    out_csv = Path(os.environ["RANK_OUT"])
    shard = os.environ.get("SHARD")
    with cfg_csv.open() as fh:
        configs = list(csv.DictReader(fh))
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        configs = [c for k, c in enumerate(configs) if k % n == i]
    fields = ["lens", "mag_label", "aperture", "M", "n_eff", "rmse", "cls", "label",
              "type", "zone", "axis", "pitch_px", "f_subj_lpmm", "contrast",
              "ceiling", "over", "snr", "focus_idx"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for c in configs:
            sample = Path(c["sample"])
            sweep_dir = sample.parent
            try:
                n_marked = _ap_to_n(c["aperture"])
            except ValueError:
                continue
            print(f"=== {c['lens']} {c['mag_label']} {c['aperture']} ===", flush=True)
            res = run(sweep_dir, n_marked, verbose=False)
            if res is None:
                print("  FAILED/empty", flush=True)
                continue
            for d in res["rows"]:
                w.writerow(dict(lens=c["lens"], mag_label=c["mag_label"],
                                aperture=c["aperture"], M=round(res["M"], 4),
                                n_eff=round(res["n_eff"], 2), rmse=round(res["rmse"], 2),
                                **{k: (round(v, 4) if isinstance(v, float) else v)
                                   for k, v in d.items()}))
            fh.flush()
            print(f"  M={res['M']:.3f} measured {len(res['rows'])} regions", flush=True)


if __name__ == "__main__":
    if os.environ.get("RANK_CONFIGS"):
        rank_mode()
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        run(Path(args[0]), float(args[1]) if len(args) > 1 else 8.0)
