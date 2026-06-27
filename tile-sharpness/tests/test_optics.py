"""Tests for the diffraction / effective-aperture physics (optics.py)."""
import math

import pytest

from tile_sharpness.optics import (
    diffraction_mtf50_sensor_lpmm,
    diffraction_mtf50_subject_lpmm,
    effective_fnumber,
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


def test_real_lens_cannot_beat_ceiling_is_the_point():
    # sanity: a 1:1 macro at f/16 has a low subject ceiling (~23 lp/mm) — explains
    # why stopped-down corners collapse.
    c = diffraction_mtf50_subject_lpmm(16, 1.0)
    assert 20 < c < 26
