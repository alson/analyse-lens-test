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
    ok, reason = rr.reg_guard(1.0, 9.9)
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
