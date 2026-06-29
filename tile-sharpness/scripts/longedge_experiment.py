"""Long-isolated-edge MTF50 experiment (height hypothesis + absolute metric).

For each config: register, locate the 4D dark-bar long vertical edges, then
  (1) EDGE-LENGTH SWEEP on the best-focus frame: measure mtf50_step_erf on centred
      sub-segments of increasing length -> test whether MTF50 depends on edge length.
  (2) FULL-LENGTH read per config -> cross-config discrimination + ceiling check.
  (3) optional SHARP-vs-DEFOCUSED control: full-length read on the sharpest vs a
      deliberately-defocused frame of the SAME config.

Output: JSONL rows (one per config x bar x edge x length) to OUT/<shard>.jsonl.
Subject lp/mm = cy/px x 229.9 x M. Ceiling: optics, N_eff = N*(1+M).

Shard: SHARD=i/n env over the config list. Run on nufan.
"""
from __future__ import annotations
import importlib.util, sys, json, os
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
TS = HERE.parent
WA = TS.parent / "wafer-atlas"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.lsf import Segment
from tile_sharpness.methods.long_edge import refine_bar_edge, subsegment
from tile_sharpness.methods.slanted_edge import mtf50_step_erf, mtf50_long_edge
from tile_sharpness import optics

_s = importlib.util.spec_from_file_location("reg_auto", WA / "scripts" / "reg_auto.py")
reg_auto = importlib.util.module_from_spec(_s); _s.loader.exec_module(reg_auto)
_a = importlib.util.spec_from_file_location("acm", HERE / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_a); _a.loader.exec_module(acm)

