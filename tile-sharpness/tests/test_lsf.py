import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from tile_sharpness.methods.lsf import (
    Segment,
    cross_section,
    detect_scribe,
    lsf_mtf50,
    lsf_peak_amp,
)


def _make_scribe_image(
    size: int = 512, scribe_sigma: float = 1.0, scribe_depth: float = 80.0,
    angle_deg: float = 4.5, scribe_width_px: float = 3.0,
) -> np.ndarray:
    """Build a synthetic ROI: bright background with one dark slanted line."""
    rng = np.random.default_rng(0)
    img = np.full((size, size), 200.0, dtype=np.float64)
    # Add a slanted dark line through the centre.
    yy, xx = np.indices(img.shape)
    cx, cy = size // 2, size // 2
    a = np.deg2rad(angle_deg)
    # Perpendicular distance to a line through (cx, cy) with direction (cos a, sin a).
    perp = (xx - cx) * np.sin(a) - (yy - cy) * np.cos(a)
    profile = np.exp(-0.5 * (perp / scribe_width_px) ** 2)
    img -= scribe_depth * profile
    # Apply optical blur (LSF width to be measured).
    img = gaussian_filter(img, sigma=scribe_sigma)
    img += rng.normal(0, 1.0, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_detect_scribe_finds_dark_line():
    img = _make_scribe_image(size=512, scribe_sigma=1.0, angle_deg=4.5)
    seg = detect_scribe(img, min_length_ratio=0.5, min_length_px=100)
    assert seg is not None
    # Length should span most of the ROI.
    assert seg.length_px > 0.6 * 512
    # Angle should be near ±4.5° (LSD may flip endpoints; compare against |sin|).
    angle = abs(seg.angle_rad) * 180 / np.pi
    angle = min(angle, 180 - angle)
    assert angle < 12.0  # within 12° of horizontal


def test_detect_scribe_returns_none_on_blank():
    img = np.full((512, 512), 200, dtype=np.uint8)
    rng = np.random.default_rng(0)
    img = (img + rng.normal(0, 1.0, img.shape)).clip(0, 255).astype(np.uint8)
    seg = detect_scribe(img, min_length_ratio=0.5, min_length_px=100)
    assert seg is None


def test_cross_section_recovers_lsf_width():
    # Sharp scribe (sigma=1.0) → narrow cross-section
    sharp = _make_scribe_image(scribe_sigma=1.0)
    seg_sharp = detect_scribe(sharp, min_length_ratio=0.5, min_length_px=100)
    assert seg_sharp is not None
    profile_sharp = cross_section(sharp, seg_sharp, half_window_px=16)
    # Profile minimum at centre, recovers toward edges
    centre_idx = profile_sharp.size // 2
    assert profile_sharp[centre_idx] < profile_sharp[0] - 10
    assert profile_sharp[centre_idx] < profile_sharp[-1] - 10


def test_sharp_profile_has_higher_lsf_peak_amp_than_blurred():
    sharp = _make_scribe_image(scribe_sigma=0.7)
    blurred = _make_scribe_image(scribe_sigma=4.0)
    seg_s = detect_scribe(sharp, min_length_ratio=0.5, min_length_px=100)
    seg_b = detect_scribe(blurred, min_length_ratio=0.5, min_length_px=100)
    assert seg_s is not None and seg_b is not None
    ps = cross_section(sharp, seg_s, half_window_px=24)
    pb = cross_section(blurred, seg_b, half_window_px=24)
    amp_sharp = lsf_peak_amp(ps, ref_freq_cy_per_px=0.20)
    amp_blurred = lsf_peak_amp(pb, ref_freq_cy_per_px=0.20)
    assert amp_sharp > amp_blurred


def test_sharp_profile_has_higher_lsf_mtf50_than_blurred():
    sharp = _make_scribe_image(scribe_sigma=0.7)
    blurred = _make_scribe_image(scribe_sigma=4.0)
    seg_s = detect_scribe(sharp, min_length_ratio=0.5, min_length_px=100)
    seg_b = detect_scribe(blurred, min_length_ratio=0.5, min_length_px=100)
    assert seg_s is not None and seg_b is not None
    ps = cross_section(sharp, seg_s, half_window_px=24)
    pb = cross_section(blurred, seg_b, half_window_px=24)
    mtf_sharp = lsf_mtf50(ps)
    mtf_blurred = lsf_mtf50(pb)
    # Both should produce a usable MTF50; sharp > blurred.
    assert mtf_sharp is not None
    assert mtf_blurred is not None
    assert mtf_sharp > mtf_blurred


def test_lsf_peak_amp_handles_zero_profile():
    assert lsf_peak_amp(np.zeros(49)) == 0.0


def test_lsf_mtf50_handles_zero_profile():
    assert lsf_mtf50(np.zeros(49)) is None
