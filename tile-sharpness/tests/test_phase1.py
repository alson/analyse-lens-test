"""Tests for the LSF + maze-FFT Phase 1 + Phase 2 pipeline."""
from __future__ import annotations

import numpy as np
import pytest

from tile_sharpness.phase1 import (
    SCRIBE_WIDTH_UM,
    TROUGH_FWHM_REJECTION_FRACTION,
    _align_up,
    _expected_scribe_fwhm_px,
    _roi_sizes,
    _rollup_peaks_v2,
    _trough_fwhm_samples,
)
from tile_sharpness.sweeps import Shot, Sweep


def _row(
    *, ix=0, iy=0, k=0, fs=None, on_target=True, lsf_amp=1.0, lsf_mtf=0.10,
    maze_amp=None, maze_resolves=False, rail_mm=None, trough_fwhm=20,
) -> dict:
    return {
        "sweep": "test-sweep",
        "tile_ix": ix,
        "tile_iy": iy,
        "shot_idx": k,
        "rail_position_mm": rail_mm,
        "tile_x_px": 4128,
        "tile_y_px": 2752,
        "lsf_roi_px": 1024,
        "maze_roi_px": 1024,
        "filesize_bytes": fs,
        "on_target": on_target,
        "m": 1.0,
        "m_source": "algo_high",
        "scribe_detected": True,
        "trough_fwhm_px": trough_fwhm,
        "lsf_peak_amp": lsf_amp,
        "lsf_mtf50_cy_per_px": lsf_mtf,
        "maze_resolves": maze_resolves,
        "maze_fft_amp": maze_amp,
    }


def _mk_sweep() -> Sweep:
    return Sweep(label="t", family="test", lens="X", aperture="F8",
                 shots=[Shot(path=__file__, rail_step=k, rail_position_mm=None)
                        for k in range(5)])


def test_align_up_rounds_to_mcu():
    assert _align_up(1024) == 1024
    assert _align_up(1025) == 1040
    assert _align_up(1023) == 1024


def test_roi_sizes_at_1to1():
    """At M=1.0 on Z7: scribe ROI ~3328 px, maze ROI ~256 px (minimums apply)."""
    lsf, maze = _roi_sizes(1.0)
    # 3 * (5000 * 1.0 / 4.35) = ~3448 → aligned up to 3456
    assert lsf >= 3000
    assert lsf % 16 == 0
    # 64 * (13 * 1.0 / 4.35) = ~191 → max(191, 256) = 256
    assert maze == 256


def test_roi_sizes_at_low_M():
    """At very low M the 1024/256 floors kick in (M=0.2 gives 3*230=690 → floor 1024)."""
    lsf, maze = _roi_sizes(0.2)
    assert lsf == 1024
    assert maze == 256


def test_roi_sizes_at_high_M():
    """At M=2.0 on Z7: LSF ROI is huge (centre-only territory)."""
    lsf, _ = _roi_sizes(2.0)
    # 3 * (5000 * 2.0 / 4.35) = ~6896 → aligned up
    assert lsf >= 6896
    assert lsf % 16 == 0


def test_rollup_picks_maze_when_resolves():
    sweep = _mk_sweep()
    rows = [
        _row(k=0, lsf_amp=0.5, maze_amp=0.3, maze_resolves=True, lsf_mtf=0.12),
        _row(k=1, lsf_amp=1.0, maze_amp=0.9, maze_resolves=True, lsf_mtf=0.20),
        _row(k=2, lsf_amp=0.8, maze_amp=0.6, maze_resolves=True, lsf_mtf=0.15),
    ]
    out = _rollup_peaks_v2(rows, sweep, M=1.0)
    assert len(out) == 1
    r = out[0]
    assert r["primary_metric_used"] == "maze_fft"
    assert r["argmax_shot_idx"] == 1
    assert r["peak_value"] == 0.9
    assert r["mtf50_sensor_cy_per_px"] == 0.20
    # subject_lp_per_mm = 0.20 * 1.0 * (1000/4.35) ≈ 45.98
    assert abs(r["mtf50_subject_lp_per_mm"] - 0.20 * 1000.0 / 4.35) < 1e-6