ATLAS = json.load(open(WA / "atlas.json"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
LPMM_PER_CYPX = 229.9
SE_BBOX = ATLAS["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]["bbox_uv"]
LENGTHS = [30, 50, 80, 120, 180, 250, 999]   # 999 -> full edge
OUT = Path(os.environ.get("OUT", HERE.parent / "out_longedge"))
OUT.mkdir(parents=True, exist_ok=True)

# (label, relative config dir, aperture N, expected tier) -- the 4D bar must be in FOV.
CONFIGS = [
    ("AF200 1:1 F8",        "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F8", 8.0, "sharp-bare"),
    ("AF200 1:1 F11",       "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11", 11.0, "sharp-bare"),
    ("Sigma150 1:1 F8",     "Sigma APO Macro 150mm F2.8 EX DG OS HSM/1_1/F8", 8.0, "sharp-bare"),
    ("Sigma105 1:1 F8",     "Sigma Macro 105mm F2.8 EX DG OS HSM/1_1/F8", 8.0, "sharp-bare"),
    ("105VR 1:1 F8",        "NIKKOR Z MC 105mm f_2.8 VR S/1_1/F8", 8.0, "sharp-bare"),
    ("AF60 1:1 F8",         "Nikon AF Micro-Nikkor 60mm f_2.8D/1_1/F8", 8.0, "sharp-bare"),
    ("100-400+6T F8",       "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T/1.27_1/F8", 8.0, "soft-diopter"),
    ("100-400+5T F8",       "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 5T/1_1.19/F8", 8.0, "soft-diopter"),
    ("100-400+MCON35 F8",   "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35/1_1.16/F8", 8.0, "soft-diopter"),
    ("100-400+Canon500D F8","NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D/1.07_1/F8", 8.0, "soft-diopter"),
]


def find_bars(p):
    u0, v0, u1, v1 = SE_BBOX
    out = []
    for col in range(0, 11):
        for row in range(0, 6):
            if (col % 4, row % 4) != (0, 3):
                continue
            corners = [(reg_auto.grid_xy_distorted(col + u, row + v, p) if "k1" in p
                        else reg_auto.af.grid_xy(col + u, row + v, p, ATLAS))
                       for (u, v) in [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
            xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
            m = 90
            if m < min(xs) and max(xs) < IMAGE_W - m and m < min(ys) and max(ys) < IMAGE_H - m:
                out.append((col, row, (min(xs), min(ys), max(xs), max(ys))))
    return out


def focus_ranked(jpgs, cx, cy):
    """Return frames ranked by roi_lapvar at (cx,cy): [(lapvar, gray), ...] desc."""
    scored = []
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        scored.append((acm.roi_lapvar(g, int(cx), int(cy), half=90), g))
    scored.sort(key=lambda t: -t[0])
    return scored


def measure(label, rel, N, tier, rows):
    d = RAW / rel
    jpgs = sorted(d.glob("*.jpg"))
    if not jpgs:
        rows.append(dict(config=label, status="no_jpgs")); return
    aff = acm.register(jpgs)
    if aff is None:
        rows.append(dict(config=label, status="reg_failed")); return
    M = aff["scale"] / acm.M_ANCHOR_SCALE
    n_eff = N * (1.0 + M)
    ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / LPMM_PER_CYPX
    ceil_sub = optics.diffraction_mtf50_sensor_lpmm(n_eff) * M   # subject lp/mm
    bars = find_bars(aff)
    base = dict(config=label, tier=tier, N=N, M=round(M, 4), rmse=round(aff["reg_fit_rmse_px"], 2),
                n_eff=round(n_eff, 2), ceil_cypx=round(ceil_cypx, 4), ceil_sub=round(ceil_sub, 2),
                n_bars=len(bars))
    if not bars:
        rows.append({**base, "status": "no_bar_in_fov"}); return
    for (col, row, bb) in bars:
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        ranked = focus_ranked(jpgs, cx, cy)
        if not ranked:
            continue
        sharp = ranked[0][1].astype(np.float32)
        # defocus control: the worst-focus frame (lowest lapvar) at this bar
        defoc = ranked[-1][1].astype(np.float32)
        for side in ("left", "right"):
            r = refine_bar_edge(sharp, bb, side=side)
            if r is None:
                rows.append({**base, "die": f"c{col}r{row}", "side": side, "status": "no_edge"})
                continue
            seg, off = r
            full_len = seg.length_px
            for Lreq in LENGTHS:
                sub = subsegment(seg, Lreq)
                # primary: recentred long-edge erf; cross-check: fixed-line step erf
                m_rc = mtf50_long_edge(sharp, sub, half_window_px=16)
                m_fl = mtf50_step_erf(sharp, sub, half_window_px=30)
                rows.append({**base, "die": f"c{col}r{row}", "side": side,
                             "off_axis_deg": round(off, 2), "full_len_px": round(full_len, 1),
                             "len_req": Lreq, "len_px": round(sub.length_px, 1),
                             "mtf50_recentred_cypx": (round(m_rc, 4) if m_rc else None),
                             "mtf50_fixedline_cypx": (round(m_fl, 4) if m_fl else None),
                             "sub_lpmm_rc": (round(m_rc * LPMM_PER_CYPX * M, 2) if m_rc else None),
                             "over_ceiling": (bool(m_rc and m_rc > ceil_cypx * 1.02) if m_rc else None),
                             "status": "ok"})
            # sharp-vs-defocus control at FULL length (recentred)
            sd = refine_bar_edge(defoc, bb, side=side)
            m_def = mtf50_long_edge(defoc, sd[0], half_window_px=16) if sd else None
            m_sharp_full = mtf50_long_edge(sharp, seg, half_window_px=16)
            rows.append({**base, "die": f"c{col}r{row}", "side": side, "status": "focus_control",
                         "mtf50_sharp_full": (round(m_sharp_full, 4) if m_sharp_full else None),
                         "mtf50_defocus_full": (round(m_def, 4) if m_def else None),
                         "lapvar_sharp": round(float(ranked[0][0]), 1),
                         "lapvar_defoc": round(float(ranked[-1][0]), 1)})


def main():
    shard = os.environ.get("SHARD", "0/1")
    i, n = (int(x) for x in shard.split("/"))
    rows = []
    for idx, cfg in enumerate(CONFIGS):
        if idx % n != i:
            continue
        try:
            measure(*cfg, rows)
        except Exception as e:
            rows.append(dict(config=cfg[0], status=f"error:{type(e).__name__}:{e}"))
        print(f"[{shard}] done {cfg[0]}", flush=True)
    fn = OUT / f"shard_{i}of{n}.jsonl"
    with open(fn, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"[{shard}] wrote {fn} ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
