"""Tests for the POC 2 DoF-based rail step-size estimator helpers.

Covers the self-contained Gaussian-FWHM fit (on a synthetic Gaussian) and the
through-origin linear fit used to calibrate k. The optics predictor itself is
tested in test_optics.py.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

# Load the POC script as a module (it lives in scripts/, not the package).
_SPEC = importlib.util.spec_from_file_location(
    "poc_dof_step_size",
    Path(__file__).resolve().parent.parent / "scripts" / "poc_dof_step_size.py",
)
poc = importlib.util.module_from_spec(_SPEC)
sys.modules["poc_dof_step_size"] = poc
_SPEC.loader.exec_module(poc)


def _gaussian_curve(n, mu, sigma, peak=1000.0, base=50.0):
    z = np.arange(n, dtype=float)
    return base + peak * np.exp(-((z - mu) ** 2) / (2 * sigma ** 2))


def test_fit_gaussian_fwhm_recovers_known_width():
    # FWHM of a Gaussian = 2.3548 * sigma. Recover it from a clean synthetic curve.
    for sigma in (3.0, 5.0, 8.0):
        n = max(31, int(8 * sigma))
        curve = _gaussian_curve(n, mu=n / 2, sigma=sigma)
        fw = poc._fit_gaussian_fwhm(np.arange(n), curve)
        assert fw == pytest.approx(2.3548 * sigma, rel=0.05)


def test_fwhm_frames_uses_finite_only_and_matches_inline():
    sigma = 4.0
    n = 41
    curve = _gaussian_curve(n, mu=20, sigma=sigma)
    # inject a couple of NaN frames (decode failures) — must be dropped, not crash
    curve[3] = np.nan
    curve[37] = np.nan
    fw = poc.fwhm_frames(curve)
    assert fw == pytest.approx(2.3548 * sigma, rel=0.08)


def test_fit_gaussian_fwhm_flat_returns_nan():
    # A flat curve has no peak above its own 10th-percentile baseline -> NaN.
    n = 31
    flat = np.full(n, 42.0)
    assert np.isnan(poc._fit_gaussian_fwhm(np.arange(n), flat))


def test_fit_gaussian_fwhm_too_few_points_returns_nan():
    assert np.isnan(poc._fit_gaussian_fwhm(np.arange(5), np.arange(5.0)))


def test_fit_through_origin_exact_and_r2():
    # y = 0.5 * x exactly -> k=0.5, R²=1.
    x = np.array([2.0, 4.0, 8.0, 16.0])
    y = 0.5 * x
    k, r2 = poc.fit_through_origin(x, y)
    assert k == pytest.approx(0.5)
    assert r2 == pytest.approx(1.0)


def test_fit_through_origin_with_noise_high_r2():
    rng = np.random.default_rng(0)
    x = np.linspace(5, 50, 30)
    y = 0.3 * x + rng.normal(0, 0.5, x.shape)
    k, r2 = poc.fit_through_origin(x, y)
    assert k == pytest.approx(0.3, abs=0.05)
    assert r2 > 0.95


def test_compare_predictors_picks_best_form():
    # Construct rows where fwhm_obj_mm is exactly k*pred for neff_over_m.
    from tile_sharpness.optics import object_dof_predictor
    rng = np.random.default_rng(1)
    rows = []
    for m in (0.5, 1.0, 1.5, 2.0):
        for n in (4.0, 8.0, 16.0):
            pred = {f"pred_{f}": object_dof_predictor(n, m, form=f)
                    for f in poc.DOF_PREDICTOR_FORMS}
            fwhm_obj = 0.02 * pred["pred_neff_over_m"] * (1 + rng.normal(0, 0.01))
            rows.append({"fwhm_obj_mm": fwhm_obj, **pred})
    fits = poc.compare_predictors(rows)
    assert fits[0].form == "neff_over_m"
    assert fits[0].r2 > 0.98


def test_aperture_and_mag_dir_parsing():
    assert poc._aperture_from_f_dir("f_5_6") == pytest.approx(5.6)
    assert poc._aperture_from_f_dir("f_8") == pytest.approx(8.0)
    assert poc._aperture_from_f_dir("f_11") == pytest.approx(11.0)
    # bare-number F-dirs (manual AI-S lenses, e.g. the 55mm)
    assert poc._aperture_from_f_dir("8") == pytest.approx(8.0)
    assert poc._aperture_from_f_dir("6_3") == pytest.approx(6.3)
    assert poc._aperture_from_f_dir("notf") is None
    assert poc._older_m_from_dir("1_1") == pytest.approx(1.0)
    assert poc._older_m_from_dir("1_2.60") == pytest.approx(1 / 2.6)
    assert poc._older_m_from_dir("2_1") == pytest.approx(2.0)


def test_looks_bare_excludes_accessories():
    assert poc._looks_bare("Sigma APO Macro 150mm F2.8 EX DG OS HSM")
    assert poc._looks_bare("Nikon AF Micro-Nikkor 200mm f_4D IF-ED")
    assert not poc._looks_bare("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T")
    assert not poc._looks_bare("Viltrox 85mm extension")  # 'extension' token
    assert not poc._looks_bare("NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x")
    assert not poc._looks_bare("100-400 + Olympus MCON-35")


def test_eff_aperture_csv_resolution_avoids_double_count():
    # exact CSV row -> use effective_f_exact DIRECTLY (no (1+M/p) reapplied)
    ec = poc.EffApertureCSV(
        exact={("Tube Lens + 35mm extension", 8.0): 10.6848},
        mult={"Tube Lens + 35mm extension": 1.3356},
    )
    n, src = ec.n_working("Tube Lens + 35mm extension", 8.0, 0.476)
    assert src == "csv_exact"
    assert n == pytest.approx(10.6848)         # NOT 8*(1+0.476)
    # multiplier fallback for an aperture without an exact row
    n2, src2 = ec.n_working("Tube Lens + 35mm extension", 5.6, 0.476)
    assert src2 == "csv_mult"
    assert n2 == pytest.approx(5.6 * 1.3356)
    # Lens NOT in CSV: folder f-number used DIRECTLY (already effective); never ×(1+M)
    n3, src3 = ec.n_working("Nikon Micro-Nikkor 55mm f_2.8 AIS", 4.0, 1.0)
    assert src3 == "folder_direct"
    assert n3 == pytest.approx(4.0)   # NOT 8.0
    n4, src4 = ec.n_working("Sigma APO Macro 150mm F2.8 EX DG OS HSM", 5.6, 1.0)
    assert src4 == "folder_direct"
    assert n4 == pytest.approx(5.6)   # NOT 11.2


def test_marked_max_aperture_parse_and_overrides():
    assert poc._marked_max_aperture("Sigma APO Macro 150mm F2.8 EX DG OS HSM") == pytest.approx(2.8)
    assert poc._marked_max_aperture("NIKKOR Z 24-120mm f_4 S") == pytest.approx(4.0)
    # zoom: long-end / smallest token
    assert poc._marked_max_aperture("NIKKOR Z 100-400mm f_4.5-5.6 VR S") == pytest.approx(4.5)
    # manual lens override
    assert poc._marked_max_aperture("Nikon Micro-Nikkor 55mm f_2.8 AIS — serial 287318") == pytest.approx(2.8)
    assert poc._marked_max_aperture("Nikon Micro-Nikkor Auto 55mm f_3.5 209088") == pytest.approx(3.5)


def test_predictor_uses_n_working_not_double_bellows():
    from tile_sharpness.optics import object_dof_predictor
    # With an empirical working f of 10.68 at M=0.476, neff_over_m must use 10.68
    # directly, NOT effective_fnumber(10.68, 0.476).
    p = object_dof_predictor(8.0, 0.476, form="neff_over_m", n_working=10.6848)
    assert p == pytest.approx(10.6848 / 0.476)
