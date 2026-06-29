"""PROBE (task A): does atlas-M reproduce KNOWN nominal M on the anchor sweeps?

The 3 built-in SWEEPS span nominal M = 0.385 (100-400 @ 1:2.60), 1.0 (AF200 @ 1:1,
THE anchor), 2.0 (Sigma+TC @ 2:1). If atlas-M tracks nominal across this range, the
registration+anchor method is geometrically sound -> the diopter-config atlas-vs-
nominal gaps are nominal-label errors, not registration errors. sweep2 is the anchor
so it returns 1.0 by construction (consistency check, not independent).
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np

WA = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reg_auto", WA / "reg_auto.py")
ra = importlib.util.module_from_spec(spec); spec.loader.exec_module(ra)

M_ANCHOR_SCALE = 1.6549
NOMINAL = {"sweep1_M0.385": 0.385, "sweep2_M1.0": 1.0, "sweep3_M2.0": 2.0,
           "sweep4_newer_rig": float("nan")}


def main():
    print(f"{'sweep':<18}{'M_nom':>7}{'M_atlas':>9}{'gap%':>8}{'refrmse':>9}{'n_int':>6}"
          f"   col_f / row_f")
    for name, (path, anchors) in ra.SWEEPS.items():
        p = ra.register_and_refine(name, path=path, anchors=anchors)
        if p is None:
            print(f"{name:<18}   FAILED"); continue
        M = p["scale"] / M_ANCHOR_SCALE
        nom = NOMINAL.get(name, float("nan"))
        gap = (M/nom - 1)*100 if nom == nom else float("nan")
        gs = f"{gap:+7.1f}" if gap == gap else f"{'-':>7}"
        print(f"{name:<18}{nom:7.3f}{M:9.3f}{gs:>8}{p['reg_fit_rmse_px']:9.2f}"
              f"{p['n_refine_intersections']:6d}   "
              f"{p['reg_col_first']}({p['reg_col_method'].split('(')[0]}) / "
              f"{p['reg_row_first']}({p['reg_row_method']})")


if __name__ == "__main__":
    main()
