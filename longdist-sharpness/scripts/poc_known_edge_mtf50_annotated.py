"""Annotation-driven slanted-edge MTF50 for tele datasets.

Tele scenes (e.g. ``tele2025_07_09``) have focus subjects whose image-
coordinates aren't always at the AF point — the user sometimes focuses
on a structural feature off-centre (paver path at frame bottom,
specific feature at the AF point distance but not its image position).
The wide-angle ``poc_known_edge_mtf50.py`` discover-edges algorithm
auto-detects the long Hough segments in a sharp reference, which on
tele scenes biases toward grass-mow features rather than the user's
actual focus subject.

This script reads an annotations JSON (produced by the contact-sheet
annotator) giving (x_frac, y_frac) per (lens, FL), and constrains
edge discovery to a ROI centred on that point. Edges found in that
ROI are at the user's focus plane by construction.

Usage::

    direnv exec . uv run python -u poc_known_edge_mtf50_annotated.py \\
        --annotations /path/to/annotations.json \\
        --dataset tele2025_07_09 \\
        --out-dir poc_known_edge_mtf50_annotated_out/tele2025_07_09 \\
        [--workers 12] [--limit 0]

Inputs:
- annotations.json: list of {slug, x_frac, y_frac, skipped, ...}
  where slug must match ``_safe_slug(lens) + '__' + f'{fl:.1f}mm'``
  (the same convention used by ``poc_known_edge_mtf50.dataset``).
- dataset key matches one in ``poc_longdist_algorithms.DATASETS``.

Output (same as poc_known_edge_mtf50 dataset mode):
- per_measurement.csv
- per-(lens, FL) sub-dir with edges.json + overlay.jpg
"""
from __future__ import annotations

import argparse
import csv as _csv
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poc_longdist_algorithms as pla  # noqa: E402
from poc_known_edge_mtf50 import (  # noqa: E402
    EdgeSpec, discover_edges, load_luma, load_rgb, render_overlay,
    measure_edge_metrics, MIN_PEAK_RATIO, HOUGH_MIN_LINE_PX,
    _safe_slug,
)

# ----- ROI around annotated focus point ----------------------------------

ROI_FRAC_W = 0.30
ROI_FRAC_H = 0.40


