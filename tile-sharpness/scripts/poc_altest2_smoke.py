"""Stage AltEst-2 smoke — register every widened-subset config, report M, rmse, FOV
grid bounds, and how many GLOBAL-lattice patches are in-FOV. This both validates that
the new lenses (vintage 55/60mm) register and tells us the FOV-overlap structure that
the transitive bridge rides on (P1 robustness)."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_altest_lib as L

SUBSET = HERE / "poc_altest2_subset.csv"
GLOBAL_CL = (1.5, 11.0)
GLOBAL_RL = (0.5, 6.0)
PATCH_UNITS = 0.5
MARGIN = 60


def short_id(c):
    lens = c["lens"]
    base = (lens.split(" + ")[0]
            .replace("NIKKOR Z MC 105mm f_2.8 VR S", "Z105")
            .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
            .replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "S105")
            .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "S150")
            .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100400")
            .replace("Nikon AF Micro-Nikkor 60mm f_2.8D", "AF60")
            .replace("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED", "Z70180")
            .replace("Nikon Micro-Nikkor 55mm f_2.8 AIS", "V55f28")
            .replace("Nikon Micro-Nikkor Auto 55mm f_3.5", "V55f35"))
    acc = ""
    if " + " in lens:
        acc = "+" + lens.split(" + ", 1)[1].replace(" ", "").replace("Olympus", "") \
            .replace("Canon", "C").replace("Nikon", "").replace("KenkoPro300DG1.4x", "Kenko14")
    return f"{base}{acc}_{c['mag_label']}_{c['aperture']}".replace(" ", "").replace("/", "")


def patch_layout():
    out = []
    cl = GLOBAL_CL[0]; i = 0
    while cl + PATCH_UNITS <= GLOBAL_CL[1]:
        rl = GLOBAL_RL[0]; j = 0
        while rl + PATCH_UNITS <= GLOBAL_RL[1]:
            out.append((cl, rl, cl + PATCH_UNITS, rl + PATCH_UNITS, f"A{i:02d}{j:02d}"))
            rl += PATCH_UNITS; j += 1
        cl += PATCH_UNITS; i += 1
    return out


def main():
    with SUBSET.open() as fh:
        configs = list(csv.DictReader(fh))
    patches = patch_layout()
    ok = 0
    for c in configs:
        sd = Path(c["sample"]).parent
        p, M, jpgs = L.register_config(sd)
        sid = short_id(c)
        if p is None:
            print(f"DROP {sid}: reg fail ({len(jpgs)} jpgs)", flush=True); continue
        nfov = 0
        cls, rls = [], []
        for (a, b, a1, b1, plab) in patches:
            corners = [L.reg_auto.grid_xy_distorted(cc, rr, p)
                       for (cc, rr) in [(a, b), (a, b1), (a1, b), (a1, b1)]]
            xs = [pt[0] for pt in corners]; ys = [pt[1] for pt in corners]
            if (min(xs) >= MARGIN and max(xs) <= L.IMAGE_W - MARGIN and
                    min(ys) >= MARGIN and max(ys) <= L.IMAGE_H - MARGIN):
                nfov += 1
                cls += [a, a1]; rls += [b, b1]
        clr = f"cl[{min(cls):.1f},{max(cls):.1f}]" if cls else "cl[--]"
        rlr = f"rl[{min(rls):.1f},{max(rls):.1f}]" if rls else "rl[--]"
        print(f"OK {sid:34s} M={M:.3f} rmse={p['reg_fit_rmse_px']:5.1f} "
              f"nfov={nfov:3d} {clr} {rlr}", flush=True)
        ok += 1
    print(f"\n{ok}/{len(configs)} registered")


if __name__ == "__main__":
    main()
