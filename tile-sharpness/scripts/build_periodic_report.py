"""Aggregate the periodic-FFT per-region CSV into a cross-config ranking.

Reads the concatenated shard output (RANK_OUT files) and produces:
  * per-config summary: centre/all-zone mean peak contrast, split CYAN vs MAGENTA,
    plus over-read fraction (contrast > ceiling) as the gate audit.
  * a same-structure comparison: for a chosen (type, zone) present across configs,
    the contrast ranking at a common physical structure (hence common subject freq).

Usage: python build_periodic_report.py rank_out.csv [--type "(2, 1)"] [--zone centre]
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from statistics import mean


def load(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rows = []
    for p in args:
        rows += load(p)
    for r in rows:
        for k in ("contrast", "ceiling", "over", "f_subj_lpmm", "M", "snr"):
            r[k] = f(r[k])

    def cfg(r):
        return f"{r['lens']} [{r['mag_label']}]"

    # over-read audit (the gate): any region with contrast > ceiling by >0.03
    n_over = sum(1 for r in rows if (r["over"] or -1) > 0.03)
    print(f"CEILING GATE: {n_over}/{len(rows)} region-reads over the diffraction "
          f"ceiling (>0.03). Periodic contrast is bounded and under-reads past "
          f"cutoff, so this should be ~0.\n")

    # per-config, per-class centre + all-zone mean
    by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["contrast"] is None:
            continue
        cls = "magenta" if r["cls"] == "magenta" else "cyan"
        by[cfg(r)][(cls, "all")].append(r["contrast"])
        if r["zone"] == "centre":
            by[cfg(r)][(cls, "centre")].append(r["contrast"])

    def cell(vals):
        return f"{mean(vals):.4f}(n{len(vals)})" if vals else "-"

    print(f"{'config':<58}{'cyan_ctr':>14}{'cyan_all':>14}{'mag_ctr':>14}{'mag_all':>14}")
    order = sorted(by, key=lambda c: -(mean(by[c][('cyan', 'all')] + by[c][('magenta', 'all')])
                                       if (by[c][('cyan', 'all')] + by[c][('magenta', 'all')]) else 0))
    for c in order:
        d = by[c]
        print(f"{c[:57]:<58}{cell(d[('cyan','centre')]):>14}{cell(d[('cyan','all')]):>14}"
              f"{cell(d[('magenta','centre')]):>14}{cell(d[('magenta','all')]):>14}")

    # same-structure comparison
    want_type = None; want_zone = None
    for a in sys.argv:
        if a.startswith("--type"):
            want_type = sys.argv[sys.argv.index(a) + 1]
        if a.startswith("--zone"):
            want_zone = sys.argv[sys.argv.index(a) + 1]
    if want_type:
        print(f"\nSAME-STRUCTURE: type={want_type} zone={want_zone or 'any'} "
              f"(common subject frequency)")
        sub = [r for r in rows if r["type"] == want_type
               and (want_zone is None or r["zone"] == want_zone) and r["contrast"] is not None]
        sub.sort(key=lambda r: -r["contrast"])
        print(f"  {'config':<54}{'zone':<7}{'f_subj':>8}{'C':>9}{'ceil':>7}")
        for r in sub:
            print(f"  {cfg(r)[:53]:<54}{r['zone']:<7}{r['f_subj_lpmm']:8.1f}"
                  f"{r['contrast']:9.4f}{r['ceiling']:7.3f}")


if __name__ == "__main__":
    main()
