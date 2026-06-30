"""Smoke test for poc_altest_lib: verify _cum_vec, same-patch resampling, PSD ratio."""
import sys
from pathlib import Path
import numpy as np
import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_altest_lib as L

# 1. _cum_vec matches scalar _cum
af = L.reg_auto.af
d4 = L.reg_auto.D_COL
ks = np.array([0.0, 0.5, 1.0, 2.3, 4.0, 5.7, 9.9])
ref = np.array([af._cum(d4, float(k)) for k in ks])
vec = L._cum_vec(d4, ks)
print("cum match:", np.allclose(ref, vec), "maxerr", np.max(np.abs(ref - vec)))

OUT = HERE / "poc_comb_chain_out" / "altest"
OUT.mkdir(parents=True, exist_ok=True)

configs = {
    "bare105_M1": "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Sigma Macro 105mm F2.8 EX DG OS HSM/1_1/F8",
    "105+TC2001_M2": "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001/2_1/F11",
}
RECT = (4.0, 2.0, 5.0, 3.0)
SPU = 600

patches = {}
for name, sd in configs.items():
    p, M, jpgs = L.register_config(sd)
    print(f"{name}: M={M:.3f} rmse={p['reg_fit_rmse_px']:.2f} nframes={len(jpgs)}")
    corners = [L.reg_auto.grid_xy_distorted(c, r, p)
               for (c, r) in [(RECT[0], RECT[1]), (RECT[0], RECT[3]),
                              (RECT[2], RECT[1]), (RECT[2], RECT[3])]]
    xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
    box = (min(xs), min(ys), max(xs), max(ys))
    bf = L.best_focus_frame(jpgs, box, topk=1)
    if not bf:
        print("  no best frame"); continue
    seq, jp = bf[0]
    chan = L.decode_channel(jp, "sat")
    patch = L.atlas_rect_to_common_grid(chan, p, *RECT, samples_per_unit=SPU)
    if patch is None:
        print("  patch outside frame"); continue
    patches[name] = (patch, M, p)
    cv2.imwrite(str(OUT / f"smoke_{name}.png"), L.ccolor.norm8(patch))
    print(f"  patch {patch.shape} focus_seq={seq}")

if len(patches) == 2:
    (pa, Ma, _), (pb, Mb, _) = patches.values()
    fa, psa = L.radial_psd(pa)
    fb, psb = L.radial_psd(pb)
    ratio = psb / psa
    print("\ncommon-grid f (cy/px) | PSD_lowM | PSD_highM | ratio(high/low)")
    for i in range(2, len(fa), 6):
        print(f"  {fa[i]:.3f}  {psa[i]:.3e}  {psb[i]:.3e}  {ratio[i]:.2f}")
print("\nSMOKE OK")
