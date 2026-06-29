"""Stage T_n — step 1: re-extract the comb amplitudes A_n on the SATURATION channel.

UNTRACKED / exploratory. Mirrors poc_comb_chain_a1_driver.py exactly (same atlas
registration, same M-aware A5 pad-fundamental discovery, same comb prediction + maze,
same bounded-Michelson read), but decodes the SATURATION channel (HSV S) instead of
luma. Saturation suppresses the achromatic speculars (diag-2 winner) so the intrinsic
harmonic content T_n has the best chance of being stable.

For focus selection we keep the achromatic Laplacian-variance criterion (focus is a
luma property), but we store the SATURATION ROI for the FFT reads.

Emits one long-table row per (config, region, rung) with the same columns as a1_all
plus pitch-cluster bookkeeping done downstream. Sharded like run_a1.sh.

Usage (nufan):
  SHARD=0/8 RANK_CONFIGS=subset.csv RANK_OUT=out/tn_shard_0.csv \
    PYTHONPATH=<src> python scripts/poc_comb_chain_tn_extract.py
"""
from __future__ import annotations

import csv
import importlib.util
import os
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402

from tile_sharpness.methods.periodic_fft import periodic_contrast, derotate  # noqa: E402
from tile_sharpness import optics  # noqa: E402

NYQ = L.NYQUIST
MAZE_HARMONICS = 4   # read maze fundamental + 2f,3f,4f so we can measure its EVEN (N=2)
                     # content (the report's prediction) and overlap pad/maze at shared f_px


def read_comb_local(frames, theta_deg, M, n_marked, *, label_prefix=""):
    """Local copy of L.read_comb_contrast that ALSO reads MAZE harmonics 2f,3f,4f (the
    committed lib only reads the maze fundamental). Same A5 pad-fundamental discovery and
    bounded-Michelson read; operates on whatever channel the frames carry (here: sat)."""
    if not frames:
        return []
    der_frames = [(lv, seq, derotate(roi.astype(np.float64), theta_deg))
                  for lv, seq, roi in frames]
    der_bf = der_frames[0][2]
    pad_rec, mb = L.discover_pad_fundamental(der_bf, M)
    n_eff = optics.effective_fnumber(n_marked, M)
    samples = []

    def _read_at(f_subj, feature, order):
        f_px = L.subj_to_px(f_subj, M)
        if not (0.02 < f_px < NYQ - 1e-3):
            return None
        pitch = 1.0 / f_px
        best = None
        for _lv, _seq, der in der_frames:
            c = periodic_contrast(der, pitch_px=pitch, axis="auto")
            if c and (best is None or c["contrast"] > best["contrast"]):
                best = c
        if best is None:
            return None
        f_sensor_lpmm = f_px * L.LPMM_PER_CYPX
        ceil = optics.diffraction_mtf_at(f_sensor_lpmm, n_eff)
        return dict(feature=feature, harmonic_order=order,
                    f_subj_lpmm=float(f_subj), f_px=float(f_px),
                    contrast=float(best["contrast"]), snr=float(best["snr"]),
                    ceiling=float(ceil), over_ceiling=float(best["contrast"] - ceil))

    if pad_rec is not None:
        pad_f1_subj = L.px_to_subj(pad_rec["f0_cy_per_px"], M)
        for feature, order, f_subj in L.predict_comb_subj(pad_f1_subj, max_order=7):
            s = _read_at(f_subj, feature, order)
            if s is not None:
                samples.append(s)
    # maze comb: fundamental + harmonics (M-invariant subject freq * order)
    if mb is not None:
        for order in range(1, MAZE_HARMONICS + 1):
            s = _read_at(L.MAZE_SUBJ_LPMM * order, "maze", order)
            if s is not None:
                samples.append(s)
    for s in samples:
        s["label"] = label_prefix
    return samples


def _ap_to_n(aperture: str) -> float:
    return float(aperture.replace("F", "").replace("f_", "").replace("f", ""))


def sat_of(bgr):
    """HSV saturation S in 0..255 (same decode as contrast_color / t1_hmtf)."""
    b = bgr[:, :, 0].astype(np.float64)
    g = bgr[:, :, 1].astype(np.float64)
    r = bgr[:, :, 2].astype(np.float64)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    return np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0) * 255.0


