"""Tests for the diffraction / effective-aperture physics (optics.py)."""
import math

import pytest

from tile_sharpness.optics import (
    DOF_PREDICTOR_FORMS,
    diffraction_mtf50_sensor_lpmm,
    diffraction_mtf50_subject_lpmm,
    effective_fnumber,
    object_dof_predictor,
)


def test_effective_fnumber_bellows():
    # at 1:1 a symmetric lens loses one stop equivalent -> N_eff = 2N
    assert effective_fnumber(11, 1.0) == pytest.approx(22.0)
    # at infinity focus N_eff == N
    assert effective_fnumber(8, 0.0) == pytest.approx(8.0)
    # pupil_mag > 1 (telephoto) suffers less than symmetric
    assert effective_fnumber(8, 1.0, pupil_mag=2.0) < effective_fnumber(8, 1.0)


def test_effective_fnumber_validation():
    for bad in (lambda: effective_fnumber(0, 1.0),
                lambda: effective_fnumber(8, -0.1),
                lambda: effective_fnumber(8, 1.0, pupil_mag=0)):
        with pytest.raises(ValueError):
            bad()


def test_sensor_ceiling_known_value():
    # f/8, green: cutoff = 1/(0.00055*8) = 227.3 lp/mm; MTF50 = 0.404*cutoff
    assert diffraction_mtf50_sensor_lpmm(8) == pytest.approx(0.404 / (0.00055 * 8), rel=1e-9)


def test_sensor_ceiling_monotonic_in_aperture():
    # stopping down (larger N) lowers the diffraction ceiling
    assert diffraction_mtf50_sensor_lpmm(4) > diffraction_mtf50_sensor_lpmm(8) > diffraction_mtf50_sensor_lpmm(16)


def test_subject_ceiling_saturates_with_magnification():
    # subject ceiling = sensor_at_Neff * M; with N_eff=N(1+M) it ~ M/(1+M) -> saturates.
    n = 11.0
    asymptote = 0.404 / (0.00055 * n)   # limit as M -> inf (p=1)
    c1 = diffraction_mtf50_subject_lpmm(n, 1.0)
    c2 = diffraction_mtf50_subject_lpmm(n, 2.0)
    c10 = diffraction_mtf50_subject_lpmm(n, 10.0)
    assert c1 < c2 < c10 < asymptote          # monotone up, bounded by the asymptote
    assert c10 == pytest.approx(asymptote * (10.0 / 11.0), rel=1e-9)


def test_object_dof_predictor_known_value():
    # neff_over_m at N=11, M=1, p=1: N_eff = 22, predictor = 22/1 = 22
    assert object_dof_predictor(11, 1.0, form="neff_over_m") == pytest.approx(22.0)
    # n_over_m strips the bellows factor: 11/1 = 11
    assert object_dof_predictor(11, 1.0, form="n_over_m") == pytest.approx(11.0)
    # neff control: just N_eff
    assert object_dof_predictor(11, 1.0, form="neff") == pytest.approx(22.0)
    # neff_1pm_over_m2: 22*(1+1)/1 = 44
    assert object_dof_predictor(11, 1.0, form="neff_1pm_over_m2") == pytest.approx(44.0)


def test_object_dof_predictor_decreasing_in_m():
    # All magnification-dependent forms shrink object-space DoF as M grows.
    for form in ("neff_over_m", "n_over_m", "neff_1pm_over_m2"):
        vals = [object_dof_predictor(8, m, form=form) for m in (0.5, 1.0, 1.5, 2.0)]
        assert all(a > b for a, b in zip(vals, vals[1:])), form


def test_object_dof_predictor_increasing_in_aperture():
    # Stopping down (larger N) deepens DoF for every form.
    for form in DOF_PREDICTOR_FORMS:
        assert object_dof_predictor(16, 1.0, form=form) > object_dof_predictor(4, 1.0, form=form)


def test_object_dof_predictor_validation():
    for bad in (lambda: object_dof_predictor(0, 1.0),
                lambda: object_dof_predictor(8, 0.0),
                lambda: object_dof_predictor(8, 1.0, form="bogus")):
        with pytest.raises(ValueError):
            bad()


def test_real_lens_cannot_beat_ceiling_is_the_point():
    # sanity: a 1:1 macro at f/16 has a low subject ceiling (~23 lp/mm) — explains
    # why stopped-down corners collapse.
    c = diffraction_mtf50_subject_lpmm(16, 1.0)
    assert 20 < c < 26
