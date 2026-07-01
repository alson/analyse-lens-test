"""Tests for POC 3 — physical through-focus conversion + flags (focus_physical).

Covers: the frames->mm conversion, the step-source selection (documented wins,
else DoF, with the M>1 low-confidence flag), the imputation/suspect rule tied to
POC-1 coverage, the DoF non-circularity identity, and the M-exponent sensitivity.
"""
import math

import numpy as np
import pytest

from tile_sharpness import focus_physical as FP
from tile_sharpness.optics import object_dof_predictor


# --------------------------------------------------------------------------- #
# frames -> mm
# --------------------------------------------------------------------------- #
def test_frames_to_mm_basic():
    assert FP.frames_to_mm(10.0, 0.05) == pytest.approx(0.5)
    assert FP.frames_to_mm(0.0, 0.05) == 0.0


def test_frames_to_mm_nan_safe():
    assert math.isnan(FP.frames_to_mm(float("nan"), 0.05))
    assert math.isnan(FP.frames_to_mm(10.0, float("nan")))


# --------------------------------------------------------------------------- #
# step-source selection
# --------------------------------------------------------------------------- #
def test_documented_step_wins():
    s = FP.resolve_step(m=1.0, n_working=8.0, marked_f=8.0, fwhm_frames=10.0,
                        documented_step_mm=0.0960)
    assert s.step_source == "documented"
    assert s.step_mm == pytest.approx(0.0960)
    assert not s.low_confidence


def test_falls_back_to_dof_when_no_documented():
    s = FP.resolve_step(m=1.0, n_working=8.0, marked_f=8.0, fwhm_frames=10.0,
                        documented_step_mm=None)
    assert s.step_source == "dof_estimated"
    pred = object_dof_predictor(8.0, 1.0, form=FP.DOF_FORM, n_working=8.0)
    assert s.step_mm == pytest.approx(FP.DOF_K * pred / 10.0)
    assert not s.low_confidence  # M==1 is on the threshold, not above it


def test_invalid_documented_step_falls_back_to_dof():
    for bad in (0.0, -1.0, float("nan")):
        s = FP.resolve_step(m=1.0, n_working=8.0, marked_f=8.0, fwhm_frames=10.0,
                            documented_step_mm=bad)
        assert s.step_source == "dof_estimated"


def test_m_above_one_dof_is_low_confidence():
    s = FP.resolve_step(m=2.0, n_working=12.0, marked_f=8.0, fwhm_frames=10.0,
                        documented_step_mm=None)
    assert s.step_source == "dof_estimated"
    assert s.low_confidence
    assert "extrapolation" in s.note.lower()


def test_documented_step_at_high_m_is_not_low_confidence():
    # a documented step is exact regardless of M
    s = FP.resolve_step(m=2.0, n_working=12.0, marked_f=8.0, fwhm_frames=10.0,
                        documented_step_mm=0.5)
    assert s.step_source == "documented"
    assert not s.low_confidence


# --------------------------------------------------------------------------- #
# non-circularity identity: dof_estimated fwhm_mm == k*predictor exactly
# --------------------------------------------------------------------------- #
def test_dof_estimated_fwhm_mm_is_identically_k_pred():
    m, n_working, marked_f, fwhm_frames = 0.385, 11.52, 11.0, 14.64
    s = FP.resolve_step(m=m, n_working=n_working, marked_f=marked_f,
                        fwhm_frames=fwhm_frames, documented_step_mm=None)
    # fwhm_mm = fwhm_frames * step = fwhm_frames * (k*pred/fwhm_frames) = k*pred
    fwhm_mm = FP.frames_to_mm(fwhm_frames, s.step_mm)
    dof = FP.dof_expected_fwhm_mm(m, n_working, marked_f)
    assert fwhm_mm == pytest.approx(dof, rel=1e-9)


# --------------------------------------------------------------------------- #
# imputation / suspect rule
# --------------------------------------------------------------------------- #
def test_fwhm_truncated_is_imputed_from_dof():
    val, q, imputed = FP.fwhm_quality(measured_fwhm_mm=0.10, coverage_flag="fwhm_truncated",
                                      dof_fwhm_mm=0.50)
    assert q == "fwhm_imputed"
    assert imputed
    assert val == pytest.approx(0.50)  # replaced by DoF expectation


