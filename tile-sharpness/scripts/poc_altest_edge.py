"""Stage AltEst approach 5 — robust direction-aware edge MTF at a fixed SENSOR
frequency. Reuses production slanted_edge + edge_aggregate (read-only) on the atlas's
designated cyan SLANTED-EDGE die feature (die type (0,3)) — a true reflectance edge,
NOT the groove scribe (the groove over-reads via emboss; REPORT §E.4). MTF50 is in
sensor cy/px by construction, so this IS a fixed-sensor-frequency read; we also report
the subject-space MTF50 (x M) and the diffraction-ceiling headroom.

Per config: register, find in-FOV (0,3) bars, refine the left (rising) + right (falling)
vertical edges, measure each at its own best-focus frame, aggregate direction-aware
(edge_aggregate.aggregate_conservative, min_direction) — the matte-reframed clean read.

Sharded by SHARD; sparse feature so coverage is reported honestly.
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
import poc_altest_lib as L

WA = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/wafer-atlas/scripts")
spec = importlib.util.spec_from_file_location("bar4d", WA / "diag_4d_bar_edges.py")
bar4d = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(WA))
spec.loader.exec_module(bar4d)

from tile_sharpness.methods import slanted_edge as SE  # noqa: E402
from tile_sharpness.methods import edge_aggregate as EA  # noqa: E402
from tile_sharpness import optics  # noqa: E402

SUBSET = HERE / "poc_comb_chain_subset.csv"
OUT = HERE / "poc_comb_chain_out" / "altest"


def ap_to_n(a): return float(a.replace("F", "").replace("f_", "").replace("f", ""))


def short_id(c):
    lens = c["lens"]
    base = (lens.split(" + ")[0]
            .replace("NIKKOR Z MC 105mm f_2.8 VR S", "Z105")
            .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
            .replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "S105")
            .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "S150")
            .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100400"))
    acc = ""
    if " + " in lens:
        acc = "+" + lens.split(" + ", 1)[1].replace(" ", "").replace("Olympus", "") \
            .replace("Canon", "C").replace("Nikon", "")
    return f"{base}{acc}_{c['mag_label']}".replace(" ", "").replace("/", "")


def main():
    with SUBSET.open() as fh:
        configs = list(csv.DictReader(fh))
    shard = os.environ.get("SHARD")
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        configs = [c for k, c in enumerate(configs) if k % n == i]
    OUT.mkdir(parents=True, exist_ok=True)
    rows, edge_rows = [], []
    for c in configs:
        cid = f"{c['lens']} | {c['mag_label']} | {c['aperture']}"
        sid = short_id(c); sd = Path(c["sample"]).parent
        p, M, jpgs = L.register_config(sd)
        if p is None:
            print(f"DROP {cid}", flush=True); continue
        n_marked = ap_to_n(c["aperture"]); n_eff = optics.effective_fnumber(n_marked, M)
        ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / 229.9
        bars = bar4d.find_bars(p)
        if not bars:
            print(f"  {sid} M={M:.2f}: no in-FOV SE bar", flush=True); continue
        # box around all bars to scan best focus once
        recs = []
        for (col, row, x0, y0, x1, y1) in bars:
            box = (int(x0), int(y0), int(x1), int(y1))
            bf = L.best_focus_frame(jpgs, box, topk=1)
            if not bf:
                continue
            seq, jp = bf[0]
            g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
            if g is None:
                continue
            for side, kind in (("left", "rising"), ("right", "falling")):
                r = bar4d.refine_vertical_edge(g, x0, y0, x1, y1, side=side)
                if r is None:
                    continue
                seg, off_axis, _ = r
                if not (0.5 < off_axis < 12):   # need a slanted edge for ESF binning
                    continue
                m = SE.mtf50_step_erf(g, seg)
                if m is None:
                    continue
                over = m / ceil_cypx if ceil_cypx > 0 else None
                recs.append(dict(mtf50=float(m), kind=kind, over=over, flag=False))
                edge_rows.append(dict(config=cid, sid=sid, M=M, col=col, row=row,
                                      side=side, kind=kind, mtf50=float(m),
                                      mtf50_subj=float(m) * M, over=over, off_axis=off_axis))
        if not recs:
            print(f"  {sid} M={M:.2f}: bars present but no valid edge MTF", flush=True); continue
        agg = EA.aggregate_conservative(recs, over_ceiling=1.05, combine="min_direction")
        if agg is None:
            continue
        rows.append(dict(config=cid, sid=sid, M=M, n_eff=n_eff, n_marked=n_marked,
                         ceil_cypx=ceil_cypx, mtf50_cypx=agg["mtf50"],
                         mtf50_subj=agg["mtf50"] * M, over=agg["mtf50"] / ceil_cypx,
                         rising_med=agg["rising_med"], falling_med=agg["falling_med"],
                         n_edges=agg["n"]))
        print(f"  {sid} M={M:.2f} N_eff={n_eff:.1f} edgeMTF50={agg['mtf50']:.3f} cy/px "
              f"(subj {agg['mtf50']*M:.3f}) ceil={ceil_cypx:.3f} over={agg['mtf50']/ceil_cypx:.2f} "
              f"n={agg['n']}", flush=True)
    tag = (shard or "0_1").replace("/", "_")
    with (OUT / f"edge_shard_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "sid", "M", "n_eff", "n_marked",
                                           "ceil_cypx", "mtf50_cypx", "mtf50_subj",
                                           "over", "rising_med", "falling_med", "n_edges"])
        w.writeheader(); w.writerows(rows)
    with (OUT / f"edge_edges_shard_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "sid", "M", "col", "row", "side",
                                           "kind", "mtf50", "mtf50_subj", "over", "off_axis"])
        w.writeheader(); w.writerows(edge_rows)
    print(f"WROTE edge shard {tag}: {len(rows)} configs, {len(edge_rows)} edges", flush=True)


if __name__ == "__main__":
    main()
