"""Merge the min-method shards, quantify the mean->min over-read reduction, and
emit the unified BARE + ACCESSORY resolution ranking (combine='min').

Inputs (in out_accessory_atlas/):
  accessory_ranking.csv            mean-method accessory (for the comparison)
  accessory_ranking_min_shard*.csv min-method accessory shards
  bare_ranking_min_shard*.csv      min-method bare shards
Outputs:
  accessory_ranking_min.csv, bare_ranking_min.csv (merged)
  unified_ranking.csv  (bare+accessory, min)
"""
from __future__ import annotations
import csv, glob
from pathlib import Path

OUTDIR = Path(__file__).resolve().parent.parent / "out_accessory_atlas"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def merge(stem):
    rows, fields = {}, None
    for fn in sorted(glob.glob(str(OUTDIR / f"{stem}_shard*of*.csv"))):
        with open(fn) as f:
            r = csv.DictReader(f); fields = r.fieldnames
            for row in r:
                rows[(row["lens"], row["mag_label"], row["aperture"])] = row
    if not fields:
        return []
    out = [rows[k] for k in sorted(rows)]
    with (OUTDIR / f"{stem}.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(out)
    return out


def regime(h):
    if h is None:
        return "no-data"
    return "OVER-READ" if h >= 1.0 else ("diffraction-ltd" if h >= 0.85 else "glass-ltd")


def overread_frac(rows, ap):
    sub = [r for r in rows if r["aperture"] == ap and r["status"] == "ok" and fnum(r["centre_headroom"]) is not None]
    if not sub:
        return 0, 0
    over = sum(1 for r in sub if fnum(r["centre_headroom"]) >= 1.0)
    return over, len(sub)


def main():
    acc_min = merge("accessory_ranking_min")
    bare_min = merge("bare_ranking_min")
    acc_mean = list(csv.DictReader(open(OUTDIR / "accessory_ranking.csv")))
    print(f"merged: accessory_min {len(acc_min)} rows, bare_min {len(bare_min)} rows")

    # mean -> min over-read reduction (accessory, F8 + F11)
    print("\n=== over-read reduction (centre headroom >= 1.0), accessory ===")
    for ap in ("F8", "F11"):
        om, nm = overread_frac(acc_mean, ap)
        oi, ni = overread_frac(acc_min, ap)
        print(f"  {ap}: mean {om}/{nm} over-read -> min {oi}/{ni} over-read")

    # unified ranking (bare + accessory, min), tagged
    rows = []
    for src, kind in ((bare_min, "bare"), (acc_min, "accessory")):
        for r in src:
            if r["status"] != "ok":
                continue
            rows.append(dict(kind=kind, config=f"{r['lens']} [{r['mag_label']}]", ap=r["aperture"],
                             M=fnum(r["atlas_M"]), n_eff=fnum(r["n_eff"]), ceiling=fnum(r["ceiling_lpmm"]),
                             centre=fnum(r["centre"]), corner_mean=fnum(r["corner_mean"]),
                             uniformity=fnum(r["uniformity"]), headroom=fnum(r["centre_headroom"]),
                             regime=regime(fnum(r["centre_headroom"]))))
    with (OUTDIR / "unified_ranking.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    for ap in ("F8", "F11"):
        sub = sorted([x for x in rows if x["ap"] == ap and x["centre"] is not None], key=lambda x: -x["centre"])
        if not sub:
            continue
        print(f"\n=== UNIFIED @ {ap} (combine=min; subject lp/mm by centre; *=bare) ===")
        print(f"{'M':>5}{'Neff':>6}{'ceil':>6}{'centre':>7}{'corn':>6}{'unif':>6}{'head':>6} {'regime':<15} config")
        for x in sub:
            star = "*" if x["kind"] == "bare" else " "
            cm = f"{x['corner_mean']:.1f}" if x["corner_mean"] is not None else "-"
            u = f"{x['uniformity']:.2f}" if x["uniformity"] is not None else "-"
            h = f"{x['headroom']:.2f}" if x["headroom"] is not None else "-"
            print(f"{x['M']:>5.2f}{x['n_eff']:>6.1f}{x['ceiling']:>6.1f}{x['centre']:>7.1f}{cm:>6}{u:>6}{h:>6} "
                  f"{x['regime']:<15} {star}{x['config'][:44]}")
    print(f"\n[written] unified_ranking.csv (+ merged min csvs) in {OUTDIR}")


if __name__ == "__main__":
    main()
