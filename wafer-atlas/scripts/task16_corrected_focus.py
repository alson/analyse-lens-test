"""Task 16 — corrected atlas-anchored focus measurement (supersedes task15's
argmax logic).

Two corrections vs task15:
  1. FOCUS METRIC. task15 used lsf_mtf50 for the focus argmax, but at M>=1.0 the
     4D bar's MTF50 SATURATES (flat-tops ~0.337 cy/px) over the in-focus region,
     so its argmax is degenerate. We use a non-saturating focus measure
     (Laplacian variance on the per-shot-tracked bar box) for the argmax, and
     report lsf_mtf50 only as the absolute-resolution readout at the focus shot.
  2. REFERENCE. task15's "lsf_ref_shot" (137/41/47) were actually JPEG-FILESIZE
     argmaxes, not LSF focus argmaxes (verified against the tile-sharpness
     per-shot CSVs). We pull the true lsf_mtf50 and maze_fft_amp centre-tile
     argmaxes from those CSVs as the reference.

Also: per-shot bar tracking removes focus-rail subject drift, and measuring
every in-frame 4D instance exposes the field-focus TILT (best-focus shot varies
with field x-position).

Output: out/diag_2026_06/task16_corrected.{json,png} + printed summary.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from tile_sharpness.methods.lsf import cross_section, lsf_mtf50

_spec = importlib.util.spec_from_file_location(
    "diag_measure", Path(__file__).parent / "diag_measure.py")
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

A = Path(__file__).parent.parent
OUT = A / "out" / "diag_2026_06"
TS = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness")

# tile-sharpness per-shot CSV + sweep-key for the true reference, per sweep.
REF_CSV = {
    "sweep1_M0.385": (TS / "out_task2/per_shot_per_tile.csv", "100-400"),
    "sweep2_M1.0":   (TS / "out_apertures_for_calibration/per_shot_per_tile.csv",
                      "200mm_f_4D_IF-ED__1_1__F11"),
    "sweep3_M2.0":   (TS / "out_task4/per_shot_per_tile.csv", "TC-2001"),
    "sweep4_newer_rig": (None, None),
}


def csv_reference(name):
    path, key = REF_CSV.get(name, (None, None))
    if path is None or not path.exists():
        return {}
    by_tile = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            if key in r["sweep"]:
                by_tile[(r["tile_ix"], r["tile_iy"])].append(r)
    centre = by_tile.get(("0", "0")) or (next(iter(by_tile.values()), []))

    def am(col):
        best = None
        for r in centre:
            try:
                v = float(r[col])
            except (ValueError, KeyError):
                continue
            if v <= 0:
                continue
            si = int(r["shot_idx"])
            if best is None or v > best[1]:
                best = (si, v)
        return best and best[0]
    return {"lsf_centre": am("lsf_mtf50_cy_per_px"),
            "maze_centre": am("maze_fft_amp"),
            "filesize_centre": am("filesize_bytes")}


def lapvar_box(roi, cx, cy, half):
    y0, y1 = max(0, int(cy - half)), min(roi.shape[0], int(cy + half))
    x0, x1 = max(0, int(cx - half)), min(roi.shape[1], int(cx + half))
    box = roi[y0:y1, x0:x1].astype(np.float32)
    if box.size == 0:
        return np.nan
    return float(cv2.Laplacian(box, cv2.CV_32F).var())


def measure_instance(cfg, aff, col, shots):
    geo = dm.instance_geometry(aff, col)
    rx0, ry0, rx1, ry1 = geo["roi"]
    bw, bh = geo["w_px"], abs(geo["y_top"] - geo["y_bottom"])
    pred_cx, pred_cy = geo["cx"] - rx0, geo["cy"] - ry0
    half = int(max(bw, bh) * 0.7)
    lap, mtf = [], []
    for sp in shots:
        img = np.asarray(Image.open(sp).convert("L"))
        roi = img[ry0:min(img.shape[0], ry1), rx0:min(img.shape[1], rx1)]
        d = dm.detect_bar_segment(roi, pred_cx, pred_cy, bw, bh)
        if d is None:
            lap.append(np.nan); mtf.append(np.nan); continue
        seg, hw, (dcx, dcy), _ = d
        lap.append(lapvar_box(roi, dcx, dcy, half))
        prof = cross_section(roi.astype(np.float32), seg, half_window_px=hw)
        m = lsf_mtf50(prof)
        mtf.append(m if m is not None else np.nan)
    lap = np.array(lap, float); mtf = np.array(mtf, float)
    focus = int(np.nanargmax(lap)) if not np.all(np.isnan(lap)) else None
    mtf_argmax = int(np.nanargmax(mtf)) if not np.all(np.isnan(mtf)) else None
    return dict(col=col, cx=geo["cx"], focus_shot=focus, mtf50_argmax=mtf_argmax,
                mtf50_at_focus=(float(mtf[focus]) if focus is not None and not np.isnan(mtf[focus]) else None),
                lapvar=lap.tolist(), mtf50=mtf.tolist())


def main():
    anchors = dm.anchors
    results = {}
    for cfg in dm.task15.SWEEPS:
        name = cfg["name"]
        aff = anchors.get(name)
        if not aff:
            continue
        shots = sorted(cfg["dir"].glob("*.jpg")) + sorted(cfg["dir"].glob("*.JPG"))
        cols = [c for c in (0, 4, 8) if dm.in_frame(dm.instance_geometry(aff, c))]
        ref = csv_reference(name)
        insts = [measure_instance(cfg, aff, c, shots) for c in cols]
        results[name] = dict(n_shots=len(shots), ref=ref, instances=insts,
                             old_filesize_ref=cfg["lsf_ref_shot"])
        print(f"\n{name}: {len(shots)} shots")
        print(f"  true LSF-centre ref={ref.get('lsf_centre')}  maze-centre={ref.get('maze_centre')}  "
              f"filesize(old 'ref')={ref.get('filesize_centre')} [hardcoded {cfg['lsf_ref_shot']}]")
        for it in insts:
            print(f"  {it['col']}D (x={it['cx']:.0f}): focus_shot(lapvar)={it['focus_shot']}  "
                  f"mtf50_argmax(saturating)={it['mtf50_argmax']}  "
                  f"mtf50@focus={it['mtf50_at_focus']}")

    json.dump(results, open(OUT / "task16_corrected.json", "w"), indent=1, default=float)

    # plot lapvar focus curves per sweep
    names = list(results)
    fig, axes = plt.subplots(len(names), 1, figsize=(13, 3.0 * len(names)), squeeze=False)
    for ax, name in zip(axes[:, 0], names):
        R = results[name]
        for it in R["instances"]:
            lap = np.array(it["lapvar"], float)
            if np.all(np.isnan(lap)):
                continue
            ax.plot(lap / np.nanmax(lap), lw=1.3, label=f"{it['col']}D focus={it['focus_shot']}")
        ref = R["ref"]
        if ref.get("lsf_centre") is not None:
            ax.axvline(ref["lsf_centre"], color="g", ls="--", alpha=.7, label=f"true LSF centre {ref['lsf_centre']}")
        if R["old_filesize_ref"] is not None:
            ax.axvline(R["old_filesize_ref"], color="r", ls=":", alpha=.6, label=f"old filesize 'ref' {R['old_filesize_ref']}")
        ax.set_title(f"{name} — tracked-bar Laplacian-variance focus (normalized)")
        ax.set_xlabel("shot"); ax.set_ylabel("lapvar/max"); ax.grid(alpha=.3); ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / "task16_corrected.png", dpi=110)
    print(f"\nsaved {OUT/'task16_corrected.png'} and .json")


if __name__ == "__main__":
    main()
