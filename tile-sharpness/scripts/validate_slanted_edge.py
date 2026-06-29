"""Validate the super-resolved slanted-edge estimator against the diffraction
ceiling on real sweeps. For each config: register (atlas), then at centre + corners
take the best-focus shot and compare OLD lsf_mtf50(min) vs NEW mtf50_erf/mtf50_iso,
all in cy/px, against the ceiling. A correct estimator reads <= ceiling for
diffraction-limited configs.
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import cv2, numpy as np

TS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.lsf import cross_section, lsf_mtf50
from tile_sharpness.methods.slanted_edge import mtf50_erf, mtf50_iso
from tile_sharpness import optics
_s = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_s); _s.loader.exec_module(acm)

RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
CONFIGS = [
    ("AF200 1:1 F11 (anchor; sharp macro)", RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F11", 11.0, 1.0),
    ("105VR + 6T F8 (over-read 92lp/mm)", RAW / "NIKKOR Z MC 105mm f_2.8 VR S + 6T" / "1.4_1" / "F8", 8.0, None),
    ("Sigma150 + TC-2001 2:1 F11", RAW / "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001" / "2_1" / "F11", 11.0, None),
]


def main():
    for label, d, n_set, m_known in CONFIGS:
        jpgs = sorted(d.glob("*.jpg"))
        if not jpgs:
            print(f"{label}: no jpgs"); continue
        aff = acm.register(jpgs)
        if aff is None:
            print(f"{label}: REG FAILED"); continue
        M = aff["scale"] / acm.M_ANCHOR_SCALE
        scribes = acm.pick_scribes(aff)
        ceil = optics.diffraction_mtf50_sensor_lpmm(n_set * (1 + M)) / 229.9
        print(f"\n{label}\n  M_atlas={M:.3f} N_eff={n_set*(1+M):.1f} ceiling={ceil:.3f} cy/px  "
              f"(reg rmse {aff['reg_fit_rmse_px']:.2f})")
        # centre + 2 corners, best-focus per position
        for name in [k for k in ("centre", "TL", "BR") if k in scribes]:
            mx, my, seg = scribes[name]
            best = (-1.0, None)
            for jp in jpgs:
                g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
                if g is None:
                    continue
                lv = acm.roi_lapvar(g, mx, my)
                if lv > best[0]:
                    best = (lv, g)
            g = best[1]
            gf = g.astype(np.float32)
            prof = cross_section(gf, seg, half_window_px=acm.HALF_WIN, samples_per_pixel=acm.SPP)
            old = lsf_mtf50(prof, combine="min")
            erf_m = mtf50_erf(gf, seg, combine="min")
            erf_mean = mtf50_erf(gf, seg, combine="mean")
            iso_m = mtf50_iso(gf, seg, combine="min")
            def f(x): return f"{x:.3f}" if x else "  -  "
            flag = lambda x: "OVER" if (x and x > ceil * 1.02) else "ok"
            print(f"    {name:6} old={f(old)}[{flag(old)}]  erf_min={f(erf_m)}[{flag(erf_m)}]  "
                  f"erf_mean={f(erf_mean)}  iso_min={f(iso_m)}[{flag(iso_m)}]")


if __name__ == "__main__":
    main()
