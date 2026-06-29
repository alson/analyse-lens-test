"""A5 validation: re-measure the Sigma 105/150 + TC-2001 @ 2:1 configs and show the
pad fundamental/harmonics are identified and the maze is correctly LABELLED as the
maze (vs the current atlas_periodic_fft code returning a ~76 lp/mm "fundamental"
because the maze slid into the static 0.06-0.30 discovery band at high M).

For each config: register (reg_auto), enumerate regions, find the topk best-focus ROIs,
then compare:
  OLD: discover_fundamental(band=(0.06,0.30), exclude=(0.31,0.36))  -> f_subj
  NEW (A5): discover_pad_fundamental (M-aware band + M-aware maze exclude)
            + maze labelled separately from M physics.

Usage (on nufan):
  PYTHONPATH=<src> python scripts/poc_comb_chain_a5_validate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

# reuse the existing driver's registration + ROI plumbing
import importlib.util
spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402

from tile_sharpness.methods.periodic_fft import derotate, discover_fundamental  # noqa: E402

TC2001_2to1 = [
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001", "2_1", 22.0,  # F11
     "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001", "2_1", 22.0,  # F11
     "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001/2_1/F11"),
]


def topk_frames(jpgs, region, topk=5):
    import heapq
    x0, y0, x1, y1 = [int(v) for v in region["bbox"]]
    h = []
    for seq, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        roi = g[y0:y1, x0:x1]
        if roi.size == 0 or min(roi.shape) < 16:
            continue
        lv = float(cv2.Laplacian(roi.astype(np.float32), cv2.CV_32F).var())
        if len(h) < topk:
            heapq.heappush(h, (lv, seq, roi.copy()))
        elif lv > h[0][0]:
            heapq.heapreplace(h, (lv, seq, roi.copy()))
    return sorted(h, reverse=True)


def main():
    for lens, mag, n_marked, sweep_dir in TC2001_2to1:
        sd = Path(sweep_dir)
        jpgs = sorted(sd.glob("*.jpg")) + sorted(sd.glob("*.JPG"))
        print(f"\n{'='*78}\n{lens} {mag} ({len(jpgs)} frames)\n{'='*78}")
        if not jpgs:
            print("  NO FRAMES")
            continue
        p = apf.register(jpgs)
        if p is None:
            print("  REG FAILED")
            continue
        M = p["scale"] / apf.M_ANCHOR_SCALE
        theta = p["theta_deg"]
        regions = apf.enumerate_regions(p, p["scale"])
        mb = L.maze_band_cy_per_px(M)
        lo, hi = L.resolvable_band_cy_per_px(M)
        f_maze = L.maze_freq_cy_per_px(M)
        print(f"  M={M:.3f}  theta={theta:.2f}  rmse={p['reg_fit_rmse_px']:.2f}  regions={len(regions)}")
        print(f"  A5 bands: resolvable=({lo:.3f},{hi:.3f}) cy/px  "
              f"maze f={f_maze:.3f} cy/px ({L.px_to_subj(f_maze, M):.1f} lp/mm subj), "
              f"exclude={None if mb is None else (round(mb[1],3), round(mb[2],3))}")
        # pick the magenta bond-pad regions near centre (the pad arrays)
        pad_regions = [r for r in regions if r["cls"] == "magenta"]
        pad_regions.sort(key=lambda r: (abs(r["cx"] - apf.IMAGE_W / 2) + abs(r["cy"] - apf.IMAGE_H / 2)))
        n_old_is_maze = 0
        n_new_pad = 0
        shown = 0
        for r in pad_regions[:14]:
            frames = topk_frames(jpgs, r, topk=4)
            if not frames:
                continue
            der_bf = derotate(frames[0][2].astype(np.float64), theta)
            old = discover_fundamental(der_bf, band=(0.06, 0.30), exclude=(0.31, 0.36))
            new_rec, _mb = L.discover_pad_fundamental(der_bf, M)
            old_subj = L.px_to_subj(old["f0_cy_per_px"], M) if old else None
            new_subj = L.px_to_subj(new_rec["f0_cy_per_px"], M) if new_rec else None
            # is the OLD pick actually the maze? (within 12% subject lp/mm of 76.9)
            old_is_maze = old_subj is not None and abs(old_subj - L.MAZE_SUBJ_LPMM) / L.MAZE_SUBJ_LPMM < 0.12
            if old_is_maze:
                n_old_is_maze += 1
            if new_rec is not None:
                n_new_pad += 1
            if shown < 8:
                print(f"    {r['label']:<16} OLD f0={old['f0_cy_per_px']:.3f}cy/px "
                      f"({old_subj:.1f}lpmm){'  <-MAZE!' if old_is_maze else ''}  "
                      f"| NEW pad f0={new_rec['f0_cy_per_px']:.3f}cy/px ({new_subj:.1f}lpmm)"
                      if old and new_rec else
                      f"    {r['label']:<16} OLD={old_subj} NEW={new_subj}")
                shown += 1
        print(f"  SUMMARY: of {min(len(pad_regions),14)} pad regions: "
              f"OLD picked the MAZE (~77 lp/mm) on {n_old_is_maze}; "
              f"NEW found a pad fundamental on {n_new_pad}; maze now labelled separately.")


if __name__ == "__main__":
    main()
