"""Regression test for autonomous registration (reg_auto.register_and_refine).

Locks the behaviour established 2026-06-27 so later edits to detection /
labelling / refinement / the v3 grid can't silently regress it. For each sweep
it asserts the things that matter and are stable:

  - registration SUCCEEDS (non-None affine);
  - the absolute (col_first, row_first) offsets are EXACTLY the known values
    (the hard part — absolute labelling — and the most sensitive to regressions);
  - the radial-distortion term is selected for the non-macro lenses and NOT for
    the internal-focus macros (model auto-selection);
  - the refined fit RMSE stays under a ceiling (didn't degrade); and
  - the recovered tilt is within the fixed-mount envelope.

Exact RMSE/tilt are deterministic (no RNG in the pipeline) but are asserted as
bounds, not equalities, so a legitimate *improvement* doesn't fail the test.

HEAVY: one full-res decode + refinement per sweep (~30-60s total). Data lives on
the NFS share; run on a host that can read it (nufan), per-host venv. Standalone:

    uv run --no-sync python scripts/test_reg_auto.py
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

# Unseen-sweep shot: NIKKOR Z MC 105mm @ 1:1 / F11, the shot diag_validate_unseen
# selected (index 23 of the sorted stack). Pinned for determinism.
_MC105_DIR = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
              "NIKKOR Z MC 105mm f_2.8 VR S/1_1/F11")


def _mc105_shot():
    hit = sorted(glob.glob(os.path.join(_MC105_DIR, "10471*.jpg")))
    if hit:
        return hit[0]
    return sorted(glob.glob(os.path.join(_MC105_DIR, "*.jpg")))[23]


# name -> (path_override or None for built-in SWEEPS, expected dict)
# rmse_max ~ known fit residual x1.4 (a generous "didn't regress" ceiling).
CASES = [
    ("sweep1_M0.385",    None,          dict(col=2, row=2, radial=True,  rmse_max=2.0, tilt=(4.6, 5.0))),
    ("sweep2_M1.0",      None,          dict(col=5, row=2, radial=False, rmse_max=4.0, tilt=(4.4, 4.9))),
    ("sweep3_M2.0",      None,          dict(col=5, row=2, radial=False, rmse_max=8.5, tilt=(4.0, 4.6))),
    ("sweep4_newer_rig", None,          dict(col=4, row=2, radial=True,  rmse_max=3.5, tilt=(4.3, 4.7))),
    ("unseen_mc105_f11", _mc105_shot,   dict(col=5, row=2, radial=False, rmse_max=4.0, tilt=(4.0, 4.6))),
]


def _check(name, path_fn, exp):
    path = path_fn() if path_fn else None
    p = ra.register_and_refine(name, path=path)
    if p is None:
        return [f"{name}: registration FAILED (None)"], None
    fails = []
    if p["reg_col_first"] != exp["col"]:
        fails.append(f"col_first {p['reg_col_first']} != {exp['col']}")
    if p["reg_row_first"] != exp["row"]:
        fails.append(f"row_first {p['reg_row_first']} != {exp['row']}")
    has_radial = "k1" in p
    if has_radial != exp["radial"]:
        fails.append(f"radial {has_radial} != {exp['radial']} (model={p.get('model')})")
    if p["reg_fit_rmse_px"] > exp["rmse_max"]:
        fails.append(f"fit_rmse {p['reg_fit_rmse_px']:.2f} > {exp['rmse_max']}")
    lo, hi = exp["tilt"]
    if not (lo <= p["theta_deg"] <= hi):
        fails.append(f"tilt {p['theta_deg']:.2f} outside [{lo},{hi}]")
    return [f"{name}: {m}" for m in fails], p


def main():
    print("reg_auto regression: register_and_refine on 4 dev sweeps + 1 unseen sweep\n")
    all_fails = []
    for name, path_fn, exp in CASES:
        fails, p = _check(name, path_fn, exp)
        if fails:
            all_fails += fails
            tag = "FAIL"
        else:
            tag = "ok"
        if p is not None:
            print(f"  [{tag:4}] {name:<18} col={p['reg_col_first']} row={p['reg_row_first']} "
                  f"fit={p['reg_fit_rmse_px']:.2f}px tilt={p['theta_deg']:.2f} "
                  f"{'+radial' if 'k1' in p else 'similarity'}")
        else:
            print(f"  [{tag:4}] {name:<18} <no affine>")
    print()
    if all_fails:
        print(f"REGRESSION: {len(all_fails)} assertion(s) failed:")
        for f in all_fails:
            print(f"  - {f}")
        return 1
    print("PASS: all sweeps register at the expected offsets / model / accuracy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
