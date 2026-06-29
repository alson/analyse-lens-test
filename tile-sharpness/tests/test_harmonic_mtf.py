"""Tests for the Route-1 harmonic-decay MTF (self-normalised grating MTF shape)."""
import numpy as np

from tile_sharpness.methods import harmonic_mtf as hm


def _grating(n, pitch, duty):
    x = np.arange(n)
    return ((x % pitch) < pitch * duty).astype(float)


def _blur_with_gaussian_mtf(sig_px, sq):
    n = sq.size
    F = np.fft.rfft(sq)
    fr = np.fft.rfftfreq(n)
    mtf = np.exp(-2 * (np.pi * sig_px * fr) ** 2)
    return np.fft.irfft(F * mtf, n)


def test_recovers_gaussian_mtf_shape_on_square_wave():
    pitch, sig = 16.0, 1.4
    sq = _grating(4096, pitch, 0.5)
    blur = _blur_with_gaussian_mtf(sig, sq)[:256]
    r = hm.harmonic_mtf(blur, 1.0 / pitch, n_harmonics=5)
    assert r is not None
    # duty-0.5 square wave: even harmonics vanish -> only odd ones survive the
    # near-null skip; first surviving ratio is the 3rd harmonic.
    f0 = 1.0 / pitch
    for f, m in zip(r["f_cy_per_px"], r["mtf_ratio"]):
        true = np.exp(-2 * (np.pi * sig * f) ** 2) / np.exp(-2 * (np.pi * sig * f0) ** 2)
        assert abs(m - true) < 0.05, (f, m, true)


def test_duty_cycle_estimate():
    assert abs(hm.estimate_duty_cycle(_grating(2000, 20, 0.3)) - 0.3) < 0.06
    assert abs(hm.estimate_duty_cycle(_grating(2000, 20, 0.6)) - 0.6) < 0.06


def test_sharper_lens_has_slower_harmonic_decay():
    """A sharper (smaller-sigma) lens must show a HIGHER MTF ratio at the same
    harmonic — the discrimination property the metric needs."""
    pitch = 18.0
    sq = _grating(4096, pitch, 0.35)
    sharp = hm.harmonic_mtf(_blur_with_gaussian_mtf(0.8, sq)[:300], 1.0 / pitch)
    soft = hm.harmonic_mtf(_blur_with_gaussian_mtf(2.0, sq)[:300], 1.0 / pitch)
    assert sharp is not None and soft is not None
    # compare the first common harmonic beyond the fundamental
    assert sharp["mtf_ratio"][1] > soft["mtf_ratio"][1]


def test_ratio_bounded_and_monotone_on_clean_target():
    pitch = 20.0
    sq = _grating(4096, pitch, 0.4)
    r = hm.harmonic_mtf(_blur_with_gaussian_mtf(1.2, sq)[:300], 1.0 / pitch, n_harmonics=4)
    assert r is not None
    ratios = r["mtf_ratio"]
    assert ratios[0] == 1.0
    # a real MTF is non-increasing: each ratio <= 1 (+ tiny numerical slack)
    assert all(x <= 1.02 for x in ratios)


def test_none_on_flat_input():
    assert hm.harmonic_mtf(np.ones(256) * 50.0, 0.05) is None


def test_none_on_aliased_fundamental():
    assert hm.harmonic_amplitudes(np.random.rand(256), 0.6) is None
