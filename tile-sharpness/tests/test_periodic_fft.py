"""Tests for the bounded periodic-FFT contrast metric and the arbitrary-frequency
diffraction MTF ceiling."""
from __future__ import annotations

import math

import numpy as np
import pytest

from tile_sharpness.methods.periodic_fft import (
    periodic_contrast, derotate, discover_fundamental, discover_fundamental_2d,
    maze_band_cy_per_px, resolvable_band_cy_per_px, LPMM_PER_CYPX,
)
from tile_sharpness.methods.maze_fft import maze_freq_cy_per_px
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


# --- M-aware band + maze exclusion (A5 fix) -----------------------------------

def _pad_plus_maze(n, pad_pitch, maze_pitch, axis="u", pad_C=0.5, maze_C=0.6,
                   mean=128.0, noise=1.0, seed=1):
    """ROI carrying TWO gratings along ``axis``: a low-frequency pad fundamental and a
    high-contrast maze line. Used to prove the discovery locks onto the pad, not the
    (stronger) maze, once the maze is excluded."""
    rng = np.random.default_rng(seed)
    x = np.arange(n)
    line = mean * (1.0 + pad_C * np.cos(2 * np.pi * x / pad_pitch)
                   + maze_C * np.cos(2 * np.pi * x / maze_pitch))
    img = (np.tile(line[None, :], (n, 1)) if axis == "u"
           else np.tile(line[:, None], (1, n)))
    if noise:
        img = img + rng.normal(0, noise, img.shape)
    return img.astype(np.float64)


def test_M_none_is_exactly_static():
    # Backward-compat: M=None must return byte-identical results to the static call.
    img = _grating(512, pitch=10.0, contrast=0.5, axis="u", noise=2.0)
    static = discover_fundamental(img, band=(0.06, 0.30), exclude=(0.31, 0.36))
    default = discover_fundamental(img)            # same static defaults
    none_M = discover_fundamental(img, M=None)
    assert default == static
    assert none_M == static


def test_maze_band_tracks_M():
    # Maze frequency slides DOWN with M; the exclusion window must follow it.
    f1 = maze_band_cy_per_px(1.0)
    f2 = maze_band_cy_per_px(2.0)
    assert f1 is not None and f2 is not None
    assert f1[0] == pytest.approx(maze_freq_cy_per_px(1.0), rel=1e-9)   # ~0.335
    assert f2[0] == pytest.approx(maze_freq_cy_per_px(2.0), rel=1e-9)   # ~0.167
    assert f2[0] < f1[0]
    # ±10%-of-freq window brackets the maze frequency.
    assert f2[1] < f2[0] < f2[2]
    assert f2[2] - f2[1] == pytest.approx(0.2 * f2[0], rel=1e-6)


def test_resolvable_band_reproduces_static_at_low_M():
    # Regression invariant: at M≈1 the M-aware band must equal the static (0.06,0.30)
    # band exactly — the pad fundamental sits well above 0.06 so the floor is not lowered.
    lo1, hi1 = resolvable_band_cy_per_px(1.0)
    assert (lo1, hi1) == pytest.approx((0.06, 0.30))
    lo105, hi105 = resolvable_band_cy_per_px(1.056)
    assert (lo105, hi105) == pytest.approx((0.06, 0.30))


def test_resolvable_band_floor_drops_only_at_high_M():
    # The floor lowers only when the static 0.06 would clip the pad fundamental.
    lo1, hi1 = resolvable_band_cy_per_px(1.0)
    lo2, hi2 = resolvable_band_cy_per_px(2.0)
    assert lo2 < lo1                       # higher M -> lower floor (admits ~18 lp/mm)
    assert hi1 == hi2 == pytest.approx(0.30)   # ceiling unchanged at the static value
    # f1 of an 18 lp/mm pad at M=2 (~0.039 cy/px) is below static 0.06 but inside the band.
    f1_px_M2 = 18.0 / (LPMM_PER_CYPX * 2.0)
    assert f1_px_M2 < 0.06
    assert lo2 < f1_px_M2 < hi2


