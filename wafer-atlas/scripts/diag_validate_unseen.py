"""Validate autonomous registration on a GENUINELY UNSEEN sweep (HANDOVER step 3).

The four sweeps in reg_auto.SWEEPS were all used during development (two also in
the grid recalibration), so they cannot prove generalization. This registers a
sweep that was never touched: NIKKOR Z MC 105mm f/2.8 @ 1:1 / F11 (2026-01-29) —
a different lens from all four dev sweeps, an internal-focus macro (like the
AF200) so distortion ~0, at the standard F11 and M=1.0.

It registers FULLY AUTONOMOUSLY (anchors=None): scan a few shots for the best
scribe detection (focus position in the stack is unknown), then
register_and_refine on the best one. Success criteria:
  - registers (success / non-None affine);
  - refined fit RMSE in the dev-sweep range (~1-6 px);
  - tilt within the fixed-mount envelope (~4.3-4.8 deg);
  - scale consistent with the magnification — for M=1.0 it should match sweep2
    (the AF200, also 1:1 / F11) to ~1%, an independent correctness cross-check;
  - distortion model correctly NOT applied (macro lens -> similarity).

Run on nufan (per-host venv). Pure validation: writes nothing, prints a report.
"""
from __future__ import annotations

import glob
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ra = _load("reg_auto")

SWEEP_DIR = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
             "NIKKOR Z MC 105mm f_2.8 VR S/1_1/F11")
# sweep2 (AF200 @ 1:1 / F11) scale, for the M=1.0 cross-check.
SWEEP2_SCALE = 1.655


def main():
    shots = sorted(glob.glob(os.path.join(SWEEP_DIR, "*.jpg")))
    print(f"UNSEEN sweep: NIKKOR Z MC 105mm @ 1:1 / F11 (2026-01-29) — {len(shots)} shots")
    print("  internal-focus macro, never used in dev / recal.")

    # focus position in the stack is unknown -> scan a few shots, pick the best
    # scribe detection (#cols + #rows + a 4D bar present).
    idxs = sorted(set(int(len(shots) * f) for f in (0.3, 0.4, 0.5, 0.6, 0.7)))
    best = None
    print("\n=== scribe-detection scan ===")
    for i in idxs:
        p = shots[i]
        try:
            det = ra.detect(p)
            nc, nr, nb = len(det["col_x"]), len(det["row_y"]), len(ra.detect_4d_bars(det))
            print(f"  #{i:<3} tilt={det['tilt']:+.2f}  cols={nc} rows={nr}  4D-bars={nb}")
            score = nc + nr + (5 if nb else 0)
            if best is None or score > best[0]:
                best = (score, p)
        except Exception as e:                       # noqa: BLE001 — report, keep scanning
            print(f"  #{i:<3} detect FAILED: {e}")
    assert best, "no candidate detected"

    chosen = best[1]
    print(f"\n=== register_and_refine on {os.path.basename(chosen).split('|')[0]} "
          f"(NO anchors) ===")
    p = ra.register_and_refine("unseen_mc105_1to1_f11", path=chosen, anchors=None)
    if p is None:
        print("\nRESULT: registration FAILED")
        return 1

    print("\nRESULT: registration SUCCEEDED")
    for k in ("reg_method", "reg_col_first", "reg_col_method", "reg_row_first",
              "reg_row_method", "reg_fit_rmse_px", "n_refine_intersections",
              "theta_deg", "scale", "model"):
        if k in p:
            print(f"  {k:24} {p[k]}")
    if "k1" in p:
        print(f"  {'k1/k2':24} {p['k1']:.4f} / {p['k2']:.4f}")

    # sanity checks
    ok_rmse = p["reg_fit_rmse_px"] < 8.0
    ok_tilt = 4.0 < p["theta_deg"] < 5.0
    ok_scale = abs(p["scale"] - SWEEP2_SCALE) / SWEEP2_SCALE < 0.02
    ok_sim = "k1" not in p
    print("\n=== sanity ===")
    print(f"  fit RMSE < 8px:                 {ok_rmse}  ({p['reg_fit_rmse_px']:.2f})")
    print(f"  tilt in [4.0,5.0] deg:          {ok_tilt}  ({p['theta_deg']:.2f})")
    print(f"  scale ~ sweep2 (M=1.0) ±2%:     {ok_scale}  "
          f"({p['scale']:.4f} vs {SWEEP2_SCALE})")
    print(f"  similarity model (macro, k~0):  {ok_sim}")
    print(f"\n  ALL PASS: {all([ok_rmse, ok_tilt, ok_scale, ok_sim])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