def test_fwhm_truncated_without_dof_keeps_value_but_labels():
    val, q, imputed = FP.fwhm_quality(measured_fwhm_mm=0.10, coverage_flag="fwhm_truncated",
                                      dof_fwhm_mm=float("nan"))
    assert q == "fwhm_imputed"
    assert not imputed
    assert val == pytest.approx(0.10)


def test_large_disagreement_is_suspect():
    # measured 3x the DoF expectation -> |log 3| = 1.10 > log(2)=0.69 -> suspect
    val, q, imputed = FP.fwhm_quality(measured_fwhm_mm=1.5, coverage_flag="ok",
                                      dof_fwhm_mm=0.5)
    assert q == "fwhm_suspect"
    assert not imputed
    assert val == pytest.approx(1.5)  # value unchanged


def test_close_agreement_is_ok():
    # measured 1.3x DoF -> |log 1.3| = 0.26 < 0.69 -> ok
    val, q, imputed = FP.fwhm_quality(measured_fwhm_mm=0.65, coverage_flag="ok",
                                      dof_fwhm_mm=0.5)
    assert q == "ok"
    assert not imputed


def test_truncated_low_high_not_imputed():
    for cov in ("truncated_low", "truncated_high"):
        val, q, imputed = FP.fwhm_quality(measured_fwhm_mm=0.10, coverage_flag=cov,
                                          dof_fwhm_mm=0.50)
        assert q == "ok"  # carried coverage_flag is the authority; not imputed here
        assert not imputed
        assert val == pytest.approx(0.10)


# --------------------------------------------------------------------------- #
# full per-patch row
# --------------------------------------------------------------------------- #
def test_patch_physical_row_documented():
    s = FP.resolve_step(m=1.0, n_working=8.0, marked_f=8.0, fwhm_frames=10.0,
                        documented_step_mm=0.096)
    row = FP.patch_physical_row(mu_frames=40.0, fwhm_frames=10.0, coverage_flag="ok",
                                step=s, m=1.0, n_working=8.0, marked_f=8.0)
    assert row["mu_mm"] == pytest.approx(40.0 * 0.096)
    assert row["fwhm_mm"] == pytest.approx(10.0 * 0.096)
    assert row["step_source"] == "documented"
    assert row["coverage_flag"] == "ok"
    assert not row["step_low_confidence"]


def test_patch_physical_row_imputes_truncated():
    s = FP.resolve_step(m=1.0, n_working=8.0, marked_f=8.0, fwhm_frames=10.0,
                        documented_step_mm=0.096)
    # a truncated patch with a tiny measured fwhm -> imputed to DoF expectation
    row = FP.patch_physical_row(mu_frames=2.0, fwhm_frames=1.0,
                                coverage_flag="fwhm_truncated", step=s,
                                m=1.0, n_working=8.0, marked_f=8.0)
    assert row["fwhm_quality"] == "fwhm_imputed"
    assert row["fwhm_imputed"]
    assert row["fwhm_mm"] == pytest.approx(row["fwhm_dof_mm"])
    # mu position kept as measured
    assert row["mu_mm"] == pytest.approx(2.0 * 0.096)


# --------------------------------------------------------------------------- #
# M-exponent sensitivity
# --------------------------------------------------------------------------- #
def test_m_exponent_sensitivity_ratio_equals_m():
    for m in (1.5, 2.0):
        s = FP.m_extrapolation_sensitivity(m=m, n_working=12.0, marked_f=8.0,
                                           fwhm_frames=10.0)
        assert s["ratio_exp1_over_exp2"] == pytest.approx(m, rel=1e-9)
        assert s["frac_shift"] == pytest.approx(abs(m - 1.0), rel=1e-9)
        # both steps scale by the same ratio
        assert s["step_mm_exp1"] / s["step_mm_exp2"] == pytest.approx(m, rel=1e-9)


def test_dof_step_mm_nan_on_bad_fwhm():
    step, pred = FP.dof_step_mm(0.0, 1.0, 8.0, 8.0)
    assert math.isnan(step)
    step, pred = FP.dof_step_mm(float("nan"), 1.0, 8.0, 8.0)
    assert math.isnan(step)
