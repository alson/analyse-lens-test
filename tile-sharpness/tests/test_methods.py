from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from tile_sharpness.methods import (
    score_dct_kurtosis,
    score_edge_decay,
    score_laplacian_var,
    score_radial_fft,
    score_tenengrad,
    score_wavelet_ratio,
)


def _synthetic_blurred_step(sigma: float, size: int = 512) -> np.ndarray:
    """A step-edge image, with each row blurred by ``sigma``."""
    rng = np.random.default_rng(42)
    img = np.where(np.arange(size) < size // 2, 50.0, 200.0)
    img = np.tile(img, (size, 1))
    img += rng.normal(0, 1.5, img.shape)
    img = gaussian_filter(img, sigma=(0, sigma))
    return np.clip(img, 0, 255).astype(np.uint8)


def _synthetic_blurred_random(sigma: float, size: int = 1024) -> np.ndarray:
    rng = np.random.default_rng(0)
    img = rng.uniform(0, 255, (size, size))
    img = gaussian_filter(img, sigma=sigma)
    img = (img - img.min()) / (img.max() - img.min()) * 200 + 20
    return img.astype(np.uint8)


def _save_tile(arr: np.ndarray, path: Path) -> Path:
    Image.fromarray(arr, mode="L").save(path, "JPEG", quality=92)
    return path


def test_edge_decay_monotone_in_blur(tmp_path):
    sharp = _save_tile(_synthetic_blurred_step(0.8), tmp_path / "sharp.jpg")
    blur = _save_tile(_synthetic_blurred_step(3.5), tmp_path / "blur.jpg")
    w_sharp = score_edge_decay(sharp)
    w_blur = score_edge_decay(blur)
    assert w_sharp is not None and w_blur is not None
    assert w_sharp < w_blur  # smaller width = sharper


def test_radial_fft_monotone_in_blur(tmp_path):
    sharp = _save_tile(_synthetic_blurred_random(0.6), tmp_path / "sharp.jpg")
    blur = _save_tile(_synthetic_blurred_random(2.5), tmp_path / "blur.jpg")
    mtf_sharp = score_radial_fft(sharp)
    mtf_blur = score_radial_fft(blur)
    assert mtf_sharp is not None and mtf_blur is not None
    assert mtf_sharp > mtf_blur  # higher MTF50 = sharper


def test_laplacian_var_monotone_in_blur(tmp_path):
    sharp = _save_tile(_synthetic_blurred_random(0.6), tmp_path / "sharp.jpg")
    blur = _save_tile(_synthetic_blurred_random(2.5), tmp_path / "blur.jpg")
    assert score_laplacian_var(sharp) > score_laplacian_var(blur)


def test_tenengrad_monotone_in_blur(tmp_path):
    sharp = _save_tile(_synthetic_blurred_random(0.6), tmp_path / "sharp.jpg")
    blur = _save_tile(_synthetic_blurred_random(2.5), tmp_path / "blur.jpg")
    assert score_tenengrad(sharp) > score_tenengrad(blur)


def test_dct_kurtosis_monotone_in_blur(tmp_path):
    sharp = _save_tile(_synthetic_blurred_random(0.6), tmp_path / "sharp.jpg")
    blur = _save_tile(_synthetic_blurred_random(2.5), tmp_path / "blur.jpg")
    # Blurred image concentrates AC energy near zero → higher kurtosis.
    # Sharp image spreads it out → lower kurtosis. So lower = sharper.
    assert score_dct_kurtosis(sharp) < score_dct_kurtosis(blur)


def test_wavelet_ratio_monotone_in_blur(tmp_path):
    sharp = _save_tile(_synthetic_blurred_random(0.6), tmp_path / "sharp.jpg")
    blur = _save_tile(_synthetic_blurred_random(2.5), tmp_path / "blur.jpg")
    assert score_wavelet_ratio(sharp) > score_wavelet_ratio(blur)
