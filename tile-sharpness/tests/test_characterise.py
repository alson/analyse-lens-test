"""Tests for the Phase 3 per-slug characterisation."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from tile_sharpness.characterise import (
    _peak_asymmetry,
    _plane_fit,
    characterise_sweep,
)


def _peaks_row(
    *, ix: int, iy: int, x: int, y: int, mtf_subj: float = 30.0,
    peak: float = 1.0, argmax_idx: int = 30, rail_mm: float | None = None,
) -> dict:
    return {
        "sweep": "test",
        "tile_ix": ix,
        "tile_iy": iy,
        "primary_metric_used": "maze_fft",
        "argmax_shot_idx": argmax_idx,
        "peak_value": peak,
        "mtf50_sensor_cy_per_px": 0.15,
        "mtf50_subject_lp_per_mm": mtf_subj,
        "rail_position_mm_at_argmax": rail_mm,
        "m": 1.0,
        "m_source": "algo_high",
        "tile_x_px": x,
        "tile_y_px": y,
        "lsf_roi_px": 1024,
        "maze_roi_px": 256,
    }


def _z7_full_grid_rows(centre_mtf: float, dx_mtf: float, fx_mtf: float) -> list[dict]:
    """Build 9 rows: centre + 4 DX corners + 4 FX corners."""
    rows = []
    # Centre
    rows.append(_peaks_row(ix=0, iy=0, x=4128, y=2752, mtf_subj=centre_mtf))
    # DX corners: ~(±2704, ±1800) → nearest cells (±3, ±2) at 1024 step
    # actually closer to (±2, ±1) at 1024 step (cell centre 4128 ± 2048 = 2080 / 6176)
    for ix, iy in [(-2, -1), (2, -1), (-2, 1), (2, 1)]:
        rows.append(_peaks_row(
            ix=ix, iy=iy, x=4128 + 1024 * ix, y=2752 + 1024 * iy,
            mtf_subj=dx_mtf,
        ))
    # FX corners: extreme grid (±3, ±2)
    for ix, iy in [(-3, -2), (3, -2), (-3, 2), (3, 2)]:
        rows.append(_peaks_row(
            ix=ix, iy=iy, x=4128 + 1024 * ix, y=2752 + 1024 * iy,
            mtf_subj=fx_mtf,
        ))
    return rows


def test_peak_asymmetry_basic():
    assert _peak_asymmetry(1.2, 0.8) == pytest.approx(0.4)
    assert _peak_asymmetry(0.8, 1.2) == pytest.approx(-0.4)
    assert _peak_asymmetry(1.0, 1.0) == 0.0
    assert _peak_asymmetry(None, 1.0) is None
    assert _peak_asymmetry(0.0, 0.0) is None  # mean=0 guard


def test_plane_fit_recovers_known_plane():
    # z = 0.5 * x + 0.0 * y + 10.0
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    ys = [0.0, 0.0, 1.0, 1.0, 2.0]
    zs = [0.5 * x + 0.0 * y + 10.0 for x, y in zip(xs, ys, strict=True)]
    a, b, c, rms = _plane_fit(xs, ys, zs)
    assert a == pytest.approx(0.5, abs=1e-9)
    assert b == pytest.approx(0.0, abs=1e-9)
    assert c == pytest.approx(10.0, abs=1e-9)
    assert rms < 1e-9


def test_plane_fit_too_few_points_returns_nan():
    a, b, c, rms = _plane_fit([0.0], [0.0], [1.0])
    assert math.isnan(a)
    assert math.isnan(rms)


def test_characterise_full_9_position():
    df = pd.DataFrame(_z7_full_grid_rows(centre_mtf=40.0, dx_mtf=30.0, fx_mtf=20.0))
    result = characterise_sweep(df)
    assert result["n_positions"] == 9
    assert result["mtf50_centre_lpmm"] == 40.0
    assert result["mtf50_dx_corner_mean_lpmm"] == 30.0
    assert result["mtf50_fx_corner_mean_lpmm"] == 20.0
    assert result["uniformity_dx"] == pytest.approx(0.75)
    assert result["uniformity_fx"] == pytest.approx(0.5)


def test_characterise_centre_only():
    df = pd.DataFrame([_peaks_row(ix=0, iy=0, x=4128, y=2752, mtf_subj=35.0)])
    result = characterise_sweep(df)
    assert result["n_positions"] == 1
    assert result["mtf50_centre_lpmm"] == 35.0
    assert math.isnan(result["mtf50_dx_corner_mean_lpmm"])
    assert math.isnan(result["uniformity_dx"])
    # FX must also be NaN when grid is centre-only — pre-fix bug returned
    # centre values for fx corners, silently reporting uniformity_fx = 1.0.
    assert math.isnan(result["mtf50_fx_corner_mean_lpmm"])
    assert math.isnan(result["uniformity_fx"])
    assert "centre_only" in result["note"]


def test_characterise_decentering_value_asymmetry():
    # Left corners weaker than right corners → negative dec_*_lr
    rows = []
    rows.append(_peaks_row(ix=0, iy=0, x=4128, y=2752, peak=1.0))
    for ix, iy, peak in [(-2, -1, 0.8), (2, -1, 1.2),
                          (-2, 1, 0.8), (2, 1, 1.2)]:
        rows.append(_peaks_row(ix=ix, iy=iy, x=4128 + 1024 * ix, y=2752 + 1024 * iy, peak=peak))
    for ix, iy, peak in [(-3, -2, 0.7), (3, -2, 1.3),
                          (-3, 2, 0.7), (3, 2, 1.3)]:
        rows.append(_peaks_row(ix=ix, iy=iy, x=4128 + 1024 * ix, y=2752 + 1024 * iy, peak=peak))
    result = characterise_sweep(pd.DataFrame(rows))
    # DX: (left_avg − right_avg) / mean = (0.8 − 1.2) / 1.0 = -0.4
    assert result["decentering_dx_lr"] == pytest.approx(-0.4, abs=1e-9)
    # FX: stronger asymmetry
    assert result["decentering_fx_lr"] == pytest.approx(-0.6, abs=1e-9)
    # Top vs bottom should be ~0 (symmetric peak values across the rows)
    assert abs(result["decentering_dx_tb"]) < 1e-9
    assert abs(result["decentering_fx_tb"]) < 1e-9


def test_characterise_subject_tilt_from_rail_mm():
    """Tilt along x: rail_mm rises with tile_x_px → physical subject tilt in degrees."""
    rows = []
    base = 4128
    for ix in [-3, -1, 0, 1, 3]:
        for iy in [-2, 0, 2]:
            x = base + 1024 * ix
            y = 2752 + 1024 * iy
            rail = 10.0 + 0.001 * x  # 0.001 mm rail shift per sensor px
            rows.append(_peaks_row(ix=ix, iy=iy, x=x, y=y, rail_mm=rail))
    result = characterise_sweep(pd.DataFrame(rows))
    # At M=1, 0.001 mm/px rail-slope = object-slope tan = 0.001 / (4.35e-6 m / 1)
    # = 0.001 × 1 × 1000 / 4.35 = 0.2299 → 12.95°.
    assert result["subject_tilt_x_deg"] == pytest.approx(12.95, abs=0.1)
    assert abs(result["subject_tilt_y_deg"]) < 0.01
    # Plane fit residuals are zero on a true plane (× 1000 mm→µm still ≈ 0).
    assert result["field_curvature_um_rms"] < 1e-3
    assert "rail_mm_unavailable" not in result["note"]
    assert result["rail_z_source"] == "recorded"


def test_characterise_no_rail_mm_falls_back_to_argmax_idx():
    rows = []
    for ix in [-1, 0, 1]:
        for iy in [-1, 0, 1]:
            x = 4128 + 1024 * ix
            y = 2752 + 1024 * iy
            rows.append(_peaks_row(
                ix=ix, iy=iy, x=x, y=y, rail_mm=None, argmax_idx=30 + iy,
            ))
    result = characterise_sweep(pd.DataFrame(rows))
    assert "rail_mm_unavailable" in result["note"]
    assert math.isnan(result["field_curvature_um_rms"])
    assert result["rail_z_source"] == "shot_index"
    # Tilt should be along y, since argmax_idx = 30 + iy
    assert abs(result["subject_tilt_y_deg"]) > 0.05


def test_characterise_uses_rail_step_calibration_when_rail_mm_missing():
    """With rail_step_mm provided, the synthesized rail-mm path gives real degrees."""
    rows = []
    rail_step = 0.05  # mm per shot
    for ix in [-3, -1, 0, 1, 3]:
        for iy in [-2, 0, 2]:
            x = 4128 + 1024 * ix
            y = 2752 + 1024 * iy
            # rail_position = 30 + iy shots = (30+iy) * 0.05 mm — pure y tilt
            rows.append(_peaks_row(
                ix=ix, iy=iy, x=x, y=y, rail_mm=None, argmax_idx=30 + iy,
            ))
    result = characterise_sweep(pd.DataFrame(rows), rail_step_mm=rail_step)
    assert result["rail_z_source"] == "calibrated"
    assert "rail_mm_calibrated" in result["note"]
    # Slope_b = (0.05 mm/shot × 1 shot per iy) / (1024 px per iy) = 4.88e-5 mm/px
    # tilt_y_deg = atan(4.88e-5 × 1 × 1000 / 4.35) × 180/π = atan(0.01122) ≈ 0.643°
    assert result["subject_tilt_y_deg"] == pytest.approx(0.643, abs=0.05)
    # And field_curvature is now in µm (was NaN without calibration).
    assert math.isfinite(result["field_curvature_um_rms"])


def test_characterise_calibration_preferred_over_shot_index_fallback():
    """Even when rail_step_mm is supplied, recorded rail_mm wins per-row."""
    rows = []
    for ix in [-1, 0, 1]:
        for iy in [-1, 0, 1]:
            x = 4128 + 1024 * ix
            y = 2752 + 1024 * iy
            # Each row HAS recorded rail_mm.
            rows.append(_peaks_row(
                ix=ix, iy=iy, x=x, y=y, rail_mm=10.0 + 0.0005 * y,
                argmax_idx=30,
            ))
    result = characterise_sweep(pd.DataFrame(rows), rail_step_mm=0.05)
    # Source is "recorded" because every row carried a real rail_mm; the
    # supplied rail_step_mm is unused (and harmless).
    assert result["rail_z_source"] == "recorded"