def topk_per_region_sat(jpgs, regions, topk=4):
    """One COLOR decode per frame; focus-rank ROIs by luma Laplacian variance but keep
    the SATURATION ROI (so the comb FFT reads the specular-suppressed channel)."""
    import heapq
    boxes = {i: [int(v) for v in r["bbox"]] for i, r in enumerate(regions)}
    heaps = {i: [] for i in range(len(regions))}
    for seq, jp in enumerate(jpgs):
        bgr = cv2.imread(str(jp), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        for i, (x0, y0, x1, y1) in boxes.items():
            sub = bgr[y0:y1, x0:x1]
            if sub.size == 0 or min(sub.shape[:2]) < 16:
                continue
            # focus rank on luma; store the specular-suppressed saturation ROI.
            roi_g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
            lv = float(cv2.Laplacian(roi_g.astype(np.float32), cv2.CV_32F).var())
            roi_s = sat_of(sub)   # crop-only saturation (fast; full-frame sat was the bottleneck)
            h = heaps[i]
            if len(h) < topk:
                heapq.heappush(h, (lv, seq, roi_s.copy()))
            elif lv > h[0][0]:
                heapq.heapreplace(h, (lv, seq, roi_s.copy()))
    return {i: sorted(h, reverse=True) for i, h in heaps.items()}


def run_config(c):
    sweep_dir = Path(c["sample"]).parent
    jpgs = sorted(sweep_dir.glob("*.jpg")) + sorted(sweep_dir.glob("*.JPG"))
    if not jpgs:
        return None, "no_frames"
    p = apf.register(jpgs)
    if p is None:
        return None, "reg_failed"
    M = p["scale"] / apf.M_ANCHOR_SCALE
    theta = p["theta_deg"]
    if not (0.2 < M < 3.5):
        return None, f"scale_collapse_M={M:.2f}"
    regions = apf.enumerate_regions(p, p["scale"])
    regions = [r for r in regions if r["cls"] in ("magenta", "cyan")]
    if not regions:
        return None, "no_regions"
    n_marked = _ap_to_n(c["aperture"])
    framed = topk_per_region_sat(jpgs, regions, topk=4)
    rows = []
    for ri, reg in enumerate(regions):
        frames = framed.get(ri) or []
        samples = read_comb_local(frames, theta, M, n_marked,
                                   label_prefix=reg["label"])
        for s in samples:
            s.update(zone=reg["zone"], cls=reg["cls"], region=reg["label"])
            rows.append(s)
    return dict(M=M, theta=theta, rmse=p["reg_fit_rmse_px"], n_marked=n_marked,
                n_regions=len(regions), rows=rows), "ok"


def main():
    cfg_csv = Path(os.environ["RANK_CONFIGS"])
    out_csv = Path(os.environ["RANK_OUT"])
    shard = os.environ.get("SHARD")
    with cfg_csv.open() as fh:
        configs = list(csv.DictReader(fh))
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        configs = [c for k, c in enumerate(configs) if k % n == i]
    fields = ["config", "lens", "mag_label", "aperture", "M", "rmse", "region",
              "cls", "zone", "feature", "harmonic_order", "f_subj_lpmm", "f_px",
              "contrast", "snr", "ceiling", "over_ceiling"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for c in configs:
            config_id = f"{c['lens']} | {c['mag_label']} | {c['aperture']}"
            print(f"=== {config_id} ===", flush=True)
            try:
                res, status = run_config(c)
            except Exception as e:  # noqa: BLE001
                print(f"  EXC {e}", flush=True)
                continue
            if res is None:
                print(f"  DROPPED ({status})", flush=True)
                continue
            for s in res["rows"]:
                w.writerow(dict(
                    config=config_id, lens=c["lens"], mag_label=c["mag_label"],
                    aperture=c["aperture"], M=round(res["M"], 4),
                    rmse=round(res["rmse"], 2), region=s["region"], cls=s["cls"],
                    zone=s["zone"], feature=s["feature"],
                    harmonic_order=s["harmonic_order"],
                    f_subj_lpmm=round(s["f_subj_lpmm"], 2), f_px=round(s["f_px"], 4),
                    contrast=round(s["contrast"], 4), snr=round(s["snr"], 2),
                    ceiling=round(s["ceiling"], 4), over_ceiling=round(s["over_ceiling"], 4)))
            fh.flush()
            print(f"  M={res['M']:.3f} rmse={res['rmse']:.2f} regions={res['n_regions']} "
                  f"samples={len(res['rows'])}", flush=True)


if __name__ == "__main__":
    main()
