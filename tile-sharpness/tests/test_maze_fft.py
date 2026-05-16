import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from tile_sharpness.methods.maze_fft import (
    MAZE_PITCH_UM,
    SENSOR_PITCH_UM_Z7,
    maze_amp,
    maze_freq_cy_per_px,
)


def _make_maze(size: int = 1024, period_px: float = 3.0, blur_sigma: float = 0.0) -> np.ndarray:
    """Build a synthetic 2-D maze with one fundamental + a little broadband noise."""
    yy, xx = np.indices((size, size))
    img = (
        128.0
        + 50.0 * np.sin(2 * np.pi * xx / period_px)
        + 50.0 * np.sin(2 * np.pi * yy / period_px)
    )
    if blur_sigma > 0:
        img = gaussian_filter(img, sigma=blur_sigma)
    rng = np.random.default_rng(0)
    img += rng.normal(0, 1.0, img.shape)
    return np.clip(img, 0, 255).astype(np.float32)


def test_maze_freq_at_1to1_matches_prototype():
    # M=1.0, pitch=4.35, maze=13.0 → 0.3346 cy/px (centre of prototype's 0.30-0.36 band).
    f = maze_freq_cy_per_px(1.0)
    assert f == pytest.approx(4.35 / 13.0, rel=1e-6)
    assert 0.30 <= f <= 0.36


def test_maze_freq_scales_inversely_with_M():
    # Half magnification → twice the maze frequency
    f1 = maze_freq_cy_per_px(1.0)
    f_half = maze_freq_cy_per_px(0.5)
    assert f_half == pytest.approx(2 * f1, rel=1e-6)


def test_maze_freq_zero_M_returns_inf():
    assert maze_freq_cy_per_px(0.0) == float("inf")


def test_maze_amp_returns_none_when_aliased():
    # At M=0.4, period_px = 13 * 0.4 / 4.35 = 1.195 px → freq = 0.836 cy/px (past Nyquist).
    img = _make_maze(size=512, period_px=3.0)
    assert maze_amp(img, M=0.4) is None


def test_maze_amp_peaks_at_correct_frequency():
    # Synthetic maze at period 3 px (matches M=1.0 prototype geometry).
    img = _make_maze(size=512, period_px=3.0)
    amp = maze_amp(img, M=1.0)
    assert amp is not None
    assert amp > 0


def test_maze_amp_drops_with_blur():
    sharp = _make_maze(size=512, period_px=3.0, blur_sigma=0.0)
    blurred = _make_maze(size=512, period_px=3.0, blur_sigma=2.5)
    amp_sharp = maze_amp(sharp, M=1.0)
    amp_blurred = maze_amp(blurred, M=1.0)
    assert amp_sharp is not None and amp_blurred is not None
    # Blurring at ~2.5 px sigma kills high-frequency content.
    assert amp_sharp > 5 * amp_blurred


def test_maze_amp_small_roi_returns_zero():
    tiny = np.zeros((4, 4), dtype=np.float32)
    assert maze_amp(tiny, M=1.0) == 0.0


def test_maze_amp_off_frequency_low():
    """A synthetic maze at the WRONG period should give a low maze_amp at M=1.0."""
    # Build a maze at period 10 px instead of 3 px — its energy is well outside
    # the M=1.0 annulus around 0.33 cy/px.
    img = _make_maze(size=512, period_px=10.0)
    amp_wrong = maze_amp(img, M=1.0)
    # And the right maze at period 3 px → high amp.
    img_right = _make_maze(size=512, period_px=3.0)
    amp_right = maze_amp(img_right, M=1.0)
    assert amp_right is not None and amp_wrong is not None
    # period 10 has harmonics + spectral leakage into the annulus; expect
    # the right-period image to dominate by >4×, not orders of magnitude.
    assert amp_right > 4 * amp_wrong
