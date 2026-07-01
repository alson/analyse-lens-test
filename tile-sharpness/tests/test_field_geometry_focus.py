"""POC 4 tests — plane/curvature/decentering recovery on synthetic fields."""
from __future__ import annotations

import math

import numpy as np
import pytest

from tile_sharpness.field_geometry_focus import (
    analyse_field_geometry,
    compute_decentering,
    fit_field_curvature,
    fit_plane_tilt,
)
from tile_sharpness.methods.maze_fft import SENSOR_PITCH_UM_Z7

# A Z7-ish 5x3 sensor-pixel grid centred on the frame.
_PX = np.array([2080, 3104, 4128, 5152, 6176], float)
_PY = np.array([1728, 2752, 3776], float)
HALF_DIAG = 0.5 * math.hypot(8256, 5504)  # Z7 full frame


def _grid():
    xs, ys = np.meshgrid(_PX, _PY)
    return xs.ravel(), ys.ravel()


def _field_height(px, py, cx, cy):
    return np.hypot(px - cx, py - cy) / HALF_DIAG


# --------------------------------------------------------------------------- #
# Plane tilt recovery
# --------------------------------------------------------------------------- #
def test_plane_fit_recovers_known_slope():
    px, py = _grid()
    a_true, b_true, c_true = 1.3e-4, -7.0e-5, 3.2  # mm per px
    mu = a_true * px + b_true * py + c_true
    pt = fit_plane_tilt(px, py, mu, m=1.0)
    assert pt.a_mm_per_px == pytest.approx(a_true, rel=1e-6)
    assert pt.b_mm_per_px == pytest.approx(b_true, rel=1e-6)
    assert pt.c_mm == pytest.approx(c_true, rel=1e-6)
    assert pt.rms_residual_mm == pytest.approx(0.0, abs=1e-9)


def test_tilt_deg_matches_slope_to_tilt_formula():
    # object_slope = slope * M * 1000 / pitch_um ; tilt = atan(object_slope)
    px, py = _grid()
    a_true = 2.0e-4
    m = 1.0
    mu = a_true * px + 0.0 * py + 1.0
    pt = fit_plane_tilt(px, py, mu, m=m)
    expected = math.degrees(math.atan(a_true * m * 1000.0 / SENSOR_PITCH_UM_Z7))
    assert pt.tilt_x_deg == pytest.approx(expected, rel=1e-9)
    assert pt.tilt_y_deg == pytest.approx(0.0, abs=1e-9)


def test_tilt_magnitude_combines_axes():
    px, py = _grid()
    a_true, b_true = 1.5e-4, 1.5e-4
    mu = a_true * px + b_true * py
    pt = fit_plane_tilt(px, py, mu, m=1.0)
    tx = math.radians(pt.tilt_x_deg)
    ty = math.radians(pt.tilt_y_deg)
    mag = math.degrees(math.atan(math.hypot(math.tan(tx), math.tan(ty))))
    assert pt.tilt_mag_deg == pytest.approx(mag, rel=1e-9)
    assert pt.tilt_mag_deg > max(abs(pt.tilt_x_deg), abs(pt.tilt_y_deg))


