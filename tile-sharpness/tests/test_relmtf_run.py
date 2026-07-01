"""Tests for the pure / wiring pieces of the P2 driver ``scripts/relmtf_run.py``.

The heavy extract/analyse image work is INTEGRATION (smoke-tested on nufan, not here).
These cover the pure decision logic the driver adds on top of the P1/POC modules:

* :func:`reg_guard` — the reg_auto plausibility predicate (ruling #5): absolute-M
  bounds, residual ceiling, and the M~0 scale-collapse mode.
* :func:`step_source_for_session` — documented (2026-05+ with a finite step) vs
  dof_estimated (pre-2026-05 / no documented step); NEVER dof when documented exists.
* :func:`_ap_to_n` / :func:`_ap_str_to_f` — aperture parsing used by the step /
  effective-aperture wiring.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# Load the driver as a module (it lives in scripts/, not the package). It imports cv2 /
# pandas and _load()s the reg_auto POC scripts at import time; all are in the venv.
_SPEC = importlib.util.spec_from_file_location(
    "relmtf_run",
    Path(__file__).resolve().parent.parent / "scripts" / "relmtf_run.py",
)
rr = importlib.util.module_from_spec(_SPEC)
sys.modules["relmtf_run"] = rr
_SPEC.loader.exec_module(rr)


# --------------------------------------------------------------------------- #
# reg_guard (ruling #5)
# --------------------------------------------------------------------------- #
def test_reg_guard_accepts_a_sane_registration():
    ok, reason = rr.reg_guard(1.00, 1.2)
    assert ok and reason == ""


def test_reg_guard_accepts_high_but_in_bounds_M():
    # M=2 is in-bounds for the reg guard (the M>1.10 LOW-CONF flag is a SEPARATE,
    # orthogonal mechanism handled in analyse, not a hard drop).
    ok, _ = rr.reg_guard(2.0, 2.0)
    assert ok


def test_reg_guard_drops_scale_collapse_even_at_low_residual():
    # The documented M~0 scale-collapse failure mode: a near-zero M returned at a
    # DECEPTIVELY LOW residual must still be dropped.
    ok, reason = rr.reg_guard(0.05, 0.4)
    assert not ok
    assert "collapse" in reason


def test_reg_guard_drops_M_below_min():
    ok, reason = rr.reg_guard(0.10, 1.0)
    assert not ok
    assert "collapse" in reason or "out_of_bounds" in reason


def test_reg_guard_drops_M_above_max():
    ok, reason = rr.reg_guard(4.0, 1.0)
    assert not ok
    assert "out_of_bounds" in reason


def test_reg_guard_drops_residual_above_ceiling():
    # 9.9px @ M=1.0 -> 9.9*4.35/1.0 = 43um object, over the 25um ceiling.
    ok, reason = rr.reg_guard(1.0, 9.9)
    assert not ok
    assert "rmse" in reason


def test_reg_guard_admits_high_M_borderline_under_object_ceiling():
    # The near-ceiling high-M group: 6.6px @ M=2.25 = 12.8um object, WELL within the
    # ~9um-median / p99~20um envelope. A flat 6px ceiling wrongly dropped these; the
    # object-space ceiling admits them.
    ok, reason = rr.reg_guard(2.25, 6.6)
    assert ok and reason == ""


def test_reg_guard_tightens_at_low_M():
    # Object-space is STRICTER at low M than a flat 6px: 5px @ M=0.4 = 54um object,
    # over the 25um ceiling (a flat 6px would have wrongly ADMITTED it). This is what
    # rejects the bare 24-120 F5.6/F8 wrong-locks (255-293um).
    ok, reason = rr.reg_guard(0.4, 5.0)
    assert not ok
    assert "rmse" in reason


def test_reg_guard_drops_nonfinite_M():
    ok, reason = rr.reg_guard(float("nan"), 1.0)
    assert not ok
    assert "nonfinite" in reason


def test_reg_guard_drops_nonfinite_rmse():
    ok, reason = rr.reg_guard(1.0, float("nan"))
    assert not ok
    assert "rmse_nonfinite" in reason


# --------------------------------------------------------------------------- #
# min-residual-over-frames selection (recovery fix)
# --------------------------------------------------------------------------- #
def test_select_registration_picks_min_rmse_among_plausible():
    # honest lock (M=0.41, rmse=0.6) beats a lower-rmse-looking but higher-rmse alt;
    # simple min-rmse over plausible locks.
    cand = [dict(M=0.41, rmse=0.6, frame="a"),
            dict(M=0.40, rmse=1.2, frame="b"),
            dict(M=0.42, rmse=3.4, frame="c")]
    best = rr.select_registration(cand)
    assert best["frame"] == "a"


def test_select_registration_rejects_collapse_even_at_lowest_rmse():
    # THE recovery case: a scale-collapse (M=0.19) lands at a DECEPTIVELY LOW residual
    # (10.3) that would win min-rmse outright; the honest M=0.41 lock has a slightly
    # higher rmse. The collapse must be rejected so the honest lock wins.
    cand = [dict(M=0.193, rmse=10.3, frame="collapse"),
            dict(M=0.410, rmse=0.63, frame="honest")]
    best = rr.select_registration(cand)
    assert best["frame"] == "honest" and best["M"] == 0.410


def test_select_registration_absolute_floor_rejects_sub_floor_M():
    # every candidate below the absolute floor -> nothing plausible -> None (drop).
    cand = [dict(M=0.16, rmse=0.4), dict(M=0.27, rmse=0.9)]
    assert rr.select_registration(cand) is None


def test_select_registration_nominal_band_rejects_collapse_above_floor():
    # a collapse that clears the absolute floor (M=0.31) but is far below a KNOWN nominal
    # (0.775 -> lo=0.55*0.775=0.43) is still rejected; the honest near-nominal lock wins.
    cand = [dict(M=0.31, rmse=0.5, frame="collapse"),
            dict(M=0.78, rmse=1.4, frame="honest")]
    best = rr.select_registration(cand, nominal_M=0.775)
    assert best["frame"] == "honest"


def test_select_registration_nominal_band_rejects_double_lock():
    # a 2x mis-lock (M=1.55, nominal 0.775 -> hi=1.9*0.775=1.47) is rejected.
    cand = [dict(M=1.55, rmse=0.3, frame="double"),
            dict(M=0.77, rmse=2.0, frame="honest")]
    best = rr.select_registration(cand, nominal_M=0.775)
    assert best["frame"] == "honest"


def test_select_registration_ignores_nonfinite_rmse_and_returns_none_if_empty():
    assert rr.select_registration([]) is None
    assert rr.select_registration([dict(M=0.5, rmse=float("nan"))]) is None
    assert rr.select_registration([dict(M=0.5, rmse=None)]) is None


def test_select_registration_no_nominal_falls_back_to_absolute_floor_only():
    # bare-zoom configs carry no nominal M; only the absolute floor gates. A plausible
    # honest lock is kept; a collapse below the floor is dropped.
    cand = [dict(M=0.19, rmse=0.5, frame="collapse"),
            dict(M=0.40, rmse=1.0, frame="honest")]
    best = rr.select_registration(cand, nominal_M=float("nan"))
    assert best["frame"] == "honest"


def test_lock_plausible_boundaries():
    assert not rr._lock_plausible(0.29, float("nan"))   # just below floor
    assert rr._lock_plausible(0.31, float("nan"))       # just above floor
    assert not rr._lock_plausible(-0.5, float("nan"))
    assert not rr._lock_plausible(float("nan"), float("nan"))


# --------------------------------------------------------------------------- #
# step-source selection (documented vs dof_estimated)
# --------------------------------------------------------------------------- #
def test_step_source_documented_for_2026_05_with_finite_step():
    assert rr.step_source_for_session("2026-05-13", 0.02) == "documented"
    assert rr.step_source_for_session("2026-05-12", 0.05) == "documented"


def test_step_source_dof_for_manual_sessions_even_with_a_step_value():
    # A pre-2026-05 session is DoF-estimated regardless of any documented value.
    assert rr.step_source_for_session("2026-01-29", 0.02) == "dof_estimated"
    assert rr.step_source_for_session("2026-02-18", 0.02) == "dof_estimated"
    assert rr.step_source_for_session("2025-10-17", 0.02) == "dof_estimated"


def test_step_source_dof_when_no_documented_step_for_2026_05():
    # A 2026-05 session with NO derivable documented step falls back to DoF.
    assert rr.step_source_for_session("2026-05-13", None) == "dof_estimated"
    assert rr.step_source_for_session("2026-05-13", 0.0) == "dof_estimated"
    assert rr.step_source_for_session("2026-05-13", float("nan")) == "dof_estimated"


def test_step_source_never_dof_when_documented_exists():
    # The binding rule: with a finite positive documented step on a 2026-05 session,
    # the source is ALWAYS documented, never dof_estimated.
    for step in (0.001, 0.02, 1.5):
        assert rr.step_source_for_session("2026-05-13", step) == "documented"


# --------------------------------------------------------------------------- #
# aperture parsing (used by step + effective-aperture wiring)
# --------------------------------------------------------------------------- #
def test_ap_to_n_parses_marked_aperture_dirs():
    assert rr._ap_to_n("F8") == 8.0
    assert rr._ap_to_n("F5.6") == pytest.approx(5.6)
    assert rr._ap_to_n("f_11") == 11.0


def test_ap_str_to_f_parses_shots_csv_aperture_strings():
    assert rr._ap_str_to_f("f/4.5") == pytest.approx(4.5)
    assert rr._ap_str_to_f("6.3") == pytest.approx(6.3)
    assert rr._ap_str_to_f("F8") == 8.0
    assert rr._ap_str_to_f("nonsense") is None


# --------------------------------------------------------------------------- #
# tier routing (which pool is primary given --tier)
# --------------------------------------------------------------------------- #
def test_tier_default_is_rail_coverage():
    p = rr.build_parser()
    args = p.parse_args(["analyse", "--subset", "s.csv", "--out", "o"])
    assert args.tier == "rail-coverage"


def test_tier_all_is_accepted():
    p = rr.build_parser()
    args = p.parse_args(["analyse", "--subset", "s.csv", "--out", "o", "--tier", "all"])
    assert args.tier == "all"


def test_extract_requires_subset_and_out():
    p = rr.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["extract"])  # missing required --subset/--out
