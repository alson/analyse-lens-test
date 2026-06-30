"""Probe the COMMON in-FOV atlas (cl,rl) region across all 16 configs, so the
same-physical-patch resampling can pick rects valid in every config (the high-M
configs have the smallest FOV and dominate the intersection)."""
import csv
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_altest_lib as L

SUBSET = HERE / "poc_comb_chain_subset.csv"
M = 100  # px margin from frame edge


def fov_grid_bounds(p):
    """Find the (cl,rl) bounding box that maps INSIDE the frame (with margin), by
    scanning a coarse grid of (cl,rl) and keeping those whose forward map is in-frame."""
    cls = np.arange(0.0, 11.0, 0.1)
    rls = np.arange(0.0, 6.0, 0.1)
    good_cl, good_rl = [], []
    for cl in cls:
        for rl in rls:
            x, y = L.reg_auto.grid_xy_distorted(cl, rl, p)
            if M < x < L.IMAGE_W - M and M < y < L.IMAGE_H - M:
                good_cl.append(cl); good_rl.append(rl)
    if not good_cl:
        return None
    return (min(good_cl), min(good_rl), max(good_cl), max(good_rl))


def main():
    with SUBSET.open() as fh:
        configs = list(csv.DictReader(fh))
    cl0s, rl0s, cl1s, rl1s = [], [], [], []
    for c in configs:
        sd = Path(c["sample"]).parent
        p, Mm, jpgs = L.register_config(sd)
        name = f"{c['lens'].split()[0]}_{c['mag_label']}"
        if p is None:
            print(f"{name}: REG FAIL", flush=True); continue
        b = fov_grid_bounds(p)
        if b is None:
            print(f"{name} M={Mm:.2f}: NO in-FOV grid", flush=True); continue
        cl0s.append(b[0]); rl0s.append(b[1]); cl1s.append(b[2]); rl1s.append(b[3])
        print(f"{name} M={Mm:.2f} rmse={p['reg_fit_rmse_px']:.1f} "
              f"FOV cl[{b[0]:.1f},{b[2]:.1f}] rl[{b[1]:.1f},{b[3]:.1f}]", flush=True)
    if cl0s:
        inter = (max(cl0s), max(rl0s), min(cl1s), min(rl1s))
        print(f"\nCOMMON in-FOV atlas rect: cl[{inter[0]:.2f},{inter[2]:.2f}] "
              f"rl[{inter[1]:.2f},{inter[3]:.2f}]  "
              f"(span cl={inter[2]-inter[0]:.2f} rl={inter[3]-inter[1]:.2f})", flush=True)


if __name__ == "__main__":
    main()