def discover_around_xy(luma: np.ndarray, xy_frac: tuple[float, float],
                       min_line_px: int = 150, top_k: int = 12,
                       roi_frac_w: float = ROI_FRAC_W,
                       roi_frac_h: float = ROI_FRAC_H,
                       ) -> tuple[list[EdgeSpec], tuple[int, int, int, int]]:
    """Run Canny+Hough only within a ROI centred on (x_frac*W, y_frac*H).

    Outside-ROI pixels are filled with the ROI's mean brightness so
    Canny doesn't fire there. Returns (edges, roi).
    """
    h, w = luma.shape
    cx = int(xy_frac[0] * w)
    cy = int(xy_frac[1] * h)
    roi_w = int(w * roi_frac_w)
    roi_h = int(h * roi_frac_h)
    x0 = max(0, cx - roi_w // 2)
    y0 = max(0, cy - roi_h // 2)
    x1 = min(w, x0 + roi_w)
    y1 = min(h, y0 + roi_h)
    masked = luma.copy().astype(np.uint8) if luma.dtype != np.uint8 else luma.copy()
    inside_mean = int(luma[y0:y1, x0:x1].mean())
    out = np.full_like(masked, inside_mean)
    out[y0:y1, x0:x1] = masked[y0:y1, x0:x1]
    specs = discover_edges(out, top_k=top_k, min_line_px=min_line_px)
    return specs, (x0, y0, x1, y1)


# ----- aperture reference picker ------------------------------------------

REF_APERTURE_ORDER = ["F8", "F11", "F5.6", "F4", "F2.8", "F16", "F22"]


def _pick_reference_jpeg(configs_for_lens_fl: list["pla.Config"]) -> Optional[Path]:
    by_aper = {c.aperture: c for c in configs_for_lens_fl}
    for aper in REF_APERTURE_ORDER:
        if aper in by_aper and by_aper[aper].jpegs:
            return max(by_aper[aper].jpegs, key=lambda p: p.stat().st_size)
    for c in configs_for_lens_fl:
        if c.jpegs:
            return max(c.jpegs, key=lambda p: p.stat().st_size)
    return None


def _pick_widest_jpeg(configs_for_lens_fl: list["pla.Config"]) -> Optional[Path]:
    """Widest aperture = smallest f-number. Used for edge discovery so the
    in-focus subject pops vs the blurred background."""
    valid = [c for c in configs_for_lens_fl
             if c.aperture_f is not None and not math.isnan(c.aperture_f) and c.jpegs]
    if not valid:
        return None
    cfg = min(valid, key=lambda c: c.aperture_f)
    return max(cfg.jpegs, key=lambda p: p.stat().st_size)


# ----- per-group worker ---------------------------------------------------

def process_group(args: tuple) -> dict:
    """Worker: discover edges on widest-aperture frame, measure on all replicates.

    Returns a dict with rows + meta to be merged in the main process.
    """
    (slug, lens, fl, x_frac, y_frac, group_configs_dicts, out_sub, date, camera,
     top_k, min_line_px) = args
    # Reconstruct Config dataclasses
    group_cfgs = [pla.Config(**d) for d in group_configs_dicts]
    rows: list[dict] = []
    out_sub_p = Path(out_sub)
    out_sub_p.mkdir(parents=True, exist_ok=True)
    ref_path = _pick_reference_jpeg(group_cfgs)
    widest_path = _pick_widest_jpeg(group_cfgs)
    if ref_path is None:
        return dict(slug=slug, rows=[], status="no_ref")
    # Discovery on WIDEST aperture (best DOF differential)
    disc_path = widest_path if widest_path is not None else ref_path
    disc_luma = load_luma(disc_path)
    specs, roi = discover_around_xy(disc_luma, (x_frac, y_frac),
                                    min_line_px=min_line_px, top_k=top_k)
    if not specs:
        return dict(slug=slug, rows=[], status="no_edges", roi=roi,
                    ref_path=str(ref_path), disc_path=str(disc_path))
    (out_sub_p / "edges.json").write_text(
        json.dumps([asdict(s) for s in specs], indent=2))
    # Save overlay on widest-ap frame
    render_overlay(load_rgb(disc_path), specs, out_sub_p / "overlay.jpg")
    # Measure on F8 reference itself + every replicate at every aperture
    ref_luma = load_luma(ref_path)
    for s in specs:
        m = measure_edge_metrics(ref_luma, s)
        rows.append(dict(
            date=date, camera=camera, lens_dir=lens, focal_mm=fl,
            aperture="REF", aperture_f=float("nan"),
            jpeg=ref_path.name, edge_id=s.edge_id,
            edge_mid_x=s.mid_x, edge_mid_y=s.mid_y,
            edge_angle_deg=math.degrees(s.angle_rad),
            edge_length_px=s.length_px, edge_score=s.score,
            mtf50=m["mtf50"], mtf_at_nyquist=m["mtf_at_nyquist"],
            mtf10_freq=m["mtf10_freq"], role="reference",
            x_frac=x_frac, y_frac=y_frac,
        ))
    for c in sorted(group_cfgs, key=lambda c: c.aperture_f):
        for jp in c.jpegs:
            luma = load_luma(jp)
            for s in specs:
                m = measure_edge_metrics(
                    luma, s, min_peak=s.ref_peak * MIN_PEAK_RATIO)
                rows.append(dict(
                    date=date, camera=camera, lens_dir=lens, focal_mm=fl,
                    aperture=c.aperture, aperture_f=c.aperture_f,
                    jpeg=jp.name, edge_id=s.edge_id,
                    edge_mid_x=s.mid_x, edge_mid_y=s.mid_y,
                    edge_angle_deg=math.degrees(s.angle_rad),
                    edge_length_px=s.length_px, edge_score=s.score,
                    mtf50=m["mtf50"], mtf_at_nyquist=m["mtf_at_nyquist"],
                    mtf10_freq=m["mtf10_freq"], role="test",
                    x_frac=x_frac, y_frac=y_frac,
                ))
    return dict(slug=slug, rows=rows, status="ok", n_edges=len(specs),
                roi=roi, ref_path=str(ref_path), disc_path=str(disc_path))


# ----- main ---------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--annotations", required=True,
                   help="Path to annotations.json from the contact sheet")
    p.add_argument("--dataset", required=True, choices=list(pla.DATASETS),
                   help="Dataset key (e.g. tele2025_07_09)")
    p.add_argument("--out-dir", required=True,
                   help="Output directory")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--min-line-px", type=int, default=150)
    p.add_argument("--limit", type=int, default=0,
                   help="Only process first N (lens, FL) groups; 0 = all.")
    p.add_argument("--workers", type=int, default=max(1, os.cpu_count() - 2),
                   help="Process-pool size for parallel groups")
    args = p.parse_args()

    annotations = json.loads(Path(args.annotations).read_text())
    by_slug = {a["slug"]: a for a in annotations}
    cfg = pla.DATASETS[args.dataset]
    configs = pla.discover(cfg["root"], cfg["date"], cfg["lens_filter"])
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[main] {args.dataset}: {len(configs)} configs", flush=True)

    # Group by (lens_dir, focal_mm)
    from collections import defaultdict
    groups = defaultdict(list)
    for c in configs:
        groups[(c.lens_dir, c.focal_mm)].append(c)
    items = sorted(groups.items())
    if args.limit:
        items = items[:args.limit]
    print(f"[main] {len(items)} groups to process, workers={args.workers}",
          flush=True)

    # Build worker args, skipping annotated-as-skipped groups
    work = []
    skipped_groups = 0
    for (lens, fl), group_cfgs in items:
        slug = f"{_safe_slug(lens)}__{fl:.1f}mm"
        a = by_slug.get(slug)
        if a is None:
            print(f"[main] {slug}: no annotation found, skip", flush=True)
            skipped_groups += 1
            continue
        if a.get("skipped"):
            print(f"[main] {slug}: marked skipped, skip", flush=True)
            skipped_groups += 1
            continue
        x_frac = float(a["x_frac"]); y_frac = float(a["y_frac"])
        out_sub = out_dir / slug
        # Serialise Config objects as dicts so they cross the pool boundary
        cfg_dicts = []
        for c in group_cfgs:
            d = dict(
                lens_dir=c.lens_dir, focal_mm=c.focal_mm, aperture=c.aperture,
                aperture_f=c.aperture_f, jpegs=list(c.jpegs),
            )
            cfg_dicts.append(d)
        work.append((slug, lens, fl, x_frac, y_frac, cfg_dicts, str(out_sub),
                     cfg["date"], cfg["camera"], args.top_k, args.min_line_px))
    print(f"[main] will process {len(work)} groups, skipped {skipped_groups}",
          flush=True)

    all_rows: list[dict] = []
    summary: list[dict] = []
    if args.workers <= 1:
        for w in work:
            r = process_group(w)
            print(f"[main] {r['slug']} {r['status']}", flush=True)
            all_rows.extend(r["rows"])
            summary.append(r)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process_group, w): w[0] for w in work}
            for fut in as_completed(futs):
                slug = futs[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    print(f"[main] {slug} ERROR: {e}", flush=True)
                    continue
                print(f"[main] {r['slug']} {r['status']} "
                      f"({len(r['rows'])} rows, "
                      f"{r.get('n_edges', 0)} edges)", flush=True)
                all_rows.extend(r["rows"])
                summary.append(r)

    # Write summary + per_measurement.csv
    csv_path = out_dir / "per_measurement.csv"
    if all_rows:
        with csv_path.open("w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            for r in all_rows:
                w.writerow(r)
        print(f"[main] wrote {csv_path} ({len(all_rows)} rows)", flush=True)
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(
        [{k: v for k, v in s.items() if k != "rows"} for s in summary],
        indent=2, default=str))
    print(f"[main] wrote {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