def test_low_M_matches_static_pick_with_maze_present():
    # At M≈1 the M-aware path must reproduce the static pick: the maze (~0.335 cy/px) is
    # outside both ceilings, and a real pad fundamental inside the band is picked the same.
    n = 512
    maze_pitch = 1.0 / maze_freq_cy_per_px(1.0)        # ~2.99 px
    img = _pad_plus_maze(n, pad_pitch=10.0, maze_pitch=maze_pitch, axis="u")
    static = discover_fundamental(img, band=(0.06, 0.30), exclude=(0.31, 0.36))
    aware = discover_fundamental(img, M=1.0)
    assert static is not None and aware is not None
    # same pad fundamental, not the maze
    assert aware["f0_cy_per_px"] == pytest.approx(static["f0_cy_per_px"], abs=1e-6)
    assert aware["pitch_px"] == pytest.approx(10.0, rel=0.05)
    assert abs(aware["f0_cy_per_px"] - maze_freq_cy_per_px(1.0)) > 0.05


def test_high_M_excludes_maze_finds_pad():
    # The A5 bug: at M≈2 the maze (~0.167 cy/px) slides INTO the static 0.06-0.30 band,
    # so the static call locks onto the (stronger) maze. The M-aware call must exclude
    # the maze and return the lower-frequency pad fundamental instead.
    n = 512
    M = 2.0
    maze_px = 1.0 / maze_freq_cy_per_px(M)             # ~5.98 px (0.167 cy/px)
    # pad fundamental ~18 lp/mm subject -> ~0.039 cy/px -> ~25.5 px pitch at M=2
    pad_px = 1.0 / (18.0 / (LPMM_PER_CYPX * M))
    img = _pad_plus_maze(n, pad_pitch=pad_px, maze_pitch=maze_px, axis="u",
                         pad_C=0.4, maze_C=0.7)
    static = discover_fundamental(img, band=(0.06, 0.30), exclude=(0.31, 0.36))
    aware = discover_fundamental(img, M=M)
    # static path is fooled by the maze (high-contrast line now inside the band)
    assert static is not None
    assert static["f0_cy_per_px"] == pytest.approx(maze_freq_cy_per_px(M), abs=0.01)
    # M-aware path excludes the maze and recovers the pad
    assert aware is not None
    assert aware["pitch_px"] == pytest.approx(pad_px, rel=0.08)
    assert abs(aware["f0_cy_per_px"] - maze_freq_cy_per_px(M)) > 0.02


def test_M_aware_degenerate_band_returns_none():
    # If a band collapses (lo>=hi) the function must bail rather than raise.
    img = _grating(256, pitch=8.0, contrast=0.5)
    assert discover_fundamental(img, band=(0.30, 0.10)) is None


# --- 2-D-lattice-aware per-axis discovery (relock fix) ------------------------

def _lattice(n, pu, pv, Cu=0.4, Cv=0.4, mean=128.0, noise=1.0, seed=3):
    """n×n anisotropic 2-D dot lattice: a u-axis grating (pitch ``pu``, vary across
    columns) modulated by a v-axis grating (pitch ``pv``, vary across rows)."""
    rng = np.random.default_rng(seed)
    x = np.arange(n)
    cu = 1.0 + Cu * np.cos(2 * np.pi * x / pu)        # along columns -> u axis
    cv = 1.0 + Cv * np.cos(2 * np.pi * x / pv)        # along rows    -> v axis
    img = mean * np.outer(cv, cu)
    if noise:
        img = img + rng.normal(0, noise, img.shape)
    return img.astype(np.float64)


def test_2d_reports_both_axes_anisotropic():
    # The 5C/5D-style anisotropic case: a ~21 px u-grid AND a dominant ~30 px v-grid.
    # The single-value auto pick collapses to ONE axis; the 2-D entry point must report
    # BOTH, with the true per-axis pitches ~21 (u) and ~30 (v), and flag anisotropy.
    img = _lattice(384, pu=21.0, pv=30.0, Cu=0.3, Cv=0.6)
    d = discover_fundamental_2d(img, band=(0.06, 0.30))
    assert d is not None
    assert d["u"] is not None and d["v"] is not None
    assert d["u"]["axis"] == "u" and d["v"]["axis"] == "v"
    # Both true per-axis grid pitches recovered (in-band: both ~21/~30 sit above 0.06).
    assert d["u"]["true_pitch_px"] == pytest.approx(21.0, rel=0.1)
    assert d["v"]["true_pitch_px"] == pytest.approx(30.0, rel=0.1)
    assert d["anisotropic"] is True
    # The single-value auto pick returns exactly ONE of these axes (and may miss the
    # dominant one) — that is the lossy behaviour the 2-D path fixes.
    single = discover_fundamental(img, axis="auto", band=(0.06, 0.30))
    assert single is not None
    assert single["axis"] in ("u", "v")


