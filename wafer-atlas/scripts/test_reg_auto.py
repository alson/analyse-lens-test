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


# High-M (2:1, M~2) cases: these are the configs the 2026-06-29 high-M robustness
# fix recovered (scale-collapse / reg-fail before). At M~2 a die is ~2475px so the
# frame holds only ~3 cols x 2 rows; the fix cleans high-M scribe doublets/partials,
# seeds+guards scale from the labelling-independent detected pitch, and allows 2-row
# registration. These assert a SANE atlas-M (not collapsed to ~0) + low residual on
# a pinned sharp frame; absolute (col,row) is asserted loosely (the 4D-bar anchor
# may pick an equivalent col phase) — the load-bearing property is M~2 not collapse.
_R = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
HIGHM_CASES = [
    ("AF200+5T+6T_2:1", f"{_R}/Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 5T + 6T/2_1/F11/"
        "02951|Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 5T + 6T|2_1|200.0 mm|F11|"
        "alm-20260130-020052-3007.jpg", dict(M=(1.9, 2.15), rmse_max=8.0, row=3)),
    ("Sigma150+TC_2:1", f"{_R}/Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11/"
        "04057|Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001|2_1|300.0 mm|F11|"
        "alm-20260131-001612-1022.jpg", dict(M=(1.9, 2.15), rmse_max=8.0, row=2)),
]
M_ANCHOR_SCALE = 1.6549


def _check_highm(name, path, exp):
    p = ra.register_and_refine(name, path=path)
    if p is None:
        return [f"{name}: registration FAILED (None) — high-M regression"], None
    fails = []
    M = p["scale"] / M_ANCHOR_SCALE
    lo, hi = exp["M"]
    if not (lo <= M <= hi):
        fails.append(f"atlas-M {M:.3f} outside [{lo},{hi}] (scale-collapse regression?)")
    if p["reg_row_first"] != exp["row"]:
        fails.append(f"row_first {p['reg_row_first']} != {exp['row']}")
    if p["reg_fit_rmse_px"] > exp["rmse_max"]:
        fails.append(f"fit_rmse {p['reg_fit_rmse_px']:.2f} > {exp['rmse_max']}")
    return [f"{name}: {m}" for m in fails], p


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
    print("\n  -- high-M (2:1) configs recovered by the 2026-06-29 robustness fix --")
    for name, path, exp in HIGHM_CASES:
        fails, p = _check_highm(name, path, exp)
        if fails:
            all_fails += fails
            tag = "FAIL"
        else:
            tag = "ok"
        if p is not None:
            print(f"  [{tag:4}] {name:<18} M={p['scale']/M_ANCHOR_SCALE:.3f} "
                  f"col={p['reg_col_first']} row={p['reg_row_first']} "
                  f"fit={p['reg_fit_rmse_px']:.2f}px tilt={p['theta_deg']:.2f}")
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


def test_reg_auto_regression():
    """Pytest entry point: all dev sweeps + the recovered high-M 2:1 configs must
    register at their expected offsets / model / accuracy / sane M."""
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
