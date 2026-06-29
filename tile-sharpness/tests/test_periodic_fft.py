"""Tests for the bounded periodic-FFT contrast metric and the arbitrary-frequency
diffraction MTF ceiling."""
from __future__ import annotations

import math

import numpy as np
import pytest

from tile_sharpness.methods.periodic_fft import (
    periodic_contrast, derotate, discover_fundamental,
)
from tile_sharpness import optics


def _grating(n, pitch, contrast, axis="u", mean=128.0, noise=0.0, seed=0):
    """n×n image: m + m*C*cos(2π x/pitch) along the chosen axis."""
    rng = np.random.default_rng(seed)
    x = np.arange(n)
    line = mean * (1.0 + contrast * np.cos(2 * np.pi * x / pitch))
    if axis == "u":
        img = np.tile(line[None, :], (n, 1))
    else:
        img = np.tile(line[:, None], (1, n))
    if noise:
        img = img + rng.normal(0, noise, img.shape)
    return img.astype(np.float64)


def test_recovers_known_contrast():
    for C in (0.2, 0.5, 0.9):
        img = _grating(256, pitch=8.0, contrast=C)
        r = periodic_contrast(img, pitch_px=8.0, axis="u")
        assert r is not None
        assert r["contrast"] == pytest.approx(C, abs=0.05)


def test_bounded_in_unit_interval():
    # Even a square wave (rich harmonics) must not exceed 1 at the fundamental.
    n = 256
    x = np.arange(n)
    sq = 128.0 * (1.0 + np.sign(np.cos(2 * np.pi * x / 10.0)))
    img = np.tile(sq[None, :], (n, 1))
    r = periodic_contrast(img, pitch_px=10.0, axis="u")
    assert r is not None
    assert 0.0 <= r["contrast"] <= 1.0


def test_flat_field_reads_zero():
    img = np.full((128, 128), 100.0)
    r = periodic_contrast(img, pitch_px=8.0, axis="u")
    assert r is not None
    assert r["contrast"] < 0.02


def test_aliased_pitch_returns_none():
    img = _grating(128, pitch=8.0, contrast=0.5)
    assert periodic_contrast(img, pitch_px=1.5) is None  # f0 > Nyquist


def test_auto_axis_picks_stronger():
    img = _grating(256, pitch=8.0, contrast=0.7, axis="v")
    r = periodic_contrast(img, pitch_px=8.0, axis="auto")
    assert r is not None
    assert r["axis"] == "v"
    assert r["contrast"] == pytest.approx(0.7, abs=0.06)


def test_contrast_drops_with_blur():
    # A blurred grating must read lower contrast than a sharp one (tracks MTF).
    sharp = _grating(256, pitch=6.0, contrast=0.8)
    import cv2
    blur = cv2.GaussianBlur(sharp, (0, 0), 1.5)
    cs = periodic_contrast(sharp, pitch_px=6.0, axis="u")["contrast"]
    cb = periodic_contrast(blur, pitch_px=6.0, axis="u")["contrast"]
    assert cb < cs


# --- pitch discovery ----------------------------------------------------------

def test_discover_finds_pitch_in_band():
    img = _grating(512, pitch=10.0, contrast=0.5, axis="u", noise=2.0)
    d = discover_fundamental(img, band=(0.06, 0.30))
    assert d is not None
    assert d["pitch_px"] == pytest.approx(10.0, rel=0.1)
    assert d["axis"] == "u"


def test_discover_excludes_maze_band():
    # A 3px-pitch grating (0.33 cy/px) must be skipped by the maze exclude.
    img = _grating(512, pitch=3.0, contrast=0.6, axis="u")
    d = discover_fundamental(img, band=(0.06, 0.45), exclude=(0.31, 0.36))
    # nothing else periodic -> the in-band peak is noise, not the 0.33 line
    assert d is None or abs(d["f0_cy_per_px"] - 0.333) > 0.02


def test_discover_none_on_flat():
    assert discover_fundamental(np.full((128, 128), 50.0)) is None


# --- diffraction ceiling at arbitrary frequency -------------------------------

def test_diffraction_mtf_at_endpoints():
    assert optics.diffraction_mtf_at(1e-9, 8.0) == pytest.approx(1.0, abs=1e-3)
    # at cutoff and beyond -> 0
    cutoff = 1.0 / (0.55e-3 * 8.0)
    assert optics.diffraction_mtf_at(cutoff, 8.0) == pytest.approx(0.0, abs=1e-6)
    assert optics.diffraction_mtf_at(cutoff * 1.5, 8.0) == 0.0


def test_diffraction_mtf50_consistency():
    # diffraction_mtf_at should cross 0.5 at the MTF50 sensor frequency.
    n_eff = 11.0
    nu50 = optics.diffraction_mtf50_sensor_lpmm(n_eff)
    assert optics.diffraction_mtf_at(nu50, n_eff) == pytest.approx(0.5, abs=0.01)


def test_diffraction_mtf_monotone_decreasing():
    n_eff = 8.0
    cutoff = 1.0 / (0.55e-3 * n_eff)
    xs = np.linspace(0.01, 0.99, 50) * cutoff
    ys = [optics.diffraction_mtf_at(x, n_eff) for x in xs]
    assert all(ys[i] >= ys[i + 1] - 1e-9 for i in range(len(ys) - 1))


def test_subject_ceiling_bounded_and_consistent():
    # The subject-space ceiling at a subject frequency must equal the sensor-plane
    # ceiling at the corresponding sensor frequency ν_subj/M, and stay in [0,1].
    f_subj, n_marked, M = 30.0, 8.0, 1.6
    c = optics.diffraction_mtf_subject_at(f_subj, n_marked, M)
    n_eff = optics.effective_fnumber(n_marked, M)
    c_sensor = optics.diffraction_mtf_at(f_subj / M, n_eff)
    assert c == pytest.approx(c_sensor, abs=1e-9)
    assert 0.0 <= c <= 1.0