def test_rollup_falls_back_to_lsf_when_maze_does_not_resolve():
    sweep = _mk_sweep()
    rows = [
        _row(k=0, lsf_amp=0.5, maze_amp=None, maze_resolves=False),
        _row(k=1, lsf_amp=1.5, maze_amp=None, maze_resolves=False),
        _row(k=2, lsf_amp=0.8, maze_amp=None, maze_resolves=False),
    ]
    out = _rollup_peaks_v2(rows, sweep, M=0.4)
    assert len(out) == 1
    assert out[0]["primary_metric_used"] == "lsf"
    assert out[0]["argmax_shot_idx"] == 1
    assert out[0]["peak_value"] == 1.5


def test_rollup_off_target_filesize_fallback():
    sweep = _mk_sweep()
    rows = [
        _row(k=0, on_target=False, fs=100, lsf_amp=0.0, maze_amp=None),
        _row(k=1, on_target=False, fs=200, lsf_amp=0.0, maze_amp=None),
        _row(k=2, on_target=False, fs=150, lsf_amp=0.0, maze_amp=None),
    ]
    out = _rollup_peaks_v2(rows, sweep, M=1.0)
    assert len(out) == 1
    assert out[0]["primary_metric_used"] == "filesize_fallback"
    assert out[0]["argmax_shot_idx"] == 1
    assert out[0]["peak_value"] == 200


def test_rollup_off_target_no_filesize_skips():
    sweep = _mk_sweep()
    rows = [
        _row(k=0, on_target=False, fs=None),
        _row(k=1, on_target=False, fs=None),
    ]
    out = _rollup_peaks_v2(rows, sweep, M=1.0)
    assert out == []


def test_trough_fwhm_samples_counts_below_half_depth():
    """Helper counts samples below (min + max) / 2."""
    import numpy as np
    profile = np.array([200, 200, 150, 100, 80, 100, 150, 200, 200], dtype=float)
    # min=80, max=200, half=140. Samples below 140: indices 3, 4, 5 → 3 samples
    # (100, 80, 100)
    assert _trough_fwhm_samples(profile) == 3


def test_expected_scribe_fwhm_scales_with_M():
    """Predicted FWHM = SCRIBE_WIDTH_UM × M / Z7_pitch."""
    pitch = 4.35
    assert _expected_scribe_fwhm_px(1.0) == pytest.approx(SCRIBE_WIDTH_UM / pitch)
    assert _expected_scribe_fwhm_px(2.0) == pytest.approx(2 * SCRIBE_WIDTH_UM / pitch)
    assert _expected_scribe_fwhm_px(0.385) == pytest.approx(0.385 * SCRIBE_WIDTH_UM / pitch)


def test_trough_fwhm_threshold_catches_AF200_outlier():
    """At M=1.0 with FWHM=8 (the AF 200/4D (+1, 0) anomaly), reject."""
    expected = _expected_scribe_fwhm_px(1.0)  # ~20 at M=1.0
    threshold = TROUGH_FWHM_REJECTION_FRACTION * expected
    assert 8 < threshold  # the AF 200/4D outlier gets rejected
    assert 17 > threshold  # real-scribe FWHM (17-22) passes


def test_trough_fwhm_threshold_accepts_low_M_scribe():
    """At M=0.385 a real scribe has FWHM ~7.7 px; threshold should accept."""
    expected = _expected_scribe_fwhm_px(0.385)  # ~7.7 at M=0.385
    threshold = TROUGH_FWHM_REJECTION_FRACTION * expected
    assert 4 >= threshold  # real-scribe FWHM at low M still passes


def test_rollup_multiple_tiles():
    sweep = _mk_sweep()
    rows = []
    for ix, iy in [(0, 0), (1, 0), (-1, 0)]:
        for k in range(3):
            rows.append(_row(ix=ix, iy=iy, k=k, lsf_amp=float(k),
                             maze_amp=None, maze_resolves=False))
    out = _rollup_peaks_v2(rows, sweep, M=0.5)
    assert len(out) == 3
    for r in out:
        assert r["argmax_shot_idx"] == 2
        assert r["primary_metric_used"] == "lsf"
