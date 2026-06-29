"""Drive route2_flat_edge over the 1<M<2 configs whose 2B serpent die is in FOV
(from diag_2b_intermediate_fov: 9 configs, M=1.00-1.40). For each, measure at the
sharpest aperture (F8 family). Emit a results CSV + the full per-edge dump so the
parent can build the yield / ceiling / agreement tables.

Runs on nufan. Each config: register (already cached behaviour) + locate 2B +
detect line edges + per-edge MTF50 (erf+iso) + rim + top/bottom agreement.
"""
from __future__ import annotations
import csv, sys, os
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import route2_flat_edge as R2  # noqa: E402
import lib_2b as L  # noqa: E402

# (lens, mag, aperture) for the 9 in-FOV configs. Aperture = sharpest/F8 family.
# Also run F11 for a couple to test discrimination across focus/aperture.
INFOV = [
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x", "1_1", "F8"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x", "1_1", "F8"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35", "1_1.16", "F8"),
    ("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + 5T + 6T", "1.14_1", "F8"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T", "1.27_1", "F8"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T", "1.3_1", "F8"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x", "1.4_1", "F8"),
    # discrimination cross-checks: a soft aperture on a couple of in-FOV configs
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x", "1.4_1", "F16"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T", "1.3_1", "F16"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T", "1.27_1", "F16"),
]


def main():
    shard = os.environ.get("SHARD")
    items = list(enumerate(INFOV))
    if shard:
        i, n = map(int, shard.split("/"))
        items = [(k, v) for k, v in items if k % n == i]
    out_rows = []
    for k, (lens, mag, ap) in items:
        r = R2.measure_config(lens, mag, ap)
        print(R2.fmt(r), flush=True)
        if not r.get("ok"):
            out_rows.append(dict(lens=lens, mag=mag, ap=ap, ok=False, reason=r.get("reason"),
                                 M="", ceil_cypx="", n_edges="", n_pass="", median_erf="",
                                 median_lpmm="", n_over="", n_rim="", agree_ratio="",
                                 rising_med="", falling_med=""))
            continue
        passing = [x for x in r["results"] if x["mtf50_erf"]]
        rising = [x["mtf50_erf"] for x in passing if x["kind"] == "rising"]
        falling = [x["mtf50_erf"] for x in passing if x["kind"] == "falling"]
        allm = [x["mtf50_erf"] for x in passing]
        n_over = sum(1 for x in passing if x["over_erf"] and x["over_erf"] > 1.0)
        n_rim = sum(1 for x in passing if x["rim"])
        med = float(np.median(allm)) if allm else None
        agree = (max(np.median(rising), np.median(falling)) /
                 min(np.median(rising), np.median(falling))) if rising and falling else None
        out_rows.append(dict(
            lens=lens, mag=mag, ap=ap, ok=True, reason="",
            M=round(r["M"], 3), ceil_cypx=round(r["ceil_cypx"], 4),
            ceil_lpmm=round(r["ceil_lpmm"], 1), n_eff=round(r["n_eff"], 2),
            line_pitch=r["line_pitch_est"], n_edges=r["n_edges"], n_pass=len(passing),
            median_erf=round(med, 4) if med else "",
            median_lpmm=round(med * r["M"] * L.LPMM_PER_CYPX, 1) if med else "",
            range_erf=f"[{min(allm):.3f},{max(allm):.3f}]" if allm else "",
            n_over=f"{n_over}/{len(passing)}", n_rim=f"{n_rim}/{len(passing)}",
            agree_ratio=round(agree, 2) if agree else "",
            rising_med=round(float(np.median(rising)), 4) if rising else "",
            falling_med=round(float(np.median(falling)), 4) if falling else ""))
    out = HERE / (f"route2_intermediate_results{'_' + shard.replace('/', 'of') if shard else ''}.csv")
    if out_rows:
        keys = sorted({k for row in out_rows for k in row})
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for row in out_rows:
                w.writerow({kk: row.get(kk, "") for kk in keys})
        print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    main()