def test_2d_isotropic_not_flagged():
    img = _lattice(384, pu=12.0, pv=12.0, Cu=0.5, Cv=0.5)
    d = discover_fundamental_2d(img, band=(0.06, 0.30))
    assert d is not None
    assert d["anisotropic"] is False
    assert d["u"]["true_pitch_px"] == pytest.approx(12.0, rel=0.12)
    assert d["v"]["true_pitch_px"] == pytest.approx(12.0, rel=0.12)


def test_2d_coarse_grid_below_floor_is_flagged_not_substituted():
    # A coarse pad super-pitch (~120 px -> f≈0.0083 cy/px) below the 0.06 floor, with a
    # finer in-band harmonic at ~15 px on the SAME axis. The in-band pick must stay the
    # resolvable ~15 px feature (MTF-bearing) — NOT silently replaced by the coarse line —
    # while true_below_floor flags that the dominant real structure is below the floor.
    n = 512
    x = np.arange(n)
    line = 128.0 * (1.0 + 0.7 * np.cos(2 * np.pi * x / 120.0)
                    + 0.3 * np.cos(2 * np.pi * x / 15.0))
    img = np.tile(line[None, :], (n, 1))
    img = img + np.random.default_rng(5).normal(0, 1.0, img.shape)
    d = discover_fundamental_2d(img, band=(0.06, 0.30))
    assert d is not None and d["u"] is not None
    u = d["u"]
    # in-band pick is the resolvable fine harmonic, not the coarse super-pitch
    assert u["pitch_px"] == pytest.approx(15.0, rel=0.1)
    assert u["f0_cy_per_px"] >= 0.06
    # the true dominant line is the coarse ~120 px grid, flagged below the usable floor
    assert u["true_pitch_px"] == pytest.approx(120.0, rel=0.15)
    assert u["true_below_floor"] is True


def test_2d_dominant_axis_matches_single_auto_amp():
    # dominant_axis (higher in-band amplitude) must equal the single-value auto pick's axis
    # so existing auto-pick callers reading dominant_axis observe no change.
    for pu, pv, Cu, Cv in [(21.0, 30.0, 0.6, 0.2), (18.0, 26.0, 0.2, 0.6)]:
        img = _lattice(384, pu=pu, pv=pv, Cu=Cu, Cv=Cv)
        d2 = discover_fundamental_2d(img, band=(0.06, 0.30))
        single = discover_fundamental(img, axis="auto", band=(0.06, 0.30))
        assert d2 is not None and single is not None
        assert d2["dominant_axis"] == single["axis"]


def test_2d_M_none_in_band_equals_single_axis():
    # Per-axis in-band pick (M=None) must equal the single-axis discover_fundamental pick
    # on that axis exactly — the 2-D path reuses the identical in-band peak finder.
    img = _lattice(384, pu=21.0, pv=30.0)
    d2 = discover_fundamental_2d(img, band=(0.06, 0.30), exclude=(0.31, 0.36))
    for ax in ("u", "v"):
        single = discover_fundamental(img, axis=ax, band=(0.06, 0.30),
                                      exclude=(0.31, 0.36))
        rec = d2[ax]
        assert (single is None) == (rec is None)
        if single is not None:
            assert rec["pitch_px"] == pytest.approx(single["pitch_px"], abs=1e-9)
            assert rec["f0_cy_per_px"] == pytest.approx(single["f0_cy_per_px"], abs=1e-9)
            assert rec["amp"] == pytest.approx(single["amp"], abs=1e-9)


def test_2d_M_aware_band_threads_through():
    # When M is given, the 2-D path uses the M-aware band/exclude defaults (A5) — the
    # resolved band/exclude must equal resolvable_band_cy_per_px(M) / maze_band_cy_per_px(M).
    img = _lattice(384, pu=21.0, pv=30.0)
    d = discover_fundamental_2d(img, M=2.0)
    assert d is not None
    assert d["band"] == pytest.approx(resolvable_band_cy_per_px(2.0))
    mb = maze_band_cy_per_px(2.0)
    assert d["exclude"] == pytest.approx((mb[1], mb[2]))


def test_2d_none_on_flat_and_bad_input():
    assert discover_fundamental_2d(np.full((128, 128), 50.0))["u"] is None
    assert discover_fundamental_2d(np.zeros((0, 0))) is None
    assert discover_fundamental_2d(np.zeros(10)) is None


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
