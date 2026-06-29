"""A1 driver: per-config atlas-predicted harmonic-comb spectrum -> tidy long table.

Reuses atlas_periodic_fft's registration + ROI enumeration + one-decode-per-frame
topk-focus plumbing, but instead of locking ONE discovered fundamental, it:
  1. discovers the pad fundamental in an M-aware band (A5),
  2. predicts the comb {f1, 2f1, ..., 7f1} in subject space + the maze (M physics),
  3. reads bounded Michelson contrast at each rung over the best-focus frames,
  4. emits one long-table row per (config, region, rung).

Sharded like run_periodic_rank.sh: env SHARD="i/N", RANK_CONFIGS, RANK_OUT.

Usage (on nufan):
  SHARD=0/6 RANK_CONFIGS=subset.csv RANK_OUT=out/a1_shard_0.csv \
    PYTHONPATH=<src> python scripts/poc_comb_chain_a1_driver.py
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


def _ap_to_n(aperture: str) -> float:
    return float(aperture.replace("F", "").replace("f_", "").replace("f", ""))


def topk_per_region(jpgs, regions, topk=4):
    """One decode per frame; keep topk sharpest ROIs per region (heap)."""
    import heapq
    boxes = {i: [int(v) for v in r["bbox"]] for i, r in enumerate(regions)}
    heaps = {i: [] for i in range(len(regions))}
    for seq, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        for i, (x0, y0, x1, y1) in boxes.items():
            roi = g[y0:y1, x0:x1]
            if roi.size == 0 or min(roi.shape) < 16:
                continue
            lv = float(cv2.Laplacian(roi.astype(np.float32), cv2.CV_32F).var())
            h = heaps[i]
            if len(h) < topk:
                heapq.heappush(h, (lv, seq, roi.copy()))
            elif lv > h[0][0]:
                heapq.heapreplace(h, (lv, seq, roi.copy()))
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
    # focus on magenta bond-pad arrays (primary periodic class) + cyan experimental
    regions = [r for r in regions if r["cls"] in ("magenta", "cyan")]
    if not regions:
        return None, "no_regions"
    n_marked = _ap_to_n(c["aperture"])
    framed = topk_per_region(jpgs, regions, topk=4)
    rows = []
    for ri, reg in enumerate(regions):
        frames = framed.get(ri) or []
        samples = L.read_comb_contrast(frames, theta, M, n_marked,
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
