"""POC 4 tests — tilt-removed field curvature + vertex-offset recovery.

Key known-answer contracts:
  * a PURE-TILT input yields ~zero curvature (k≈0, sag≈0) and ~zero residual
    after the joint plane+quadratic detrend,
  * a BOWL+TILT input recovers the bowl sag INDEPENDENT of the tilt,
  * the DoF-normalised sag scales as sag_mm / median FWHM,
  * a vertex-shifted paraboloid (no tilt) recovers the vertex offset.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from tile_sharpness.field_geometry_focus import (
    Z7_CENTRE,
    Z7_HALF_DIAG_PX,
    analyse_field_geometry,
    fit_curvature_detrended,
    fit_vertex_offset,
)

CX, CY = Z7_CENTRE
HD = Z7_HALF_DIAG_PX

# A Z7-ish dense grid spanning most of the frame.
_PX = np.linspace(900, 7350, 6)
_PY = np.linspace(700, 4800, 5)


def _grid():
    xs, ys = np.meshgrid(_PX, _PY)
    return xs.ravel(), ys.ravel()


# --------------------------------------------------------------------------- #
# Pure tilt → zero curvature, zero residual after detrend
# --------------------------------------------------------------------------- #
def test_pure_tilt_yields_zero_curvature_and_residual():
    px, py = _grid()
    # a strong pure plane, NO curvature
    mu = 3.0 + 2.0e-4 * (px - CX) - 1.3e-4 * (py - CY)
    fit = fit_curvature_detrended(px, py, mu, fwhm_mm_median=1.3,
                                  cx=CX, cy=CY, half_diag_px=HD)
    assert abs(fit.k_mm_per_px2) < 1e-12
    assert abs(fit.sag_um) < 1e-4
    assert abs(fit.sag_dof) < 1e-4
    assert fit.rms_residual_um < 1e-6   # plane fully absorbed → residual ~0


def test_pure_tilt_vertex_not_reported():
    px, py = _grid()
    mu = 1.0 + 1.5e-4 * (px - CX)      # pure tilt, no curvature
    res = analyse_field_geometry(px, py, mu, 1.3, cx=CX, cy=CY, half_diag_px=HD)
    # no curvature ⇒ vertex offset not estimable (curvature too weak)
    assert res.vertex.estimable is False


# --------------------------------------------------------------------------- #
# Bowl + tilt → recover bowl sag independent of the tilt
# --------------------------------------------------------------------------- #
def test_bowl_plus_tilt_recovers_sag_independent_of_tilt():
    px, py = _grid()
    xr, yr = px - CX, py - CY
    k_true = 1.2e-8      # mm per px²
    # bowl centred on the frame + a large tilt on top
    bowl = k_true * (xr * xr + yr * yr)
    for tilt in (0.0, 2.0e-4, -3.5e-4):
        mu = 2.0 + bowl + tilt * xr + 0.7 * tilt * yr
        fit = fit_curvature_detrended(px, py, mu, fwhm_mm_median=1.3,
                                      cx=CX, cy=CY, half_diag_px=HD)
        assert fit.k_mm_per_px2 == pytest.approx(k_true, rel=1e-6)
        # sag = k * px_corner²  (independent of the tilt)
        expected_sag_um = k_true * fit.px_corner ** 2 * 1000.0
        assert fit.sag_um == pytest.approx(expected_sag_um, rel=1e-6)
        assert fit.rms_residual_um < 1e-6


def test_sag_sign_bowl_vs_dome():
    px, py = _grid()
    xr, yr = px - CX, py - CY
    r2 = xr * xr + yr * yr
    up = fit_curvature_detrended(px, py, 2.0 + 1e-8 * r2, 1.3,
                                 cx=CX, cy=CY, half_diag_px=HD)
    dn = fit_curvature_detrended(px, py, 2.0 - 1e-8 * r2, 1.3,
                                 cx=CX, cy=CY, half_diag_px=HD)
    assert up.sag_um > 0      # corners focus farther
    assert dn.sag_um < 0      # corners focus nearer


def test_dof_normalised_sag_scales_with_fwhm():
    px, py = _grid()
    xr, yr = px - CX, py - CY
    r2 = xr * xr + yr * yr
    mu = 2.0 + 1e-8 * r2
    a = fit_curvature_detrended(px, py, mu, fwhm_mm_median=1.0,
                                cx=CX, cy=CY, half_diag_px=HD)
    b = fit_curvature_detrended(px, py, mu, fwhm_mm_median=2.0,
                                cx=CX, cy=CY, half_diag_px=HD)
    assert b.sag_dof == pytest.approx(a.sag_dof / 2.0, rel=1e-9)
    # sag_dof = sag_mm / fwhm
    assert a.sag_dof == pytest.approx(a.sag_um / 1000.0 / 1.0, rel=1e-9)


def test_radius_from_curvature_coefficient():
    px, py = _grid()
    xr, yr = px - CX, py - CY
    k = 2.5e-8                      # mm per px²
    pitch_mm = 4.35e-3
    fit = fit_curvature_detrended(px, py, 1.0 + k * (xr * xr + yr * yr), 1.3,
                                  cx=CX, cy=CY, half_diag_px=HD,
                                  sensor_pitch_um=4.35)
    # radius in the sensor-mm frame: k' = k / pitch_mm²; R = 1/(2k')
    k_per_mm2 = k / (pitch_mm * pitch_mm)
    assert fit.radius_mm == pytest.approx(1.0 / (2.0 * k_per_mm2), rel=1e-6)


# --------------------------------------------------------------------------- #
# Vertex offset (tilt-independent decentering)
# --------------------------------------------------------------------------- #
def test_vertex_offset_recovered_no_tilt():
    px, py = _grid()
    k = 1.5e-8
    x0, y0 = CX + 600.0, CY - 400.0     # shifted vertex
    mu = 3.0 + k * ((px - x0) ** 2 + (py - y0) ** 2)
    # a shifted paraboloid IS a plane+quad, so the free-tilt residual ~0; pass it
    # as the reference → vertex estimable.
    curv = fit_curvature_detrended(px, py, mu, 1.3, cx=CX, cy=CY, half_diag_px=HD)
    v = fit_vertex_offset(px, py, mu, cx=CX, cy=CY, half_diag_px=HD,
                          freetilt_rms_um=curv.rms_residual_um)
    assert v.estimable
    assert v.x0_px == pytest.approx(x0, abs=1.0)
    assert v.y0_px == pytest.approx(y0, abs=1.0)
    assert v.offset_px == pytest.approx(math.hypot(600.0, 400.0), rel=1e-3)


def test_vertex_flagged_not_separable_when_true_tilt_present():
    # a CENTRED bowl + a genuine plane tilt is ALGEBRAICALLY identical to a
    # bowl whose vertex is shifted by -t/(2k). With weak curvature + strong tilt
    # that apparent vertex flies far outside the frame → flagged non-estimable
    # (the honest single-config degeneracy: tilt ≡ vertex shift).
    px, py = _grid()
    xr, yr = px - CX, py - CY
    mu = 2.0 + 1.5e-8 * (xr * xr + yr * yr) + 3.0e-4 * xr   # bowl + strong tilt
    curv = fit_curvature_detrended(px, py, mu, 1.3, cx=CX, cy=CY, half_diag_px=HD)
    v = fit_vertex_offset(px, py, mu, cx=CX, cy=CY, half_diag_px=HD,
                          freetilt_rms_um=curv.rms_residual_um)
    assert v.estimable is False
    assert "not separable" in v.note.lower()
    # the apparent vertex is far outside the frame (tilt in disguise)
    assert v.offset_field_frac > 1.0


def test_astigmatism_unavailable():
    px, py = _grid()
    res = analyse_field_geometry(px, py, np.ones_like(px), 1.3,
                                 cx=CX, cy=CY, half_diag_px=HD)
    assert res.astigmatism.available is False
    assert "per-orientation" in res.astigmatism.note
