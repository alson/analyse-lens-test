"""(1) MATERIAL CHECK — matte serpent vs shiny bond/solder pads, same frame.

The task's background asserts the 2B "serpent" (die type (2,1)) is a FLAT MATTE
feature (dielectric/mask/poly), and the shiny bits are the bond/solder pads. If the
serpent is matte its edges are diffuse clean steps → a "rim" flag on the edge metric
is spurious. If instead it shows metal glints, the over-read could be a real specular
rim.

This script registers each in-FOV 6B config, locates (via the atlas) BOTH the serpent
experimental block and the bond-pad arrays in the SAME frame, and compares specular-
glint statistics:
  * saturated-pixel fraction (>= sat_thr DN, default 250) — specular highlights clip;
  * local max-vs-median ratio (P99.9 / median) — glints are isolated bright outliers;
  * highlight excess: fraction of pixels above (median + 4·robust-sigma).
The serpent's BRIGHT LINES (its metal) are isolated from the dark substrate so the
glint comparison is fair: serpent-bright-pixels vs pad-bright-pixels.

Runs on nufan. Output: a per-config table + a verdict line.
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path
import numpy as np, cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_2b as L  # noqa: E402

ATLAS = json.load(open(HERE.parent / "atlas.json"))
SAT_THR = 250.0

# A few in-FOV 6B configs spanning the M range (from diag_2b_intermediate_fov).
CONFIGS = [
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x", "1_1", "F8"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35", "1_1.16", "F8"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T", "1.27_1", "F8"),
]


def die_uv_to_img(col, row, u, v, aff):
    return L.reg_auto.grid_xy_distorted(col + u, row + v, aff)


def region_bbox(col, row, bbox_uv, aff):
    u0, v0, u1, v1 = bbox_uv
    cor = [die_uv_to_img(col, row, u, v, aff) for u, v in
           [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
    xs = [c[0] for c in cor]; ys = [c[1] for c in cor]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def glint_stats(roi, bright_only=True):
    """Specular-glint statistics on an ROI. If bright_only, compute the bright-metal
    sub-population (pixels above the ROI's 70th percentile) so we compare the metal of
    each feature, not the dark substrate."""
    a = roi.astype(np.float32).ravel()
    if a.size < 50:
        return None
    if bright_only:
        thr = np.percentile(a, 70)
        b = a[a >= thr]
        if b.size < 20:
            b = a
    else:
        b = a
    med = float(np.median(b))
    mad = float(np.median(np.abs(b - med))) + 1e-6
    rsig = 1.4826 * mad
    sat_frac = float(np.mean(a >= SAT_THR))                 # over FULL ROI
    p999 = float(np.percentile(b, 99.9))
    glint_ratio = p999 / (med + 1e-6)
    hi_excess = float(np.mean(b > med + 4 * rsig))
    return dict(n=int(a.size), n_bright=int(b.size), bright_med=med,
                sat_frac=sat_frac, glint_ratio=glint_ratio, hi_excess=hi_excess,
                p999=p999, max=float(a.max()))


def serpent_line_strip(block_derot):
    """Isolate the matte serpent horizontal-LINE band (NOT the whole experimental
    block, which also holds bright clipping bond-pad structure). The lines live in the
    upper region of the 2B block; central x dodges the flanking pad columns. Mirrors
    diag_2b_serpent_profile.py."""
    H, W = block_derot.shape
    sx0, sx1 = int(0.18 * W), int(0.78 * W)
    sy0, sy1 = int(0.06 * H), int(0.30 * H)
    return block_derot[sy0:sy1, sx0:sx1]


def measure(lens, mag, ap):
    ap_dir = L.RAW / lens / mag / ap
    rmse, aff, jp0, jpgs = L.register_best(ap_dir)
    if aff is None:
        return dict(config=f"{lens}|{mag}", ok=False, reason="reg-fail")
    info = L.get_block(jp0, aff, want_type=(2, 1), derotate=True)
    if info is None:
        return dict(config=f"{lens}|{mag}", ok=False, reason="no-2b")
    g = info["full"]
    col = int("".join(c for c in info["label"] if c.isdigit()))
    row = "ABCDEF".index(info["label"][-1])
    fi = ATLAS["die_types"]["(2, 1)"]["feature_inventory"]
    # SERPENT = the matte horizontal-line band inside the experimental block (the
    # actual feature under test), NOT the whole block. PADS = the bond_pad arrays.
    serp = serpent_line_strip(info["block"])
    serp_st = glint_stats(serp, bright_only=True)
    # bright/dark levels of the serpent band (the matte-vs-clip discriminator)
    prof = serp.mean(axis=1)
    serp_bright = float(np.percentile(prof, 85))
    serp_dark = float(np.percentile(prof, 15))
    pad_sts = []
    for bp in fi["bond_pads"]:
        px0, py0, px1, py1 = region_bbox(col, row, bp["bbox_uv"], aff)
        roi = g[max(0, py0):py1, max(0, px0):px1]
        st = glint_stats(roi, bright_only=True)
        if st:
            pad_sts.append(st)
    if not serp_st or not pad_sts:
        return dict(config=f"{lens}|{mag}", ok=False, reason="roi-empty")
    # aggregate the pad arrays (worst / brightest glint)
    pad_glint = max(s["glint_ratio"] for s in pad_sts)
    pad_sat = max(s["sat_frac"] for s in pad_sts)
    pad_hi = max(s["hi_excess"] for s in pad_sts)
    pad_bright_med = float(np.median([s["bright_med"] for s in pad_sts]))
    return dict(config=f"{lens}|{mag}", ok=True, die=info["label"], rmse=round(rmse, 2),
                serp_glint=round(serp_st["glint_ratio"], 3), pad_glint=round(pad_glint, 3),
                serp_sat=round(serp_st["sat_frac"], 5), pad_sat=round(pad_sat, 5),
                serp_hi=round(serp_st["hi_excess"], 4), pad_hi=round(pad_hi, 4),
                serp_max=round(serp_st["max"], 0), pad_max=round(max(s["max"] for s in pad_sts), 0),
                serp_bright_med=round(serp_st["bright_med"], 1),
                serp_line_bright=round(serp_bright, 1), serp_line_dark=round(serp_dark, 1),
                pad_bright_med=round(pad_bright_med, 1))


def main():
    rows = []
    for lens, mag, ap in CONFIGS:
        r = measure(lens, mag, ap)
        rows.append(r)
        if not r["ok"]:
            print(f"{r['config']}: FAIL ({r['reason']})", flush=True); continue
        print(f"{r['config']} die={r['die']} rmse={r['rmse']}\n"
              f"   serpent-LINE level: bright={r['serp_line_bright']:.0f} dark={r['serp_line_dark']:.0f} DN "
              f"(matte mid-gray if << 255);  pad bright-median={r['pad_bright_med']:.0f} DN\n"
              f"   GLINT ratio (P99.9/med, bright pop):  serpent={r['serp_glint']:.2f}  pad={r['pad_glint']:.2f}\n"
              f"   SAT frac (>= {SAT_THR:.0f} DN):           serpent={r['serp_sat']:.4%}  pad={r['pad_sat']:.4%}\n"
              f"   HI-excess (>med+4sig):                serpent={r['serp_hi']:.3f}  pad={r['pad_hi']:.3f}\n"
              f"   max DN:                               serpent={r['serp_max']:.0f}  pad={r['pad_max']:.0f}",
              flush=True)
    out = HERE / "study_material_glint.csv"
    ok = [r for r in rows if r.get("ok")]
    if ok:
        keys = sorted({k for r in ok for k in r})
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
            for r in ok:
                w.writerow({k: r.get(k, "") for k in keys})
    # verdict
    if ok:
        serp_lvl = np.median([r["serp_line_bright"] for r in ok])
        pad_lvl = np.median([r["pad_bright_med"] for r in ok])
        serp_sat = np.median([r["serp_sat"] for r in ok])
        pad_sat = np.median([r["pad_sat"] for r in ok])
        # The matte discriminator: the serpent's BRIGHT LINES sit well below clip
        # (no specular highlight), while the bond pads clip / saturate.
        matte = serp_lvl < 0.7 * 255 and serp_sat < max(1e-9, 0.5 * pad_sat + 1e-6)
        verdict = ("MATTE serpent (lines are diffuse mid-gray, well below clip; "
                   "the shiny clipping bits are the bond/solder pads). A 'rim' flag on a "
                   "serpent edge is therefore spurious." if matte else
                   "serpent shows metal-like glints — rim could be real")
        print(f"\nVERDICT: serpent bright-line level {serp_lvl:.0f} DN vs pad bright {pad_lvl:.0f} DN; "
              f"serpent sat-frac {serp_sat:.4%} vs pad {pad_sat:.4%} "
              f"(median over {len(ok)} configs).\n  => {verdict}", flush=True)
        print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