def test_tilt_azimuth_points_uphill_image_convention():
    # mu increases to the RIGHT only (a>0, b=0) → steepest ascent at +x = 0°.
    px, py = _grid()
    mu = 1e-4 * px
    assert fit_plane_tilt(px, py, mu, 1.0).tilt_azimuth_deg == pytest.approx(0.0, abs=1e-6)
    # mu increases DOWNWARD in the image (py grows down, b>0) → ascent is DOWN = -90°.
    mu = 1e-4 * py
    assert fit_plane_tilt(px, py, mu, 1.0).tilt_azimuth_deg == pytest.approx(-90.0, abs=1e-6)
    # mu increases UPWARD in the image (b<0) → ascent is UP = +90°.
    mu = -1e-4 * py
    assert fit_plane_tilt(px, py, mu, 1.0).tilt_azimuth_deg == pytest.approx(90.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# Field curvature recovery
# --------------------------------------------------------------------------- #
def test_curvature_recovers_known_bowl():
    px, py = _grid()
    cx, cy = px.mean(), py.mean()
    fh = _field_height(px, py, cx, cy)
    k_true, d_true = 0.40, 0.0   # mm per fh² ; sag scales with fh_max²
    resid = k_true * fh * fh + d_true
    fc = fit_field_curvature(fh, resid)
    assert fc.curv_coef_mm_per_fh2 == pytest.approx(k_true, rel=1e-6)
    fh_max = fh.max()
    expected_sag_um = k_true * fh_max * fh_max * 1000.0
    assert fc.sag_um == pytest.approx(expected_sag_um, rel=1e-6)
    assert fc.rms_residual_um == pytest.approx(0.0, abs=1e-6)


def test_curvature_sign_dome_vs_bowl():
    px, py = _grid()
    cx, cy = px.mean(), py.mean()
    fh = _field_height(px, py, cx, cy)
    # corners focus FARTHER (mu larger at edge) → +ve sag
    assert fit_field_curvature(fh, 0.3 * fh * fh).sag_um > 0
    # corners focus NEARER → -ve sag
    assert fit_field_curvature(fh, -0.3 * fh * fh).sag_um < 0
    # flat field → ~0 sag
    assert abs(fit_field_curvature(fh, np.zeros_like(fh)).sag_um) < 1e-9


def test_plane_plus_bowl_separates_cleanly():
    # A tilted plane PLUS a bowl: plane fit removes the tilt, curvature catches the bowl.
    px, py = _grid()
    cx, cy = px.mean(), py.mean()
    fh = _field_height(px, py, cx, cy)
    a_true, b_true, c_true = 1.0e-4, -5e-5, 2.0
    k_true = 0.25
    mu = a_true * px + b_true * py + c_true + k_true * fh * fh
    res = analyse_field_geometry(px, py, mu, fh, np.zeros_like(fh), m=1.0)
    # tilt comes from the plane part
    exp_tx = math.degrees(math.atan(a_true * 1000.0 / SENSOR_PITCH_UM_Z7))
    assert res.plane.tilt_x_deg == pytest.approx(exp_tx, rel=1e-3)
    # curvature coefficient ~ k_true (plane removal shifts it slightly but sign+scale hold)
    assert res.curvature.curv_coef_mm_per_fh2 == pytest.approx(k_true, rel=0.15)
    assert res.curvature.sag_um > 0


# --------------------------------------------------------------------------- #
# Decentering
# --------------------------------------------------------------------------- #
def test_decentering_left_right():
    px, py = _grid()
    cx, cy = px.mean(), py.mean()
    # left half focuses 0.10 mm farther than the right half
    mu = np.where(px < cx, 0.10, 0.0) + np.where(px > cx, -0.10, 0.0)
    dec = compute_decentering(px, py, mu, cx, cy)
    assert dec.lr_mm == pytest.approx(0.20, rel=1e-6)
    assert dec.tb_mm == pytest.approx(0.0, abs=1e-9)
    assert dec.n_left == dec.n_right


def test_decentering_top_bottom_sign():
    px, py = _grid()
    cx, cy = px.mean(), py.mean()
    # image-TOP (py<cy) focuses farther → +ve tb
    mu = np.where(py < cy, 0.05, 0.0) + np.where(py > cy, -0.05, 0.0)
    dec = compute_decentering(px, py, mu, cx, cy)
    assert dec.tb_mm == pytest.approx(0.10, rel=1e-6)
    assert dec.lr_mm == pytest.approx(0.0, abs=1e-9)


def test_astigmatism_unavailable_without_orientation():
    px, py = _grid()
    cx, cy = px.mean(), py.mean()
    fh = _field_height(px, py, cx, cy)
    res = analyse_field_geometry(px, py, np.zeros_like(px), fh,
                                 np.zeros_like(px), m=1.0, edge_orient_deg=None)
    assert res.astigmatism.available is False


def test_astigmatism_recovered_when_orientation_given():
    # synthetic: sagittal edges focus 0.08 mm farther than tangential ones.
    rng = np.random.default_rng(0)
    n = 60
    ang = rng.uniform(-180, 180, n)
    fh = rng.uniform(0.4, 0.9, n)
    px = 4128 + fh * 1000 * np.cos(np.radians(ang))
    py = 2752 - fh * 1000 * np.sin(np.radians(ang))
    # half the patches sagittal (edge along radius), half tangential (perpendicular)
    is_sag = rng.random(n) < 0.5
    edge = np.where(is_sag, ang, ang + 90.0)
    mu = np.where(is_sag, 0.08, 0.0)
    from tile_sharpness.field_geometry_focus import compute_astigmatism
    a = compute_astigmatism(ang, edge, mu, fh)
    assert a.available
    assert a.delta_mm == pytest.approx(0.08, abs=0.01)
