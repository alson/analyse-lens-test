"""Merge pad-edge ranking shards into a unified table, compute the over-read
fraction vs the groove `min` baseline, and emit the F8 top/bottom ranking.

Inputs:  out_padedge/{accessory,bare}_padedge*.csv  (shards merged)
         out_accessory_atlas/unified_ranking.csv    (groove `min` baseline)
Outputs: out_padedge/unified_ranking_padedge.csv
         prints F8 ranking + over-read comparison.
"""
from __future__ import annotations
import csv, glob, sys
from pathlib import Path

TS = Path(__file__).resolve().parent.parent
OUTD = TS / "out_padedge"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def merge_shards(stem):
    rows = {}
    for f in sorted(glob.glob(str(OUTD / f"{stem}*.csv"))):
        for r in csv.DictReader(open(f)):
            rows[(r["lens"], r["mag_label"], r["aperture"])] = r
    return rows


def main():
    acc = merge_shards("accessory_padedge")
    bare = merge_shards("bare_padedge")
    allrows = {("accessory", *k): v for k, v in acc.items()}
    allrows |= {("bare", *k): v for k, v in bare.items()}

    # unified output
    OUTD.mkdir(exist_ok=True)
    fields = ["kind", "config", "ap", "M", "n_eff", "ceiling_cypx", "centre_cypx",
              "centre_lpmm", "corner_mean_lpmm", "uniformity", "headroom",
              "n_targets", "regime", "status"]
    out = []
    for (kind, lens, mag, ap), r in allrows.items():
        cyp = fnum(r.get("centre_cypx"))
        ceil_c = fnum(r.get("ceiling_cypx"))
        hr = (cyp / ceil_c) if (cyp and ceil_c) else None
        regime = "OVER-READ" if (hr and hr > 1.02) else ("glass-ltd" if hr else "")
        out.append(dict(kind=kind, config=f"{lens} [{mag}]", ap=ap,
                        M=r.get("atlas_M", ""), n_eff=r.get("n_eff", ""),
                        ceiling_cypx=r.get("ceiling_cypx", ""),
                        centre_cypx=r.get("centre_cypx", ""),
                        centre_lpmm=r.get("centre", ""),
                        corner_mean_lpmm=r.get("corner_mean", ""),
                        uniformity=r.get("uniformity", ""),
                        headroom=(f"{hr:.2f}" if hr else ""),
                        n_targets=r.get("n_targets", ""), regime=regime,
                        status=r.get("status", "")))
    with open(OUTD / "unified_ranking_padedge.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in sorted(out, key=lambda x: (x["ap"], -(fnum(x["centre_lpmm"]) or -1))):
            w.writerow(r)

    # over-read fraction: how many F8/F11 centres read OVER the ceiling
    for ap_grp in (("F8", "F8.0"), ("F11", "F11.0")):
        oks = [r for r in out if r["ap"] in ap_grp and r["status"] == "ok" and fnum(r["centre_cypx"])]
        over = [r for r in oks if r["regime"] == "OVER-READ"]
        n = len(oks)
        print(f"PAD-EDGE over-read [{ap_grp[0]}]: {len(over)}/{n} centres OVER ceiling"
              + (f" = {len(over)/n*100:.0f}%" if n else ""))

    # F8 ranking by centre lp/mm (glass-ltd only at top)
    f8 = [r for r in out if r["ap"] in ("F8", "F8.0") and r["status"] == "ok" and fnum(r["centre_lpmm"])]
    f8.sort(key=lambda x: -(fnum(x["centre_lpmm"]) or -1))
    print("\n=== F8 pad-edge centre ranking (subject lp/mm) ===")
    print(f"{'centre':>7}{'corner':>7}{'unif':>6}{'hr':>5} {'regime':<10} config")
    for r in f8:
        print(f"{r['centre_lpmm']:>7}{r['corner_mean_lpmm']:>7}{r['uniformity']:>6}"
              f"{r['headroom']:>5} {r['regime']:<10} {r['config']}")


if __name__ == "__main__":
    main()
